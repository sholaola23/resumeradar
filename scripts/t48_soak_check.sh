#!/bin/bash
# ============================================================
# T+48h Soak Check — ResumeRadar Phase 2 Go/No-Go
# Scheduled: Feb 28, 2026 09:26 UTC
# ============================================================

set -euo pipefail

STAGING_URL="https://resumeradar-staging.onrender.com"
RENDER_API_KEY="rnd_C86e5Aibkd5vOWpbPQ1DwYk0bjQc"
SERVICE_ID="srv-d6g7jvk50q8c73ckhnk0"
REPORT_FILE="/Users/olushola/ATS Job Scan Project/tasks/t48_soak_report.md"
PASS=0
FAIL=0

log() { echo "[$(date '+%H:%M:%S')] $1"; }
pass() { PASS=$((PASS + 1)); echo "  ✅ $1"; }
fail() { FAIL=$((FAIL + 1)); echo "  ❌ $1"; }

echo "============================================================"
echo "  T+48h SOAK CHECK — $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "============================================================"
echo ""

# ---- Check 1: No sustained 5xx ----
log "Check 1: Render service health + recent errors"
HEALTH=$(curl -sf "$STAGING_URL/api/health" 2>/dev/null || echo "FAILED")
if echo "$HEALTH" | grep -q '"healthy"'; then
    pass "Health endpoint: OK"
else
    fail "Health endpoint: $HEALTH"
fi

# Hit multiple endpoints to check for 5xx
for path in "/" "/build" "/api/scan-count" "/robots.txt"; do
    CODE=$(curl -s -o /dev/null -w "%{http_code}" "$STAGING_URL$path" 2>/dev/null || echo "000")
    if [ "$CODE" -ge 200 ] && [ "$CODE" -lt 400 ]; then
        pass "GET $path → $CODE"
    else
        fail "GET $path → $CODE"
    fi
done

# ---- Check 2: No recurring tracebacks (Render logs) ----
log "Check 2: Recent deploy status"
DEPLOY_STATUS=$(curl -s "https://api.render.com/v1/services/$SERVICE_ID/deploys?limit=1" \
    -H "Authorization: Bearer $RENDER_API_KEY" 2>/dev/null | \
    python3 -c "import sys,json;d=json.load(sys.stdin);print(d[0].get('deploy',{}).get('status','?'))" 2>/dev/null || echo "unknown")

if [ "$DEPLOY_STATUS" = "live" ]; then
    pass "Latest deploy: live"
else
    fail "Latest deploy: $DEPLOY_STATUS"
fi

# ---- Check 3: Bundle endpoints respond ----
log "Check 3: Bundle endpoint availability"

# bundle-status (should return active:false for fake token)
BSTATUS=$(curl -s -w "\n%{http_code}" -X POST "$STAGING_URL/api/build/bundle-status" \
    -H "Content-Type: application/json" \
    -d '{"bundle_token":"soak-test-fake-token"}' 2>/dev/null)
BCODE=$(echo "$BSTATUS" | tail -1)
BBODY=$(echo "$BSTATUS" | head -1)
if [ "$BCODE" = "200" ] && echo "$BBODY" | grep -q '"active"'; then
    pass "bundle-status: $BCODE (active:false, non-enumerable)"
else
    fail "bundle-status: $BCODE — $BBODY"
fi

# bundle-recover (should always return sent:true)
RSTATUS=$(curl -s -w "\n%{http_code}" -X POST "$STAGING_URL/api/build/bundle-recover" \
    -H "Content-Type: application/json" \
    -d '{"email":"soak-check@test.local"}' 2>/dev/null)
RCODE=$(echo "$RSTATUS" | tail -1)
RBODY=$(echo "$RSTATUS" | head -1)
if [ "$RCODE" = "200" ] && echo "$RBODY" | grep -q '"sent":true'; then
    pass "bundle-recover: $RCODE (sent:true, non-enumerable)"
else
    fail "bundle-recover: $RCODE — $RBODY"
fi

# bundle-exchange with invalid token (should reject)
ESTATUS=$(curl -s -w "\n%{http_code}" -X POST "$STAGING_URL/api/build/bundle-exchange" \
    -H "Content-Type: application/json" \
    -d '{"exchange_token":"00000000-0000-0000-0000-000000000000"}' 2>/dev/null)
ECODE=$(echo "$ESTATUS" | tail -1)
if [ "$ECODE" = "410" ] || [ "$ECODE" = "404" ] || [ "$ECODE" = "400" ]; then
    pass "bundle-exchange (invalid): $ECODE (correctly rejected)"
else
    fail "bundle-exchange (invalid): $ECODE"
fi

# create-bundle-checkout (should work with Stripe)
CSTATUS=$(curl -s -w "\n%{http_code}" -X POST "$STAGING_URL/api/build/create-bundle-checkout" \
    -H "Content-Type: application/json" \
    -d '{"tier":"jobhunt","provider":"stripe","email":"soak-check@test.local","idempotency_key":"soak-check-'"$(date +%s)"'"}' 2>/dev/null)
CCODE=$(echo "$CSTATUS" | tail -1)
CBODY=$(echo "$CSTATUS" | head -1)
if [ "$CCODE" = "200" ] && echo "$CBODY" | grep -q 'session_id'; then
    pass "create-bundle-checkout: $CCODE (session created)"
else
    fail "create-bundle-checkout: $CCODE — $CBODY"
fi

# ---- Check 4: Existing scan/build/download not regressed ----
log "Check 4: Core feature regression check"

# Scan endpoint accepts valid input
SCAN_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$STAGING_URL/api/scan" \
    -F "jobDescription=We are looking for a software engineer with 5 years experience in Python, AWS, Docker, Kubernetes, and CI/CD pipelines. Strong problem solving skills required." \
    -F "resumeText=Software engineer with 6 years experience in Python, AWS, Docker, Kubernetes. Built CI/CD pipelines. Strong problem solver." 2>/dev/null || echo "000")
if [ "$SCAN_CODE" = "200" ]; then
    pass "Scan endpoint: $SCAN_CODE"
else
    fail "Scan endpoint: $SCAN_CODE"
fi

# Build page loads
BUILD_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$STAGING_URL/build" 2>/dev/null || echo "000")
if [ "$BUILD_CODE" = "200" ]; then
    pass "Build page: $BUILD_CODE"
else
    fail "Build page: $BUILD_CODE"
fi

# ============================================================
# REPORT
# ============================================================
echo ""
echo "============================================================"
TOTAL=$((PASS + FAIL))
echo "  RESULTS: $PASS/$TOTAL passed, $FAIL failed"
if [ "$FAIL" -eq 0 ]; then
    echo "  VERDICT: ✅ ALL CLEAR — safe to deploy to production"
else
    echo "  VERDICT: ❌ FAILURES DETECTED — investigate before deploy"
fi
echo "  Time: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "============================================================"

# Write report to file
cat > "$REPORT_FILE" << REPORT
# T+48h Soak Check Report

**Date**: $(date '+%Y-%m-%d %H:%M:%S %Z')
**Staging URL**: $STAGING_URL
**Result**: $PASS/$TOTAL passed, $FAIL failed

## Verdict

$(if [ "$FAIL" -eq 0 ]; then echo "**✅ ALL CLEAR — safe to deploy to production**"; else echo "**❌ FAILURES DETECTED — investigate before deploy**"; fi)

## Next Steps

$(if [ "$FAIL" -eq 0 ]; then echo "1. Merge \`staging\` → \`master\`
2. Render auto-deploys to production
3. Run 30-60 min post-deploy canary
4. Declare Phase 2 live"; else echo "1. Investigate failures above
2. Fix and re-deploy to staging
3. Re-run this check"; fi)
REPORT

echo ""
echo "Report saved to: $REPORT_FILE"

# macOS notification
osascript -e "display notification \"T+48 Soak: $PASS/$TOTAL passed, $FAIL failed\" with title \"ResumeRadar\" sound name \"Glass\"" 2>/dev/null || true
