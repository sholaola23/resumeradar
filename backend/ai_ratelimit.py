"""
In-handler daily rate limiting for AI tools.

Replaces static Flask-Limiter decorator limits so that bundle users
can bypass the daily IP cap while still being subject to burst limits.

Uses atomic INCR + EXPIRE via Redis pipeline to avoid race/TTL bugs.
All date keys use UTC.

Redis key: resumeradar:ratelimit:{tool}:{ip}:{YYYY-MM-DD-UTC}
TTL: 86400
"""

from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_RL_PREFIX = "resumeradar:ratelimit:"
_RL_TTL = 86400  # 24 hours

# Tool-specific daily limits (per IP)
DAILY_LIMITS = {
    "cover_letter": 3,
    "enhance_bullet": 10,
    "generate_summary": 5,
}

# ---------------------------------------------------------------------------
# Module-level Redis reference (set via init())
# ---------------------------------------------------------------------------
_redis = None


def init(redis_client):
    """Initialize rate limit module with the app's Redis client. Call once at startup."""
    global _redis
    _redis = redis_client


def check_and_increment(tool_name, ip_address):
    """
    Check if the IP is under the daily limit for this tool. If yes, increment
    the counter atomically and return True. If over limit, return False.

    Args:
        tool_name: one of DAILY_LIMITS keys
        ip_address: client IP string

    Returns:
        True if under limit (counter incremented), False if limit exceeded.
        Always returns True if Redis unavailable (fail-open).
    """
    try:
        if not _redis:
            return True

        limit = DAILY_LIMITS.get(tool_name)
        if limit is None:
            return True  # Unknown tool, no limit

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"{_RL_PREFIX}{tool_name}:{ip_address}:{today}"

        # Check current count first
        current = _redis.get(key)
        if current is not None and int(current) >= limit:
            return False

        # Atomic increment + set TTL
        pipe = _redis.pipeline(transaction=True)
        pipe.incr(key)
        pipe.expire(key, _RL_TTL)
        results = pipe.execute()

        # After increment, check if we just crossed the limit
        new_count = results[0]  # INCR returns the new value
        if new_count > limit:
            return False

        return True
    except Exception:
        return True  # Fail-open


def get_remaining(tool_name, ip_address):
    """
    Return how many requests remain for this IP/tool today.

    Returns:
        int remaining, or the full limit if Redis unavailable.
    """
    try:
        limit = DAILY_LIMITS.get(tool_name, 0)
        if not _redis:
            return limit

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"{_RL_PREFIX}{tool_name}:{ip_address}:{today}"

        current = _redis.get(key)
        if current is None:
            return limit

        return max(0, limit - int(current))
    except Exception:
        return DAILY_LIMITS.get(tool_name, 0)
