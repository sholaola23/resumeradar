"""
"Was this useful?" comments for ResumeRadar.

The Yes/No votes are plain funnel counters (feedback_yes / feedback_no in
funnel_metrics). This module holds only the optional free-text comment.

What is stored, and nothing else: the comment text (cleaned, 500 characters at
most), the UTC date, whether the vote was Yes, and whether the visitor ticked
"may quote". No IP address, journey ID, scan ID, score, email or CV text is
stored with a comment, so a comment cannot be tied back to a person or a scan.

Redis key: resumeradar:feedback:{YYYY-MM-DD} (list of JSON strings)
TTL: 90 days, the same as the funnel counters.
"""

from datetime import datetime, timezone, timedelta
import json
import re
import unicodedata

_PREFIX = "resumeradar:feedback:"
_TTL = 90 * 86400
MAX_COMMENT_CHARS = 500
MAX_COMMENTS_PER_DAY = 200  # bounds Redis memory if someone floods the form

_EMAIL = re.compile(r"\S+@\S+")
# Links: any scheme (https, ftp, ...), www., or a domain followed by a path
# (linkedin.com/in/x).
_URL = re.compile(
    r"(?:\b[a-z][a-z0-9+.-]*://|\bwww\.)\S+"
    r"|\b(?:[a-z0-9-]+\.)+(?!js\b)[a-z]{2,}/\S*",
    re.IGNORECASE,
)
# Bare domains (janedoe.dev, JANEDOE.NET, Jane.Me). There are over a thousand
# top-level domains, so any word.letters token counts unless the whole token
# is a known tech name. Over-removing a missing space ("useful.Thanks") is
# harmless; keeping a personal site is not.
_BARE_DOMAIN = re.compile(r"\b(?:[a-z0-9-]+\.)+([a-z]{2,24})\b(?![\w-]|\.\w)", re.IGNORECASE)
_TECH_NAMES = frozenset({"asp.net", "vb.net", "ado.net", "socket.io"})
# Nine or more digits, so dates (2026-11-19) and scores are left alone.
_PHONE = re.compile(r"\+?\(?\d(?:[\s().-]{0,2}\d){8,}")
_REMOVED = "[removed]"

_redis = None


def init(redis_client):
    """Initialise with the app's Redis client."""
    global _redis
    _redis = redis_client


def _strip_bare_domain(match):
    token, last = match.group(0), match.group(1)
    if last.lower() == "js" or token.lower() in _TECH_NAMES:
        return token
    return _REMOVED


def clean_comment(text):
    """Return a storable comment: one line, contact details removed, capped."""
    if not isinstance(text, str):
        return ""
    text = text[:MAX_COMMENT_CHARS * 4]  # bound the work before the regexes run
    # Fold look-alikes (full-width "ｃｏｍ", "＠") into plain letters first.
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch if ch.isprintable() else " " for ch in text)
    text = _URL.sub(_REMOVED, text)
    text = _BARE_DOMAIN.sub(_strip_bare_domain, text)
    text = _EMAIL.sub(_REMOVED, text)
    text = _PHONE.sub(_REMOVED, text)
    return " ".join(text.split())[:MAX_COMMENT_CHARS].strip()


def save_comment(useful, comment, may_quote=False):
    """Store one comment. Returns True if stored. Never raises."""
    try:
        cleaned = clean_comment(comment)
        if not _redis or not cleaned:
            return False
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = _PREFIX + date_str
        if _redis.llen(key) >= MAX_COMMENTS_PER_DAY:
            return False
        entry = {
            "date": date_str,
            "useful": bool(useful),
            "comment": cleaned,
            # Permission to quote is only asked for after a Yes.
            "may_quote": bool(useful) and may_quote is True,
        }
        _redis.rpush(key, json.dumps(entry))
        _redis.expire(key, _TTL)
        return True
    except Exception:
        return False


def get_recent(days=30):
    """Return stored comments for the last N days, newest day first."""
    comments = []
    try:
        if not _redis:
            return comments
        today = datetime.now(timezone.utc).date()
        for i in range(max(1, min(int(days), 90))):
            key = _PREFIX + (today - timedelta(days=i)).isoformat()
            for raw in _redis.lrange(key, 0, -1):
                try:
                    if isinstance(raw, bytes):
                        raw = raw.decode()
                    comments.append(json.loads(raw))
                except (ValueError, UnicodeDecodeError):
                    continue
    except Exception:
        pass
    return comments
