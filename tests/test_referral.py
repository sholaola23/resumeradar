"""Referral loop: /share page, ref counting and the privacy rules around share links."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

with patch.dict(os.environ, {}, clear=True), patch('dotenv.load_dotenv'):
    from app import app  # noqa: E402
from backend import funnel_metrics  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REFERRAL_EVENTS = {
    'share_prompt_shown', 'share_clicked', 'job_link_created', 'job_link_opened',
    'referred_scan_completed', 'ref_visit_whatsapp', 'ref_visit_linkedin', 'ref_visit_copy',
    'ref_visit_native', 'ref_visit_qr', 'ref_visit_group', 'ref_visit_job',
}


def read(path):
    with open(os.path.join(ROOT, path), encoding='utf-8') as handle:
        return handle.read()


class ReferralTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_share_page_has_text_qr_and_ref_links(self):
        response = self.client.get('/share')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('https://resumeradar.sholastechnotes.com/?ref=group', html)
        self.assertIn('/static/images/share-qr.svg', html)
        self.assertIn('data-share-ref="group"', html)
        for path in ('/static/images/share-qr.svg', '/static/images/share-qr.png', '/static/js/share.js'):
            with self.client.get(path) as asset:
                self.assertEqual(asset.status_code, 200, path)

    def test_results_page_has_prompt_card_and_job_notice(self):
        html = self.client.get('/').get_data(as_text=True)
        for marker in ('id="sharePrompt"', 'id="shareCard"', 'id="jobLinkNotice"', 'data-share-job',
                       'data-share="whatsapp"', '/static/js/share.js'):
            self.assertIn(marker, html)

    def test_any_ref_value_serves_the_normal_page_without_echoing_it(self):
        response = self.client.get('/?ref=%3Cscript%3Ealert(1)%3C/script%3E')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('alert(1)', response.get_data(as_text=True))

    def test_referral_events_are_counted_and_others_are_not(self):
        self.assertLessEqual(REFERRAL_EVENTS, funnel_metrics.CLIENT_EVENTS)
        self.assertLessEqual(funnel_metrics.CLIENT_EVENTS, funnel_metrics.VALID_EVENTS)
        for bad in ('ref_visit_', 'ref_visit_evil', 'ref_visit_qr ', 'REF_VISIT_QR'):
            self.assertNotIn(bad, funnel_metrics.VALID_EVENTS)

    def test_event_endpoint_records_a_referral_event(self):
        headers = {'Origin': 'https://resumeradar.sholastechnotes.com'}
        with patch.object(funnel_metrics, 'record') as record:
            self.assertEqual(self.client.post('/api/event', json={'event': 'ref_visit_qr'}, headers=headers).status_code, 204)
            self.assertEqual(self.client.post('/api/event', json={'event': 'ref_visit_evil'}, headers=headers).status_code, 204)
        record.assert_called_once_with('ref_visit_qr', None)

    def test_python_and_browser_agree_on_ref_sources(self):
        for source in funnel_metrics.REF_SOURCES:
            self.assertIn(f"'{source}'", read('static/js/scan-utils.js'))
        self.assertEqual(len(funnel_metrics.REF_SOURCES), read('static/js/scan-utils.js').split('REF_SOURCES: [')[1].split(']')[0].count("'") // 2)

    def test_share_links_never_carry_a_score_or_cv(self):
        share_js = read('static/js/share.js')
        app_js = read('static/js/app.js')
        self.assertNotIn('score', share_js.lower())
        self.assertNotIn('resumeText', share_js)
        self.assertNotIn('score_tier', app_js)
        self.assertNotIn('job-description match estimate on ResumeRadar', app_js)


if __name__ == '__main__':
    unittest.main()
