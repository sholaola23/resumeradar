"""Public wording stays honest and consistent, and stale features stay gone.

Each check here comes from the November 2026 UX audit (section A): promise
wording, unverifiable testimonials, contradicting privacy lines, the forced
newsletter pop-up, developer error text and keyboard access.
"""
import os
import re
import sys
import json
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

with patch.dict(os.environ, {}, clear=True), patch('dotenv.load_dotenv'):
    from app import app  # noqa: E402

from backend.site_copy import STRAPLINE, PRIVACY_LINE  # noqa: E402
from backend.report_generator import generate_pdf_report  # noqa: E402

PAGES = ['/', '/ats-resume-checker/', '/ats-resume-checker/cloud-engineer', '/privacy']

BANNED = [
    'beat the scan', 'land the interview', 'beat the ats', 'verified user',
    'within hours', 'never sold or shared', 'dream job', 'how you rank',
    'up the ranking', 'get ranked', 'ats looks for', 'getting past ats',
    'filtered out by ats', '90% of large companies', 'your ats score',
    'ats match score', 'unlock your full report', 'newsletterpopup',
]


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as handle:
        return handle.read()


class SiteCopyTest(unittest.TestCase):
    def setUp(self):
        env = {k: v for k, v in os.environ.items() if k != 'CV_BUILDER_ENABLED'}
        patcher = patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = app.test_client()

    def page(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, path)
        return response.get_data(as_text=True)

    def test_pages_carry_no_stale_promises(self):
        for path in PAGES:
            body = self.page(path).lower()
            for phrase in BANNED:
                self.assertFalse(phrase in body, f'{phrase!r} on {path}')

    def test_static_text_carries_no_stale_promises(self):
        for parts in [('static', 'llms.txt'), ('static', 'js', 'app.js'),
                      ('backend', 'report_generator.py'), ('templates', '404.html')]:
            text = read(*parts).lower()
            for phrase in BANNED + ['make sure the app is running', 'resumeradar team',
                                    'bullet enhancer', 'summary generator']:
                self.assertFalse(phrase in text, f'{phrase!r} in {"/".join(parts)}')

    def test_one_privacy_statement_everywhere(self):
        import html
        for path in ['/', '/ats-resume-checker/', '/ats-resume-checker/cloud-engineer', '/privacy']:
            self.assertIn(PRIVACY_LINE, html.unescape(self.page(path)), path)
        self.assertIn(PRIVACY_LINE, read('static', 'llms.txt'))
        # The email body interpolates the shared constant, not a second copy.
        self.assertIn('{PRIVACY_LINE}', read('app.py'))
        self.assertIn('{STRAPLINE}', read('app.py'))

    def test_privacy_line_matches_the_code(self):
        from backend import ai_cache
        self.assertEqual(ai_cache._CACHE_TTL, 3600)
        self.assertIn('one hour', PRIVACY_LINE)

    def test_strapline(self):
        home = self.page('/')
        self.assertEqual(STRAPLINE, 'Make your experience clear.')
        self.assertIn(f'content="ResumeRadar — {STRAPLINE}"', home)
        self.assertIn(STRAPLINE, read('static', 'js', 'app.js'))

    def test_visible_faq_matches_structured_data(self):
        import html
        home = self.page('/')
        blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', home, re.S)
        faq = next(json.loads(b) for b in blocks if '"FAQPage"' in b)
        visible = dict(re.findall(r'<summary>(.*?)</summary>\s*<p>(.*?)</p>', home, re.S))
        for item in faq['mainEntity']:
            question = item['name']
            self.assertIn(question, visible)
            shown = html.unescape(re.sub(r'<[^>]+>', '', visible[question]))
            self.assertTrue(shown.startswith(item['acceptedAnswer']['text']), question)

    def test_privacy_page_and_sitemap(self):
        body = self.page('/privacy')
        for word in ['Anthropic', 'Resend', 'Beehiiv', 'one hour']:
            self.assertIn(word, body)
        sitemap = self.client.get('/sitemap.xml').get_data(as_text=True)
        self.assertIn('https://resumeradar.sholastechnotes.com/privacy', sitemap)
        self.assertNotIn('2026-09-05', sitemap)

    def test_builder_links_get_their_own_message(self):
        for path in ['/build', '/build/', '/build?payment=cancelled']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404, path)
            self.assertIn('The CV builder has closed', response.get_data(as_text=True))
        other = self.client.get('/no-such-page')
        self.assertEqual(other.status_code, 404)
        self.assertNotIn('The CV builder has closed', other.get_data(as_text=True))
        self.assertIn('Page not found', other.get_data(as_text=True))

    def test_keyboard_access_markup(self):
        home = self.page('/')
        self.assertRegex(home, r'<button type="button" class="file-upload-area" id="dropZone"')
        self.assertNotIn('<div class="card-header-toggle"', home)
        toggles = re.findall(r'<button type="button" class="card-header-toggle"[^>]*>', home)
        self.assertEqual(len(toggles), 5)
        for tag in toggles:
            target = re.search(r'data-target="(\w+)"', tag).group(1)
            self.assertIn(f'aria-controls="{target}"', tag)
            self.assertRegex(tag, r'aria-expanded="(true|false)"')
            self.assertIn(f'id="{target}"', home)
        self.assertIn('role="dialog" aria-modal="true" aria-labelledby="emailModalTitle"', home)

    def test_scan_counter_uses_one_wording_function(self):
        script = read('static', 'js', 'app.js')
        self.assertEqual(script.count("fetch('/api/scan-count')"), 1)
        self.assertNotIn("toLocaleString() + '+'", script)

    def test_pdf_report_builds_with_shared_wording(self):
        pdf = bytes(generate_pdf_report({
            'match_score': 64, 'total_matched': 9, 'total_missing': 5, 'total_job_keywords': 14,
            'category_scores': {}, 'matched_keywords': {}, 'missing_keywords': {},
            'ats_formatting': {}, 'ai_suggestions': {},
        }))
        self.assertTrue(pdf.startswith(b'%PDF'))


if __name__ == '__main__':
    unittest.main()
