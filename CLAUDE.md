# ResumeRadar

A free CV checker, live at https://resumeradar.sholastechnotes.com. A job seeker uploads or pastes a CV and pastes a job description. They get a keyword match estimate, matched and missing keywords, AI suggestions, and free cover-letter, bullet and summary tools. It is Shola's personal project.

Process (review levels, reviews, merging, feature map) follows shola-project-run-rules. This file adds only what is specific to this repo. If anything here conflicts with that skill, the skill wins: flag the line and fix it in a small PR.

## Stack

- Python 3.11 (`runtime.txt`), Flask, gunicorn (`Procfile`, `render.yaml`). Vanilla HTML, CSS and JS. Use pip and a venv, not bun or npm.
- Redis for rate limits, the AI budget, the AI cache and funnel counts. Without `REDIS_URL`, Flask-Limiter and the scan count fall back to memory, the AI budget and the per-IP daily limits let every call through, and emailed reports are refused (they fail closed), so production must always have Redis.
- Anthropic Claude for suggestions (`backend/ai_analyzer.py`), Resend for emailed reports, Beehiiv for newsletter sign-ups. fpdf2 for the report PDF.
- Env var names are in `.env.example`. Never put values in code, commits or chat.

## Set up, test, run

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

.venv/bin/python tests/qa_suite.py          # expect "STATUS: ALL CLEAR"
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'   # expect "OK"
node --test tests/scan_utils.test.cjs        # expect "fail 0"
cd tests/user-check && bun install && bun run typecheck && bun x playwright test   # user check, expect "N passed"

PORT=5011 FLASK_ENV=production .venv/bin/python app.py
```

After a local run, scan a sample CV on `/` and check `/build` returns 404. The user check does this and more: the `resumeradar-verify` skill says how to run it, and `docs/feature-map.md` lists every flow and the test that covers it. Its launcher, `tests/user-check/serve.py`, fakes Claude, Resend and Beehiiv, runs a private Redis and refuses any connection off the machine; production never imports it. Tests need no API keys and no Redis service, but `tests/test_repeat_downloads.py` starts its own `redis-server`, so the binary must be installed.

CI (`.github/workflows/ci.yml`) runs on every PR and every push to `master`: a gitleaks secret scan over the commit's history (confirmed-dead findings go in `.gitleaksignore`, each with how it was confirmed), the first three test commands above, and the user check (Playwright at 375px and 1280px with axe), all with no keys.

## Structure

- `app.py`: every route (scan, AI tools, report download and email, subscribe, health, scan count, `/api/feedback`, `/privacy`, `/share`, role landing pages, sitemap, admin, and the switched-off builder and payment routes). `_client_ip` and `_visitor_key` decide who a Flask-Limiter rate limit counts: `CF-Connecting-IP` only when the request came from Cloudflare, and IPv6 by its /64.
- `backend/`: `resume_parser.py` (PDF, DOCX, text), `keyword_engine.py` (matching and the score), `ai_analyzer.py` (Claude calls), `ai_budget.py`, `ai_cache.py`, `ai_ratelimit.py`, `ai_metrics.py`, `report_generator.py` (PDF), `audit_log.py`, `funnel_metrics.py`, `role_content.py` (role pages), `site_copy.py` (the strapline and privacy line shared by the site, email and PDF), `log_safe.py` (error text that is safe to log), `feedback.py` (the optional "Was this useful?" comment), `report_signing.py` (signs scan results so reports can only be built from them). `cv_builder.py`, `cv_*_generator.py`, `bundle_credits.py`, `stripe_utils.py` and `paystack_utils.py` belong to the switched-off builder.
- `templates/` (`privacy.html` is the privacy page), `static/js/` (`app.js`, `scan-utils.js`, `share.js`, `feedback.js`), `static/css/style.css`, `static/llms.txt`.
- `tests/`: `qa_suite.py`, the `test_*.py` unittest files, `scan_utils.test.cjs` and `user-check/` (the Playwright user check, run with bun).
- `.github/workflows/`: `ci.yml` (secret scan and tests) and `resumeradar-claude-review.yml` (below).
- `.claude/skills/resumeradar-final-review/SKILL.md`: the review checklist. `.claude/skills/resumeradar-verify/SKILL.md`: the smoke test to run before handing over a commit. `.claude/settings.json` runs `qa_suite.py --quick` after edits to `app.py`, `index.html`, `app.js` or `style.css` on a local machine.

## Guards

**No payments.** The paid CV builder is off. `_cv_builder_disabled` in `app.py` returns 404 for `/build`, `/build/*`, every `/api/build/*` route and `builder.js` and `builder.css`, unless `CV_BUILDER_ENABLED=true`. Only `/api/build/webhook/resend` stays open, because scan-report emails use it. Never set that variable, never add Stripe or Paystack keys, and never re-enable a paid feature. Any paid feature is Shola's decision.

**CV privacy.** An uploaded file is deleted straight after parsing (`os.remove` in `scan_resume`). CV text goes only to Anthropic, to write the suggestions and cover letters, and is not saved. AI suggestions and tool results are cached in Redis for at most 1 hour (`_CACHE_TTL = 3600` in `backend/ai_cache.py`). Logs on the scan, email, PDF and AI paths hold only the error type and status (`backend/log_safe.py`), never CV text or the AI reply. A feedback comment is stored with only its text (links, emails and phone numbers removed), the Yes or No, the may-quote tick and the date, nothing that ties it to a person or scan, for 90 days (`backend/feedback.py`); Yes and No on their own are only daily counts. Emails are kept only as HMAC hashes (`backend/audit_log.py`, 120-day TTL; the report confirmation keys, 24 hours). Scan history lives in the browser's localStorage only. Never log CV text or AI replies, never add a new place CV text is sent, and never lengthen what is kept. `PRIVACY_LINE` in `backend/site_copy.py` and `templates/privacy.html` must match the code exactly: change them in the same PR as the code, and any change to what they promise goes to Shola.

**Input size.** Uploads are capped at 5 MB (`MAX_CONTENT_LENGTH`), pasted job descriptions at 20,000 characters and CV text at 50,000 (`app.py`), and PDF parsing rejects files over 50 pages or 3 MB of page content and stops extracting after 100,000 characters or 3 seconds (`backend/resume_parser.py`). Don't loosen these: they stop one request tying up a worker.

**AI spend.** Every Claude call goes through `backend/ai_budget.py` (daily cost and call caps; they fail closed when Redis errors, and let calls through when no Redis is configured) plus Flask-Limiter rate limits on each route. The free tools also call the per-IP daily limits in `backend/ai_ratelimit.py` (cover letter 3, bullet 10, summary 5), but those are keyed on `request.remote_addr`, a rotating Cloudflare edge IP, so they have never fired in production. Switching them to `_client_ip()` is a staged rollout (see the comment in `app.py`); don't rely on them as a cost guard until then. `AI_DAILY_COST_LIMIT_USD` is 5.00 on Render. If it is unset the code falls back to 50.00, so never remove it from Render. Don't raise it, don't add a call that skips the budget or the limits, and don't change a model in `ai_analyzer.py` (`MODEL_FREE`, `MODEL_FREE_ECONOMY`, `MODEL_PAID`) without saying what it costs. A new model also needs its price in `_PRICING` in `ai_budget.py`, or it is costed at the default rate.

**Reports.** `/api/scan` signs the fields the PDF and the report email use, and `/api/email-report` and `/api/download-report` only build a report from a result with a valid signature less than 24 hours old (`backend/report_signing.py`). The first email to an address is only a confirm link (`/confirm-email`, a signed token that expires after an hour, confirmed by a button press so mail scanners that open links can't confirm). The open page polls `/api/email-report/status` and sends the report once confirmed. Each signed scan can be emailed at most 3 times (`_REPORT_SENDS_PER_SCAN`) and get 3 confirm emails, and one address gets at most 5 confirm emails a day (`app.py`). Every one of these caps fails closed: no Redis or a Redis error means no email. A new field in the report must be added to `SIGNED_FIELDS`, or it never reaches the report.

**Secrets.** No keys in the repo. Env var names only. Never remove `FLASK_SECRET_KEY` from Render: report signing keys off it (`backend/report_signing.py`), and without it (and without `AUDIT_HMAC_SECRET`) each gunicorn worker makes its own key, so a report download or email that lands on another worker fails with a 403.

## Wording

- The score is a keyword match estimate against the job description. Never call it an employer's ATS score or a hiring prediction.
- Never promise interviews or jobs.
- AI prompts must tell the model not to invent experience, metrics or skills.
- The strapline is "Make your experience clear." (`STRAPLINE` in `backend/site_copy.py`). Change it there, not in a template.
- UK spelling and "CV" in new text. "resume" stays where it is part of an existing page URL, title or the product name.
- Never name any company as the site's owner or operator on the site, in emails or in docs. It is Shola's personal project.
- The public scan count (`/api/scan-count`) is also shown on sholaoladipupo.com. Don't change how it is counted or shown without Shola's OK.

## Hosting and deploys

- Render, web service `resumeradar` with Key Value `resumeradar-redis`. Production deploys from `master`, so merging to `master` is a production release. There is no Render CLI here; Render changes go through Shola.
- Live check: `/api/health` returns `{"ai_enabled":true,"status":"healthy"}`, and `/build` and `/api/build/create-checkout` return 404.
- `render.yaml` still lists the old Stripe and Paystack env var names. Leave them unset.

## Claude review

A comment starting `@claude-qa review` on a PR, from Shola's account (typed, or posted through the Claude GitHub app), runs `.github/workflows/resumeradar-claude-review.yml`. It calls the Claude API through `.github/scripts/claude_review.py` with read-only tools, against the checklist in `.claude/skills/resumeradar-final-review/SKILL.md` read from `master`, never from the PR. It signs in by workload identity federation, so no key is stored. It bills the "ResumeRadar GitHub reviews" workspace, which has a $60 monthly spend limit. Because the workflow and checklist are read from `master`, a change to either only takes effect after merge.

Grok (`@grok-qa review`) posts its verdict from a separate bot account through the Cursor app, not as `github-actions[bot]`. A review verdict normally arrives through the PR activity subscription within 1 to 2 minutes, but the subscription can miss those comments. So after each review request, also read the PR's issue comments, reviews and inline comments yourself 5 and 10 minutes later, then about every 10 minutes until it merges (schedule each check with send_later), and act on what you find. If Grok has not replied 10 minutes after the request, tell the coordinator. This check is stricter than the run rules and adds to them; when to ask for a review, how many to ask for, and what to do with each verdict follow "Claude review" and "Grok final review" in shola-project-run-rules.

## What failure looks like

- The CI "Secret scan (gitleaks)" job fails: a secret is in the commit's history. Revoke it first; never add it to `.gitleaksignore` until it is confirmed dead.
- `qa_suite.py` prints FAIL lines and no "ALL CLEAR"; unittest prints `FAILED (failures=N)`; node prints `fail` above 0.
- `/build` or any `/api/build/*` route other than `/api/build/webhook/resend` returns anything but 404: the builder guard is broken.
- `/api/health` shows `"ai_enabled": false`: `ANTHROPIC_API_KEY` is not set (the check only looks for the key, not whether it works), and scans fall back to rule-based suggestions.
- Users see "This tool is temporarily unavailable due to high demand" (`BUDGET_EXCEEDED_MESSAGE` in `backend/ai_budget.py`): the daily AI budget is spent. A 429 with "Daily limit reached (N per day). Try again tomorrow." means a per-IP tool limit is spent (rare until the staged rollout above). Both are the guards working, not bugs to fix by raising limits.
- A review comment says the review failed (sign-in, spend limit, timeout). What to do next follows "Claude review" in shola-project-run-rules.
