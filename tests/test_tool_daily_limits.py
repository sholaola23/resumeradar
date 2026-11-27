"""The free AI tools' daily caps count each real visitor.

They used to be keyed on request.remote_addr, which behind Cloudflare is a
rotating edge IP, so they never fired. These tests send real requests through
ProxyFix and the route handlers, the way Render's proxy delivers them, with a
small in-memory stand-in for Redis and the Claude calls patched out.
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

with patch.dict(os.environ, {}, clear=True), patch('dotenv.load_dotenv'):
    import app as app_module  # noqa: E402

from backend import ai_ratelimit  # noqa: E402

app = app_module.app

RENDER_PROXY = '10.201.0.7'
CF_EDGES = ['172.69.224.38', '162.158.216.204', '172.68.229.194']
NOT_CF = '203.0.113.9'

RESUME = 'Experienced data analyst with Python, SQL and dashboard skills. ' * 3
JD = 'We need a data analyst who knows Python, SQL, Tableau and reporting well.'

TOOLS = {
    'cover_letter': ('/api/generate/cover-letter', 'generate_cover_letter',
                     {'resume_text': RESUME, 'job_description': JD}),
    'enhance_bullet': ('/api/tools/enhance-bullet', 'enhance_bullet_point',
                       {'bullet_text': 'Built weekly sales dashboards in Tableau'}),
    'generate_summary': ('/api/tools/generate-summary', 'generate_resume_summary',
                         {'resume_text': RESUME, 'job_description': JD}),
}


class _FakeRedis:
    """Just the calls ai_ratelimit makes: get, and a pipeline of incr + expire."""

    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def decr(self, key):
        self.store[key] = self.store.get(key, 0) - 1
        return self.store[key]

    def pipeline(self, transaction=True):
        return _FakePipe(self)


class _FakePipe:
    def __init__(self, r):
        self.r, self.ops = r, []

    def incr(self, key):
        self.ops.append(('incr', key))

    def expire(self, key, ttl):
        self.ops.append(('expire', key))

    def execute(self):
        out = []
        for op, key in self.ops:
            if op == 'incr':
                self.r.store[key] = self.r.store.get(key, 0) + 1
                out.append(self.r.store[key])
            else:
                out.append(True)
        return out


def _env(peer):
    return {'REMOTE_ADDR': RENDER_PROXY, 'HTTP_X_FORWARDED_FOR': peer}


class ToolDailyLimitTest(unittest.TestCase):
    def setUp(self):
        self.redis = _FakeRedis()
        ai_ratelimit.init(self.redis)
        self.addCleanup(ai_ratelimit.init, None)
        # Switch off the per-minute burst limits so only the daily cap decides.
        app_module.limiter.enabled = False
        self.addCleanup(setattr, app_module.limiter, 'enabled', True)
        for _, fn, _ in TOOLS.values():
            p = patch.object(app_module, fn, return_value={'ok': True})
            p.start()
            self.addCleanup(p.stop)
        self.client = app.test_client()

    def _post(self, tool, peer, cf_header=None):
        route, _, body = TOOLS[tool]
        headers = {'CF-Connecting-IP': cf_header} if cf_header else {}
        return self.client.post(route, json=body, headers=headers, environ_base=_env(peer))

    def test_limits_are_the_agreed_numbers(self):
        self.assertEqual(ai_ratelimit.DAILY_LIMITS['cover_letter'], 5)
        self.assertEqual(ai_ratelimit.DAILY_LIMITS['generate_summary'], 5)
        self.assertEqual(ai_ratelimit.DAILY_LIMITS['enhance_bullet'], 10)

    def test_one_visitor_across_rotating_edges_hits_the_cap(self):
        for tool in TOOLS:
            limit = ai_ratelimit.DAILY_LIMITS[tool]
            for i in range(limit):
                r = self._post(tool, CF_EDGES[i % 3], cf_header='198.51.100.23')
                self.assertEqual(r.status_code, 200, f'{tool} request {i + 1} refused early')
            r = self._post(tool, CF_EDGES[0], cf_header='198.51.100.23')
            self.assertEqual(r.status_code, 429, tool)
            self.assertEqual(r.get_json()['error'],
                             f'Daily limit reached ({limit} per day). Try again tomorrow.')

    def test_visitors_sharing_an_edge_have_their_own_caps(self):
        for _ in range(5):
            self._post('cover_letter', CF_EDGES[0], cf_header='198.51.100.23')
        self.assertEqual(self._post('cover_letter', CF_EDGES[0], cf_header='198.51.100.23').status_code, 429)
        self.assertEqual(self._post('cover_letter', CF_EDGES[0], cf_header='198.51.100.99').status_code, 200)

    def test_tools_are_counted_separately(self):
        for _ in range(5):
            self._post('cover_letter', CF_EDGES[0], cf_header='198.51.100.23')
        self.assertEqual(self._post('generate_summary', CF_EDGES[0], cf_header='198.51.100.23').status_code, 200)

    def test_spoofed_header_sent_straight_to_the_origin_cannot_dodge_the_cap(self):
        for i in range(5):
            self._post('cover_letter', NOT_CF, cf_header=f'198.51.100.{i + 1}')
        self.assertEqual(self._post('cover_letter', NOT_CF, cf_header='198.51.100.250').status_code, 429)

    def test_key_holds_the_visitor_not_the_edge(self):
        self._post('enhance_bullet', CF_EDGES[0], cf_header='198.51.100.23')
        keys = list(self.redis.store)
        self.assertEqual(len(keys), 1)
        self.assertIn(':enhance_bullet:198.51.100.23:', keys[0])
        self.assertNotIn(CF_EDGES[0], keys[0])

    def test_a_failed_call_does_not_use_up_the_allowance(self):
        from backend import ai_budget
        with patch.object(app_module, 'generate_cover_letter',
                          return_value={'error': ai_budget.BUDGET_EXCEEDED_MESSAGE}):
            for _ in range(8):
                r = self._post('cover_letter', CF_EDGES[0], cf_header='198.51.100.23')
                self.assertEqual(r.status_code, 503)
        # The budget is back: all 5 of the day's letters are still there.
        for i in range(5):
            r = self._post('cover_letter', CF_EDGES[i % 3], cf_header='198.51.100.23')
            self.assertEqual(r.status_code, 200, f'request {i + 1} refused')
        self.assertEqual(self._post('cover_letter', CF_EDGES[0], cf_header='198.51.100.23').status_code, 429)

    def test_failed_bullet_and_summary_calls_are_given_back(self):
        for tool, fn in [('enhance_bullet', 'enhance_bullet_point'),
                         ('generate_summary', 'generate_resume_summary')]:
            with patch.object(app_module, fn, return_value={'error': 'AI error'}):
                self.assertEqual(self._post(tool, CF_EDGES[0], cf_header='198.51.100.23').status_code, 500)
        self.assertEqual(sum(int(v) for v in self.redis.store.values()), 0)

    def test_no_redis_lets_calls_through(self):
        ai_ratelimit.init(None)
        for _ in range(7):
            self.assertEqual(self._post('cover_letter', CF_EDGES[0], cf_header='198.51.100.23').status_code, 200)


if __name__ == '__main__':
    unittest.main()
