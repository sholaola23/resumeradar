# ResumeRadar

**Make your experience clear for the job.**

ResumeRadar is a free ATS resume scanner with a paid AI CV builder. Upload your resume, paste a job description, and get your match score, missing keywords, and AI-powered fixes in ~30 seconds. When you're ready, a one-off £2 payment (₦ via Paystack in Nigeria) generates an ATS-optimized rewrite of your CV — no subscription, no weekly plan, no trap.

**Live at:** [resumeradar.sholastechnotes.com](https://resumeradar.sholastechnotes.com)

---

## Features

**Free scan**
- **Job-description match estimate** — custom weighted keyword coverage, with no score when fewer than three substantive terms are recognized; not an employer ranking or hiring prediction
- **Keyword analysis** — matched and missing keywords across 5 categories, with source-grounded required/preferred priorities and recognition of explicit tool alternatives (technical skills, soft skills, certifications, education, action verbs)
- **AI suggestions** — summary, strengths, improvements, quick wins, and cover-letter talking points powered by Claude
- **Sub-scores** — ATS formatting (0-100) and recruiter tips (0-100) with expandable checklists, including a bullet-quantification checker
- **Free AI micro-tools** — cover-letter generator (3/day), bullet enhancer (10/day), summary generator (5/day)
- **Reports** — copy, download, or email a branded multi-page PDF report
- **Scan history** — local-only history; trends compare the same job-description hash and scoring version (localStorage, never sent to the server)

**Paid CV builder (£2 one-off / bundle credits)**
- Upload your CV + target JD → AI extracts and polishes every section for ATS systems
- Strict anti-fabrication rules: no invented metrics, skills, jobs, or years-of-experience claims
- Full readable preview before payment; use Edit & Regenerate to change content
- 3 templates, paid PDF + DOCX export, email delivery
- Bundle packs with atomic credit tracking (Lua-scripted double-spend protection)

**Privacy-first**
- Resumes are parsed in real time and never stored; uploads are deleted immediately after parsing
- Emails stored only as HMAC hashes; audit log fields are allowlisted with a 120-day TTL

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, Flask, gunicorn |
| AI | Anthropic Claude — Sonnet 5 (`claude-sonnet-5`) on both gates, with tiered degradation to Haiku 4.5 → rule-based as the daily AI budget fills |
| NLP | Rule-based keyword extraction + AI analysis (hybrid) |
| Payments | Stripe (GBP) + Paystack (NGN), signature-verified webhooks with event dedup |
| Store | Redis (rate limits, AI budget, bundle credits, payment flags, funnel metrics) |
| PDF/DOCX | fpdf2, python-docx |
| Email | Resend (delivery webhooks verified via svix) |
| Newsletter | Beehiiv API v2 |
| Frontend | Vanilla HTML/CSS/JS |
| Hosting | Render (prod + staging), Cloudflare in front |

## How the AI layer stays affordable

Every Claude call runs through a cost-guard layer most side projects skip:

- **Daily budget** — cost + call caps that fail closed (`backend/ai_budget.py`); per-model pricing drives real cost estimates from actual token usage
- **Tiered degradation** — free scans run Sonnet 5 while the daily budget is under 60% spent, drop to Haiku 4.5 until the cap, then fall back to rule-based suggestions (zero AI spend past the cap)
- **Per-tool metrics + response caching + per-IP daily limits** with paid-bundle bypass

## Project Structure

```
.
├── app.py                        # Flask app & API routes (scan, builder, payments, webhooks, admin)
├── backend/
│   ├── resume_parser.py          # PDF/DOCX/text parsing
│   ├── keyword_engine.py         # Keyword extraction, matching & ATS checks
│   ├── ai_analyzer.py            # Claude integration: scan suggestions + micro-tools
│   ├── ai_budget.py              # Daily cost/call caps, tiered-degradation signal
│   ├── ai_cache.py               # Response caching
│   ├── ai_metrics.py             # Per-tool call metrics
│   ├── ai_ratelimit.py           # Per-IP daily tool limits
│   ├── cv_builder.py             # Paid CV polish (Claude)
│   ├── cv_pdf_generator.py       # CV PDF rendering (fpdf2)
│   ├── cv_docx_generator.py      # CV DOCX rendering
│   ├── report_generator.py       # Scan report PDF
│   ├── bundle_credits.py         # Atomic bundle credits (Lua CAS, HMAC tokens)
│   ├── stripe_utils.py           # Stripe checkout + webhook verification
│   ├── paystack_utils.py         # Paystack checkout + HMAC webhook verification
│   ├── audit_log.py              # HMAC-hashed audit trail (120-day TTL)
│   └── funnel_metrics.py         # Conversion funnel counters
├── templates/                    # index.html (scan), build.html (CV builder), 404.html
├── static/                       # css/, js/ (app.js, builder.js), robots.txt
├── tests/qa_suite.py             # 460+ checks incl. multi-threaded double-spend race tests
├── render.yaml / Procfile        # Render deployment (gunicorn, 3 workers × 4 threads)
└── requirements.txt
```

## API Overview

| Area | Endpoints |
|------|-----------|
| Scan (free) | `POST /api/scan` · `POST /api/download-report` · `POST /api/email-report` |
| Free AI tools | `POST /api/generate/cover-letter` · `POST /api/tools/enhance-bullet` · `POST /api/tools/generate-summary` |
| CV builder | `POST /api/build/generate` · `/generate-from-scan` · `/generate-from-upload` · `GET|POST /api/build/download/<token>` |
| Payments | `POST /api/build/create-checkout` · `/create-bundle-checkout` · webhooks for Stripe, Paystack, Resend |
| Bundles | `POST /api/build/bundle-use` · `/bundle-status` · `/bundle-exchange` · `/bundle-recover` · `/bundle-activate-from-payment` |
| Misc | `GET /api/health` · `GET /api/scan-count` · `POST /api/subscribe` · SEO routes (`/sitemap.xml`, `/robots.txt`, `/ats-resume-checker/<role>`) |

All state-changing endpoints are rate-limited (flask-limiter on Redis, with in-memory fallback); webhooks verify signatures before any side effect and dedup on event id.

## Product analytics

The existing authenticated `/api/admin/funnel` endpoint supports `?days=90` and
`?journey_id=<UUID>`. Daily counters and anonymous journey event timestamps are
retained for 90 days after activity. Journey IDs are random per browser session;
no CV text, job description, email, or IP is stored in these records. Purchase
and successful-export events remain server-originated. Client events indicate
attempts and visible screens, not payment proof. Repeat visits are a local-device
signal and cannot identify users across devices. Old seven-day records cannot
be backfilled; the longer window accumulates after deployment.

## Getting Started

```bash
git clone https://github.com/sholaola23/resumeradar.git
cd resumeradar
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your keys
python app.py          # http://localhost:5001
```

### Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `ANTHROPIC_API_KEY` | Yes | Claude API (AI suggestions + CV builder) |
| `REDIS_URL` | Prod | Rate limits, budget, credits, payment flags |
| `STRIPE_SECRET_KEY` / `STRIPE_PRICE_ID` / `STRIPE_WEBHOOK_SECRET` | For payments | Stripe checkout + webhook verification |
| `PAYSTACK_SECRET_KEY` | Optional | Paystack (NGN) payments |
| `RESEND_API_KEY` / `RESEND_WEBHOOK_SECRET` | Optional | Email delivery + delivery webhooks |
| `BEEHIIV_API_KEY` / `BEEHIIV_PUBLICATION_ID` | Optional | Newsletter subscription |
| `AUDIT_HMAC_SECRET` / `AUDIT_ADMIN_TOKEN` | Optional | Privacy-preserving audit log + admin lookup |
| `PUBLIC_BASE_URL` | Prod | Absolute URLs in emails/redirects |
| `AI_DAILY_COST_LIMIT_USD` / `AI_DAILY_CALL_LIMIT` | Optional | AI budget caps (default $50 / 5000 calls) |
| `FLASK_SECRET_KEY` / `FLASK_ENV` | Optional | Flask session key / `production` |

### Testing

```bash
python tests/qa_suite.py --quick   # ~2s: routes, structure, security, race tests
python tests/qa_suite.py           # full: includes live AI + PDF checks
```

## Built By

**[Olushola Oladipupo](https://www.linkedin.com/in/olushola-oladipupo/)** — AWS Solutions Architect

Helping people break into tech and cloud, one resume at a time.

## Licence

MIT — see [LICENCE](LICENCE).
