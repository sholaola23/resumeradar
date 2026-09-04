"""Isolated analytics tests: never connect to services or load app configuration."""
import unittest
from backend import funnel_metrics as metrics


class MemoryRedis:
    def __init__(self):
        self.hashes = {}
        self.expiries = {}
        self.now = 0

    def pipeline(self, transaction=True):
        return self

    def hincrby(self, key, field, amount):
        bucket = self.hashes.setdefault(key, {})
        bucket[field] = str(int(bucket.get(field, 0)) + amount)
        return self

    def hset(self, key, mapping):
        self.hashes.setdefault(key, {}).update({k: str(v) for k, v in mapping.items()})
        return self

    def hsetnx(self, key, field, value):
        self.hashes.setdefault(key, {}).setdefault(field, str(value))
        return self

    def expire(self, key, seconds):
        self.expiries[key] = self.now + seconds
        return self

    def execute(self):
        return []

    def hgetall(self, key):
        if self.expiries.get(key, float('inf')) <= self.now:
            self.hashes.pop(key, None)
        return self.hashes.get(key, {}).copy()


class FunnelMetricsTests(unittest.TestCase):
    journey = '12345678-1234-4234-8234-123456789abc'
    normalized = '12345678123442348234123456789abc'

    def setUp(self):
        self.redis = MemoryRedis()
        metrics.init(self.redis)

    def tearDown(self):
        metrics.init(None)

    def test_aggregate_survives_89_days_and_expires_after_90(self):
        metrics.record('scan_completed')
        self.redis.now = 89 * 86400
        self.assertEqual(metrics.get_day()['scan_completed'], 1)
        self.redis.now = 90 * 86400
        self.assertEqual(metrics.get_day()['scan_completed'], 0)

    def test_journey_counts_normalized_ids_and_timestamps(self):
        metrics.record('builder_generation_completed', self.journey)
        metrics.record('builder_generation_completed', self.normalized.upper())
        result = metrics.get_journey(self.journey)
        self.assertEqual(result['journey_id'], self.normalized)
        self.assertEqual(result['events']['builder_generation_completed']['count'], 2)
        self.assertLessEqual(result['first_seen'], result['last_seen'])
        self.assertTrue(result['events']['builder_generation_completed']['last_seen'])
        self.redis.now = 89 * 86400
        self.assertIsNotNone(metrics.get_journey(self.journey))
        self.redis.now = 90 * 86400
        self.assertIsNone(metrics.get_journey(self.journey))

    def test_invalid_identifiers_only_count_aggregate(self):
        for value in ['person@example.com', '../secret', '{'+self.journey+'}', None, 12, {}, []]:
            metrics.record('scan_started', value)
            self.assertIsNone(metrics.get_journey(value))
        self.assertEqual(metrics.get_day()['scan_started'], 7)
        self.assertFalse(any(k.startswith('resumeradar:journey:') for k in self.redis.hashes))

    def test_server_truth_events_are_not_client_events(self):
        self.assertTrue({'scan_started', 'scan_failed', 'builder_generation_started',
                         'builder_generation_completed', 'builder_generation_failed',
                         'builder_preview_viewed', 'repeat_visit'} <= metrics.CLIENT_EVENTS)
        self.assertFalse({'scan_completed', 'purchase_completed', 'download_completed'} & metrics.CLIENT_EVENTS)

    def test_journey_read_excludes_untrusted_fields(self):
        metrics.record('repeat_visit', self.journey)
        self.redis.hset('resumeradar:journey:' + self.normalized,
                        mapping={'email': 'private@example.com', 'unknown': '1'})
        result = metrics.get_journey(self.journey)
        self.assertEqual(set(result), {'journey_id', 'first_seen', 'last_seen', 'events'})
        self.assertEqual(set(result['events']), {'repeat_visit'})

    def test_range_is_bounded(self):
        self.assertEqual(len(metrics.get_range(1000)), 90)
        self.assertEqual(len(metrics.get_range(-1)), 0)

    def test_missing_or_broken_redis_is_best_effort(self):
        class BrokenRedis:
            def pipeline(self, **kwargs):
                raise ConnectionError()
            def hgetall(self, key):
                raise ConnectionError()
        for client in (None, BrokenRedis()):
            metrics.init(client)
            metrics.record('scan_started', self.journey)
            self.assertEqual(metrics.get_day()['scan_started'], 0)
            self.assertIsNone(metrics.get_journey(self.journey))


if __name__ == '__main__':
    unittest.main()
