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

    # ---- SECTION 9: JS SYNTAX CHECK ----
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
