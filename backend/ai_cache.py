"""
AI Response Cache for ResumeRadar.

Deduplicates Claude API calls by caching responses keyed on
tool name + normalized inputs. Best-effort: cache failures
never break the calling flow.

Redis key: resumeradar:ai_cache:{sha256_hash}
TTL: 3600 (1 hour)
"""

import hashlib
import json
import re

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_CACHE_PREFIX = "resumeradar:ai_cache:"
_CACHE_TTL = 3600  # 1 hour

# ---------------------------------------------------------------------------
# Module-level Redis reference (set via init())
# ---------------------------------------------------------------------------
_redis = None


def init(redis_client):
    """Initialize cache module with the app's Redis client. Call once at startup."""
    global _redis
    _redis = redis_client


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------
def _normalize(text):
    """Normalize text for cache key: lowercase, collapse whitespace, strip."""
    if not text:
        return ""
    t = str(text).lower().strip()
    t = re.sub(r'\s+', ' ', t)
    return t


def _make_key(tool_name, *inputs):
    """
    Build a deterministic cache key from tool name + inputs.
    Returns the full Redis key string.
    """
    parts = [_normalize(tool_name)]
    for inp in inputs:
        parts.append(_normalize(inp))
    raw = "|".join(parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"{_CACHE_PREFIX}{digest}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def cache_get(tool_name, *inputs):
    """
    Look up a cached response for the given tool + inputs.

    Returns:
        Parsed response dict if cache hit, None if miss or error.
    """
    try:
        if not _redis:
            return None
        key = _make_key(tool_name, *inputs)
        raw = _redis.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:
        return None


def cache_set(tool_name, response, *inputs):
    """
    Store a response in the cache for the given tool + inputs.
    Best-effort: never raises.
    """
    try:
        if not _redis or response is None:
            return
        key = _make_key(tool_name, *inputs)
        _redis.setex(key, _CACHE_TTL, json.dumps(response, separators=(',', ':')))
    except Exception:
        pass
