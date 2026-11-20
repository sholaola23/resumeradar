"""Rate limits key on the real visitor, and CF-Connecting-IP is only trusted
when the request really came from Cloudflare.

The end-to-end tests go through the full WSGI stack, simulating Render's
proxy the way it behaves: it connects from a private address and appends the
peer it saw to X-Forwarded-For, which ProxyFix(x_for=1) turns into
remote_addr. The unit tests set remote_addr directly to that peer.
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import with an empty environment and no .env, so the limiter uses in-memory
# storage and no real credentials load into the test process.
with patch.dict(os.environ, {}, clear=True), patch('dotenv.load_dotenv'):
    import app as app_module  # noqa: E402

app = app_module.app
limiter = app_module.limiter

RENDER_PROXY = '10.201.0.7'
CF_EDGE_V4 = '172.69.224.38'       # seen in Render logs, inside 172.64.0.0/13
CF_EDGE_V4_OTHER = '162.158.216.204'  # inside 162.158.0.0/15
CF_EDGE_V6 = '2a06:98c3:3600::103'  # inside 2a06:98c0::/29
NOT_CF = '203.0.113.9'             # TEST-NET-3, not Cloudflare

LIMITED_ROUTE = '/api/download-report'  # 20 per hour, returns 400 on {}
LIMIT = 20


def _env(peer):
    """What the app receives when `peer` connects to Render's proxy."""
    return {'REMOTE_ADDR': RENDER_PROXY, 'HTTP_X_FORWARDED_FOR': peer}


class ClientIpTest(unittest.TestCase):
    def _client_ip(self, peer, cf_header=None):
        """Key for a request whose remote_addr (after ProxyFix) is `peer`."""
        headers = {'CF-Connecting-IP': cf_header} if cf_header is not None else {}
        environ = {'REMOTE_ADDR': peer} if peer is not None else {}
        with app.test_request_context('/', headers=headers, environ_base=environ):
            return {'ip': app_module._client_ip(), 'limiter_key': limiter._key_func()}

    def test_real_cloudflare_peer_uses_header(self):
        got = self._client_ip(CF_EDGE_V4, cf_header='198.51.100.23')
        self.assertEqual(got['ip'], '198.51.100.23')

    def test_ipv6_cloudflare_peer_uses_header(self):
        got = self._client_ip(CF_EDGE_V6, cf_header='2001:db8::1')
        self.assertEqual(got['ip'], '2001:db8::/64')

    def test_spoofed_header_from_non_cloudflare_peer_is_ignored(self):
        got = self._client_ip(NOT_CF, cf_header='198.51.100.23')
        self.assertEqual(got['ip'], NOT_CF)

    def test_garbage_header_from_cloudflare_falls_back_to_peer(self):
        got = self._client_ip(CF_EDGE_V4, cf_header='not-an-ip')
        self.assertEqual(got['ip'], CF_EDGE_V4)

    def test_header_is_normalised(self):
        got = self._client_ip(CF_EDGE_V4, cf_header='2001:DB8:0:0::1, 1.2.3.4')
        self.assertEqual(got['ip'], '2001:db8::/64')

    def test_ipv6_keyed_by_slash_64(self):
        a = self._client_ip(CF_EDGE_V4, cf_header='2001:db8:1:2::1')['ip']
        b = self._client_ip(CF_EDGE_V4, cf_header='2001:db8:1:2:ffff:ffff:ffff:fffe')['ip']
        c = self._client_ip(CF_EDGE_V4, cf_header='2001:db8:1:3::1')['ip']
        self.assertEqual(a, '2001:db8:1:2::/64')
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_ipv4_mapped_header_is_keyed_as_ipv4(self):
        got = self._client_ip(CF_EDGE_V4, cf_header='::ffff:198.51.100.23')
        self.assertEqual(got['ip'], '198.51.100.23')

    def test_ipv6_peer_without_cloudflare_keyed_by_slash_64(self):
        got = self._client_ip('2001:db8:9:9::5', cf_header='198.51.100.23')
        self.assertEqual(got['ip'], '2001:db8:9:9::/64')

    def test_no_header_uses_peer(self):
        got = self._client_ip(NOT_CF)
        self.assertEqual(got['ip'], NOT_CF)

    def test_limiter_key_is_client_ip(self):
        self.assertIs(limiter._key_func, app_module._client_ip)
        got = self._client_ip(CF_EDGE_V4, cf_header='198.51.100.23')
        self.assertEqual(got['limiter_key'], '198.51.100.23')

    def test_cloudflare_ranges(self):
        for addr in (CF_EDGE_V4, CF_EDGE_V4_OTHER, '172.68.229.194', CF_EDGE_V6,
                     '::ffff:172.69.224.38'):
            with self.subTest(addr=addr):
                self.assertTrue(app_module._is_cloudflare_ip(addr))
        for addr in (NOT_CF, RENDER_PROXY, '127.0.0.1', '2001:db8::1', '', None, 'x'):
            with self.subTest(addr=addr):
                self.assertFalse(app_module._is_cloudflare_ip(addr))


class LimiterEndToEndTest(unittest.TestCase):
    """Real requests through ProxyFix and flask-limiter."""

    def setUp(self):
        limiter.reset()
        self.addCleanup(limiter.reset)
        self.client = app.test_client()

    def _post(self, peer, cf_header=None):
        headers = {'CF-Connecting-IP': cf_header} if cf_header else {}
        return self.client.post(LIMITED_ROUTE, json={}, headers=headers,
                                environ_base=_env(peer))

    def test_one_visitor_across_edges_is_counted_together(self):
        edges = [CF_EDGE_V4, CF_EDGE_V4_OTHER]
        for i in range(LIMIT):
            r = self._post(edges[i % 2], cf_header='198.51.100.23')
            self.assertNotEqual(r.status_code, 429, f'request {i + 1} limited early')
        self.assertEqual(self._post(CF_EDGE_V4, cf_header='198.51.100.23').status_code, 429)

    def test_visitors_sharing_an_edge_have_separate_limits(self):
        for _ in range(LIMIT):
            self._post(CF_EDGE_V4, cf_header='198.51.100.23')
        self.assertEqual(self._post(CF_EDGE_V4, cf_header='198.51.100.23').status_code, 429)
        self.assertNotEqual(self._post(CF_EDGE_V4, cf_header='198.51.100.99').status_code, 429)

    def test_client_supplied_forwarded_for_cannot_fake_a_cloudflare_peer(self):
        # Caller sends "X-Forwarded-For: <cf edge>" straight to the origin;
        # Render appends the real peer and only that last hop is trusted.
        for i in range(LIMIT):
            self.client.post(LIMITED_ROUTE, json={},
                             headers={'CF-Connecting-IP': f'198.51.100.{i + 1}'},
                             environ_base=_env(f'{CF_EDGE_V4}, {NOT_CF}'))
        r = self.client.post(LIMITED_ROUTE, json={},
                             headers={'CF-Connecting-IP': '198.51.100.250'},
                             environ_base=_env(f'{CF_EDGE_V4}, {NOT_CF}'))
        self.assertEqual(r.status_code, 429)

    def test_ipv6_visitor_rotating_inside_their_64_is_counted_together(self):
        for i in range(LIMIT):
            r = self._post(CF_EDGE_V4, cf_header=f'2001:db8:1:2::{i + 1:x}')
            self.assertNotEqual(r.status_code, 429, f'request {i + 1} limited early')
        self.assertEqual(self._post(CF_EDGE_V4, cf_header='2001:db8:1:2::ffff').status_code, 429)
        # A different /64 is a different visitor.
        self.assertNotEqual(self._post(CF_EDGE_V4, cf_header='2001:db8:1:3::1').status_code, 429)

    def test_spoofed_header_from_origin_cannot_dodge_the_limit(self):
        for i in range(LIMIT):
            self._post(NOT_CF, cf_header=f'198.51.100.{i + 1}')
        self.assertEqual(self._post(NOT_CF, cf_header='198.51.100.250').status_code, 429)


if __name__ == '__main__':
    unittest.main()
