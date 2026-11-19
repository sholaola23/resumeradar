"""'Was this useful?' feedback: what is stored, what is refused, who can read it."""
import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import with an empty environment and no .env, so no real service is touched.
with patch.dict(os.environ, {}, clear=True), patch('dotenv.load_dotenv'):
    from app import app, limiter  # noqa: E402
from backend import feedback, funnel_metrics  # noqa: E402

ORIGIN = {'Origin': 'https://resumeradar.sholastechnotes.com'}


class MemoryRedis:
    """Just enough Redis for feedback lists and funnel counters."""

    def __init__(self):
        self.lists = {}
        self.hashes = {}
        self.expiries = {}

    def llen(self, key):
        return len(self.lists.get(key, []))

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    def lrange(self, key, start, end):
        return list(self.lists.get(key, []))

    def expire(self, key, seconds):
        self.expiries[key] = seconds
        return self

    def pipeline(self, transaction=True):
        return self

    def hincrby(self, key, field, amount):
        bucket = self.hashes.setdefault(key, {})
        bucket[field] = str(int(bucket.get(field, 0)) + amount)
        return self

    def hgetall(self, key):
        return self.hashes.get(key, {}).copy()

    def execute(self):
        return []


class FeedbackTestCase(unittest.TestCase):
    def setUp(self):
        self.redis = MemoryRedis()
        feedback.init(self.redis)
        funnel_metrics.init(self.redis)
        self.addCleanup(feedback.init, None)
        self.addCleanup(funnel_metrics.init, None)
        limiter.reset()
        self.client = app.test_client()

    def stored(self):
        return [json.loads(raw) for items in self.redis.lists.values() for raw in items]

    def post(self, body, headers=ORIGIN):
        return self.client.post('/api/feedback', json=body, headers=headers)


class CleanCommentTests(unittest.TestCase):
    def test_contact_details_are_removed(self):
        cases = {
            'Email me at jane.doe@example.com please': 'jane.doe',
            'Call +44 7700 900123 any time': '7700',
            'Ring (020) 7946-0958': '7946',
            'See https://linkedin.com/in/jane-doe for more': 'linkedin',
            'my site is www.janedoe.dev': 'janedoe',
        }
        for text, leaked in cases.items():
            with self.subTest(text=text):
                cleaned = feedback.clean_comment(text)
                self.assertNotIn(leaked, cleaned)
                self.assertIn('[removed]', cleaned)

    def test_ordinary_comments_are_kept_word_for_word(self):
        text = 'On 2026-11-19 the 3 missing keywords were spot on. Scored 62 then 81 then 90.'
        self.assertEqual(feedback.clean_comment(text), text)

    def test_messy_input(self):
        self.assertEqual(feedback.clean_comment('  line one\r\n\tline two\x00\x1b[31m  '), 'line one line two [31m')
        self.assertEqual(len(feedback.clean_comment('a' * 5000)), feedback.MAX_COMMENT_CHARS)
        for junk in (None, 42, ['x'], {'a': 1}, '', '   \n\t '):
            with self.subTest(junk=junk):
                self.assertEqual(feedback.clean_comment(junk), '')


class FeedbackRouteTests(FeedbackTestCase):
    def test_comment_is_stored_with_only_the_allowed_fields(self):
        r = self.post({'useful': True, 'comment': 'Clear and quick.', 'may_quote': True,
                       'journey_id': '12345678-1234-4234-8234-123456789abc', 'email': 'a@b.co',
                       'cv_text': 'ten years at Acme'},
                      headers={**ORIGIN, 'CF-Connecting-IP': '203.0.113.9'})
        self.assertEqual(r.status_code, 200)
        entry, = self.stored()
        self.assertEqual(set(entry), {'date', 'useful', 'comment', 'may_quote'})
        self.assertEqual(entry['comment'], 'Clear and quick.')
        self.assertTrue(entry['useful'])
        self.assertTrue(entry['may_quote'])
        self.assertRegex(entry['date'], r'^\d{4}-\d{2}-\d{2}$')
        everything = json.dumps([self.redis.lists, self.redis.hashes])
        for secret in ('203.0.113.9', '123456781234', 'a@b.co', 'Acme'):
            self.assertNotIn(secret, everything)

    def test_comment_expires_after_90_days_and_is_counted(self):
        self.post({'useful': False, 'comment': 'Too many keywords listed.'})
        key, = self.redis.lists
        self.assertEqual(self.redis.expiries[key], 90 * 86400)
        self.assertEqual(funnel_metrics.get_day()['feedback_comment'], 1)

    def test_may_quote_needs_a_yes_vote_and_a_real_true(self):
        self.post({'useful': False, 'comment': 'Not for me.', 'may_quote': True})
        self.post({'useful': True, 'comment': 'Good.', 'may_quote': 'yes'})
        self.post({'useful': True, 'comment': 'Good.'})
        self.assertEqual([e['may_quote'] for e in self.stored()], [False, False, False])

    def test_bad_requests_store_nothing(self):
        bad = [
            {'comment': 'no vote'},
            {'useful': 'true', 'comment': 'vote is a string'},
            {'useful': 1, 'comment': 'vote is a number'},
            {'useful': True},
            {'useful': True, 'comment': '   '},
            {'useful': True, 'comment': ['list']},
            ['not', 'an', 'object'],
        ]
        for body in bad:
            with self.subTest(body=body):
                self.assertEqual(self.post(body).status_code, 400)
        self.assertEqual(self.client.post('/api/feedback', data='{{{', headers=ORIGIN,
                                          content_type='application/json').status_code, 400)
        self.assertEqual(self.stored(), [])

    def test_other_origins_are_refused(self):
        body = {'useful': True, 'comment': 'Hello'}
        for headers in ({}, {'Origin': 'https://evil.example'},
                        {'Referer': 'https://resumeradar.sholastechnotes.com.evil.example/'}):
            with self.subTest(headers=headers):
                self.assertEqual(self.post(body, headers=headers).status_code, 403)
        self.assertEqual(self.stored(), [])

    def test_daily_cap_and_missing_redis_fail_safely(self):
        for _ in range(feedback.MAX_COMMENTS_PER_DAY):
            self.assertTrue(feedback.save_comment(True, 'ok'))
        self.assertEqual(self.post({'useful': True, 'comment': 'one too many'}).status_code, 503)
        self.assertEqual(len(self.stored()), feedback.MAX_COMMENTS_PER_DAY)
        feedback.init(None)
        self.assertEqual(self.post({'useful': True, 'comment': 'no redis'}).status_code, 503)

    def test_rate_limit(self):
        codes = [self.post({'useful': True, 'comment': 'again'}).status_code for _ in range(11)]
        self.assertEqual(codes, [200] * 10 + [429])

    def test_votes_are_client_funnel_events(self):
        for event in ('feedback_yes', 'feedback_no'):
            self.assertIn(event, funnel_metrics.CLIENT_EVENTS)
            self.client.post('/api/event', json={'event': event}, headers=ORIGIN)
        # A visitor cannot inflate the comment counter through /api/event.
        self.assertNotIn('feedback_comment', funnel_metrics.CLIENT_EVENTS)
        self.client.post('/api/event', json={'event': 'feedback_comment'}, headers=ORIGIN)
        day = funnel_metrics.get_day()
        self.assertEqual((day['feedback_yes'], day['feedback_no'], day['feedback_comment']), (1, 1, 0))


class FeedbackAdminTests(FeedbackTestCase):
    def test_admin_read_needs_the_token(self):
        self.post({'useful': True, 'comment': 'Helpful.', 'may_quote': True})
        with patch.dict(os.environ, {'AUDIT_ADMIN_TOKEN': ''}):
            self.assertEqual(self.client.get('/api/admin/feedback').status_code, 503)
        with patch.dict(os.environ, {'AUDIT_ADMIN_TOKEN': 'test-token'}):
            self.assertEqual(self.client.get('/api/admin/feedback').status_code, 401)
            for token in ('nope', 'caf\u00e9'):
                wrong = self.client.get('/api/admin/feedback', headers={'Authorization': 'Bearer ' + token})
                self.assertEqual(wrong.status_code, 401)
            ok = self.client.get('/api/admin/feedback?days=abc', headers={'Authorization': 'Bearer test-token'})
            self.assertEqual(ok.status_code, 200)
            self.assertEqual(ok.headers['Cache-Control'], 'no-store')
            self.assertEqual([c['comment'] for c in ok.get_json()['comments']], ['Helpful.'])


class FeedbackPageTests(FeedbackTestCase):
    def test_card_and_script_are_on_the_scan_page(self):
        home = self.client.get('/').data.decode()
        for needle in ('id="feedbackCard"', 'Was this report useful?', '/static/js/feedback.js'):
            self.assertIn(needle, home)
        script = self.client.get('/static/js/feedback.js')
        self.addCleanup(script.close)
        self.assertEqual(script.status_code, 200)


if __name__ == '__main__':
    unittest.main()
