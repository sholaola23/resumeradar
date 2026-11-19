"""The paid CV builder is off by default: its pages and APIs return 404."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import with an empty environment and no .env, so a local .env can't switch
# the builder on or load real credentials into the test process.
with patch.dict(os.environ, {}, clear=True), patch('dotenv.load_dotenv'):
    from app import app  # noqa: E402

BLOCKED = [
    ('GET', '/build'),
    ('GET', '/build?payment=cancelled'),
    ('POST', '/api/build/generate'),
    ('POST', '/api/build/generate-from-upload'),
    ('POST', '/api/build/create-checkout'),
    ('POST', '/api/build/create-bundle-checkout'),
    ('POST', '/api/build/webhook'),
    ('POST', '/api/build/webhook/paystack'),
    ('POST', '/api/build/free-download-nigeria'),
    ('GET', '/api/build/download/abc'),
    ('GET', '/api/build/check-payment/abc'),
    ('GET', '/static/js/builder.js'),
    ('GET', '/static/css/builder.css'),
    ('GET', '/static/js//builder.js'),
    ('GET', '/static/./js/builder.js'),
    ('GET', '/static/js/../js/builder.js'),
    ('GET', '/static/js/builder.js/'),
    ('GET', '/static/css/builder.css/.'),
    ('GET', '/static/js/builder.js%2F'),
]


class BuilderDisabledTest(unittest.TestCase):
    def setUp(self):
        # The switch is read on every request, so keep it unset for each test.
        env = {k: v for k, v in os.environ.items() if k != 'CV_BUILDER_ENABLED'}
        patcher = patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = app.test_client()

    def test_builder_routes_return_404(self):
        for method, path in BLOCKED:
            with self.subTest(path=path):
                r = self.client.open(path, method=method, json={})
                self.assertEqual(r.status_code, 404)

    def test_free_scan_pages_still_load(self):
        for path in ('/', '/ats-resume-checker/', '/api/health', '/sitemap.xml', '/llms.txt'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_no_paid_builder_links(self):
        home = self.client.get('/').data.decode()
        self.assertNotIn('href="/build"', home)
        self.assertNotIn('£2', home)
        self.assertNotIn('/build<', self.client.get('/sitemap.xml').data.decode())
        llms = self.client.get('/llms.txt').data.decode()
        self.assertNotIn('£', llms)

    def test_resend_webhook_not_blocked(self):
        r = self.client.post('/api/build/webhook/resend', data=b'{}')
        self.assertNotEqual(r.status_code, 404)


if __name__ == '__main__':
    unittest.main()
