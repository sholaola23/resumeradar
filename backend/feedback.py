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

# Links and emails are found one whitespace-separated word at a time, in a
# single pass over each word, so the work grows in step with the length.
#
# A word holding "@", "://" or starting "www." is removed whole. Otherwise any
# run like "janedoe.dev", "Jane.Me", "janedoe.рф", "janedoe.भारत" or
# "linkedin.com/in/x" is a domain: dot-separated parts whose last part is 2 to
# 24 letters in any script (combining vowel signs included) or a punycode
# "xn--" part. There are over a thousand top-level domains, so no list is
# kept. Known tech names are the only exception. Over-removing a missing space
# ("useful.Thanks") is harmless; keeping a personal site is not. Underscores
# count as breaks ("_janedoe.dev_").
# Tech names and degree abbreviations that look like domains.
_TECH_NAMES = frozenset({"asp.net", "vb.net", "ado.net", "socket.io",
                         "b.sc", "m.sc", "b.eng", "m.eng", "b.tech", "m.tech", "m.phil", "b.ed"})
# Full stops that NFKC leaves alone: ideographic and halfwidth ideographic.
_DOTS = str.maketrans({"\u3002": ".", "\uff61": "."})
# Nine or more digits, so dates (2026-11-19) and scores are left alone.
_PHONE = re.compile(r"\+?\(?\d(?:[\s().-]{0,2}\d){8,}")
_REMOVED = "[removed]"

_redis = None


def init(redis_client):
    """Initialise with the app's Redis client."""
    global _redis
    _redis = redis_client


def _is_letter(ch):
    """A letter, digit or combining mark in any script (not "_")."""
    return ch.isalnum() or unicodedata.category(ch)[0] == "M"


def _is_domain(run):
    domain = run.strip(".-")
    parts = domain.split(".")
    if len(parts) < 2 or not all(parts):
        return False
    top = parts[-1]
    is_punycode = top.lower().startswith("xn--")
    if not is_punycode and not (2 <= len(top) <= 24 and not any(ch.isdigit() or ch == "-" for ch in top)):
        return False  # 3.11, v2.0, e.g
    return not (top.lower() == "js" or domain.lower() in _TECH_NAMES)  # Node.js, ASP.NET


def _clean_word(word):
    if "@" in word or "://" in word or word.lower().startswith("www."):
        return _REMOVED
    # Runs of letters, digits, marks, "." and "-". The first run that is a
    # domain removes it and the rest of the word, so a path
    # (linkedin.com/in/jane) or a tail (janedoe.dev_thanks) goes too. Closing
    # punctuation at the end of the word is kept.
    start = None
    for i in range(len(word) + 1):
        inside = i < len(word) and (word[i] in ".-" or _is_letter(word[i]))
        if inside and start is None:
            start = i
        elif not inside and start is not None:
            run = word[start:i]
            if _is_domain(run):
                lead = len(run) - len(run.lstrip(".-"))
                end = len(word)
                while end > i and not _is_letter(word[end - 1]) and word[end - 1] not in "/_":
                    end -= 1
                return word[:start + lead] + _REMOVED + word[end:]
            start = None
    return word


def clean_comment(text):
    """Return a storable comment: one line, contact details removed, capped."""
    if not isinstance(text, str):
        return ""
    # Fold look-alikes (full-width "ｃｏｍ", "＠", "jane。dev") into plain
    # characters first. NFKC can lengthen text ("㏂" becomes "a.m."), so the
    # cap is applied on both sides of it.
    cap = MAX_COMMENT_CHARS * 4
    text = unicodedata.normalize("NFKC", text[:cap])[:cap].translate(_DOTS)
    text = "".join(ch if ch.isprintable() else " " for ch in text)
    text = " ".join(_clean_word(word) for word in text.split())
    text = _PHONE.sub(_REMOVED, text)
    return text[:MAX_COMMENT_CHARS].strip()


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
