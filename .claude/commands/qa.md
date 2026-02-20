Run the ResumeRadar QA test suite to verify production readiness.

## What to do

1. Activate the virtual environment and run the full QA suite:

```
cd "$PROJECT_DIR" && source venv/bin/activate && python tests/qa_suite.py
```

2. Read the output carefully. Report the results to the user:
   - Total tests passed vs failed
   - If any tests FAILED, list each failure with its detail
   - If all passed, confirm the app is safe to deploy

3. If there are failures:
   - Investigate each failure
   - Suggest or apply fixes
   - Re-run the suite to confirm the fix

## Quick mode

For fast checks only (skips live scan + PDF generation), add `--quick`:

```
cd "$PROJECT_DIR" && source venv/bin/activate && python tests/qa_suite.py --quick
```

Use quick mode when checking after small CSS/HTML changes.
Use full mode before any deploy or after backend changes.

## What the suite checks (46 tests)

- **Routes**: All pages and API endpoints return correct status codes
- **Scan form integrity**: Only `jobDescription` is required (prevents the scan button bug)
- **Security headers**: X-Content-Type-Options, X-Frame-Options, XSS protection, etc.
- **HTML elements**: All critical UI elements present
- **Meta tags**: OG image, Twitter card, favicon, apple-touch-icon
- **API validation**: Proper error handling for bad inputs
- **Subscribe logic**: Signup validation
- **Full scan**: End-to-end scan with score verification
- **PDF generation**: Report downloads successfully
- **JS integrity**: File exists, not empty, has key functions
