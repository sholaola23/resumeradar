"""Regressions for the UX quick wins (B1 to B12). Offline: no keys, no network."""
import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

with patch.dict(os.environ, {}, clear=True), patch('dotenv.load_dotenv'):
    import app as product
from backend import ai_analyzer, keyword_engine as engine
from backend.report_generator import generate_pdf_report

ROOT = Path(__file__).resolve().parents[1]


def demo():
    script = (ROOT / 'static/js/app.js').read_text()
    resume = re.search(r'const DEMO_RESUME\s*=\s*`(.*?)`', script, re.S).group(1)
    jd = re.search(r'const DEMO_JOB\s*=\s*`(.*?)`', script, re.S).group(1)
    return resume, jd


def match(resume, jd):
    return engine.calculate_match(engine.extract_keywords_from_text(resume),
                                  engine.extract_keywords_from_text(jd, strict=True))


class KeywordDisplayTests(unittest.TestCase):
    def test_tool_names_keep_their_usual_capitals(self):
        for term, shown in [('cdn', 'CDN'), ('cloudfront', 'CloudFront'), ('route 53', 'Route 53'),
                            ('soc 2', 'SOC 2'), ('go', 'Go'), ('dns', 'DNS'), ('mentoring', 'mentoring')]:
            with self.subTest(term=term):
                self.assertEqual(engine.display_keyword(term), shown)

    def test_every_display_name_is_a_recognised_term(self):
        vocab = engine.TECHNICAL_SKILLS | engine.SOFT_SKILLS | engine.CERTIFICATIONS | engine.EDUCATION_KEYWORDS
        self.assertFalse(set(engine.KEYWORD_DISPLAY) - vocab)

    def test_display_never_changes_letters_only_case_and_spacing(self):
        for term, shown in engine.KEYWORD_DISPLAY.items():
            with self.subTest(term=term):
                self.assertEqual(re.sub(r'[\W_]', '', term).replace('js', ''),
                                 re.sub(r'[\W_]', '', shown.lower()).replace('js', ''))

    def test_scan_response_carries_display_names(self):
        resume, jd = demo()
        with patch.object(product, 'get_ai_suggestions', return_value={'ai_powered': False}):
            data = product.app.test_client().post('/api/scan', data={'resume_text': resume, 'job_description': jd}).get_json()
        self.assertEqual(data['keyword_display']['typescript'], 'TypeScript')
        self.assertIn('typescript', data['missing_keywords']['technical_skills'])  # matching stays lower-case


class PriorityTests(unittest.TestCase):
    def test_demo_top_three_are_not_alphabetical(self):
        resume, jd = demo()
        top = [item['keyword'] for item in engine.analyze_requirements(resume, jd, match(resume, jd))[:3]]
        self.assertNotEqual(top, sorted(top))
        self.assertEqual(top[0], 'typescript')  # named twice and a definite ask

    def test_listed_examples_are_one_of_and_rank_below_definite_asks(self):
        jd = 'Requirements\nExperience with monitoring tools (Datadog, Prometheus, Grafana).\nMust know Kubernetes and Docker.'
        items = engine.analyze_requirements('Python', jd, match('Python', jd))
        by = {item['keyword']: item for item in items}
        self.assertEqual(by['datadog']['one_of'], ['Grafana', 'Prometheus'])
        self.assertIn('one option', by['datadog']['suggestion'])
        self.assertEqual(by['kubernetes']['one_of'], [])
        order = [item['keyword'] for item in items]
        self.assertLess(order.index('kubernetes'), order.index('datadog'))

    def test_plain_heading_list_is_a_full_list_not_a_choice(self):
        jd = 'Required technologies: AWS, Docker, Kubernetes.'
        keys = {item['keyword'] for item in engine.analyze_requirements('AWS', jd, match('AWS', jd))}
        self.assertTrue({'docker', 'kubernetes'} <= keys)

    def test_term_in_two_option_lists_names_both(self):
        jd = 'Required: CI tools such as Jenkins or CircleCI, and deploy tools like Jenkins or Spinnaker.'
        by = {item['keyword']: item for item in engine.analyze_requirements('Python', jd, match('Python', jd))}
        self.assertEqual(set(by['jenkins']['one_of']), {'CircleCI', 'Spinnaker'})

    def test_or_list_is_one_of_when_none_is_held(self):
        jd = 'Required: CI/CD tools (Jenkins, GitHub Actions or CircleCI). Python required.'
        by = {item['keyword']: item for item in engine.analyze_requirements('Docker', jd, match('Docker', jd))}
        self.assertEqual(set(by['jenkins']['one_of']), {'GitHub Actions', 'CircleCI'})

    def test_held_alternative_still_removes_the_others(self):
        jd = 'Required: CI/CD tools (Jenkins, GitHub Actions or CircleCI). Python required.'
        keys = {item['keyword'] for item in engine.analyze_requirements('GitHub Actions', jd, match('GitHub Actions', jd))}
        self.assertFalse({'jenkins', 'circleci'} & keys)

    def test_suggestions_use_display_names(self):
        jd = 'Required: CDN, DNS and CloudFront experience.'
        items = engine.analyze_requirements('Python', jd, match('Python', jd))
        self.assertTrue(any('If you have used CloudFront' in item['suggestion'] for item in items))


class CategoryAndReportTests(unittest.TestCase):
    def scan_data(self):
        resume, jd = demo()
        result = match(resume, jd)
        return dict(match_score=result['overall_score'], category_scores=result['category_scores'],
                    missing_keywords=result['missing_keywords'], matched_keywords=result['matched_keywords'],
                    total_matched=1, total_missing=1, total_job_keywords=2, ai_suggestions={}, ats_formatting={})

    def test_pdf_hides_one_term_categories_and_links_back(self):
        from pypdf import PdfReader
        import io
        text = ''.join(p.extract_text() for p in PdfReader(io.BytesIO(bytes(generate_pdf_report(self.scan_data())))).pages)
        self.assertNotIn('(1/1)', text)
        self.assertIn('Technical Skills', text)
        self.assertIn('resumeradar.sholastechnotes.com', text)
        self.assertIn('TypeScript', text)

    def test_page_and_text_report_share_the_three_term_rule(self):
        script = (ROOT / 'static/js/app.js').read_text()
        self.assertIn('const MIN_TERMS_FOR_CATEGORY_SCORE = 3;', script)
        from backend import report_generator
        self.assertEqual(report_generator.MIN_TERMS_FOR_CATEGORY_SCORE, 3)


class ScanCacheTests(unittest.TestCase):
    def test_identical_scan_reuses_cached_suggestions_without_an_ai_call(self):
        cached = {'summary': 'cached', 'ai_powered': True}
        with patch.object(ai_analyzer.ai_cache, 'cache_get', return_value=cached) as get, \
             patch.object(ai_analyzer, 'make_client') as client, \
             patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key'}):
            self.assertEqual(ai_analyzer.get_ai_suggestions('cv', 'job', {}), cached)
        client.assert_not_called()
        self.assertEqual(get.call_args[0][0], ai_analyzer.SCAN_CACHE_TOOL)

    def test_capitalisation_edit_is_a_different_cache_entry(self):
        self.assertNotEqual(ai_analyzer._scan_cache_inputs('Used cdn', 'job'),
                            ai_analyzer._scan_cache_inputs('Used CDN', 'job'))

    def test_cut_off_answer_is_not_cached(self):
        class Msg:
            content = [type('B', (), {'type': 'text', 'text': '{"summary": "half", "strengths": ["a"'})()]
            usage = None
        client = type('C', (), {})()
        client.messages = type('M', (), {'create': staticmethod(lambda **kw: Msg())})()
        with patch.object(ai_analyzer.ai_cache, 'cache_get', return_value=None), \
             patch.object(ai_analyzer.ai_cache, 'cache_set') as put, \
             patch.object(ai_analyzer, 'make_client', return_value=client), \
             patch.object(ai_analyzer.ai_budget, 'check_budget', return_value=True), \
             patch.object(ai_analyzer.ai_budget, 'spent_fraction', return_value=0), \
             patch.object(ai_analyzer.ai_budget, 'record_usage'), \
             patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key'}):
            ai_analyzer.get_ai_suggestions('cv', 'job', {'missing_keywords': {}})
        put.assert_not_called()

    def test_fallback_is_not_cached(self):
        with patch.object(ai_analyzer.ai_cache, 'cache_get', return_value=None), \
             patch.object(ai_analyzer.ai_cache, 'cache_set') as put, \
             patch.dict(os.environ, {}, clear=True):
            ai_analyzer.get_ai_suggestions('cv', 'job', {'missing_keywords': {}})
        put.assert_not_called()


class PageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = product.app.test_client().get('/').data.decode()

    def test_scan_button_and_panels_say_cv(self):
        self.assertIn('Scan my CV', self.html)
        self.assertNotIn('Scan My Resume', self.html)
        # "resume" stays in the page title and structured data for search (B1); not in the form.
        self.assertIn('<h2>📄 Your CV</h2>', self.html)
        self.assertNotIn('<h2>📄 Your Resume</h2>', self.html)

    def test_header_and_footer_have_a_job(self):
        self.assertIn('href="/" aria-label="ResumeRadar home"', self.html)
        for text in ('How it works', 'id="headerShareBtn"', 'Built by', 'Newsletter', 'Contact', 'id="privacy"'):
            self.assertIn(text, self.html)

    def test_score_method_and_example_report(self):
        self.assertIn('How this is worked out', self.html)
        self.assertIn('See an example report', self.html)
        self.assertNotIn('ready-to-send', self.html)

    def test_email_report_links_back(self):
        source = (ROOT / 'app.py').read_text()
        self.assertIn('Check your own CV free at <a href="https://resumeradar.sholastechnotes.com/', source)


if __name__ == '__main__':
    unittest.main()
