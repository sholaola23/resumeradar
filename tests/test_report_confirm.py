"""A report is only emailed to an address that confirmed it, and every email
cap fails closed when Redis is missing or failing."""
import os
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_report_signing import (  # noqa: E402
    CV, JOB, FakeRedis, app_module, browser_round_trip, click_confirm, confirm_link_token,
)
from backend import report_signing  # noqa: E402


class BrokenRedis(FakeRedis):
    def incr(self, key):
        raise ConnectionError('redis down')

    def exists(self, key):
        raise ConnectionError('redis down')

    def set(self, key, value, ex=None):
        raise ConnectionError('redis down')


class ReportConfirmTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = patch.dict(os.environ, {'FLASK_SECRET_KEY': 'test-only-secret', 'RESEND_API_KEY': 'test'})
        env.start()
        cls.addClassCleanup(env.stop)
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
        cls.scan.pop('job_description_view', None)

    def setUp(self):
        self.client = app_module.app.test_client()
        self.redis = FakeRedis()
        patcher = patch.object(app_module, '_redis_client', self.redis)
        patcher.start()
        self.addCleanup(patcher.stop)
        sender = patch('resend.Emails.send')
        self.send = sender.start()
        self.addCleanup(sender.stop)

    def ask(self, email='me@example.com', scan=None):
        return self.client.post('/api/email-report', json={'email': email, 'scan_data': scan or self.scan})

    def status(self, email='me@example.com', scan=None):
        return self.client.post('/api/email-report/status', json={'email': email, 'scan_data': scan or self.scan})

    def rescan(self, offset):
        """The same result signed at another time: a separate scan to the server."""
        signed = dict(self.scan)
        signed['report_signature'] = report_signing.sign(signed, now=time.time() - offset)
        return signed

    # --- the confirm email -------------------------------------------------

    def test_first_email_is_only_a_confirm_link(self):
        r = self.ask()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['status'], 'confirm_sent')
        self.assertEqual(self.send.call_count, 1)
        params = self.send.call_args[0][0]
        self.assertEqual(params['to'], ['me@example.com'])
        self.assertEqual(params['subject'], 'Confirm to receive your ResumeRadar report')
        self.assertNotIn('attachments', params)
        # Nothing from the report, and not the address itself, in the email or link.
        for text in ('Looks good.', 'match estimate', str(self.scan['total_matched']) + '</div>'):
            self.assertNotIn(text, params['html'])
        token = confirm_link_token(params)
        self.assertNotIn('example.com', token)
        self.assertIn(token, params['text'])

    def test_opening_the_link_does_not_confirm_only_pressing_does(self):
        self.ask()
        token = confirm_link_token(self.send.call_args[0][0])
        page = self.client.get(f'/confirm-email?t={token}')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'Confirm and send my report', page.data)
        self.assertIn(b'noindex', page.data)
        self.assertEqual(self.status().get_json(), {'confirmed': False})
        done = self.client.post('/confirm-email', data={'t': token})
        self.assertEqual(done.status_code, 200)
        self.assertIn(b'Address confirmed', done.data)
        self.assertEqual(self.status().get_json(), {'confirmed': True})

    def test_report_goes_out_only_after_confirm(self):
        self.ask()
        self.ask()  # asking again before confirming sends another link, not the report
        for call in self.send.call_args_list:
            self.assertNotIn('attachments', call[0][0])
        click_confirm(self.client, self.send.call_args[0][0])
        self.send.reset_mock()
        r = self.ask()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()['success'])
        params = self.send.call_args[0][0]
        self.assertEqual(params['attachments'][0]['filename'], 'ResumeRadar_Report.pdf')
        self.assertEqual(params['to'], ['me@example.com'])

    def test_confirmation_covers_only_that_address_and_scan(self):
        self.ask()
        click_confirm(self.client, self.send.call_args[0][0])
        self.assertEqual(self.status('ME@Example.com').get_json(), {'confirmed': True})
        self.assertEqual(self.status('other@example.com').get_json(), {'confirmed': False})
        self.assertEqual(self.status(scan=self.rescan(60)).get_json(), {'confirmed': False})
        self.send.reset_mock()
        self.assertEqual(self.ask('other@example.com').get_json()['status'], 'confirm_sent')
        self.assertNotIn('attachments', self.send.call_args[0][0])

    def test_bad_expired_and_tampered_tokens_are_refused(self):
        self.ask()
        token = confirm_link_token(self.send.call_args[0][0])
        old = report_signing.confirm_token(self.scan, 'me@example.com', now=time.time() - 3700)
        tampered = token[:-1] + ('0' if token[-1] != '0' else '1')
        other_address = token.split('.')
        other_address[3] = report_signing.email_id('victim@example.com')
        for bad in (old, tampered, '.'.join(other_address), '', 'nonsense'):
            self.assertEqual(self.client.get(f'/confirm-email?t={bad}').status_code, 410)
            self.assertEqual(self.client.post('/confirm-email', data={'t': bad}).status_code, 410)
        self.assertEqual(self.redis.values, {})

    def test_only_one_plain_address_is_accepted(self):
        for email in ('a@example.com, b@example.com', 'a@example.com;b@example.com',
                      'Name <a@example.com>', 'a b@example.com', 'a@example', 'x' * 250 + '@example.com'):
            self.assertEqual(self.ask(email).status_code, 400, email)
            self.assertEqual(self.status(email).status_code, 400, email)
        self.send.assert_not_called()

    def test_confirm_emails_are_capped_per_scan(self):
        codes = [self.ask(f'u{i}@example.com').status_code for i in range(4)]
        self.assertEqual(codes, [200, 200, 200, 429])
        self.assertEqual(self.send.call_count, 3)

    def test_confirm_emails_are_capped_per_address_across_scans(self):
        codes = [self.ask('target@example.com', self.rescan(i * 10)).status_code for i in range(6)]
        self.assertEqual(codes, [200, 200, 200, 200, 200, 429])
        self.assertEqual(self.send.call_count, 5)
        # The refused one did not use up a slot on its own scan.
        self.assertEqual(self.ask('someone@example.com', self.rescan(50)).status_code, 200)

    def test_failed_confirm_email_gives_both_slots_back(self):
        self.send.side_effect = RuntimeError('resend down')
        self.assertEqual(self.ask().status_code, 500)
        self.assertTrue(all(v == 0 for v in self.redis.counts.values()), self.redis.counts)

    # --- fail closed -------------------------------------------------------

    def test_no_redis_refuses_every_email(self):
        with patch.object(app_module, '_redis_client', None):
            r = self.ask()
            self.assertEqual(r.status_code, 503)
            self.assertEqual(r.get_json()['error'], app_module.EMAIL_UNAVAILABLE_MESSAGE)
            self.assertEqual(self.status().status_code, 503)
            token = report_signing.confirm_token(self.scan, 'me@example.com')
            page = self.client.post('/confirm-email', data={'t': token})
            self.assertEqual(page.status_code, 503)
            self.assertIn(b'Please try again later', page.data)
        self.send.assert_not_called()

    def test_failing_redis_refuses_every_email(self):
        with patch.object(app_module, '_redis_client', BrokenRedis()):
            r = self.ask()
            self.assertEqual(r.status_code, 503)
            self.assertIn('try again later', r.get_json()['error'])
            self.assertEqual(self.status().status_code, 503)
            token = report_signing.confirm_token(self.scan, 'me@example.com')
            self.assertEqual(self.client.post('/confirm-email', data={'t': token}).status_code, 503)
        self.send.assert_not_called()

    def test_redis_failing_after_confirm_still_refuses_the_report(self):
        self.ask()
        click_confirm(self.client, self.send.call_args[0][0])
        self.send.reset_mock()

        class IncrFails(FakeRedis):
            def incr(self, key):
                raise ConnectionError('redis down')
        broken = IncrFails()
        broken.values = self.redis.values
        with patch.object(app_module, '_redis_client', broken):
            r = self.ask()
        self.assertEqual(r.status_code, 503)
        self.send.assert_not_called()

    def test_no_address_in_redis_keys_or_values(self):
        self.ask('private.person@example.com')
        click_confirm(self.client, self.send.call_args[0][0])
        self.ask('private.person@example.com')
        stored = ' '.join(list(self.redis.counts) + list(self.redis.values) + [str(v) for v in self.redis.values.values()])
        self.assertNotIn('private', stored)
        self.assertNotIn('example.com', stored)


if __name__ == '__main__':
    unittest.main()
