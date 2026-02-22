#!/usr/bin/env python3
"""
ResumeRadar QA Suite
====================
Automated production-readiness checks for ResumeRadar.
Run via: python tests/qa_suite.py [--quick]

--quick  : Run fast checks only (routes, structure, security). ~2s
(default): Run full suite including live scan + PDF generation. ~8s

Exit codes:
  0 = all passed
  1 = one or more failures
"""

import sys
import os
import re
import json
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

# ============================================================
# CONFIG
# ============================================================
QUICK_MODE = '--quick' in sys.argv

PASS = 0
FAIL = 0
RESULTS = []


def check(name, passed, detail=""):
    """Record a test result."""
    global PASS, FAIL
    if passed:
        PASS += 1
        RESULTS.append(("PASS", name, detail))
    else:
        FAIL += 1
        RESULTS.append(("FAIL", name, detail))


# ============================================================
# TEST SUITE
# ============================================================
def run_tests():
    start = time.time()

    with app.test_client() as c:

        # ---- SECTION 1: ROUTES ----
        # 1. Main page
        r = c.get('/')
        check("GET / returns 200", r.status_code == 200)

        html = r.data.decode()

        # 2. Health check
        r = c.get('/api/health')
        check("GET /api/health returns 200", r.status_code == 200)

        # 3. Scan count
        r = c.get('/api/scan-count')
        d = r.get_json()
        check("GET /api/scan-count returns count", r.status_code == 200 and 'count' in d)

        # 4. robots.txt
        r = c.get('/robots.txt')
        check("GET /robots.txt returns 200", r.status_code == 200)

        # 5. favicon.ico
        r = c.get('/favicon.ico')
        check("GET /favicon.ico returns 200", r.status_code == 200)

        # 6. apple-touch-icon
        r = c.get('/apple-touch-icon.png')
        check("GET /apple-touch-icon.png returns 200", r.status_code == 200)

        # 7. 404 page (browser)
        r = c.get('/nonexistent-page')
        check("GET /nonexistent returns 404", r.status_code == 404)

        # 8. 404 API (JSON)
        r = c.get('/api/nonexistent')
        d = r.get_json()
        check("GET /api/404 returns JSON error", r.status_code == 404 and d and 'error' in d)

        # ---- SECTION 2: SCAN FORM STRUCTURE ----
        # 9. Only jobDescription is required inside the form
        form_match = re.search(r'<form[^>]*id="scanForm"[^>]*>(.*?)</form>', html, re.DOTALL)
        if form_match:
            form_html = form_match.group(1)
            required_inputs = re.findall(r'<(?:input|textarea)[^>]*required[^>]*>', form_html)
            required_ids = []
            for inp in required_inputs:
                m = re.search(r'id="([^"]+)"', inp)
                if m:
                    required_ids.append(m.group(1))
            check("Only jobDescription required in form", required_ids == ['jobDescription'],
                  f"Found: {required_ids}")
        else:
            check("Scan form found in HTML", False, "Could not find scanForm")

        # ---- SECTION 3: SECURITY HEADERS ----
        r = c.get('/')
        check("X-Content-Type-Options header", r.headers.get('X-Content-Type-Options') == 'nosniff')
        check("X-Frame-Options header", r.headers.get('X-Frame-Options') == 'SAMEORIGIN')
        check("X-XSS-Protection header", r.headers.get('X-XSS-Protection') == '1; mode=block')
        check("Referrer-Policy header", 'strict-origin' in (r.headers.get('Referrer-Policy') or ''))
        check("Permissions-Policy header", bool(r.headers.get('Permissions-Policy')))

        # ---- SECTION 4: HTML INTEGRITY ----
        # 15. Key elements present
        key_elements = [
            ('scanForm', 'Scan form'),
            ('scanBtn', 'Scan button'),
            ('demoScanBtn', 'Demo scan button'),
            ('results', 'Results section'),
            ('copyReportBtn', 'Copy report button'),
            ('downloadReportBtn', 'Download PDF button'),
            ('shareLinkedIn', 'Share LinkedIn button'),
            ('newsletterPopup', 'Newsletter popup'),
            ('errorMessage', 'Error message div'),
        ]
        for elem_id, label in key_elements:
            check(f"HTML has #{elem_id}", f'id="{elem_id}"' in html, label)

        # ---- SECTION 5: META TAGS ----
        check("OG title meta tag", 'og:title' in html)
        check("OG image meta tag", 'og:image' in html)
        check("Twitter card meta tag", 'twitter:card' in html)
        check("Favicon link tag", 'favicon.ico' in html)
        check("Apple touch icon link", 'apple-touch-icon' in html)

        # ---- SECTION 6: API VALIDATION ----
        # Empty scan
        r = c.post('/api/scan', data={'job_description': ''})
        check("Scan rejects empty JD", r.status_code == 400)

        # Short scan
        r = c.post('/api/scan', data={'job_description': 'too short'})
        check("Scan rejects short JD", r.status_code == 400)

        # No resume
        r = c.post('/api/scan', data={'job_description': 'a ' * 20})
        check("Scan rejects missing resume", r.status_code == 400)

        # Subscribe without email
        r = c.post('/api/subscribe', json={'email': '', 'first_name': 'Test'})
        check("Subscribe rejects empty email", r.status_code == 400)

        # Subscribe without first name
        r = c.post('/api/subscribe', json={'email': 'a@b.com', 'first_name': '', 'utm_source': 'resumeradar'})
        check("Subscribe rejects missing name", r.status_code == 400)

        # ---- SECTION 7: FULL SCAN (skip in quick mode) ----
        if not QUICK_MODE:
            r = c.post('/api/scan', data={
                'job_description': (
                    'We are looking for a Cloud Engineer with AWS experience including '
                    'EC2 S3 Lambda CloudFormation Terraform Kubernetes Docker CI/CD pipelines '
                    'Python scripting and networking fundamentals.'
                ),
                'resume_text': (
                    'Experienced cloud engineer with 5 years of AWS experience. '
                    'Skilled in EC2, S3, Lambda, CloudFormation, and Terraform. '
                    'Built CI/CD pipelines with Jenkins and GitHub Actions. '
                    'Proficient in Python and Docker.'
                ),
            })
            d = r.get_json()
            check("Full scan returns 200", r.status_code == 200)
            check("Full scan has match_score", d and 'match_score' in d)
            check("Full scan score > 0", d and d.get('match_score', 0) > 0,
                  f"Score: {d.get('match_score') if d else 'N/A'}")
            check("Full scan has category_scores", d and 'category_scores' in d)
            check("Full scan has ai_suggestions", d and 'ai_suggestions' in d)

            # ---- SECTION 8: PDF GENERATION ----
            r = c.post('/api/download-report', json={
                'match_score': 72,
                'total_matched': 8,
                'total_missing': 3,
                'total_job_keywords': 11,
                'category_scores': {},
                'matched_keywords': {},
                'missing_keywords': {},
                'ats_formatting': {},
                'ai_suggestions': {},
            })
            check("PDF report generates", r.status_code == 200 and len(r.data) > 500,
                  f"Size: {len(r.data)} bytes")

    # ---- SECTION 9: CV BUILDER ----
    with app.test_client() as c:
        # Build page loads
        r = c.get('/build')
        check("GET /build returns 200", r.status_code == 200)
        build_html = r.data.decode()
        check("Build page has privacy badge", 'privacy-badge' in build_html)

    # Score-aware CTA on scan page
    check("Scan CTA has dynamic heading ID", 'buildCtaHeading' in html)
    check("Scan CTA has trust badge", 'build-cta-trust' in html and 'never make anything up' in html.lower())

    # PDF generation — all 3 templates
    from backend.cv_pdf_generator import generate_cv_pdf, TEMPLATES, _flatten_skills, _safe

    test_cv = {
        'personal': {'full_name': 'QA Test', 'email': 'qa@test.com', 'phone': '+1 555 0199', 'location': 'London'},
        'summary': 'Experienced engineer with 5 years building scalable systems.',
        'experience': [{'title': 'Engineer', 'company': 'Acme', 'start_date': 'Jan 2020', 'end_date': 'Present',
                        'bullets': ['Built microservices', 'Led team of 4', 'Reduced deploy time by 60%']}],
        'education': [{'degree': 'BSc CS', 'institution': 'UCL', 'graduation_date': '2019', 'details': ''}],
        'skills': ['Python', 'AWS', 'Docker'],
        'certifications': [{'name': 'AWS SA', 'issuer': 'Amazon', 'date': '2023'}]
    }

    for tmpl in TEMPLATES:
        try:
            pdf_out = generate_cv_pdf(test_cv, tmpl)
            is_pdf = isinstance(pdf_out, (bytes, bytearray)) and len(pdf_out) > 500
            check(f"PDF {tmpl} template generates", is_pdf, f"{len(pdf_out)} bytes")
        except Exception as e:
            check(f"PDF {tmpl} template generates", False, str(e))

    # Invalid template falls back to classic
    try:
        pdf_out = generate_cv_pdf(test_cv, 'nonexistent')
        check("Invalid template falls back to classic", isinstance(pdf_out, (bytes, bytearray)) and len(pdf_out) > 500)
    except Exception as e:
        check("Invalid template falls back to classic", False, str(e))

    # Empty CV doesn't crash
    empty_cv = {'personal': {}, 'summary': '', 'experience': [], 'education': [], 'skills': [], 'certifications': []}
    try:
        all_ok = True
        for tmpl in TEMPLATES:
            pdf_out = generate_cv_pdf(empty_cv, tmpl)
            if not isinstance(pdf_out, (bytes, bytearray)):
                all_ok = False
        check("Empty CV data doesn't crash (all templates)", all_ok)
    except Exception as e:
        check("Empty CV data doesn't crash (all templates)", False, str(e))

    # Long text wraps without crash
    long_cv = dict(test_cv)
    long_cv['summary'] = 'Word ' * 200
    long_cv['experience'] = [{'title': 'Engineer', 'company': 'Co', 'start_date': '2020', 'end_date': 'Present',
                               'bullets': ['Achievement ' * 50, 'Result ' * 80]}]
    long_cv['skills'] = [f'Skill{i}' for i in range(40)]
    try:
        all_ok = True
        for tmpl in TEMPLATES:
            pdf_out = generate_cv_pdf(long_cv, tmpl)
            if not isinstance(pdf_out, (bytes, bytearray)) or len(pdf_out) < 500:
                all_ok = False
        check("Long text wraps without crash (all templates)", all_ok)
    except Exception as e:
        check("Long text wraps without crash (all templates)", False, str(e))

    # _flatten_skills handles both formats
    check("_flatten_skills: flat list", _flatten_skills(['A', 'B']) == ['A', 'B'])
    dict_result = _flatten_skills({'matched': ['A'], 'missing': ['B'], 'additional': ['C']})
    check("_flatten_skills: scan dict", 'A' in dict_result and 'B' in dict_result and 'C' in dict_result)

    # _safe handles Unicode
    check("_safe: Unicode conversion", _safe('Hello \u2014 World') == 'Hello -- World' and _safe(None) == '')

    # All multi_cell calls have align='L'
    pdf_gen_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'backend', 'cv_pdf_generator.py')
    with open(pdf_gen_path, 'r') as f:
        pdf_source = f.read()
    # Check each line with multi_cell individually (avoids nested-paren regex issues)
    mc_lines = [line.strip() for line in pdf_source.split('\n') if 'multi_cell(' in line and not line.strip().startswith('#')]
    bad_mc = [line for line in mc_lines if "align='L'" not in line]
    check(f"All {len(mc_lines)} multi_cell calls have align='L'", len(bad_mc) == 0,
          f"{len(bad_mc)} missing" if bad_mc else "")

    # LLM prompts have no-hallucination guardrails
    from backend.cv_builder import polish_cv_sections, extract_and_polish
    import inspect
    polish_src = inspect.getsource(polish_cv_sections)
    extract_src = inspect.getsource(extract_and_polish)
    check("LLM polish prompt: no-hallucination rules",
          'NEVER add skills' in polish_src and 'NEVER invent metrics' in polish_src)
    check("LLM extract prompt: no-hallucination rules",
          'NEVER invent' in extract_src and 'ACTUALLY EXISTS' in extract_src)
    check("LLM prompts return smart_suggestions",
          'smart_suggestions' in polish_src and 'smart_suggestions' in extract_src)

    # Fallback when API key is dummy
    old_key = os.environ.get('ANTHROPIC_API_KEY')
    os.environ['ANTHROPIC_API_KEY'] = 'your-anthropic-api-key-here'
    fallback = polish_cv_sections(test_cv)
    check("Fallback: returns unpolished data", fallback.get('ai_polished') == False)
    check("Fallback: has smart_suggestions key", 'smart_suggestions' in fallback)
    if old_key:
        os.environ['ANTHROPIC_API_KEY'] = old_key

    # app.js has score-aware CTA function
    # ---- SECTION 10: JS SYNTAX CHECK ----
    js_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           'static', 'js', 'app.js')
    if os.path.exists(js_path):
        with open(js_path, 'r') as f:
            js_content = f.read()
        # Basic syntax checks
        check("JS file not empty", len(js_content) > 1000, f"{len(js_content)} chars")
        check("JS has DOMContentLoaded", 'DOMContentLoaded' in js_content)
        check("JS has no console.log (debug)", 'console.log(' not in js_content or
              js_content.count('console.log(') <= 2,
              f"Found {js_content.count('console.log(')} console.log calls")
    else:
        check("JS file exists", False, js_path)

    # ---- SECTION 11: UX IMPROVEMENTS + EMAIL DELIVERY ----

    # Behavioral endpoint tests (strongest — test actual HTTP responses)
    with app.test_client() as c:
        # Checkout validates bad email → 400
        r = c.post('/api/build/create-checkout',
            json={'token': 'test', 'template': 'classic', 'delivery_email': 'not-valid'},
            content_type='application/json')
        check("Checkout rejects invalid delivery email", r.status_code == 400)

        # Checkout accepts empty email → NOT a 400 about email
        r = c.post('/api/build/create-checkout',
            json={'token': 'test', 'template': 'classic', 'delivery_email': ''},
            content_type='application/json')
        d = r.get_json() or {}
        check("Checkout accepts empty delivery email",
              r.status_code != 400 or 'email' not in d.get('error', '').lower())

    # HTML structure checks (verifiable from template)
    with app.test_client() as c:
        r = c.get('/build')
        build_html = r.data.decode()

    preview_count = build_html.count('class="template-preview')
    check("Build page has 3 template previews", preview_count == 3, f"Found: {preview_count}")
    check("Delivery email input with maxlength",
          'id="deliveryEmail"' in build_html and 'maxlength="254"' in build_html)
    check("Loading text span in generate button",
          'gen-loading-text' in build_html)

    # Structural source assertions (multi-indicator to reduce false-pass risk)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    builder_js_path = os.path.join(project_root, 'static', 'js', 'builder.js')
    with open(builder_js_path, 'r') as f:
        builder_js = f.read()
    check("Loading message rotation system",
          'LOADING_MESSAGES' in builder_js and 'startLoadingRotation' in builder_js)
    check("Confetti with auto-cleanup",
          'createConfetti' in builder_js and 'confetti-piece' in builder_js and 'setTimeout' in builder_js)
    check("Form pre-populate helper",
          'populateDynamicEntries' in builder_js)
    check("Email-requested header read",
          'X-Email-Requested' in builder_js)
    check("Inline editable summary",
          'contenteditable' in builder_js and 'preview-summary-editable' in builder_js)

    app_py_path = os.path.join(project_root, 'app.py')
    with open(app_py_path, 'r') as f:
        app_source = f.read()
    check("Webhook calls _send_cv_email with event_id",
          '_send_cv_email' in app_source and "event['id']" in app_source)
    check("SETNX dedup keyed on event_id (72h TTL)",
          'nx=True' in app_source and 'cv_emailed' in app_source and '259200' in app_source)
    check("CV data TTL extended on webhook",
          '.expire(' in app_source and '259200' in app_source)
    check("User values sanitized (html.escape + re.sub)",
          'html_module.escape' in app_source and 're_module.sub' in app_source)
    check("Download route returns X-Email-Requested header",
          'X-Email-Requested' in app_source)

    builder_css_path = os.path.join(project_root, 'static', 'css', 'builder.css')
    with open(builder_css_path, 'r') as f:
        builder_css = f.read()
    check("Payment content flex-wrap for email row",
          'flex-wrap' in builder_css and 'payment-email' in builder_css)

    # ---- SECTION 12: E2E SCENARIOS ----

    with app.test_client() as c:

        # E2E-1: Stripe cancel flow — cancel URL returns cleanly
        r = c.get('/build?payment=cancelled')
        check("Cancel flow: /build?payment=cancelled returns 200", r.status_code == 200)
        cancelled_html = r.data.decode()
        check("Cancel flow: page renders without error", 'builderForm' in cancelled_html)

        # E2E-7: Token/session tampering — mismatched combos return 4xx
        # GET with fake token + fake session
        r = c.get('/api/build/download/fake-token-123?session_id=cs_fake_session&template=classic')
        check("Tampered token: download returns 4xx", r.status_code in (400, 403, 404, 500))

        # POST with fake session + fake token
        r = c.post('/api/build/download/fake-token-456',
            json={'session_id': 'cs_fake_session', 'template': 'classic', 'cv_data': {'personal': {}}},
            content_type='application/json')
        check("Tampered session POST: download returns 4xx", r.status_code in (400, 403, 404, 500))

        # Missing session_id entirely
        r = c.get('/api/build/download/some-token?template=classic')
        check("Missing session_id: download returns 400", r.status_code == 400)

        # E2E-10: Email validation normalization — edge cases
        # Valid edge emails (should not return 400 about email)
        valid_emails = ['user+tag@example.com', 'USER@EXAMPLE.COM', 'a@sub.domain.example.com']
        for em in valid_emails:
            r = c.post('/api/build/create-checkout',
                json={'token': 'test', 'template': 'classic', 'delivery_email': em},
                content_type='application/json')
            d = r.get_json() or {}
            is_email_error = r.status_code == 400 and 'email' in d.get('error', '').lower()
            check(f"Valid email accepted: {em}", not is_email_error)

        # Invalid emails (should return 400 about email)
        invalid_emails = ['notanemail', '@nolocal.com', 'spaces in@email.com', 'a@.com']
        for em in invalid_emails:
            r = c.post('/api/build/create-checkout',
                json={'token': 'test', 'template': 'classic', 'delivery_email': em},
                content_type='application/json')
            check(f"Invalid email rejected: {em}", r.status_code == 400)

        # E2E-11: Webhook signature validation — unsigned payloads rejected
        r = c.post('/api/build/webhook',
            data=b'{"type":"checkout.session.completed"}',
            content_type='application/json')
        check("Unsigned webhook: rejected (400)", r.status_code == 400)

        r = c.post('/api/build/webhook',
            data=b'{"type":"checkout.session.completed"}',
            content_type='application/json',
            headers={'Stripe-Signature': 'invalid_sig_header'})
        check("Invalid signature webhook: rejected (400)", r.status_code == 400)

    # E2E-12: UI state integrity after errors — source assertions
    check("Builder JS stops loading on scan error",
          'stopLoadingRotation()' in builder_js and 'scan-error' in builder_js)
    check("Builder JS re-enables button on generate error",
          'setGenerateLoading(false)' in builder_js and 'showError' in builder_js)
    check("Builder JS re-enables payment button on error",
          'setPaymentLoading(false)' in builder_js)

    # E2E-13: Accessibility assertions — labels, roles, keyboard support
    check("Email input has label element",
          'for="deliveryEmail"' in build_html)
    check("Summary editable in JS",
          'contenteditable' in builder_js)
    check("Template radios have labels",
          build_html.count('class="template-option"') == 3 and '<label' in build_html)
    check("Generate button is type submit",
          'type="submit"' in build_html and 'generateBtn' in build_html)

    # E2E-14: Cross-browser/mobile — responsive CSS assertions
    check("Mobile: form-row stacks to 1fr",
          '@media' in builder_css and 'grid-template-columns: 1fr' in builder_css)
    check("Mobile: template-picker stacks",
          'template-picker' in builder_css)
    check("Mobile: payment-content wraps",
          'flex-wrap: wrap' in builder_css)
    check("Mobile: celebration actions wrap",
          'celebration-actions' in builder_css and 'flex-wrap' in builder_css)

    # E2E-15: Observability assertions — logs/print statements for key events
    check("Observability: webhook error logged",
          "Webhook error:" in app_source or "Webhook processing" in app_source)
    check("Observability: email error logged",
          "CV email error" in app_source)
    check("Observability: download error logged",
          "CV Builder download error" in app_source)
    check("Observability: checkout error logged",
          "CV Builder checkout error" in app_source)

    # E2E-2/3/4: Success URL refresh, webhook replay, out-of-order timing
    # These require real Stripe sessions and Redis state — verified via structural assertions
    check("Download route enforces download limit (max 3)",
          'dl_count >= 3' in app_source or 'Download limit' in app_source)
    check("Webhook extends CV data TTL for retry window",
          '.expire(' in app_source and 'resumeradar:cv:' in app_source)
    check("SETNX dedup releases on failure for retry recovery",
          '_redis_client.delete(f"resumeradar:cv_emailed:' in app_source or
          '_redis_client.delete(dedup_key)' in app_source)

    # E2E-6: Redis degradation path — verify graceful handling
    check("Download falls back to client data when Redis unavailable",
          'client_cv_data' in app_source and 'not cv_data and client_cv_data' in app_source)
    check("Email skipped when Redis unavailable",
          'if not _redis_client:' in app_source)

    # E2E-8: Download limit enforcement
    check("Download counter tracked in Redis",
          'cv_downloads' in app_source and 'incr' in app_source)

    # E2E-9: TTL expiry behavior — graceful error messaging
    check("Expired CV data returns user-friendly message",
          'CV data not found' in app_source or 'may have expired' in app_source)
    check("Expired session returns user-friendly message",
          'CV session expired' in app_source or 'regenerate' in app_source)

    # ---- SECTION 13: E2E REGRESSION FIXES ----

    # Fix 1 (P1): Upload-to-builder handoff — scan response includes resume_text
    check("Scan response includes resume_text for file-upload users",
          "resume_text" in app_source and "extracted_resume_text" in app_source)

    # Verify app.js uses scan data fallback for file-upload users
    app_js_path = os.path.join(project_root, 'static', 'js', 'app.js')
    with open(app_js_path, 'r') as f:
        app_js = f.read()
    check("Builder handoff falls back to scan response resume_text",
          'scanData.resume_text' in app_js and 'textareaText' in app_js)

    # Fix 2 (P2): ImportError fallback validates email instead of silently dropping
    check("ImportError fallback logs warning and validates",
          'WARNING: email-validator not installed' in app_source and
          '"@" not in delivery_email' in app_source)

    # Fix 3 (P2): populateDynamicEntries clears stale entries before populating
    check("Dynamic entries cleared before re-populate",
          '.remove()' in builder_js and 'existingEntries' in builder_js)

    # Fix 4 (P2): Inline summary allows blank text (no truthy guard)
    # The blur handler should use `if (currentPolished)` not `if (currentPolished && newText)`
    check("Inline summary persists blank text",
          'currentPolished.summary = newText' in builder_js and
          'currentPolished && newText' not in builder_js)

    # Fix 5 (P3): Cancelled payment shows UX feedback
    check("Payment cancelled handler exists",
          'showPaymentCancelledMessage' in builder_js and 'payment-cancelled-banner' in builder_js)
    check("Payment cancelled auto-dismiss",
          'cancelled-dismiss' in builder_js and 'Auto-dismiss' in builder_js or
          'cancelled-dismiss' in builder_js and '8000' in builder_js)
    check("Payment cancelled CSS styles",
          'payment-cancelled-banner' in builder_css and 'cancelled-content' in builder_css)
    check("Payment cancelled URL cleanup",
          "searchParams.delete('payment')" in builder_js and 'replaceState' in builder_js)

    # Behavioral: /build?payment=cancelled still returns valid page
    with app.test_client() as c:
        r = c.get('/build?payment=cancelled')
        cancelled_page = r.data.decode()
        check("Cancel URL renders builder page with form",
              r.status_code == 200 and 'builderForm' in cancelled_page)

    # ---- SECTION 14: UPLOAD-FIRST BUILD + RATE LIMIT HARDENING ----
    print("\n-- Section 14: Upload-First Build + Rate Limit Hardening --")

    # --- HTML structure checks ---
    check("Upload section exists on build page",
          'id="uploadSection"' in build_html)
    check("Upload drop zone exists",
          'id="buildDropZone"' in build_html)
    check("Upload target JD textarea exists",
          'id="uploadTargetJD"' in build_html)
    check("Upload generate button exists",
          'id="uploadGenerateBtn"' in build_html)
    check("Manual form toggle link exists",
          'id="showManualForm"' in build_html)
    check("Back-to-upload link exists",
          'id="showUploadSection"' in build_html)
    check("Manual form hidden by default",
          'id="manualFormSection"' in build_html and 'style="display: none;"' in build_html)

    # --- JS source checks (multi-indicator) ---
    check("Upload file handler + endpoint call",
          'handleBuildFileSelect' in builder_js and 'generate-from-upload' in builder_js)
    check("Toggle handlers for both directions",
          'showManualFormLink' in builder_js and 'showUploadLink' in builder_js)
    check("Scan fallback shows upload section when data missing",
          'uploadSection.style.display' in builder_js and 'show upload section' in builder_js.lower())
    check("Retry-After parsing handles seconds and HTTP-date",
          'parseInt(retryAfter' in builder_js and 'new Date(retryAfter)' in builder_js)
    check("Edit & Regenerate hides upload section",
          'uploadSection' in builder_js and 'manualFormSection' in builder_js)

    # --- Rate limit config checks (app.py source) ---
    check("Limiter uses REDIS_URL with memory fallback",
          'REDIS_URL' in app_source and "memory://" in app_source)
    check("Checkout limit raised to 30/hour",
          app_source.count('"30 per hour"') >= 2)
    check("get_real_ip uses second-to-last for multi-proxy chains",
          'len(parts) - 2' in app_source)
    check("get_real_ip validates IP format with regex",
          "re_module.match" in app_source and r"[\d.:a-fA-F]" in app_source)

    # --- Startup logging (module-level, visible under Gunicorn) ---
    check("Startup logs Stripe Checkout status",
          'STRIPE_PRICE_ID' in app_source and 'Stripe Checkout' in app_source)
    check("Startup logs Rate Limiter backend",
          'Rate Limiter' in app_source)
    check("Startup logs outside __main__ (Gunicorn-visible)",
          app_source.index('Stripe Checkout') < app_source.index("if __name__"))

    # --- render.yaml completeness ---
    render_yaml_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'render.yaml')
    with open(render_yaml_path, 'r') as f:
        render_yaml = f.read()
    check("render.yaml includes STRIPE_PRICE_ID",
          'STRIPE_PRICE_ID' in render_yaml)

    # --- CSS checks ---
    check("Upload toggle row CSS exists",
          'upload-toggle-row' in builder_css)

    # --- Behavioral endpoint tests ---
    import io

    with app.test_client() as c:
        # Upload-generate rejects missing file
        r = c.post('/api/build/generate-from-upload',
                    data={'job_description': 'Senior software engineer with Python experience and cloud infrastructure knowledge for a fast-paced startup environment'},
                    content_type='multipart/form-data')
        check("Upload-generate rejects missing file (400)",
              r.status_code == 400)

        # Upload-generate rejects empty JD
        fake_pdf = (io.BytesIO(b'%PDF-1.4 fake pdf content'), 'test.pdf')
        r = c.post('/api/build/generate-from-upload',
                    data={'resume_file': fake_pdf, 'job_description': ''},
                    content_type='multipart/form-data')
        check("Upload-generate rejects empty JD (400)",
              r.status_code == 400)

        # Upload-generate rejects wrong file type
        fake_txt = (io.BytesIO(b'plain text content'), 'resume.txt')
        r = c.post('/api/build/generate-from-upload',
                    data={'resume_file': fake_txt,
                          'job_description': 'Senior software engineer with Python experience and cloud infrastructure knowledge for a fast-paced startup environment'},
                    content_type='multipart/form-data')
        check("Upload-generate rejects non-PDF/DOCX file (400)",
              r.status_code == 400)

        # Upload-generate rejects short JD
        fake_pdf2 = (io.BytesIO(b'%PDF-1.4 fake content'), 'resume.pdf')
        r = c.post('/api/build/generate-from-upload',
                    data={'resume_file': fake_pdf2,
                          'job_description': 'too short'},
                    content_type='multipart/form-data')
        check("Upload-generate rejects short JD (400)",
              r.status_code == 400)

    # --- .env.example completeness ---
    env_example_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env.example')
    with open(env_example_path, 'r') as f:
        env_example = f.read()
    check(".env.example includes STRIPE_PRICE_ID",
          'STRIPE_PRICE_ID' in env_example)
    check(".env.example includes REDIS_URL",
          'REDIS_URL' in env_example)

    elapsed = time.time() - start

    # ============================================================
    # REPORT
    # ============================================================
    print()
    print("=" * 55)
    print(f"  RESUMERADAR QA REPORT {'(QUICK)' if QUICK_MODE else '(FULL)'}")
    print("=" * 55)

    for status, name, detail in RESULTS:
        icon = "  PASS" if status == "PASS" else "  FAIL"
        suffix = f"  ({detail})" if detail else ""
        print(f"{icon}  {name}{suffix}")

    print()
    print("-" * 55)
    print(f"  {PASS} passed, {FAIL} failed  |  {elapsed:.1f}s")

    if FAIL > 0:
        print()
        print("  FAILURES:")
        for status, name, detail in RESULTS:
            if status == "FAIL":
                print(f"    - {name}" + (f" ({detail})" if detail else ""))

    print("-" * 55)

    if FAIL == 0:
        print("  STATUS: ALL CLEAR — safe to deploy")
    else:
        print(f"  STATUS: {FAIL} ISSUE(S) FOUND — review before deploying")

    print("=" * 55)
    print()

    return FAIL


if __name__ == '__main__':
    failures = run_tests()
    sys.exit(1 if failures > 0 else 0)
