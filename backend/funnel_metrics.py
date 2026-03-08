"""
Funnel analytics for ResumeRadar.

Daily aggregate counters stored as Redis hashes.
Best-effort: metrics failures never break the calling flow.

Redis key: resumeradar:funnel:{YYYY-MM-DD}
Hash fields: one per funnel event (scan_completed, gate_shown, etc.)
TTL: 604800 (7 days)
"""

from datetime import datetime, timezone, timedelta

_FUNNEL_PREFIX = "resumeradar:funnel:"
_FUNNEL_TTL = 604800  # 7 days

VALID_EVENTS = frozenset({
    "scan_completed",
    "subscribe_completed",
    "gate_shown",
    "gate_skipped",
    "partial_results_viewed",
    "cv_optimize_clicked",
    "cover_letter_started",
    "checkout_started",
    "bundle_checkout_started",
    "purchase_completed",
    "download_completed",
})

# Subset allowed from the public POST /api/event endpoint
CLIENT_EVENTS = frozenset({
    "gate_shown",
    "gate_skipped",
    "partial_results_viewed",
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


def record(event_name):
    """Increment a funnel event counter for today. Best-effort."""
    try:
        if not _redis or event_name not in VALID_EVENTS:
            return
        key = _key()
        pipe = _redis.pipeline(transaction=True)
        pipe.hincrby(key, event_name, 1)
        pipe.expire(key, _FUNNEL_TTL)
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
        raw = _redis.hgetall(_key(date_str))
        if not raw:
            return _empty()
        return {evt: int(raw.get(evt, 0)) for evt in VALID_EVENTS}
    except Exception:
        return _empty()


def get_range(days=7):
    """Return funnel counters for the last N days, keyed by date string."""
    result = {}
    today = datetime.now(timezone.utc).date()
    for i in range(days):
        d = (today - timedelta(days=i)).isoformat()
        result[d] = get_day(d)
    return result


def _empty():
    return {evt: 0 for evt in VALID_EVENTS}
