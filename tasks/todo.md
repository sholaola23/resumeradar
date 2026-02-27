# ResumeRadar — Implementation Progress

## Phase 1: Value Features (No New Paid Entitlements)

- [x] **1A. Testimonials** — 3 anonymous cards between hero and scanner (index.html + style.css)
- [x] **1B. Granular Scan Sub-Scores** — Formatting (0-100) + Recruiter Tips (0-100) bars with expandable checklists
  - `keyword_engine.py`: Enhanced `analyze_ats_formatting()`, added `calculate_recruiter_tips_score()`
  - `app.py`: New `recruiter_tips` field in scan response
  - `app.js`: `renderSubScoreBars()` with clickable expand/collapse
  - `style.css`: Sub-score detail CSS
- [x] **1C. Quantification Checker** — `check_bullet_quantification()` detects bullets without metrics, flagged in Recruiter Tips
- [x] **1D. Cover Letter Generator** — `POST /api/generate/cover-letter` (3/day rate limit)
  - `ai_analyzer.py`: `generate_cover_letter()` function
  - `index.html`: Button + editable output + copy/download
  - `app.js`: API call handler with loading/error states
  - `style.css`: Full cover letter output styling
- [x] **1E. AI Micro-Tools** — Bullet enhancer (10/day) + Summary generator (5/day)
  - `ai_analyzer.py`: `enhance_bullet_point()` + `generate_resume_summary()`
  - `app.py`: `/api/tools/enhance-bullet` + `/api/tools/generate-summary`
  - `build.html`: Collapsible tool sections on builder page
  - `builder.js`: Input/output UI with copy buttons
  - `builder.css`: Tool section styling
- [x] **1F. QA** — 17/17 checks pass. All new endpoints work, validation enforced, existing payment flow intact, server clean.

### Phase 1 Exit Gates
- [x] Existing single-payment flow unchanged (£2 Stripe + ₦3,500 Paystack)
- [x] New APIs rate-limited and abuse-tested
- [x] QA green — full suite 370/370, quick suite 364/364 (quick skips live scan + PDF)
- [x] Desktop browser smoke test — all UI elements verified
- [x] API smoke test — scan fields, cover letter, bullet enhancer, summary generator, rate limits
- [x] Mobile UI check — iPhone 375px (11/11 checks PASS)
- [x] Mobile UI check — Android 412px (11/11 checks PASS)
- [ ] Stability soak (24-72h) — deploy to staging, monitor for 5xx, payment regressions, traceback patterns

### Mobile CSS Fixes (applied during gate checks)
- `subscore-label`: `overflow-wrap: break-word; min-width: 0;` (flex child shrink safety)
- `@media 480px`: smaller font/gap for subscore items, flagged bullets, CL output, CL action buttons
- `@media 768px`: `overflow: hidden` on `.history-entry`, `max-width: 100%` on `.history-entry-detail`

---

## Pre-Phase 2: Staging Environment

- [x] Separate Render web service (`resumeradar-staging`, Starter, Frankfurt, srv-d6g7jvk50q8c73ckhnk0)
- [x] Separate Redis instance (`resumeradar-staging-redis`, Free, Valkey 8.1.4, red-d6g7va94tr6s73etbmf0)
- [x] Stripe test key on staging (`sk_test_...`)
- [x] ~~Paystack test key on staging~~ — Dropped (UK-based business, Paystack deferred)
- [x] `PUBLIC_BASE_URL` set to `https://resumeradar-staging.onrender.com`
- [x] `X-Robots-Tag: noindex, nofollow` on staging (via `STAGING=true`)
- [ ] Separate `AUDIT_*`, `BUNDLE_HMAC_SECRET`, webhook secrets (deferred — low risk for Phase 1 soak)

### Stability Soak — Started Feb 26, 2026 09:26 UTC

**Soak runbook:** staging deploy → 24-72h soak → Phase 2 greenlight

#### T=0 Probe Results (Feb 26, 09:30 UTC)

| Check | Result |
|-------|--------|
| `GET /api/health` | 200 `{"status":"healthy","ai_enabled":true}` (0.27s) |
| `GET /api/scan-count` | 200 `{"count":150,"velocity":0}` — Redis connected |
| `POST /api/scan` (validation) | 400 "Please provide a job description" |
| `POST /api/scan` (happy path) | 200, score 69.1%, 7426 bytes, all categories + recruiter_tips |
| `POST /api/generate/cover-letter` (validation) | 400 "Invalid request" |
| `POST /api/tools/enhance-bullet` (validation) | 400 "Invalid request" |
| `POST /api/tools/generate-summary` (validation) | 400 "Invalid request" |
| `POST /api/build/create-checkout` (fake token) | 400 "CV session expired" (Redis validated) |
| `GET /api/build/download/fake-token` | 400 (expected) |
| `X-Robots-Tag` header | `noindex, nofollow` confirmed |
| Startup logs | Clean — no tracebacks, no import errors |
| Redis connectivity | `Scan counter: Redis connected (persistent)` |
| Gunicorn workers | Started cleanly, no errors |

**Secrets isolation:**
- REDIS_URL: isolated (Render internal vs Upstash)
- STRIPE_SECRET_KEY: isolated (test vs live)
- PUBLIC_BASE_URL: isolated
- AUDIT_*/webhook secrets: shared (low risk, deferred)

#### T+24h Probe Results — Production (Feb 27, 20:48 UTC)

| Check | Result |
|-------|--------|
| `GET /api/health` | 200, healthy, AI enabled (0.33s) |
| `GET /api/scan-count` | 200, count:1874, velocity:1 — real organic traffic |
| `POST /api/scan` (happy path) | 200 (14.0s), match_score 77.5%, recruiter_tips present, 7934 bytes |
| `POST /api/scan` (validation) | 400 |
| `POST /api/generate/cover-letter` (validation) | 400 |
| `POST /api/tools/enhance-bullet` (validation) | 400 |
| `POST /api/tools/generate-summary` (validation) | 400 |
| `POST /api/build/create-checkout` (fake token) | 400 |
| `GET /api/build/download/fake-prod-t24h` | 400 |
| `X-Robots-Tag` on prod | Not present (correct — prod should be indexed) |
| Prod logs (1h) | Zero 5xx, zero tracebacks, real user scans visible |
| UptimeRobot | HEAD /api/health every ~5min, all 200 |
| Real user activity | Windows/Chrome user: page load → scan (19697 bytes) → subscribe |

**Prod URL:** `resumeradar.sholastechnotes.com` (custom domain, master branch, srv-d64cnlfgi27c73aumndg)

#### Soak Checkpoints

| Checkpoint | Timestamp (UTC) | Status |
|-----------|-----------------|--------|
| T=0 | Feb 26, 09:26 | PASS — all 13 probes clean |
| T+24h | Feb 27, 20:36 | PASS — staging clean + prod clean with real traffic |
| T+24h GO | Feb 27 | **Conditional GO** — Phase 2 impl on staging only, no prod deploy before T+48 |
| T+48h | Feb 28, 09:26 | Pending — final release go/no-go for master merge |
| T+72h | Mar 1, 09:26 | Optional — stronger confidence |

**Greenlight rule:** T+48h clean + representative traffic → proceed. Light traffic → wait T+72h.

#### Soak Exit Criteria
- [ ] 24-72h with no sustained 5xx increase
- [ ] No payment/download regression
- [ ] No recurring traceback pattern
- [ ] Cover letter rate limit boundary verified (3/day)
- [ ] Enhance-bullet rate limit boundary verified (10/day)
- [ ] Generate-summary rate limit boundary verified (5/day)

#### Phase 2 Prerequisites (close before starting)
- [x] ~~Paystack test key on staging~~ — **Dropped.** Business is UK-based; Paystack deferred. Bundle flag `PAYSTACK_BUNDLES_ENABLED=false` stays off.
- [ ] Separate staging `AUDIT_*` + webhook secrets (generate + configure)

---

## Phase 2: Bundle Monetization (Conditional GO — staging only, no prod before T+48)

- [x] **2A. Bundle checkout endpoints** (Stripe + Paystack) — **implemented on staging**
  - [x] 2A-1. `stripe_utils.py`: `create_bundle_checkout_session()`, `verify_bundle_payment()`
  - [x] 2A-2. `paystack_utils.py`: `create_paystack_bundle_transaction()` (behind `PAYSTACK_BUNDLES_ENABLED` flag, H4)
  - [x] 2A-3. `POST /api/build/create-bundle-checkout` — idempotency (H3), 409 on fingerprint mismatch
  - [x] 2A-4. `POST /api/build/bundle-activate-from-payment` — 24hr idempotent window
  - [x] 2A-5. `POST /api/build/bundle-recover` — non-enumerable (always returns `{sent: true}`)
  - [x] 2A-6. Stripe webhook: handles bundle + single CV, SETNX dedup, `_send_bundle_email()`
  - [x] 2A-7. Paystack webhook: handles bundle (behind flag) + single CV, SETNX dedup
- [x] **2B. Atomic Redis credit consumption** (Lua script) — **implemented on staging**
  - [x] 2B-1. `backend/bundle_credits.py` — Lua atomic decrement, bundle CRUD, HMAC helpers, exchange tokens, idempotency
  - [x] 2B-2. `POST /api/build/bundle-use` — atomic credit consumption with idempotency (H3), audit logging (H1), 409 on fingerprint mismatch
  - [x] 2B-3. `POST /api/build/bundle-status` — bundle status lookup, Cache-Control: no-store
  - [x] 2B-4. `POST /api/build/bundle-exchange` — single-use exchange token redemption (H8), UUID validation
  - [x] 2B-5. Cover letter bundle override (H6) — `bundle_token` in request body bypasses IP rate limit, falls back to free tier
  - [x] 2B-6. Audit events: `bundle_credit_used`, `bundle_exhausted` with `bundle_token_hash` (H1), `email_hash` (H9)
- [x] **2C. Email for bundle purchase + recovery** — **implemented on staging**
  - [x] 2C-1. `_send_bundle_email()` — exchange token link via Resend
  - [x] 2C-2. `POST /api/build/bundle-recover` — non-enumerable recovery
  - [x] 2C-3. Frontend: recovery form in `build.html` + handler in `builder.js`
  - [x] 2C-4. Frontend: auto-activation from `?activate={uuid}` URL param
  - [x] 2C-5. Frontend: post-payment bundle activation from `?bundle_payment=success`
- [x] **2D. Bundle status/expiry UX + localStorage** — **implemented on staging**
  - [x] 2D-1. Bundle credits banner (green, shows plan/remaining/expiry)
  - [x] 2D-2. 3-tier pricing cards (Job Hunt Pack + Unlimited Sprint)
  - [x] 2D-3. Bundle download via `bundle-use` → `cv_paid` flag → download endpoint
  - [x] 2D-4. Page load: localStorage check → status API → show/hide UI
  - [x] 2D-5. Download endpoint: `cv_paid` flag bypass for bundle users
  - [x] 2D-6. Bundle CSS: banner, tiers, recovery, mobile responsive
- [x] **2E. AI Cost Economics** (uncapped spend → revenue-aligned) — **implemented on staging**
  - [x] 2E-1. Usage policy: `backend/ai_ratelimit.py` — in-handler daily limits (3/day CL, 10/day bullet, 5/day summary per IP)
  - [x] 2E-2. Spend guardrail: `backend/ai_budget.py` — dual cap (cost-based primary via `AI_DAILY_COST_LIMIT_USD`, call-count fallback via `AI_DAILY_CALL_LIMIT`), user-safe fallback message
  - [x] 2E-3. Response caching: `backend/ai_cache.py` — SHA256(tool + normalized inputs), 1hr TTL, cache hit avoids Claude call
  - [x] 2E-4. Abuse controls: burst limiter (`@limiter.limit("10 per minute")`) + in-handler daily limits replace decorator daily limits (H7)
  - [x] 2E-5. Observability: `backend/ai_metrics.py` — per-tool Redis hashes: requests, claude_calls, cache_hits, rate_rejects, budget_rejects, errors (7-day TTL)
  - [x] 2E-bundle. Bundle override — valid bundle credit bypasses free IP cap (implemented in 2B)

  **2E Acceptance Criteria (locked — do not ship without all green):**
  - [x] AC-1: Free tier limits enforced — cover letter 3/day/IP, bullet 10/day/IP, summary 5/day/IP (in-handler via `ai_ratelimit.py`)
  - [x] AC-2: Bundle override — valid bundle credit bypasses free IP cap, decrements credit atomically (implemented in 2B-5)
  - [x] AC-3: Daily spend guardrail — global Claude budget threshold defined, hard block + user-safe fallback message when hit
  - [x] AC-4: Dedupe cache live — hash key = tool + normalized inputs, TTL=3600, cache hit avoids Claude call
  - [x] AC-5: Metrics/audit present — per-tool counters: requests, Claude calls, cache hits, rejects (rate/budget), errors
- [x] **2F. Audit events** — **implemented inline with 2A/2B**
  - [x] `bundle_created` — plan, provider, email_hash, bundle_token_hash (in webhooks + activate-from-payment)
  - [x] `bundle_credit_used` — type, remaining, bundle_token_hash (in bundle-use + cover letter override)
  - [x] `bundle_exhausted` — plan, bundle_token_hash (in bundle-use when both credits hit 0)
- [x] **2G. Dispute runbook + launch** — **implemented**

### Dispute Runbook

**Lookup a payment dispute by Stripe session_id:**
```
GET /api/admin/audit/lookup?type=session&id=cs_xxx
Authorization: Bearer <AUDIT_ADMIN_TOKEN>
```

**Lookup by Paystack reference:**
```
GET /api/admin/audit/lookup?type=paystack_ref&id=rr_cv_xxx
```

**Lookup by raw CV token:**
```
GET /api/admin/audit/lookup?type=token&id=<cv_token_uuid>
```

**Lookup by Stripe payment_intent_id:**
```
GET /api/admin/audit/lookup?type=pi&id=pi_xxx
```

**Response:** `{ token_hash, event_count, events: [{ event, ts, ... }] }`

Events show full chain: `payment_verified` → `bundle_created` → `bundle_credit_used` → `download_200`

**Bundle status check (support):**
1. Get bundle_token from email: `bundle_credits.get_bundle_token_by_email(email)`
2. Check status: `bundle_credits.get_status(bundle_token)`
3. Returns: plan, cv_remaining, cl_remaining, expires_in_hours, active

**Bundle recovery for customer:** Direct them to `/build` → "Already purchased a bundle? Recover access" → enter email → recovery link sent

---

## Files Modified (Phase 1)

| File | Changes |
|------|---------|
| `templates/index.html` | Testimonials section, cover letter generator UI |
| `static/css/style.css` | Testimonials CSS, sub-score bars, cover letter generator CSS |
| `backend/keyword_engine.py` | `analyze_ats_formatting()` enhanced, `check_bullet_quantification()`, `calculate_recruiter_tips_score()` |
| `backend/ai_analyzer.py` | `generate_cover_letter()`, `enhance_bullet_point()`, `generate_resume_summary()` |
| `app.py` | 3 new endpoints, new imports, recruiter_tips in scan response |
| `static/js/app.js` | `renderSubScoreBars()`, cover letter generator handler |
| `templates/build.html` | AI micro-tools section (bullet enhancer + summary generator) |
| `static/js/builder.js` | Tool toggle/API handlers |
| `static/css/builder.css` | Tool section styling |

## Files Modified/Created (Phase 2)

| File | Changes |
|------|---------|
| `backend/bundle_credits.py` | **NEW** — Lua atomic decrement, bundle CRUD, HMAC helpers, exchange tokens, idempotency |
| `backend/ai_cache.py` | **NEW** — SHA256 response deduplication cache, 1hr TTL |
| `backend/ai_budget.py` | **NEW** — Dual daily spend guardrail (cost + call count) |
| `backend/ai_metrics.py` | **NEW** — Per-tool Redis hash counters (7-day TTL) |
| `backend/ai_ratelimit.py` | **NEW** — In-handler daily rate limits with atomic INCR+EXPIRE |
| `backend/audit_log.py` | Added bundle event types + allowed kwargs |
| `backend/stripe_utils.py` | `create_bundle_checkout_session()`, `verify_bundle_payment()` |
| `backend/paystack_utils.py` | `create_paystack_bundle_transaction()` (feature-flagged) |
| `backend/ai_analyzer.py` | Integrated cache + budget + metrics into all 3 AI functions |
| `app.py` | 6 bundle endpoints, webhook refactoring, bundle download path, AI rate limit rework |
| `templates/build.html` | Bundle banner, 3-tier pricing, recovery form |
| `static/js/builder.js` | Bundle auto-activation, status check, download, purchase, recovery |
| `static/css/builder.css` | Bundle banner, tier cards, recovery form, mobile responsive |
