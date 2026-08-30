"""
Weekly hiring-signal reader.

Serves the "what recruiters are actually asking for" block on role pages from
a JSON artifact refreshed weekly by scripts/refresh_hiring_signal.py.

Three rules shape this module:

1. No network. The artifact is written by the weekly job and committed to the
   repo, so serving it is a local file read. Nothing here can add latency to a
   page load or fail because a third-party API is down.

2. Fail soft, always. A missing, corrupt, or stale artifact returns None and
   the page simply renders without the block. This data is a nice-to-have; it
   must never be able to break a role page.

3. Never touches scoring. match_score is derived from the user's actual job
   description. Recruiter chatter is noisy and gameable, so it is presented
   alongside the score as context and is deliberately not importable into the
   scoring path.
"""

import json
import os
from datetime import datetime, timezone

_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "hiring_signal.json",
)

# If the weekly job has not run for this long, stop rendering the block.
# Copy on the page says "this week"; showing month-old chatter under that
# heading is worse than showing nothing, so staleness fails closed.
MAX_SIGNAL_AGE_DAYS = 14

# Cache the parsed artifact, invalidated by file mtime so a redeploy or a
# local edit is picked up without a manual restart.
_cache = {"mtime": None, "payload": None}


def _load():
    """Read and cache the artifact. Returns dict or None. Never raises."""
    try:
        mtime = os.path.getmtime(_DATA_PATH)
    except OSError:
        return None  # not generated yet — expected before the first run

    if _cache["mtime"] == mtime:
        return _cache["payload"]

    try:
        with open(_DATA_PATH, encoding="utf-8") as fh:
            payload = json.load(fh)
        if not isinstance(payload, dict) or "roles" not in payload:
            return None
    except (ValueError, OSError):
        return None

    _cache["mtime"] = mtime
    _cache["payload"] = payload
    return payload


def _age_days(payload):
    """Days since the artifact was generated, or None if unparseable."""
    raw = (payload or {}).get("generated_at", "")
    try:
        generated = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - generated).days


def get_signal(role_slug):
    """
    Return this week's hiring signal for a role, or None.

    None means "render nothing" and covers every failure mode: artifact
    missing, malformed, stale, or simply no data for this role.

    Shape:
        {
            "week_of": "2026-08-24",
            "age_days": 2,
            "rising":  [{"skill": "dbt", "mentions": 42}, ...],
            "cooling": [{"skill": "tableau", "mentions": 3}, ...],
        }
    """
    payload = _load()
    if not payload:
        return None

    age = _age_days(payload)
    if age is None or age > MAX_SIGNAL_AGE_DAYS or age < 0:
        return None

    role = (payload.get("roles") or {}).get(role_slug)
    if not isinstance(role, dict):
        return None

    rising = [r for r in (role.get("rising") or []) if isinstance(r, dict) and r.get("skill")]
    cooling = [r for r in (role.get("cooling") or []) if isinstance(r, dict) and r.get("skill")]
    if not rising and not cooling:
        return None

    return {
        "week_of": payload.get("week_of", ""),
        "age_days": age,
        "rising": rising[:8],
        "cooling": cooling[:4],
    }


def get_meta():
    """Artifact-level metadata for ops/debugging. Returns dict or None."""
    payload = _load()
    if not payload:
        return None
    return {
        "generated_at": payload.get("generated_at", ""),
        "week_of": payload.get("week_of", ""),
        "source": payload.get("source", ""),
        "age_days": _age_days(payload),
        "role_count": len(payload.get("roles") or {}),
    }
