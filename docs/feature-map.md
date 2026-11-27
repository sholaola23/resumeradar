# ResumeRadar feature map

Every thing a user can do on ResumeRadar, one row each. Every feature PR updates this file in the same PR.

- **User check** means `tests/user-check/flows.spec.ts`. It walks the flow in a real browser at 375px and 1280px, with axe on each page, against a local server (`tests/user-check/serve.py`) where Claude, Resend and Beehiiv are faked and Redis is a private local copy. CI runs it on every PR ("User check" job). The test name is in brackets.
- **Unit** means a file in `tests/` run by `unittest discover`. **QA suite** means `tests/qa_suite.py`.
- **Status:** Live (on the site now), API only (a route with no page that uses it), or Off.
- **PENDING** means part of the flow can't be tested safely here. The reason is given, and Shola decides if it needs another check.

Who: every row is a job seeker on the public site, with no account, unless it says otherwise.

| Feature | Steps | What should happen | Covered by | Status |
|---|---|---|---|---|
| Home page | Open `/` | The form shows a CV upload or paste box, a job description box and a "Scan my CV" button. | User check ("home page loads and passes axe"); QA suite | Live |
| Scan with an uploaded CV | Choose a DOCX or PDF, paste a job description, press "Scan my CV" | The file is parsed then deleted, and the results page shows the keyword match estimate, matched and missing keywords. | User check ("scan with an uploaded DOCX"); Unit `test_resume_parser.py`, `test_pdf_extract_budget.py`, `test_scan_input_limits.py` | Live |
| Scan with pasted CV text | Choose "Paste text", paste CV and job description, scan | Same results page, with AI suggestions (strengths, improvements, keywords to add). | User check ("scan with pasted text"); Unit `test_keyword_quality.py`, `test_scoring_gaps.py`, `test_score_format.py` | Live |
| Scan errors | Scan with nothing filled in | An error message shows and no results appear. | User check ("scan with nothing filled in"); Unit `test_scan_input_limits.py` | Live |
| Results page | After a scan | Score, missing and matched keywords, AI suggestions, formatting checks, job view, scan history (this browser only). Passes axe. | User check ("scan with pasted text"); Unit `test_job_view.py`, `test_product_integration.py`; `node --test tests/scan_utils.test.cjs` | Live |
| Example report | Press "See an example report" | Fills a sample CV and job description and runs the scan straight away. A repeat within the hour reuses the cached AI reply. | User check ("example report runs a scan"); QA suite (button present) | Live |
| Cover letter | On the results page, press the cover letter button | A cover letter written from the CV and job description appears, with copy and download buttons. | User check ("writes a cover letter from the scan", "after 5 letters the page shows the daily limit message"); daily cap per visitor: unit `test_tool_daily_limits` | Live |
| Bullet tool | `POST /api/tools/enhance-bullet` | Returns an improved bullet. No page on the site calls it since the builder was switched off. | User check ("improve a bullet"); daily cap per visitor: unit `test_tool_daily_limits` | API only |
| Summary tool | `POST /api/tools/generate-summary` | Returns a CV summary. No page on the site calls it since the builder was switched off. | User check ("write a summary"); daily cap per visitor: unit `test_tool_daily_limits` | API only |
| Download report | On the results page, press "Download report" | A PDF report downloads, built only from a signed scan. | User check ("download the PDF report"); Unit `test_report_signing.py`, `test_repeat_downloads.py` | Live |
| Email report | Press "Email report", enter an address, open the link in the confirm email, press Confirm | The first email is only a confirm link. After the press, the open page sends the report with the PDF attached. Caps: 3 report sends and 3 confirm emails per scan, 5 confirm emails per address a day. | User check ("email the report", fake outbox); Unit `test_report_confirm.py`, `test_score_email_link.py` | Live. **PENDING:** real delivery through Resend, spam filtering, and mail scanners opening the link can't be tested without sending real email. |
| Share ResumeRadar | Share buttons on the results page and the header | WhatsApp, LinkedIn, copy link or the phone's share sheet, with a `?ref=` tag. | Unit `test_referral.py` | Live. **PENDING:** the WhatsApp and LinkedIn pages and the phone share sheet are outside sites, so the check blocks them. |
| Share a job description | On the results page, press "Share this job description" | The copied link opens ResumeRadar with the job description filled in and no CV text. | User check ("share this job description") | Live |
| Share page | Open `/share` | A ready-made message and QR code for a class or group. | User check ("share page loads and passes axe"); Unit `test_referral.py` | Live |
| Newsletter sign-up | On the results page, fill first name and email, press "Subscribe to free tips" | A "Subscribed" message shows and the address is sent to Beehiiv. "No thanks" hides the card. | User check ("sign up from the results page", fake Beehiiv) | Live. **PENDING:** a real Beehiiv sign-up and its welcome email can't be tested without adding a real subscriber. |
| Was this useful? | On the results page, press Yes or No, add an optional comment, send | A thank-you shows. Only the comment (links, emails and phone numbers removed), the vote, the may-quote tick and the date are kept, for 90 days. | User check ("vote yes and send a comment"); Unit `test_feedback.py` | Live |
| Privacy page | Open `/privacy` | The privacy promises, matching what the code does. | User check ("privacy page loads and passes axe"); Unit `test_site_copy.py`, `test_ai_log_privacy.py` | Live |
| Role guides | Open `/ats-resume-checker/` and a role page | The hub lists roles; each role page loads. | User check ("role guides", "a role page") | Live |
| Missing page | Open any unknown address | The branded 404 page. | User check ("missing page shows the 404 page") | Live |
| CV builder (paid) | `/build`, `/api/build/*` | Every builder page, API and file returns 404, while `app.js` and `style.css` still load. Never switch it on. | User check ("builder routes are 404"); Unit `test_builder_disabled.py` | Off |
| Scan count | Home page and `/api/scan-count` | Shows the public scan count, also used on sholaoladipupo.com. | QA suite | Live |
| AI spend limits | Any AI call | Daily cost and call caps, the 1-hour cache and per-route limits. When the budget is spent, users see rule-based suggestions or "temporarily unavailable". | User check (every AI flow runs the real budget code against the fake client); no test checks the caps themselves | Live. **Gap:** no test proves a spent budget stops calls. **PENDING:** the per-visitor daily tool limits key on the Cloudflare edge address, so they don't fire in production (see `CLAUDE.md`). |

## Not covered by any test here

These need the live site or real services, so they are **PENDING** and stay with Shola:

- Real Claude replies: whether the suggestions and cover letters are good. The check uses canned replies.
- Real email delivery (Resend) and real Beehiiv sign-ups.
- Cloudflare: the visitor address the rate limits see (`CF-Connecting-IP`).
- Anything on Render or the live site: env vars, Redis on Render, deploys. The live check is in `CLAUDE.md` ("Hosting and deploys").
- Admin routes (`/api/admin/*`), which are for Shola, not users.
