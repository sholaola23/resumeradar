"""An AI reply that cannot be parsed must not be copied into the logs.

The reply is written from the user's CV, so it can hold their name, employers
or figures. The site promises CV text "is not saved by ResumeRadar".
"""
import contextlib
import io
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend import ai_analyzer, cv_builder  # noqa: E402

MARKER = 'Jane Marker-Doe led payments at Acme Widgets Ltd'


def _fake_client(*_args, **_kwargs):
    message = SimpleNamespace(
        content=[SimpleNamespace(type='text', text=f'Not JSON at all. {MARKER}.')],
        usage=SimpleNamespace(input_tokens=10, output_tokens=10),
    )
    return SimpleNamespace(messages=SimpleNamespace(create=lambda **_kw: message))


class AiLogPrivacyTest(unittest.TestCase):
    def setUp(self):
        patches = [
            mock.patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key'}),
            mock.patch.object(ai_analyzer.ai_budget, 'check_budget', return_value=True),
            mock.patch.object(ai_analyzer.ai_budget, 'spent_fraction', return_value=0.0),
            mock.patch.object(ai_analyzer.ai_budget, 'record_usage'),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def _logged(self, fn):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            fn()
        return out.getvalue()

    def test_scan_suggestions_do_not_log_reply_text(self):
        keyword_results = {'match_score': 50, 'missing_keywords': {}, 'matched_keywords': {}}
        with mock.patch.object(ai_analyzer, 'make_client', _fake_client):
            logged = self._logged(
                lambda: ai_analyzer.get_ai_suggestions('cv text', 'job text', keyword_results))
        self.assertIn('could not be parsed', logged)
        self.assertNotIn('Marker-Doe', logged)
        self.assertNotIn('Acme', logged)

    def test_no_source_line_logs_a_slice_of_the_reply(self):
        for module in (ai_analyzer, cv_builder):
            with open(module.__file__, encoding='utf-8') as f:
                source = f.read()
            self.assertNotIn('response_text[:', source,
                             f'{module.__name__} slices the AI reply, check it is not logged')


if __name__ == '__main__':
    unittest.main()
