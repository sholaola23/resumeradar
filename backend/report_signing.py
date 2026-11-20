"""
Signed scan results for the emailed and downloaded reports.

/api/scan signs the fields the PDF and the report email use. /api/email-report
and /api/download-report only build a report from data that carries a valid,
unexpired signature, so nobody can make the server send or render text it did
not produce itself.

Nothing is stored: the signature travels with the result in the visitor's
browser. The key is derived from FLASK_SECRET_KEY (AUDIT_HMAC_SECRET as a
fallback), so it is the same in every gunicorn worker.
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import time

# Every field generate_pdf_report() and the email body read. Keep this in step
# with backend/report_generator.py: an unsigned field never reaches a report.
SIGNED_FIELDS = (
    "match_score",
    "score_explanation",
    "total_matched",
    "total_missing",
    "total_job_keywords",
    "category_scores",
    "missing_keywords",
    "matched_keywords",
    "ai_suggestions",
    "ats_formatting",
)

SIGNATURE_FIELD = "report_signature"
MAX_AGE_SECONDS = 24 * 60 * 60
_VERSION = "v1"
_SIGNATURE_RE = re.compile(r"v1\.([1-9][0-9]{0,11})\.([0-9a-f]{64})", re.ASCII)

_process_key = None


def _key():
    global _process_key
    secret = os.getenv("FLASK_SECRET_KEY") or os.getenv("AUDIT_HMAC_SECRET")
    if not secret:
        # Local runs only. A per-process key breaks verification across
        # gunicorn workers, so production must set FLASK_SECRET_KEY.
        if _process_key is None:
            _process_key = secrets.token_bytes(32)
            print("WARNING: FLASK_SECRET_KEY is not set; report signatures only work in this process.")
        return _process_key
    # Separate key for this purpose, so a report signature can never be
    # mistaken for a Flask session cookie or an audit hash.
    return hmac.new(secret.encode("utf-8"), b"resumeradar-report-signing-v1", hashlib.sha256).digest()


def _normalise(value):
    """Make the payload survive a round trip through the browser's JSON.

    JavaScript has one number type, so 50.0 comes back as 50. Treat whole
    floats as ints on both sides so the bytes we sign match the bytes we check.
    """
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    if isinstance(value, dict):
        return {str(k): _normalise(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalise(v) for v in value]
    return value


def report_fields(scan_data):
    """The signed subset of a scan result, and nothing else."""
    return {field: scan_data.get(field) for field in SIGNED_FIELDS}


def _mac(issued_at, scan_data):
    payload = json.dumps(
        _normalise(report_fields(scan_data)),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    message = f"{_VERSION}.{issued_at}.{payload}".encode("utf-8")
    return hmac.new(_key(), message, hashlib.sha256).hexdigest()


def sign(scan_data, now=None):
    issued_at = int(now if now is not None else time.time())
    return f"{_VERSION}.{issued_at}.{_mac(issued_at, scan_data)}"


def verify(scan_data, now=None):
    """Return the signed report fields if the signature is valid, else None."""
    if not isinstance(scan_data, dict):
        return None
    signature = scan_data.get(SIGNATURE_FIELD)
    if not isinstance(signature, str):
        return None
    # Accept only the exact form sign() makes: ASCII digits with no leading
    # zero and a lowercase hex MAC. Otherwise "0123" or non-ASCII digits would
    # verify as new strings and each get a fresh send counter.
    match = _SIGNATURE_RE.fullmatch(signature)
    if not match:
        return None
    issued_at = int(match.group(1))
    current = int(now if now is not None else time.time())
    if issued_at > current + 300 or current - issued_at > MAX_AGE_SECONDS:
        return None
    try:
        expected = _mac(issued_at, scan_data)
    except (TypeError, ValueError):
        return None
    if not hmac.compare_digest(expected, match.group(2)):
        return None
    return report_fields(scan_data)


def signature_id(scan_data):
    """Short hash of the signature, for counting sends without storing it.

    Only call after verify(): it accepts one spelling per signature, so this
    key is the same for every request that replays it."""
    signature = str(scan_data.get(SIGNATURE_FIELD, ""))
    return hashlib.sha256(signature.encode("utf-8")).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Recipient confirmation
#
# A report is only emailed to an address whose owner clicked a confirm link.
# The link carries a signed token naming the scan (by signature_id) and the
# address (by email_id, a keyed hash), never the address itself, so nothing
# readable ends up in a URL or a log. Nothing is stored until the click.
# ---------------------------------------------------------------------------
CONFIRM_MAX_AGE_SECONDS = 60 * 60
_CONFIRM_VERSION = "c1"
_CONFIRM_RE = re.compile(r"c1\.([1-9][0-9]{0,11})\.([0-9a-f]{32})\.([0-9a-f]{32})\.([0-9a-f]{64})", re.ASCII)


def email_id(email):
    """Keyed hash of a normalised address. Cannot be turned back into it."""
    normalised = str(email or "").strip().lower()
    return hmac.new(_key(), b"email:" + normalised.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


_DOTLESS_DOMAINS = ("gmail.com", "googlemail.com")


def inbox_id(email):
    """Keyed hash of the inbox an address delivers to, for the per-address cap
    on confirmation emails. name+anything@ and, at Gmail, dots in the name all
    reach the same inbox, so they share one count."""
    normalised = str(email or "").strip().lower()
    local, _, domain = normalised.rpartition("@")
    local = local.split("+", 1)[0]
    if domain in _DOTLESS_DOMAINS:
        local = local.replace(".", "")
        domain = "gmail.com"
    return email_id(f"{local}@{domain}")


def _confirm_mac(issued_at, scan_id, address_id):
    message = f"{_CONFIRM_VERSION}.{issued_at}.{scan_id}.{address_id}".encode("ascii")
    return hmac.new(_key(), b"confirm:" + message, hashlib.sha256).hexdigest()


def confirm_token(scan_data, email, now=None):
    """Signed token for the confirm link. Call only after verify(scan_data)."""
    issued_at = int(now if now is not None else time.time())
    scan_id = signature_id(scan_data)
    address_id = email_id(email)
    mac = _confirm_mac(issued_at, scan_id, address_id)
    return f"{_CONFIRM_VERSION}.{issued_at}.{scan_id}.{address_id}.{mac}"


def verify_confirm_token(token, now=None):
    """Return (scan_id, address_id) for a valid, unexpired token, else None."""
    if not isinstance(token, str):
        return None
    match = _CONFIRM_RE.fullmatch(token)
    if not match:
        return None
    issued_at = int(match.group(1))
    current = int(now if now is not None else time.time())
    if issued_at > current + 300 or current - issued_at > CONFIRM_MAX_AGE_SECONDS:
        return None
    scan_id, address_id = match.group(2), match.group(3)
    if not hmac.compare_digest(_confirm_mac(issued_at, scan_id, address_id), match.group(4)):
        return None
    return scan_id, address_id
