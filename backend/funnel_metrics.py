"""
Funnel analytics for ResumeRadar.

Daily aggregate counters stored as Redis hashes.
Best-effort: metrics failures never break the calling flow.

Redis key: resumeradar:funnel:{YYYY-MM-DD}
Hash fields: one per funnel event (scan_completed, gate_shown, etc.)
TTL: 7776000 (90 days)
"""

from datetime import datetime, timezone, timedelta
import re
from uuid import UUID

_FUNNEL_PREFIX = "resumeradar:funnel:"
_FUNNEL_TTL = 90 * 86400
_JOURNEY_PREFIX = "resumeradar:journey:"

VALID_EVENTS = frozenset({
    "scan_started",
    "scan_failed",
    "builder_generation_started",
    "builder_generation_completed",
    "builder_generation_failed",
    "builder_preview_viewed",
    "repeat_visit",
    "scan_completed",
    "demo_scan",
    "subscribe_completed",
    "gate_shown",
    "gate_skipped",
    "partial_results_viewed",
    "deep_results_unlocked",
    "section_expanded_categories",
    "section_expanded_ai",
    "section_expanded_ats",
    "sticky_cta_clicked",
    "cv_optimize_clicked",
    "cover_letter_started",
    "checkout_started",
    "bundle_checkout_started",
    "purchase_completed",
    "download_completed",
    "free_download_nigeria",
})

# Subset allowed from the public POST /api/event endpoint
CLIENT_EVENTS = frozenset({
    "scan_started",
    "scan_failed",
    "builder_generation_started",
    "builder_generation_completed",
    "builder_generation_failed",
    "builder_preview_viewed",
    "repeat_visit",
    "demo_scan",
    "gate_shown",
    "gate_skipped",
    "partial_results_viewed",
    "deep_results_unlocked",
    "section_expanded_categories",
    "section_expanded_ai",
    "section_expanded_ats",
    "sticky_cta_clicked",
    "cv_optimize_clicked",
    "cover_letter_started",
})

_redis = None


def init(redis_client):
    """Initialize with the app's Redis client."""
    global _redis
    _redis = redis_client


def _key(date_str=None):
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{_FUNNEL_PREFIX}{date_str}"


def normalize_journey_id(journey_id):
    """Accept only UUID hex or canonical UUID strings, never arbitrary identifiers."""
    if not isinstance(journey_id, str) or not re.fullmatch(
        r"(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
        journey_id,
    ):
        return None
    return UUID(journey_id).hex


def record(event_name, journey_id=None):
    """Increment a funnel event counter for today. Best-effort."""
    try:
        if not _redis or event_name not in VALID_EVENTS:
            return
        key = _key()
        pipe = _redis.pipeline(transaction=True)
        pipe.hincrby(key, event_name, 1)
        pipe.expire(key, _FUNNEL_TTL)
        pipe.execute()
        normalized = normalize_journey_id(journey_id)
        if normalized:
            journey_key = _JOURNEY_PREFIX + normalized
            now = datetime.now(timezone.utc).isoformat()
            pipe = _redis.pipeline(transaction=True)
            pipe.hincrby(journey_key, event_name, 1)
            pipe.hsetnx(journey_key, "first_seen", now)
            pipe.hset(journey_key, mapping={"last_seen": now, event_name + ":last_seen": now})
            pipe.expire(journey_key, _FUNNEL_TTL)
            pipe.execute()
    except Exception:
        pass


def get_day(date_str=None):
    """Return all funnel counters for a given date (default: today UTC)."""
    try:
        if not _redis:
            return _empty()
        if date_str is None:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        raw = _decode_hash(_redis.hgetall(_key(date_str)))
        if not raw:
            return _empty()
        return {evt: int(raw.get(evt, 0)) for evt in VALID_EVENTS}
    except Exception:
        return _empty()


def get_range(days=7):
    """Return funnel counters for the last N days, keyed by date string."""
    result = {}
    today = datetime.now(timezone.utc).date()
    for i in range(max(0, min(int(days), 90))):
        d = (today - timedelta(days=i)).isoformat()
        result[d] = get_day(d)
    return result


def _empty():
    return {evt: 0 for evt in VALID_EVENTS}


def _decode_hash(raw):
    return {
        (key.decode() if isinstance(key, bytes) else key):
        (value.decode() if isinstance(value, bytes) else value)
        for key, value in raw.items()
    }


def _timestamp(value):
    """Return only valid timestamps from stored data."""
    try:
        return datetime.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        return None


def get_journey(journey_id):
    """Return allowlisted anonymous event counts/timestamps, or None if unavailable."""
    normalized = normalize_journey_id(journey_id)
    if not normalized or not _redis:
        return None
    try:
        raw = _decode_hash(_redis.hgetall(_JOURNEY_PREFIX + normalized))
        if not raw:
            return None
        events = {}
        for event in VALID_EVENTS:
            try:
                count = int(raw.get(event, 0))
            except (ValueError, TypeError):
                continue
            if count > 0:
                events[event] = {
                    "count": count,
                    "last_seen": _timestamp(raw.get(event + ":last_seen")),
                }
        return {
            "journey_id": normalized,
            "first_seen": _timestamp(raw.get("first_seen")),
            "last_seen": _timestamp(raw.get("last_seen")),
            "events": events,
        }
    except Exception:
        return None
