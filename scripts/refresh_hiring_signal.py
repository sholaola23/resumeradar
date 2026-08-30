#!/usr/bin/env python3
"""
Weekly refresh of data/hiring_signal.json.

Asks Grok what recruiters and hiring managers are naming for each role on X
over the last 7 days, normalises the answer onto the keyword_engine
vocabulary, and writes the artifact the web app reads.

Run weekly, then open a PR with the diff. The PR is the quality gate: this is
AI-derived claims about the job market on public pages, so a human reads the
diff before it ships. It is a small diff by design.

Usage:
    python3 scripts/refresh_hiring_signal.py            # write the artifact
    python3 scripts/refresh_hiring_signal.py --dry-run  # print, write nothing
    python3 scripts/refresh_hiring_signal.py --role data-analyst

Env:
    XAI_API_KEY   required unless --dry-run --mock
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.keyword_engine import TECHNICAL_SKILLS, SOFT_SKILLS, CERTIFICATIONS
from backend.role_content import ROLE_CONTENT

OUT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "hiring_signal.json",
)

# A skill must be named by at least this many distinct posts to appear. Below
# this it is one person's opinion, not a signal.
MIN_MENTIONS = 5
MAX_RISING_PER_ROLE = 8
MAX_COOLING_PER_ROLE = 4

# Canonical vocabulary. Grok returns free text; the site only speaks these.
_VOCAB = set(TECHNICAL_SKILLS) | set(SOFT_SKILLS) | set(CERTIFICATIONS)

# Common shorthand that will not string-match the canonical term. Extend as
# the weekly diffs reveal gaps — every miss here shows up as a dropped skill.
_ALIASES = {
    "k8s": "kubernetes",
    "tf": "terraform",
    "gh actions": "github actions",
    "github action": "github actions",
    "postgres": "postgresql",
    "psql": "postgresql",
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "ml": "machine learning",
    "llms": "llm",
    "nlp": "natural language processing",
    "ci/cd": "ci/cd",
    "cicd": "ci/cd",
    "power bi": "powerbi",
    "aws cloud": "aws",
    "gcp cloud": "gcp",
}

# Drop any alias whose target is not in the vocabulary. Without this an alias
# can silently point at a term that does not exist (e.g. "power bi" ->
# "powerbi", which keyword_engine has never had), and the skill is discarded
# with no sign of why. UNMAPPED_ALIAS_TARGETS is the actionable list: each
# entry is a skill recruiters name that the scanner cannot yet match.
UNMAPPED_ALIAS_TARGETS = sorted({v for v in _ALIASES.values() if v not in _VOCAB})
_ALIASES = {k: v for k, v in _ALIASES.items() if v in _VOCAB}


def normalise(raw):
    """
    Map a free-text skill to the canonical vocabulary, or None to drop it.

    Dropping is the right default. An unmapped term cannot merge with the
    scanner's keyword matching, so surfacing it would show users advice the
    product cannot then act on.
    """
    if not raw or not isinstance(raw, str):
        return None
    term = re.sub(r"\s+", " ", raw.strip().lower())
    term = term.strip(".,;:!?()[]\"'")
    if not term or len(term) > 40:
        return None
    term = _ALIASES.get(term, term)
    if term in _VOCAB:
        return term
    singular = term[:-1] if term.endswith("s") else term + "s"
    if singular in _VOCAB:
        return singular
    return None


PROMPT = """You are analysing live hiring conversation on X (Twitter).

Role: {title}

Look at posts from the last 7 days by recruiters, hiring managers, and people
running interview loops for this role. Ignore job-board reposts, engagement
bait, course adverts, and people advertising their own availability.

Report which concrete skills and tools they are actually naming as things they
want to see, and which ones they mention as no longer differentiating.

Rules:
- Concrete named skills and tools only. No soft generalities like "communication".
- A skill qualifies only if at least {min_mentions} distinct posts name it.
- "mentions" must be the real count of distinct posts you observed. Do not estimate.
- If you cannot find enough posts, return fewer items or empty lists. Do not pad.

Return JSON only, no prose:
{{
  "rising":  [{{"skill": "...", "mentions": 12, "evidence": "one short sentence"}}],
  "cooling": [{{"skill": "...", "mentions": 7,  "evidence": "one short sentence"}}]
}}"""


def call_grok(role_slug, title, api_key, model):
    """
    Ask Grok for this role's signal. Returns parsed dict, or None on failure.

    NOTE: verify the current xAI API surface before trusting this shape —
    specifically whether live X search is enabled for your key's tier and how
    it is requested. If live search is unavailable the whole feature is moot,
    so check that first.
    """
    import urllib.request
    import urllib.error

    body = {
        "model": model,
        "messages": [{"role": "user",
                      "content": PROMPT.format(title=title, min_mentions=MIN_MENTIONS)}],
        "temperature": 0,
        # Live X retrieval. Confirm this parameter against current xAI docs.
        "search_parameters": {"mode": "on", "sources": [{"type": "x"}],
                              "from_date": (datetime.now(timezone.utc) - timedelta(days=7)
                                            ).strftime("%Y-%m-%d")},
    }
    req = urllib.request.Request(
        "https://api.x.ai/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read())
        text = payload["choices"][0]["message"]["content"]
    except (urllib.error.HTTPError, urllib.error.URLError, KeyError, ValueError) as e:
        detail = ""
        if isinstance(e, urllib.error.HTTPError):
            try:
                detail = e.read().decode("utf-8", "replace")[:200]
            except Exception:
                pass
        print(f"  ! {role_slug}: API call failed ({type(e).__name__}) {detail}", file=sys.stderr)
        return None

    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        print(f"  ! {role_slug}: no JSON in response", file=sys.stderr)
        return None
    try:
        return json.loads(match.group(0))
    except ValueError:
        print(f"  ! {role_slug}: unparseable JSON", file=sys.stderr)
        return None


def clean(items, limit):
    """Normalise, threshold, dedupe and rank one list from the model."""
    out, seen = [], set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        skill = normalise(item.get("skill"))
        if not skill or skill in seen:
            continue
        try:
            mentions = int(item.get("mentions", 0))
        except (TypeError, ValueError):
            continue
        if mentions < MIN_MENTIONS:
            continue
        seen.add(skill)
        entry = {"skill": skill, "mentions": mentions}
        ev = item.get("evidence")
        if isinstance(ev, str) and ev.strip():
            entry["evidence"] = ev.strip()[:160]
        out.append(entry)
    out.sort(key=lambda r: r["mentions"], reverse=True)
    return out[:limit]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print, write nothing")
    ap.add_argument("--role", help="refresh a single role slug")
    ap.add_argument("--model", default=os.getenv("XAI_MODEL", "grok-4"))
    ap.add_argument("--mock", action="store_true",
                    help="skip the API, emit fixture data (for wiring tests)")
    args = ap.parse_args()

    api_key = os.getenv("XAI_API_KEY", "")
    if not api_key and not args.mock:
        print("XAI_API_KEY not set. Use --mock to test wiring without it.", file=sys.stderr)
        return 2

    if UNMAPPED_ALIAS_TARGETS:
        print(f"  note: aliases disabled, target not in keyword_engine vocab: "
              f"{', '.join(UNMAPPED_ALIAS_TARGETS)}", file=sys.stderr)

    slugs = [args.role] if args.role else list(ROLE_CONTENT.keys())
    now = datetime.now(timezone.utc)
    monday = now - timedelta(days=now.weekday())

    roles, failures = {}, []
    for slug in slugs:
        title = slug.replace("-", " ").title()
        print(f"  {slug} ...", flush=True)
        if args.mock:
            raw = {"rising": [{"skill": "kubernetes", "mentions": 12,
                               "evidence": "fixture"},
                              {"skill": "terraform", "mentions": 9, "evidence": "fixture"}],
                   "cooling": [{"skill": "jenkins", "mentions": 6, "evidence": "fixture"}]}
        else:
            raw = call_grok(slug, title, api_key, args.model)
        if raw is None:
            failures.append(slug)
            continue
        rising = clean(raw.get("rising"), MAX_RISING_PER_ROLE)
        cooling = clean(raw.get("cooling"), MAX_COOLING_PER_ROLE)
        if rising or cooling:
            roles[slug] = {"rising": rising, "cooling": cooling}
        print(f"      {len(rising)} rising, {len(cooling)} cooling")

    if failures:
        print(f"\n  failed: {', '.join(failures)}", file=sys.stderr)

    # Refuse to publish a mostly-empty artifact. A bad API day should leave
    # last week's data in place rather than blank every role page.
    if not args.role and len(roles) < len(slugs) / 2:
        print(f"\nABORT: only {len(roles)}/{len(slugs)} roles produced data. "
              f"Leaving the existing artifact untouched.", file=sys.stderr)
        return 1

    artifact = {
        "generated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "week_of": monday.strftime("%Y-%m-%d"),
        "source": "grok live x search",
        "min_mentions": MIN_MENTIONS,
        "roles": roles,
    }

    if args.role and os.path.exists(OUT_PATH):
        with open(OUT_PATH, encoding="utf-8") as fh:
            existing = json.load(fh)
        existing.setdefault("roles", {}).update(roles)
        existing["generated_at"] = artifact["generated_at"]
        existing["week_of"] = artifact["week_of"]
        artifact = existing

    if args.dry_run:
        print(json.dumps(artifact, indent=2)[:2000])
        return 0

    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(artifact, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"\nwrote {OUT_PATH} ({len(roles)} roles)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
