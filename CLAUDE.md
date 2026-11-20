# ResumeRadar

A free CV checker, live at https://resumeradar.sholastechnotes.com. A job seeker uploads or pastes a CV and pastes a job description. They get a keyword match estimate, matched and missing keywords, AI suggestions, and free cover-letter, bullet and summary tools. It is Shola's personal project.

Process (review levels, reviews, merging, feature map) follows shola-project-run-rules. This file adds only what is specific to this repo. If anything here conflicts with that skill, the skill wins: flag the line and fix it in a small PR.

## Stack

- Python 3.11 (`runtime.txt`), Flask, gunicorn (`Procfile`, `render.yaml`). Vanilla HTML, CSS and JS. Use pip and a venv, not bun or npm.
- Redis for rate limits, the AI budget, the AI cache and funnel counts. Without `REDIS_URL` the app falls back to in-memory counters.
- Anthropic Claude for suggestions (`backend/ai_analyzer.py`), Resend for emailed reports, Beehiiv for newsletter sign-ups. fpdf2 for the report PDF.
- Env var names are in `.env.example`. Never put values in code, commits or chat.

## Set up, test, run

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

.venv/bin/python tests/qa_suite.py          # expect "STATUS: ALL CLEAR"
.venv/bin/python -m unittest tests.test_funnel_metrics tests.test_keyword_quality \
  tests.test_product_integration tests.test_repeat_downloads \
  tests.test_builder_disabled tests.test_referral   # expect "OK"
node --test tests/scan_utils.test.cjs        # expect "fail 0"

PORT=5011 FLASK_ENV=production .venv/bin/python app.py
```

After a local run, scan a sample CV on `/` and check `/build` returns 404. Tests need no API keys and no Redis.

There is no CI test job. The only workflow is the Claude review (below), so run the commands above yourself and paste the last lines as proof.

## Structure

- `app.py`: every route (scan, AI tools, report download and email, subscribe, health, scan count, role landing pages, sitemap, admin, and the switched-off builder and payment routes).
- `backend/`: `resume_parser.py` (PDF, DOCX, text), `keyword_engine.py` (matching and the score), `ai_analyzer.py` (Claude calls), `ai_budget.py`, `ai_cache.py`, `ai_ratelimit.py`, `ai_metrics.py`, `report_generator.py` (PDF), `audit_log.py`, `funnel_metrics.py`, `role_content.py` (role pages). `cv_builder.py`, `cv_*_generator.py`, `bundle_credits.py`, `stripe_utils.py` and `paystack_utils.py` belong to the switched-off builder.
- `templates/`, `static/js/` (`app.js`, `scan-utils.js`, `share.js`), `static/css/style.css`, `static/llms.txt`.
- `tests/`: `qa_suite.py` plus the unittest and node files above.
- `.claude/skills/resumeradar-final-review/SKILL.md`: the review checklist. `.claude/settings.json` runs `qa_suite.py --quick` after edits to `app.py`, `index.html`, `app.js` or `style.css` on a local machine.

## Guards

**No payments.** The paid CV builder is off. `_cv_builder_disabled` in `app.py` returns 404 for `/build`, `/build/*`, every `/api/build/*` route and `builder.js` and `builder.css`, unless `CV_BUILDER_ENABLED=true`. Only `/api/build/webhook/resend` stays open, because scan-report emails use it. Never set that variable, never add Stripe or Paystack keys, and never re-enable a paid feature. Any paid feature is Shola's decision.

**CV privacy.** An uploaded file is deleted straight after parsing (`os.remove` in `scan_resume`). CV text goes only to Anthropic, to write the suggestions, and is not saved. AI results are cached in Redis for at most 1 hour (`_CACHE_TTL = 3600` in `backend/ai_cache.py`). Emails are kept only as HMAC hashes (`backend/audit_log.py`, 120-day TTL). Scan history lives in the browser's localStorage only. Never log CV text, never add a new place it is sent, and never lengthen what is kept. The privacy wording must match the code exactly, and any change to what it promises goes to Shola.

**AI spend.** Every Claude call goes through `backend/ai_budget.py` (daily cost and call caps, which fail closed) plus Flask-Limiter rate limits on each route and, for the free tools, the per-IP daily limits in `backend/ai_ratelimit.py` (cover letter 3, bullet 10, summary 5). `AI_DAILY_COST_LIMIT_USD` is 5.00 on Render. If it is unset the code falls back to 50.00, so never remove it from Render. Don't raise it, don't add a call that skips the budget or the limits, and don't change a model in `ai_analyzer.py` (`MODEL_FREE`, `MODEL_FREE_ECONOMY`, `MODEL_PAID`) without saying what it costs. A new model also needs its price in `_PRICING` in `ai_budget.py`, or it is costed at the default rate.

**Secrets.** No keys in the repo. Env var names only.

## Wording

- The score is a keyword match estimate against the job description. Never call it an employer's ATS score or a hiring prediction.
- Never promise interviews or jobs.
- AI prompts must tell the model not to invent experience, metrics or skills.
- UK spelling and "CV" in new text. "resume" stays where it is part of an existing page URL, title or the product name.
- Never name WorkCrew on the site, in emails or in docs.
- The public scan count (`/api/scan-count`) is also shown on sholaoladipupo.com. Don't change how it is counted or shown without Shola's OK.

## Hosting and deploys

- Render, web service `resumeradar` with Key Value `resumeradar-redis`. Production deploys from `master`, so merging to `master` is a production release. There is no Render CLI here; Render changes go through Shola.
- Live check: `/api/health` returns `{"ai_enabled":true,"status":"healthy"}`, and `/build` and `/api/build/create-checkout` return 404.
- `render.yaml` still lists the old Stripe and Paystack env var names. Leave them unset.

## Claude review

A comment starting `@claude-qa review` on a PR, from Shola's account (typed, or posted through the Claude GitHub app), runs `.github/workflows/resumeradar-claude-review.yml`. It calls the Claude API through `.github/scripts/claude_review.py` with read-only tools, against the checklist in `.claude/skills/resumeradar-final-review/SKILL.md` read from `master`, never from the PR. It signs in by workload identity federation, so no key is stored. It bills the "ResumeRadar GitHub reviews" workspace, which has a $30 monthly spend limit. Because the workflow and checklist are read from `master`, a change to either only takes effect after merge.

Grok (`@grok-qa review`) posts its verdict under Shola's account through the Cursor app. A review verdict normally arrives through the PR activity subscription within 1 to 2 minutes, but the subscription can miss those comments. So after each review request, also read the PR's issue comments, reviews and inline comments yourself 5 and 10 minutes later, then about every 10 minutes until it merges (schedule each check with send_later), and act on what you find. If Grok has not replied 10 minutes after the request, tell the coordinator.

## What failure looks like

- `qa_suite.py` prints FAIL lines and no "ALL CLEAR"; unittest prints `FAILED (failures=N)`; node prints `fail` above 0.
- `/build` or any `/api/build/*` route returns anything but 404: the builder guard is broken.
- `/api/health` shows `"ai_enabled": false`: `ANTHROPIC_API_KEY` is not set (the check only looks for the key, not whether it works), and scans fall back to rule-based suggestions.
- Users see "This tool is temporarily unavailable due to high demand": the daily AI budget or a per-IP limit is spent. That is the guard working, not a bug to fix by raising limits.
- A review comment says the review failed (sign-in, spend limit, timeout): report it to Shola, don't retry.
