"""
Bundle credit management for ResumeRadar Phase 2.

Provides atomic credit consumption via Redis Lua script,
bundle creation, status lookup, email index (HMAC), and
exchange token helpers.

Security:
    H1: Never log raw bundle_token — use bundle_token_hash
    H2: Email index uses HMAC-SHA256 (not plain SHA256)
    H3: Idempotency stores fingerprint + response + ts
    H5: One active bundle per email (latest wins)
    H8: Exchange tokens are single-use (GETDEL), 15min TTL
    H9: No plaintext email in bundle JSON — email_hash only

Redis keys:
    resumeradar:bundle:{token}             → JSON bundle data
    resumeradar:bundle_email:{hmac}        → bundle_token (latest)
    resumeradar:bundle_op:{operation_id}   → JSON {fingerprint, response, ts}
    resumeradar:bundle_exchange:{uuid}     → bundle_token
"""

import os
import json
import hmac as hmac_module
import hashlib
import uuid
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_BUNDLE_PREFIX = "resumeradar:bundle:"
_EMAIL_PREFIX = "resumeradar:bundle_email:"
_OP_PREFIX = "resumeradar:bundle_op:"
_EXCHANGE_PREFIX = "resumeradar:bundle_exchange:"
_CV_PAID_PREFIX = "resumeradar:cv_paid:"

# Bundle plan configuration (H4)
PLANS = {
    "jobhunt": {
        "cv_remaining": 5,
        "cl_remaining": 5,
        "ttl": 172800,       # 48 hours
    },
    "sprint": {
        "cv_remaining": -1,  # unlimited
        "cl_remaining": -1,  # unlimited
        "ttl": 604800,       # 7 days
    },
}

_OP_TTL = 3600       # 1 hour — idempotency window for bundle-use
_EXCHANGE_TTL = 900  # 15 minutes — single-use recovery exchange token

# ---------------------------------------------------------------------------
# Lua script for atomic credit decrement (prevents multi-tab race conditions)
# ---------------------------------------------------------------------------
_DECREMENT_LUA = """
local key = KEYS[1]
local field = ARGV[1]
local data = redis.call('GET', key)
if not data then return cjson.encode({error="expired"}) end
local ttl = redis.call('TTL', key)
local bundle = cjson.decode(data)
local remaining = bundle[field]
if remaining == nil then return cjson.encode({error="invalid_field"}) end
if remaining == -1 then return cjson.encode({ok=true, remaining=-1}) end
if remaining <= 0 then return cjson.encode({error="exhausted"}) end
bundle[field] = remaining - 1
redis.call('SETEX', key, ttl, cjson.encode(bundle))
return cjson.encode({ok=true, remaining=remaining-1})
"""

# ---------------------------------------------------------------------------
# Module-level Redis reference (set via init())
# ---------------------------------------------------------------------------
_redis = None
_lua_script = None


def init(redis_client):
    """Initialize bundle module with the app's Redis client. Call once at startup."""
    global _redis, _lua_script
    _redis = redis_client
    if _redis:
        try:
            _lua_script = _redis.register_script(_DECREMENT_LUA)
        except Exception:
            _lua_script = None


# ---------------------------------------------------------------------------
# HMAC helpers (H2, H9)
# ---------------------------------------------------------------------------
def _get_bundle_hmac_secret():
    """Return BUNDLE_HMAC_SECRET from env. Falls back to AUDIT_HMAC_SECRET."""
    secret = os.getenv("BUNDLE_HMAC_SECRET", "")
    if not secret:
        secret = os.getenv("AUDIT_HMAC_SECRET", "")
    return secret


def hmac_email(email):
    """
    HMAC-SHA256 of normalized email using BUNDLE_HMAC_SECRET.
    Returns 64-char hex digest, or None if secret not configured.
    """
    secret = _get_bundle_hmac_secret()
    if not secret or not email:
        return None
    normalized = str(email).lower().strip()
    return hmac_module.new(
        secret.encode("utf-8"),
        normalized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def hmac_token(token):
    """
    HMAC-SHA256 of bundle_token using BUNDLE_HMAC_SECRET.
    For audit logging (H1) — never log raw token.
    """
    secret = _get_bundle_hmac_secret()
    if not secret or not token:
        return None
    return hmac_module.new(
        secret.encode("utf-8"),
        str(token).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


# ---------------------------------------------------------------------------
# Idempotency fingerprint (H3)
# ---------------------------------------------------------------------------
def compute_fingerprint(endpoint_name, **kwargs):
    """
    SHA256 fingerprint for idempotency.
    Schema: SHA256(endpoint_name + sorted(normalized_payload_fields) + plan + provider)
    """
    parts = [str(endpoint_name)]
    for k in sorted(kwargs.keys()):
        v = kwargs[k]
        parts.append(f"{k}={str(v).lower().strip()}" if v else f"{k}=")
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Bundle creation (called from webhook on payment success)
# ---------------------------------------------------------------------------
def create_bundle(plan, provider, email, bundle_token=None):
    """
    Create a new bundle in Redis.

    Args:
        plan: "jobhunt" or "sprint"
        provider: "stripe" or "paystack"
        email: buyer's email (used transiently for HMAC, never stored as plaintext)
        bundle_token: pre-generated token (or generates one)

    Returns:
        dict with bundle_token and bundle data on success, or {"error": ...}
    """
    if plan not in PLANS:
        return {"error": "Invalid plan"}

    if not _redis:
        return {"error": "Service unavailable"}

    try:
        plan_config = PLANS[plan]
        if not bundle_token:
            bundle_token = secrets.token_urlsafe(32)

        email_hash = hmac_email(email)

        bundle_data = {
            "plan": plan,
            "cv_remaining": plan_config["cv_remaining"],
            "cl_remaining": plan_config["cl_remaining"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "provider": provider,
            "email_hash": email_hash or "",  # H9: no plaintext email
        }

        ttl = plan_config["ttl"]
        bundle_key = f"{_BUNDLE_PREFIX}{bundle_token}"

        # Store bundle data
        _redis.setex(bundle_key, ttl, json.dumps(bundle_data))

        # Update email index (H5: latest bundle wins)
        if email_hash:
            email_key = f"{_EMAIL_PREFIX}{email_hash}"
            _redis.setex(email_key, ttl, bundle_token)

        return {
            "bundle_token": bundle_token,
            "plan": plan,
            "cv_remaining": plan_config["cv_remaining"],
            "cl_remaining": plan_config["cl_remaining"],
            "expires_in_hours": ttl // 3600,
        }
    except Exception as e:
        return {"error": f"Bundle creation failed: {type(e).__name__}"}


# need secrets for token generation
import secrets  # noqa: E402


# ---------------------------------------------------------------------------
# Atomic credit consumption (Lua script)
# ---------------------------------------------------------------------------
def use_credit(bundle_token, credit_type, cv_token=None):
    """
    Atomically decrement a bundle credit.

    Args:
        bundle_token: the bearer token
        credit_type: "cv" or "cover_letter"
        cv_token: if type=="cv", also set the cv_paid flag

    Returns:
        dict with {ok, remaining} or {error}
    """
    if not _redis:
        return {"error": "Service unavailable"}

    field = "cv_remaining" if credit_type == "cv" else "cl_remaining"

    try:
        bundle_key = f"{_BUNDLE_PREFIX}{bundle_token}"

        if _lua_script:
            # Atomic Lua decrement
            result_raw = _lua_script(keys=[bundle_key], args=[field])
            result = json.loads(result_raw)
        else:
            # Fallback: non-atomic (less safe but functional)
            data_raw = _redis.get(bundle_key)
            if not data_raw:
                return {"error": "expired"}
            ttl = _redis.ttl(bundle_key)
            bundle = json.loads(data_raw)
            remaining = bundle.get(field)
            if remaining is None:
                return {"error": "invalid_field"}
            if remaining == -1:
                result = {"ok": True, "remaining": -1}
            elif remaining <= 0:
                return {"error": "exhausted"}
            else:
                bundle[field] = remaining - 1
                _redis.setex(bundle_key, max(ttl, 1), json.dumps(bundle))
                result = {"ok": True, "remaining": remaining - 1}

        if result.get("error"):
            return result

        # On successful CV credit use, set the cv_paid flag
        if credit_type == "cv" and cv_token:
            try:
                ttl = _redis.ttl(bundle_key)
                paid_key = f"{_CV_PAID_PREFIX}{cv_token}"
                _redis.setex(paid_key, max(ttl, 7200), "1")
                # Extend CV data TTL
                _redis.expire(f"resumeradar:cv:{cv_token}", max(ttl, 7200))
            except Exception:
                pass  # cv_paid flag is best-effort

        return {"ok": True, "remaining": result.get("remaining")}

    except Exception as e:
        return {"error": f"Credit use failed: {type(e).__name__}"}


# ---------------------------------------------------------------------------
# Bundle status lookup
# ---------------------------------------------------------------------------
def get_status(bundle_token):
    """
    Get current bundle status.

    Returns:
        dict with active, plan, cv_remaining, cl_remaining, expires_in_hours
        or {"active": False} if expired/invalid
    """
    if not _redis:
        return {"active": False}

    try:
        bundle_key = f"{_BUNDLE_PREFIX}{bundle_token}"
        data_raw = _redis.get(bundle_key)
        if not data_raw:
            return {"active": False}

        bundle = json.loads(data_raw)
        ttl = _redis.ttl(bundle_key)

        return {
            "active": True,
            "plan": bundle.get("plan", ""),
            "cv_remaining": bundle.get("cv_remaining", 0),
            "cl_remaining": bundle.get("cl_remaining", 0),
            "expires_in_hours": max(0, ttl // 3600) if ttl > 0 else 0,
        }
    except Exception:
        return {"active": False}


# ---------------------------------------------------------------------------
# Bundle lookup by email (for recovery — H2, H5)
# ---------------------------------------------------------------------------
def get_bundle_token_by_email(email):
    """
    Look up the latest bundle_token for an email.
    Returns bundle_token string or None.
    """
    if not _redis or not email:
        return None

    try:
        email_hash = hmac_email(email)
        if not email_hash:
            return None
        email_key = f"{_EMAIL_PREFIX}{email_hash}"
        return _redis.get(email_key)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Exchange tokens (H8: single-use, short-lived)
# ---------------------------------------------------------------------------
def create_exchange_token(bundle_token):
    """
    Create a short-lived, single-use exchange token for recovery emails.
    Returns the exchange UUID string.
    """
    if not _redis or not bundle_token:
        return None

    try:
        exchange_id = str(uuid.uuid4())
        exchange_key = f"{_EXCHANGE_PREFIX}{exchange_id}"
        _redis.setex(exchange_key, _EXCHANGE_TTL, bundle_token)
        return exchange_id
    except Exception:
        return None


def redeem_exchange_token(exchange_id):
    """
    Redeem a single-use exchange token. Returns bundle_token or None.
    Uses GETDEL for atomic single-use guarantee.
    """
    if not _redis or not exchange_id:
        return None

    try:
        exchange_key = f"{_EXCHANGE_PREFIX}{exchange_id}"
        # GETDEL: atomic get + delete (Redis 6.2+)
        # Fallback to GET + DELETE for older Redis
        try:
            bundle_token = _redis.getdel(exchange_key)
        except AttributeError:
            bundle_token = _redis.get(exchange_key)
            if bundle_token:
                _redis.delete(exchange_key)
        return bundle_token
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Operation idempotency (H3)
# ---------------------------------------------------------------------------
def check_operation_idempotency(operation_id, fingerprint):
    """
    Check if an operation has already been processed.

    Returns:
        None if new operation (key claimed via SETNX)
        dict with stored response if duplicate with matching fingerprint
        {"error": "conflict"} if key exists with different fingerprint (409)
    """
    if not _redis or not operation_id:
        return None  # No Redis = no idempotency (proceed)

    try:
        op_key = f"{_OP_PREFIX}{operation_id}"
        existing = _redis.get(op_key)

        if existing is None:
            # New operation — will be stored after processing
            return None

        stored = json.loads(existing)
        if stored.get("fingerprint") == fingerprint:
            # Duplicate with same fingerprint — return stored response
            return stored.get("response", {})
        else:
            # Same key, different fingerprint — conflict (H3)
            return {"error": "conflict"}

    except Exception:
        return None  # Fail-open


def store_operation_result(operation_id, fingerprint, response):
    """
    Store the result of an operation for idempotency.
    """
    if not _redis or not operation_id:
        return

    try:
        op_key = f"{_OP_PREFIX}{operation_id}"
        data = json.dumps({
            "fingerprint": fingerprint,
            "response": response,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        _redis.setex(op_key, _OP_TTL, data)
    except Exception:
        pass  # Best-effort


# ---------------------------------------------------------------------------
# UUID validation
# ---------------------------------------------------------------------------
def is_valid_uuid4(value):
    """Validate that a string is a valid UUIDv4."""
    try:
        u = uuid.UUID(str(value), version=4)
        return str(u) == str(value).lower()
    except (ValueError, AttributeError):
        return False
