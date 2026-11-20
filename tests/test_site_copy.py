"""Public wording stays honest and consistent, and stale features stay gone.

Each check here comes from the November 2026 UX audit (section A): promise
wording, unverifiable testimonials, contradicting privacy lines, the forced
newsletter pop-up, developer error text and keyboard access.
"""
import ast
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


USER_TEXT_NAMES = {'resume_text', 'job_description', 'cv_text', 'response_text', 'clean_text',
                   'email', 'jd_text', 'bullet_text', 'job_context'}


def _leaky_log_lines(scope):
    """Lines where logging could carry user text, an exception message or a response body.

    - A print, logging, logger or app.logger call, or a write to sys.stderr or
      sys.stdout, may show a caught exception only as log_safe.describe(e) or
      type(e).__name__. That also applies to any name copied from it, such
      as msg = str(e).
    - Such a call may never show a response body (.text) or a variable that
      holds CV, job or email text, except as len(...).
    - traceback.* calls, .exception(...) calls and exc_info= are never
      allowed, because they write the exception message.
    """
    def chain(node):
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
        return list(reversed(parts))

    def is_log_call(call):
        names = chain(call.func)
        if names == ['print']:
            return True
        if len(names) >= 2 and names[0] in ('logging', 'logger', 'log', 'app', 'current_app'):
            return names[0] != 'app' or names[1] == 'logger'
        return names[:2] in (['sys', 'stderr'], ['sys', 'stdout']) and names[-1] == 'write'

    def always_leaky(call):
        names = chain(call.func)
        return (names[:1] == ['traceback'] or names[-1:] == ['exception']
                or any(k.arg == 'exc_info' for k in call.keywords))

    def safe_use(parent):
        f = parent.func if isinstance(parent, ast.Call) else None
        if chain(f) == ['log_safe', 'describe']:
            return True
        return isinstance(f, ast.Name) and f.id in ('type', 'len')

    def parent_map(node):
        return {child: n for n in ast.walk(node) for child in ast.iter_child_nodes(n)}

    lines = []
    calls = [n for n in ast.walk(scope) if isinstance(n, ast.Call)]
    for call in calls:
        if always_leaky(call):
            lines.append(call.lineno)
        elif is_log_call(call):
            parents = parent_map(call)
            for n in ast.walk(call):
                if isinstance(n, ast.Attribute) and n.attr == 'text':
                    lines.append(call.lineno)
                if isinstance(n, ast.Name) and n.id in USER_TEXT_NAMES and not safe_use(parents.get(n)):
                    lines.append(call.lineno)

    for handler in ast.walk(scope):
        if not isinstance(handler, ast.ExceptHandler) or not handler.name:
            continue
        body = [n for stmt in handler.body for n in ast.walk(stmt)]
        tainted = {handler.name}
        for stmt in body:
            if isinstance(stmt, ast.Assign):
                uses = [n for n in ast.walk(stmt.value) if isinstance(n, ast.Name) and n.id in tainted]
                if uses and not (isinstance(stmt.value, ast.Call) and safe_use(stmt.value)):
                    tainted |= {t.id for t in stmt.targets if isinstance(t, ast.Name)}
        for call in body:
            if not (isinstance(call, ast.Call) and is_log_call(call)):
                continue
            parents = parent_map(call)
            for n in ast.walk(call):
                if isinstance(n, ast.Name) and n.id in tainted and not safe_use(parents.get(n)):
                    lines.append(call.lineno)
    return sorted(set(lines))


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

    def test_role_guides_do_not_promise_a_ranking(self):
        from app import ROLE_PAGES
        for slug in ROLE_PAGES:
            body = self.page(f'/ats-resume-checker/{slug}').lower().replace('ranking model', '').replace('applicant ranking', '')
            self.assertNotRegex(body, r'\b(out|under)?rank', slug)

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
        # "Results are cached" must stay true for the scan itself, not only
        # for cover letters: the scan's AI call has to write to the cache.
        analyzer = read('backend', 'ai_analyzer.py')
        scan = analyzer[analyzer.index('def get_ai_suggestions'):analyzer.index('\ndef ', analyzer.index('def get_ai_suggestions') + 1)]
        self.assertIn('ai_cache.cache_set(', scan)
        self.assertIn('cached for up to one hour', self.page('/privacy'))
        # Every AI tool that writes to the cache is named on the privacy page.
        page = self.page('/privacy')
        for fn, words in [('def generate_cover_letter', 'cover letters'), ('def enhance_bullet_point', 'bullet rewrites'),
                          ('def generate_resume_summary', 'summaries')]:
            body = analyzer[analyzer.index(fn):analyzer.index('\ndef ', analyzer.index(fn) + 1)]
            self.assertIn('ai_cache.cache_set(', body, fn)
            self.assertIn(words, page, fn)
        self.assertEqual(analyzer.count('ai_cache.cache_set('), 4)

    def test_no_log_line_carries_cv_or_job_text(self):
        # "Not saved by ResumeRadar" covers the server logs too.
        risky = re.compile(r'\b(print|logger\.\w+|logging\.\w+)\(.*\b(response_text|resume_text|job_description|cv_text|clean_text)\b')
        offenders = []
        for folder in ('backend', ''):
            base = os.path.join(ROOT, folder)
            for name in sorted(os.listdir(base)):
                if not name.endswith('.py'):
                    continue
                with open(os.path.join(base, name), encoding='utf-8') as f:
                    for no, line in enumerate(f, 1):
                        code = line.split('#', 1)[0]
                        if risky.search(code) and 'len(' not in code:
                            offenders.append(f'{folder or "."}/{name}:{no}: {line.strip()}')
        self.assertEqual(offenders, [])

    def test_scan_path_logs_error_types_not_messages(self):
        # An exception message can quote the CV, job text or email address that
        # caused it, so the free handlers log log_safe.describe(e) instead.
        from backend import log_safe
        self.assertEqual(log_safe.describe(KeyError('Jane Doe, Acme Ltd')), 'KeyError')
        err = RuntimeError('quoted prompt text')
        err.status_code = 429
        self.assertEqual(log_safe.describe(err), 'RuntimeError (status 429)')

        free_routes = {'scan_resume', 'generate_cover_letter_endpoint', 'enhance_bullet_endpoint',
                       'generate_summary_endpoint', 'download_report', 'email_report',
                       'subscribe_newsletter',
                       # CV builder routes: behind the 404 today, but they hold CV text.
                       'build_generate', 'build_generate_from_scan', 'build_generate_from_upload',
                       'build_download', '_send_cv_email'}
        offenders = []
        for path in ('app.py', 'backend/ai_analyzer.py', 'backend/resume_parser.py', 'backend/cv_builder.py'):
            tree = ast.parse(read(*path.split('/')))
            if path == 'app.py':
                scopes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in free_routes]
                self.assertEqual({n.name for n in scopes}, free_routes)
            else:
                scopes = [tree]
            for scope in scopes:
                offenders += [f'{path}:{line}' for line in _leaky_log_lines(scope)]
        self.assertEqual(offenders, [])

    def test_privacy_page_lists_what_the_browser_keeps(self):
        page = self.page('/privacy')
        self.assertIn('a short code made from the job description', page)
        js = read('static', 'js', 'app.js')
        entry = js[js.index('const entry = {'):js.index('};', js.index('const entry = {'))]
        fields = set(re.findall(r'^\s*(\w+):', entry, re.M))
        # Every field a history entry stores is named on the privacy page.
        self.assertEqual(fields, {'id', 'jobKey', 'scoreVersion', 'date', 'score', 'matched', 'missing', 'total', 'jdSnippet'})

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
        visible = dict(re.findall(r'<summary>([^<]*)</summary>\s*<p>(.*?)</p>', home, re.S))
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
        self.assertEqual(len(toggles), 5)  # save, AI, categories, matched, ATS
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
