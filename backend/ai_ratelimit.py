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

# Tool-specific daily limits, per visitor. Callers pass app._client_ip(), the
# real visitor (CF-Connecting-IP only when the request came from Cloudflare),
# never request.remote_addr, which behind Cloudflare is a rotating edge IP.
# The free tools' numbers were set on 27 Nov 2026 from a week of usage (3
# cover letters, 0 bullets, 0 summaries in ~114 scans). They sit above normal
# use so a few people sharing one address under carrier NAT are not locked
# out; ai_budget's daily cost cap remains the spend backstop.
# "cv_generate" is shared by all three CV-builder generate routes so the cap
# can't be sidestepped by rotating between them. It is set well above real
# usage (including Sprint-plan users) — its job is to bound runaway spend,
# not to ration normal use.
DAILY_LIMITS = {
    "cover_letter": 5,
    "enhance_bullet": 10,
    "generate_summary": 5,
    # 50, not a tighter number, because even the true client IP is shared under
    # carrier NAT — a large share of our Nigerian traffic sits behind CGNAT, so
    # a whole pool can share one address. This still cuts the abuse ceiling from
    # ~360/day (burst limit alone) to 50 without risking a shared-IP lockout.
    "cv_generate": 50,
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


def release(tool_name, ip_address):
    """
    Give back one use counted by check_and_increment, for a request that
    produced no result (a Claude error, or the daily AI budget being spent),
    so a visitor is not locked out without getting anything. Never goes below
    zero. Errors are swallowed: at worst the visitor keeps the count.
    """
    try:
        if not _redis or tool_name not in DAILY_LIMITS:
            return
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"{_RL_PREFIX}{tool_name}:{ip_address}:{today}"
        current = _redis.get(key)
        if current is not None and int(current) > 0:
            _redis.decr(key)
    except Exception:
        pass


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
