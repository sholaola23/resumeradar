"""
Privacy-preserving audit log for ResumeRadar CV Builder.

Stores operational events (payment, download, email) with HMAC-hashed identifiers.
No CV content, no job descriptions, no plaintext PII.
Retention: 120 days (aligned with Stripe chargeback dispute window).

Events:
    payment_verified  — payment confirmed (source: "webhook" or "download_verify")
    download_200      — file served successfully (format, bytes, filename)
    download_error    — generation/serve failure (error class name only)
    email_accepted    — Resend API accepted the send request (message ID stored)
    email_send_error  — Resend API call failed (error class name only)
    email_delivered   — Resend webhook: delivered to recipient's mail server
    email_bounced     — Resend webhook: permanently rejected
    email_delivery_delayed — Resend webhook: temporary delivery failure
    email_complained  — Resend webhook: marked as spam
"""

import os
import json
import hmac
import hashlib
import uuid
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
AUDIT_TTL = 10_368_000  # 120 days in seconds
AUDIT_PREFIX = "resumeradar:audit:"
AUDIT_IDX_PREFIX = "resumeradar:audit_idx:"

# Maximum length for string fields to prevent unbounded payload growth
_MAX_FIELD_LEN = 200

VALID_EVENTS = frozenset({
    "payment_verified",
    "download_200",
    "download_error",
    "email_accepted",
    "email_send_error",
    "email_delivered",
    "email_bounced",
    "email_delivery_delayed",
    "email_complained",
    # Phase 2: Bundle events
    "bundle_created",
    "bundle_credit_used",
    "bundle_exhausted",
})

ALLOWED_KWARGS = frozenset({
    "provider", "session_id", "payment_intent_id",
    "reference",            # Paystack reference
    "resend_message_id",
    "format", "content_length", "status_code", "error",
    "filename", "source",   # source disambiguates duplicate event types
    # Phase 2: Bundle fields
    "type", "remaining", "plan",
    "bundle_token_hash",    # H1: HMAC hash, never raw token
})

# ---------------------------------------------------------------------------
# Module-level Redis reference (set via init())
# ---------------------------------------------------------------------------
_redis = None


def init(redis_client):
    """Initialize audit module with the app's Redis client. Call once at startup."""
    global _redis
    _redis = redis_client


# ---------------------------------------------------------------------------
# HMAC hashing
# ---------------------------------------------------------------------------
def _hmac_hash(value):
    """
    HMAC-SHA256 hash of a value using AUDIT_HMAC_SECRET.
    Returns 64-char hex digest, or None if secret not configured or value empty.
    """
    secret = os.getenv("AUDIT_HMAC_SECRET", "")
    if not secret or not value:
        return None
    return hmac.new(
        secret.encode("utf-8"),
        str(value).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _cap(value, max_len=_MAX_FIELD_LEN):
    """Cap a string value to max_len characters."""
    s = str(value)
    return s[:max_len] if len(s) > max_len else s


# ---------------------------------------------------------------------------
# Event logging
# ---------------------------------------------------------------------------
def log_event(event_type, token=None, email=None, **kwargs):
    """
    Record an audit event. Best-effort: never raises, never blocks callers.

    Args:
        event_type: one of VALID_EVENTS
        token: raw CV token (will be HMAC-hashed before storage)
        email: raw email address (will be HMAC-hashed before storage)
        **kwargs: additional fields — must be in ALLOWED_KWARGS
    """
    try:
        if not _redis or event_type not in VALID_EVENTS:
            return

        token_hash = _hmac_hash(token) if token else None
        if not token_hash:
            return  # Cannot store without a token identifier

        # Millisecond-precision timestamp for deterministic ordering in bursts
        now = datetime.now(timezone.utc)
        ts_ms = now.timestamp()

        event = {
            "id": str(uuid.uuid4()),
            "event": event_type,
            "ts": now.isoformat(),
            "ts_ms": ts_ms,
        }

        # Add HMAC-hashed email if present
        email_hash = _hmac_hash(email) if email else None
        if email_hash:
            event["email_hash"] = email_hash

        # Add allowed kwargs with field-length caps
        for key, value in kwargs.items():
            if key in ALLOWED_KWARGS and value is not None:
                event[key] = _cap(value)

        # Store as sorted set member (score = ms timestamp for ordering)
        audit_key = f"{AUDIT_PREFIX}{token_hash}"
        _redis.zadd(audit_key, {json.dumps(event, separators=(',', ':')): ts_ms})
        _redis.expire(audit_key, AUDIT_TTL)

        # Create reverse indexes for support lookup
        _create_indexes(token_hash, kwargs)

    except Exception:
        pass  # Best-effort: audit failures MUST NOT break business flows


def _create_indexes(token_hash, kwargs):
    """Create reverse lookup indexes. Best-effort, no exceptions propagated."""
    try:
        # Index by Stripe session_id
        session_id = kwargs.get("session_id")
        if session_id:
            _redis.set(f"{AUDIT_IDX_PREFIX}session:{session_id}",
                       token_hash, ex=AUDIT_TTL, nx=True)

        # Index by Paystack reference
        reference = kwargs.get("reference")
        if reference:
            _redis.set(f"{AUDIT_IDX_PREFIX}paystack_ref:{reference}",
                       token_hash, ex=AUDIT_TTL, nx=True)

        # Index by Stripe payment_intent_id
        pi_id = kwargs.get("payment_intent_id")
        if pi_id:
            _redis.set(f"{AUDIT_IDX_PREFIX}pi:{pi_id}",
                       token_hash, ex=AUDIT_TTL, nx=True)

        # Index by Resend message_id
        resend_id = kwargs.get("resend_message_id")
        if resend_id:
            _redis.set(f"{AUDIT_IDX_PREFIX}resend:{resend_id}",
                       token_hash, ex=AUDIT_TTL, nx=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------
def lookup_by_id(identifier_type, identifier_value):
    """
    Look up audit trail by a provider identifier.

    Args:
        identifier_type: "session" | "paystack_ref" | "pi" | "resend"
        identifier_value: the provider-specific ID

    Returns:
        dict with token_hash and events list, or None if not found
    """
    try:
        if not _redis or not identifier_value:
            return None

        valid_types = {"session", "paystack_ref", "pi", "resend"}
        if identifier_type not in valid_types:
            return None

        idx_key = f"{AUDIT_IDX_PREFIX}{identifier_type}:{identifier_value}"
        token_hash = _redis.get(idx_key)
        if not token_hash:
            return None

        return lookup_by_token_hash(token_hash)
    except Exception:
        return None


def lookup_by_token_hash(token_hash):
    """
    Return all audit events for a given token_hash, chronologically ordered.

    Returns:
        dict with token_hash and events, or None
    """
    try:
        if not _redis or not token_hash:
            return None

        audit_key = f"{AUDIT_PREFIX}{token_hash}"
        raw_events = _redis.zrangebyscore(audit_key, "-inf", "+inf")
        if not raw_events:
            return None

        events = []
        for raw in raw_events:
            try:
                events.append(json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                continue

        return {
            "token_hash": token_hash,
            "event_count": len(events),
            "events": events,
        }
    except Exception:
        return None


def lookup_by_raw_token(token):
    """Look up audit trail using a raw CV token (hashes it first)."""
    token_hash = _hmac_hash(token)
    if not token_hash:
        return None
    return lookup_by_token_hash(token_hash)
