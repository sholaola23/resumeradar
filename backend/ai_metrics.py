"""
AI Tool Metrics for ResumeRadar.

Per-tool observability counters stored as Redis hashes.
Best-effort: metrics failures never break the calling flow.

Redis key: resumeradar:ai_metrics:{tool_name}:{YYYY-MM-DD}
Hash fields: requests, claude_calls, cache_hits,
             rate_rejects, budget_rejects, errors
TTL: 604800 (7 days)
"""

from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_METRICS_PREFIX = "resumeradar:ai_metrics:"
_METRICS_TTL = 604800  # 7 days

# Canonical tool names
TOOL_COVER_LETTER = "cover_letter"
TOOL_ENHANCE_BULLET = "enhance_bullet"
TOOL_GENERATE_SUMMARY = "generate_summary"

# ---------------------------------------------------------------------------
# Module-level Redis reference (set via init())
# ---------------------------------------------------------------------------
_redis = None


def init(redis_client):
    """Initialize metrics module with the app's Redis client. Call once at startup."""
    global _redis
    _redis = redis_client


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------
def _key(tool_name):
    """Build the Redis hash key for today's metrics for a tool."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{_METRICS_PREFIX}{tool_name}:{today}"


def _incr(tool_name, field):
    """Increment a single field in the tool's daily metrics hash."""
    try:
        if not _redis:
            return
        key = _key(tool_name)
        pipe = _redis.pipeline(transaction=True)
        pipe.hincrby(key, field, 1)
        pipe.expire(key, _METRICS_TTL)
        pipe.execute()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Public API — recording
# ---------------------------------------------------------------------------
def record_request(tool_name):
    """Record an incoming request for a tool."""
    _incr(tool_name, "requests")


def record_claude_call(tool_name):
    """Record a Claude API call made for a tool."""
    _incr(tool_name, "claude_calls")


def record_cache_hit(tool_name):
    """Record a cache hit (Claude call avoided)."""
    _incr(tool_name, "cache_hits")


def record_rate_reject(tool_name):
    """Record a rate-limit rejection."""
    _incr(tool_name, "rate_rejects")


def record_budget_reject(tool_name):
    """Record a budget-limit rejection."""
    _incr(tool_name, "budget_rejects")


def record_error(tool_name):
    """Record an error during tool execution."""
    _incr(tool_name, "errors")


# ---------------------------------------------------------------------------
# Public API — reading
# ---------------------------------------------------------------------------
def get_metrics(tool_name, date_str=None):
    """
    Return metrics for a tool on a given date.

    Args:
        tool_name: canonical tool name
        date_str: YYYY-MM-DD string (default: today UTC)

    Returns:
        dict with all counter fields (0 for missing)
    """
    try:
        if not _redis:
            return _empty_metrics()

        if date_str is None:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        key = f"{_METRICS_PREFIX}{tool_name}:{date_str}"
        raw = _redis.hgetall(key)
        if not raw:
            return _empty_metrics()

        return {
            "requests": int(raw.get("requests", 0)),
            "claude_calls": int(raw.get("claude_calls", 0)),
            "cache_hits": int(raw.get("cache_hits", 0)),
            "rate_rejects": int(raw.get("rate_rejects", 0)),
            "budget_rejects": int(raw.get("budget_rejects", 0)),
            "errors": int(raw.get("errors", 0)),
        }
    except Exception:
        return _empty_metrics()


def _empty_metrics():
    return {
        "requests": 0,
        "claude_calls": 0,
        "cache_hits": 0,
        "rate_rejects": 0,
        "budget_rejects": 0,
        "errors": 0,
    }
