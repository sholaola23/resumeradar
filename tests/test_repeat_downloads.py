"""Exercise credit races against an isolated, disposable real Redis server."""
import json
import subprocess
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import redis
from backend import bundle_credits
from tests.test_product_integration import product


class RepeatDownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='rr-credits-')
        cls.socket = cls.tmp.name + '/redis.sock'
        cls.server = subprocess.Popen([
            'redis-server', '--port', '0', '--unixsocket', cls.socket,
            '--save', '', '--appendonly', 'no',
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.redis = redis.Redis(unix_socket_path=cls.socket, decode_responses=True)
        for _ in range(100):
            try:
                cls.redis.ping()
                break
            except redis.ConnectionError:
                time.sleep(.02)

    @classmethod
    def tearDownClass(cls):
        cls.server.terminate()
        cls.server.wait(timeout=5)
        cls.tmp.cleanup()

    def setUp(self):
        self.redis.flushdb()  # Only our private Unix-socket Redis instance.
        bundle_credits.init(self.redis)
        self.redis.setex('resumeradar:bundle:test', 3600,
                         json.dumps({'cv_remaining': 2, 'cl_remaining': 1}))
        for token in ('cv1', 'cv2', 'cv3'):
            self.redis.setex('resumeradar:cv:' + token, 120,
                             json.dumps({'personal': {'full_name': 'Test Candidate'}}))

    def tearDown(self):
        bundle_credits.init(None)

    def test_concurrent_repeats_charge_once_and_new_cv_costs_another_credit(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(
                lambda _: bundle_credits.use_credit('test', 'cv', 'cv1'), range(12)))
        self.assertTrue(all(result.get('ok') for result in results))
        self.assertEqual(json.loads(self.redis.get('resumeradar:bundle:test'))['cv_remaining'], 1)
        self.assertEqual(bundle_credits.use_credit('test', 'cv', 'cv2')['remaining'], 0)
        self.assertTrue(bundle_credits.use_credit('test', 'cv', 'cv1')['ok'])
        self.assertEqual(bundle_credits.use_credit('test', 'cv', 'cv3')['error'], 'exhausted')

    def test_repeat_does_not_extend_access_and_deleted_cv_cannot_spend_credit(self):
        bundle_credits.use_credit('test', 'cv', 'cv1')
        self.redis.expire('resumeradar:cv_paid:cv1', 30)
        bundle_credits.use_credit('test', 'cv', 'cv1')
        self.assertLessEqual(self.redis.ttl('resumeradar:cv_paid:cv1'), 30)
        self.redis.delete('resumeradar:cv:cv2')
        self.assertEqual(bundle_credits.use_credit('test', 'cv', 'cv2')['error'], 'invalid_cv_token')

    def test_more_than_three_downloads_and_format_switches_are_free(self):
        bundle_credits.use_credit('test', 'cv', 'cv1')
        with patch.object(product, '_redis_client', self.redis):
            client = product.app.test_client()
            for fmt in ('pdf', 'docx', 'both', 'pdf', 'docx'):
                result = client.get('/api/build/download/cv1?format=' + fmt)
                self.assertEqual(result.status_code, 200, result.get_json(silent=True))
                self.assertGreater(int(result.headers.get('X-CV-Access-Seconds', '0')), 0)
                self.assertLessEqual(int(result.headers['X-CV-Access-Seconds']), 3600)
            self.redis.delete('resumeradar:bundle:test')
            self.assertEqual(client.get('/api/build/download/cv1').status_code, 400)

    def test_paid_checkout_returns_download_instead_of_another_charge(self):
        self.redis.setex('resumeradar:cv_paid:cv1', 3600, '1')
        with patch.object(product, '_redis_client', self.redis):
            result = product.app.test_client().post('/api/build/create-checkout', json={'token': 'cv1'})
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.get_json().get('already_paid'))
        self.assertNotIn('checkout_url', result.get_json())
