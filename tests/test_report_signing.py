"""Emailed and downloaded reports only use scan results the server signed."""
import json
import os
import re
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

with patch.dict(os.environ, {}, clear=True), patch('dotenv.load_dotenv'):
    import app as app_module  # noqa: E402
from backend import report_signing  # noqa: E402

JOB = (
    'We are looking for a Cloud Engineer with AWS experience including EC2 S3 Lambda '
    'CloudFormation Terraform Kubernetes Docker CI/CD pipelines Python scripting and networking.'
)
CV = (
    'Experienced cloud engineer with 5 years of AWS experience. Skilled in EC2, S3, Lambda, '
    'CloudFormation, and Terraform. Built CI/CD pipelines with GitHub Actions. Python and Docker.'
)


def browser_round_trip(data):
    """Mimic the browser: JSON.parse then JSON.stringify turns 50.0 into 50."""
    def js(value):
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, dict):
            return {k: js(v) for k, v in value.items()}
        if isinstance(value, list):
            return [js(v) for v in value]
        return value
    return json.loads(json.dumps(js(json.loads(json.dumps(data)))))


class FakeRedis:
    def __init__(self):
        self.counts = {}
        self.values = {}

    def exists(self, key):
        return int(key in self.values)

    def set(self, key, value, ex=None, nx=False):
        if nx:
            # Counters are created with SET NX EX, then INCR'd.
            if key in self.counts:
                return None
            self.counts[key] = int(value)
            return True
        self.values[key] = value
        return True

    def delete(self, key):
        self.counts.pop(key, None)
        self.values.pop(key, None)

    def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def decr(self, key):
        self.counts[key] = self.counts.get(key, 0) - 1
        return self.counts[key]

    def expire(self, key, seconds):
        return True


class SignatureUnitTest(unittest.TestCase):
    def setUp(self):
        patcher = patch.dict(os.environ, {'FLASK_SECRET_KEY': 'test-only-secret'})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.data = {
            'match_score': 50.0,
            'score_explanation': 'Keyword coverage estimate.',
            'total_matched': 4, 'total_missing': 2, 'total_job_keywords': 6,
            'category_scores': {'technical_skills': {'score': 66.66666666666667, 'matched': 2, 'total': 3}},
            'missing_keywords': {'technical_skills': ['kubernetes']},
            'matched_keywords': {'technical_skills': ['aws', 'python']},
            'ai_suggestions': {'summary': 'Add Kubernetes — and “quotes” é'},
            'ats_formatting': {'issues': [], 'tips': []},
            'resume_text': 'not part of the signature',
        }
        self.data['report_signature'] = report_signing.sign(self.data)

    def test_survives_browser_round_trip(self):
        self.assertIsNotNone(report_signing.verify(browser_round_trip(self.data)))

    def test_returns_only_signed_fields(self):
        fields = report_signing.verify(self.data)
        self.assertEqual(set(fields), set(report_signing.SIGNED_FIELDS))

    def test_changed_field_is_rejected(self):
        for field, value in [
            ('ai_suggestions', {'summary': 'Click http://bad.example to claim a prize'}),
            ('match_score', 99),
            ('missing_keywords', {'technical_skills': ['visit bad.example']}),
        ]:
            with self.subTest(field=field):
                tampered = dict(self.data, **{field: value})
                self.assertIsNone(report_signing.verify(tampered))

    def test_unsigned_or_malformed_is_rejected(self):
        for sig in [None, '', 'v1', 'v1.abc.def', 'v2.1.abc', 123, ['x']]:
            with self.subTest(sig=sig):
                self.assertIsNone(report_signing.verify(dict(self.data, report_signature=sig)))
        self.assertIsNone(report_signing.verify(['not', 'a', 'dict']))

    def test_only_the_exact_signature_spelling_verifies(self):
        _, issued, mac = self.data['report_signature'].split('.')
        arabic = issued.translate(str.maketrans('0123456789', '٠١٢٣٤٥٦٧٨٩'))
        variants = [
            f'v1.0{issued}.{mac}',            # leading zero
            f'v1.00{issued}.{mac}',
            f'v1.{arabic}.{mac}',             # non-ASCII digits int() accepts
            f'v1.{issued}.{mac.upper()}',     # upper-case hex
            f'v1.+{issued}.{mac}',
            f'v1. {issued}.{mac}',
            f'v1.{issued}.{mac}\n',
            f'v1.{issued}².{mac}',            # isdigit() but int() raises
        ]
        for sig in variants:
            with self.subTest(sig=sig):
                self.assertIsNone(report_signing.verify(dict(self.data, report_signature=sig)))

    def test_expired_is_rejected(self):
        old = dict(self.data)
        old['report_signature'] = report_signing.sign(old, now=1_000_000)
        self.assertIsNotNone(report_signing.verify(old, now=1_000_000 + 3600))
        self.assertIsNone(report_signing.verify(old, now=1_000_000 + report_signing.MAX_AGE_SECONDS + 1))

    def test_other_secret_is_rejected(self):
        with patch.dict(os.environ, {'FLASK_SECRET_KEY': 'a-different-secret'}):
            self.assertIsNone(report_signing.verify(self.data))


def confirm_address(client, email, scan, send):
    """Ask for the report, then click the link and press Confirm, as a person would."""
    r = client.post('/api/email-report', json={'email': email, 'scan_data': scan})
    assert r.status_code == 200 and r.get_json()['status'] == 'confirm_sent', r.data
    return click_confirm(client, send.call_args[0][0])


def confirm_link_token(params):
    match = re.search(r'https://resumeradar\.sholastechnotes\.com/confirm-email\?t=([^"\s]+)', params['html'])
    assert match, params['html']
    return match.group(1)


def click_confirm(client, params):
    token = confirm_link_token(params)
    page = client.get(f'/confirm-email?t={token}')
    assert page.status_code == 200, page.data
    r = client.post('/confirm-email', data={'t': token})
    assert r.status_code == 200, r.data
    return token


class ReportRoutesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = patch.dict(os.environ, {'FLASK_SECRET_KEY': 'test-only-secret'})
        env.start()
        cls.addClassCleanup(env.stop)
        # Turn rate limits off for this class only, and put them back after.
        old_config = app_module.app.config.get('RATELIMIT_ENABLED')
        old_enabled = app_module.limiter.enabled
        app_module.app.config['RATELIMIT_ENABLED'] = False
        app_module.limiter.enabled = False
        cls.addClassCleanup(app_module.app.config.__setitem__, 'RATELIMIT_ENABLED', old_config)
        cls.addClassCleanup(setattr, app_module.limiter, 'enabled', old_enabled)
        with patch.object(app_module, 'get_ai_suggestions', return_value={'summary': 'Looks good.'}):
            r = app_module.app.test_client().post('/api/scan', data={'job_description': JOB, 'resume_text': CV})
        assert r.status_code == 200, r.data
        cls.scan = browser_round_trip(r.get_json())
        cls.scan.pop('job_description_view', None)  # app.js removes it too

    def setUp(self):
        self.client = app_module.app.test_client()

    def test_scan_returns_signature(self):
        self.assertTrue(self.scan['report_signature'].startswith('v1.'))

    def test_download_accepts_signed_scan(self):
        r = self.client.post('/api/download-report', json=self.scan)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data.startswith(b'%PDF'))

    def test_download_rejects_tampered_and_unsigned(self):
        tampered = dict(self.scan, ai_suggestions={'summary': 'Visit bad.example'})
        unsigned = {k: v for k, v in self.scan.items() if k != 'report_signature'}
        for body in (tampered, unsigned):
            r = self.client.post('/api/download-report', json=body)
            self.assertEqual(r.status_code, 403)
            self.assertIn('run the scan again', r.get_json()['error'])

    def test_email_rejects_tampered_before_sending(self):
        tampered = dict(self.scan, ai_suggestions={'summary': 'Visit bad.example'})
        with patch.dict(os.environ, {'RESEND_API_KEY': 'test'}), patch('resend.Emails.send') as send:
            r = self.client.post('/api/email-report', json={'email': 'a@example.com', 'scan_data': tampered})
        self.assertEqual(r.status_code, 403)
        send.assert_not_called()

    def test_email_sends_signed_fields_only_and_caps_resends(self):
        extra = dict(self.scan, injected='<a href="http://bad.example">x</a>')
        with patch.dict(os.environ, {'RESEND_API_KEY': 'test'}), \
                patch('resend.Emails.send') as send, \
                patch.object(app_module, '_redis_client', FakeRedis()):
            confirm_address(self.client, 'u@example.com', extra, send)
            send.reset_mock()
            codes = [
                self.client.post('/api/email-report', json={'email': 'u@example.com', 'scan_data': extra}).status_code
                for _ in range(4)
            ]
        self.assertEqual(codes, [200, 200, 200, 429])
        self.assertEqual(send.call_count, 3)
        self.assertNotIn('bad.example', send.call_args[0][0]['html'])

    def test_unconfigured_email_does_not_use_a_send(self):
        redis = FakeRedis()
        env = {k: v for k, v in os.environ.items() if k != 'RESEND_API_KEY'}
        with patch.dict(os.environ, env, clear=True), patch.object(app_module, '_redis_client', redis):
            r = self.client.post('/api/email-report', json={'email': 'a@example.com', 'scan_data': self.scan})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(redis.counts, {})

    def test_failed_send_gives_the_send_back(self):
        redis = FakeRedis()
        body = {'email': 'a@example.com', 'scan_data': self.scan}
        with patch.dict(os.environ, {'RESEND_API_KEY': 'test'}), \
                patch.object(app_module, '_redis_client', redis), \
                patch('resend.Emails.send') as send:
            confirm_address(self.client, 'a@example.com', self.scan, send)
            send.reset_mock()
            send.side_effect = [RuntimeError('resend down'), None, None, None, None]
            codes = [self.client.post('/api/email-report', json=body).status_code for _ in range(5)]
        # One failure, then still three real sends before the cap.
        self.assertEqual(codes, [500, 200, 200, 200, 429])
        self.assertEqual(send.call_count, 4)

    def test_respelled_signature_gets_no_fresh_counter(self):
        _, issued, mac = self.scan['report_signature'].split('.')
        spellings = [self.scan['report_signature'], f'v1.0{issued}.{mac}',
                     f'v1.00{issued}.{mac}', f'v1.{issued}.{mac.upper()}']
        with patch.dict(os.environ, {'RESEND_API_KEY': 'test'}), \
                patch('resend.Emails.send') as send, \
                patch.object(app_module, '_redis_client', FakeRedis()):
            codes = []
            for sig in spellings * 2:
                body = {'email': 'a@example.com', 'scan_data': dict(self.scan, report_signature=sig)}
                codes.append(self.client.post('/api/email-report', json=body).status_code)
        # Only the real spelling sends; every respelling is refused outright.
        self.assertEqual(codes, [200, 403, 403, 403] * 2)
        self.assertEqual(send.call_count, 2)
        self.assertNotIn('bad.example', send.call_args[0][0]['html'])


if __name__ == '__main__':
    unittest.main()
