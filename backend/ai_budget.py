"""
AI Budget Guardrail for ResumeRadar.

Dual daily guardrail for Claude API spend:
  1. Primary: estimated cost cap (USD) based on actual token usage
  2. Fallback: raw call count cap

Best-effort: budget failures never break the calling flow,
but budget exceeded DOES block new calls with a user-safe message.

Redis keys:
    resumeradar:ai_cost:{YYYY-MM-DD}    — accumulated USD cost (float as string)
    resumeradar:ai_budget:{YYYY-MM-DD}  — call count (integer)
TTL: 86400 (auto-expires at end of day)
"""

import os
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_COST_PREFIX = "resumeradar:ai_cost:"
_BUDGET_PREFIX = "resumeradar:ai_budget:"
_DAY_TTL = 86400  # 24 hours

# Per-model pricing (USD per million tokens) — (input, output)
_PRICING = {
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-haiku-4-5": (0.80, 4.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-7": (15.00, 75.00),
}
# Conservative default if model is unknown (falls back to Sonnet rate so the
# daily cap fires sooner rather than later — better to over-protect spend).
_DEFAULT_PRICING = (3.00, 15.00)

BUDGET_EXCEEDED_MESSAGE = (
    "This tool is temporarily unavailable due to high demand. "
    "Please try again later."
)

# ---------------------------------------------------------------------------
# Module-level Redis reference (set via init())
# ---------------------------------------------------------------------------
_redis = None


def init(redis_client):
    """Initialize budget module with the app's Redis client. Call once at startup."""
    global _redis
    _redis = redis_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _today_key():
    """UTC date string for today's key suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _get_cost_limit():
    """Daily cost limit in USD. Default $5.00."""
    try:
        return float(os.getenv("AI_DAILY_COST_LIMIT_USD", "50.00"))
    except (ValueError, TypeError):
        return 50.00


def _get_call_limit():
    """Daily call count limit. Default 500."""
    try:
        return int(os.getenv("AI_DAILY_CALL_LIMIT", "5000"))
    except (ValueError, TypeError):
        return 5000


def _estimate_cost(input_tokens, output_tokens, model=None):
    """Estimate USD cost from token counts using the model's actual pricing."""
    inp_rate, out_rate = _PRICING.get(model, _DEFAULT_PRICING)
    inp = (input_tokens or 0) / 1_000_000 * inp_rate
    out = (output_tokens or 0) / 1_000_000 * out_rate
    return inp + out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def check_budget():
    """
    Check if we're under both daily limits.

    Returns:
        True if under budget (safe to proceed), False if either limit exceeded.
        Always returns True if Redis is unavailable (fail-open for availability).
    """
    try:
        if not _redis:
            return True

        today = _today_key()

        # Check cost limit
        cost_raw = _redis.get(f"{_COST_PREFIX}{today}")
        if cost_raw is not None:
            current_cost = float(cost_raw)
            if current_cost >= _get_cost_limit():
                return False

        # Check call count limit
        count_raw = _redis.get(f"{_BUDGET_PREFIX}{today}")
        if count_raw is not None:
            current_count = int(count_raw)
            if current_count >= _get_call_limit():
                return False

        return True
    except Exception:
        return True  # Fail-open: don't block users due to budget check errors


def record_usage(input_tokens=None, output_tokens=None, model=None):
    """
    Record a Claude API call. Increments call count and adds estimated cost.

    Prefers actual token usage from Claude response. Falls back to zero
    if usage data is missing (call count still incremented as safety net).

    Args:
        input_tokens: actual input_tokens from response.usage (or None)
        output_tokens: actual output_tokens from response.usage (or None)
        model: Claude model id used for the call (drives the cost rate).
            If None, the conservative default (Sonnet rate) is applied.
    """
    try:
        if not _redis:
            return

        today = _today_key()

        # Atomic increment of call count + set TTL
        count_key = f"{_BUDGET_PREFIX}{today}"
        pipe = _redis.pipeline(transaction=True)
        pipe.incr(count_key)
        pipe.expire(count_key, _DAY_TTL)
        pipe.execute()

        # Add estimated cost (only if we have token data)
        if input_tokens is not None or output_tokens is not None:
            cost = _estimate_cost(input_tokens or 0, output_tokens or 0, model)
            if cost > 0:
                cost_key = f"{_COST_PREFIX}{today}"
                pipe = _redis.pipeline(transaction=True)
                pipe.incrbyfloat(cost_key, cost)
                pipe.expire(cost_key, _DAY_TTL)
                pipe.execute()
    except Exception:
        pass  # Best-effort: budget tracking failures don't break calls


def get_daily_usage():
    """
    Return today's usage stats.

    Returns:
        dict with calls, estimated_cost_usd, cost_limit, call_limit
    """
    try:
        if not _redis:
            return {"calls": 0, "estimated_cost_usd": 0.0,
                    "cost_limit": _get_cost_limit(), "call_limit": _get_call_limit()}

        today = _today_key()
        cost_raw = _redis.get(f"{_COST_PREFIX}{today}")
        count_raw = _redis.get(f"{_BUDGET_PREFIX}{today}")

        return {
            "calls": int(count_raw) if count_raw else 0,
            "estimated_cost_usd": round(float(cost_raw), 4) if cost_raw else 0.0,
            "cost_limit": _get_cost_limit(),
            "call_limit": _get_call_limit(),
        }
    except Exception:
        return {"calls": 0, "estimated_cost_usd": 0.0,
                "cost_limit": _get_cost_limit(), "call_limit": _get_call_limit()}
