#!/bin/bash
# Windsurf Full System Architecture Audit — Master Script
# Executes complete test suite for Phases 14-21

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUN_ID=$(date +%Y%m%d_%H%M%S)
ARTIFACTS_DIR="${PROJECT_ROOT}/artifacts/${RUN_ID}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Windsurf Full System Architecture Audit — Master Script   ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Run ID: $RUN_ID"
echo "Artifacts: $ARTIFACTS_DIR"
echo ""

# Create artifacts directory
mkdir -p "$ARTIFACTS_DIR"

# Initialize results JSON
cat > "$ARTIFACTS_DIR/results.json" << 'EOF'
{
  "run_id": "__RUN_ID__",
  "date": "__DATE__",
  "branch": "__BRANCH__",
  "commit": "__COMMIT__",
  "env": "__ENV__",
  "tester": "windsurf",
  "unit_status": "NOT_RUN",
  "integration_status": "NOT_RUN",
  "determinism_status": "NOT_RUN",
  "concurrency_status": "NOT_RUN",
  "crash_status": "NOT_RUN",
  "load_status": "NOT_RUN",
  "security_status": "NOT_RUN",
  "e2e_status": "NOT_RUN",
  "obs_status": "NOT_RUN",
  "dr_status": "NOT_RUN",
  "overall_status": "INCOMPLETE",
  "artifacts_path": "__ARTIFACTS__"
}
EOF

# Replace placeholders
sed -i.bak "s|__RUN_ID__|$RUN_ID|g" "$ARTIFACTS_DIR/results.json"
sed -i.bak "s|__DATE__|$(date -u +%Y-%m-%dT%H:%M:%SZ)|g" "$ARTIFACTS_DIR/results.json"
sed -i.bak "s|__BRANCH__|$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')|g" "$ARTIFACTS_DIR/results.json"
sed -i.bak "s|__COMMIT__|$(git rev-parse HEAD 2>/dev/null || echo 'unknown')|g" "$ARTIFACTS_DIR/results.json"
sed -i.bak "s|__ENV__|${ENVIRONMENT:-local}|g" "$ARTIFACTS_DIR/results.json"
sed -i.bak "s|__ARTIFACTS__|$ARTIFACTS_DIR|g" "$ARTIFACTS_DIR/results.json"
rm "$ARTIFACTS_DIR/results.json.bak"

# Function to update result status
update_status() {
    local key=$1
    local value=$2
    local file="$ARTIFACTS_DIR/results.json"
    
    # Use Python for JSON manipulation (more reliable than sed)
    python3 << EOF
import json
with open('$file', 'r') as f:
    data = json.load(f)
data['$key'] = '$value'
with open('$file', 'w') as f:
    json.dump(data, f, indent=2)
EOF
}

# Track overall status
OVERALL_PASS=true

# ============================================================================
# STAGE 0: Environment Snapshot
# ============================================================================

echo -e "${YELLOW}▶ Stage 0: Environment Snapshot${NC}"
if ./scripts/snapshot_env.sh > "$ARTIFACTS_DIR/snapshot.log" 2>&1; then
    echo -e "  ${GREEN}✓ Environment snapshot captured${NC}"
else
    echo -e "  ${YELLOW}⚠ Environment snapshot had issues (see snapshot.log)${NC}"
fi

# ============================================================================
# STAGE 1: Unit & Component Tests
# ============================================================================

echo -e "${YELLOW}▶ Stage 1: Unit & Component Tests${NC}"
cd "$PROJECT_ROOT"

if pytest -q --maxfail=3 backend/tests/test_phase*.py 2>&1 | tee "$ARTIFACTS_DIR/unit_tests.log"; then
    echo -e "  ${GREEN}✓ Unit tests passed${NC}"
    update_status "unit_status" "PASS"
    update_status "unit_details" "All unit tests passed"
else
    echo -e "  ${RED}✗ Unit tests failed${NC}"
    update_status "unit_status" "FAIL"
    update_status "unit_details" "See unit_tests.log"
    OVERALL_PASS=false
fi

# Count test results
UNIT_TESTS_PASSED=$(grep -c "passed" "$ARTIFACTS_DIR/unit_tests.log" 2>/dev/null || echo "0")
echo -e "  ${BLUE}  Tests passed: $UNIT_TESTS_PASSED${NC}"

# ============================================================================
# STAGE 2: Integration Tests (if available)
# ============================================================================

echo -e "${YELLOW}▶ Stage 2: Integration Tests${NC}"

if [ -f "backend/tests/test_integration_flows.py" ]; then
    if pytest -q backend/tests/test_integration_*.py 2>&1 | tee "$ARTIFACTS_DIR/integration_tests.log"; then
        echo -e "  ${GREEN}✓ Integration tests passed${NC}"
        update_status "integration_status" "PASS"
    else
        echo -e "  ${RED}✗ Integration tests failed${NC}"
        update_status "integration_status" "FAIL"
        OVERALL_PASS=false
    fi
else
    echo -e "  ${YELLOW}⚠ No integration tests found, skipping${NC}"
    update_status "integration_status" "SKIPPED"
fi

# ============================================================================
# STAGE 3: Determinism & Integrity Audits
# ============================================================================

echo -e "${YELLOW}▶ Stage 3: Determinism & Integrity Audits${NC}"

if python3 scripts/run_determinism_audits.py --output "$ARTIFACTS_DIR/determinism" 2>&1 | tee "$ARTIFACTS_DIR/determinism.log"; then
    echo -e "  ${GREEN}✓ Determinism audits passed${NC}"
    update_status "determinism_status" "PASS"
else
    echo -e "  ${RED}✗ Determinism audits failed${NC}"
    update_status "determinism_status" "FAIL"
    OVERALL_PASS=false
fi

# ============================================================================
# STAGE 4: Concurrency Tests
# ============================================================================

echo -e "${YELLOW}▶ Stage 4: Concurrency Tests${NC}"

# Test health endpoint (safe test)
if python3 scripts/concurrency_harness.py \
    --concurrency 20 \
    --endpoint "/api/admin/health" \
    --output "$ARTIFACTS_DIR/concurrency" \
    --test-name health_check 2>&1 | tee "$ARTIFACTS_DIR/concurrency.log"; then
    echo -e "  ${GREEN}✓ Concurrency tests passed${NC}"
    update_status "concurrency_status" "PASS"
else
    echo -e "  ${RED}✗ Concurrency tests failed${NC}"
    update_status "concurrency_status" "FAIL"
    OVERALL_PASS=false
fi

# ============================================================================
# STAGE 5: Crash Recovery (Manual for now)
# ============================================================================

echo -e "${YELLOW}▶ Stage 5: Crash Recovery Tests${NC}"
echo -e "  ${YELLOW}⚠ Manual verification required (see runbook)${NC}"
update_status "crash_status" "MANUAL"

# ============================================================================
# STAGE 6: Load Tests (if k6 available)
# ============================================================================

echo -e "${YELLOW}▶ Stage 6: Load Tests${NC}"

if command -v k6 &> /dev/null; then
    if k6 run --summary-export="$ARTIFACTS_DIR/k6_summary.json" perf/k6/rankings_test.js 2>&1 | tee "$ARTIFACTS_DIR/k6.log"; then
        echo -e "  ${GREEN}✓ Load tests completed${NC}"
        update_status "load_status" "COMPLETED"
        
        # Extract metrics
        if [ -f "$ARTIFACTS_DIR/k6_summary.json" ]; then
            P95=$(python3 -c "import json; d=json.load(open('$ARTIFACTS_DIR/k6_summary.json')); print(d.get('metrics', {}).get('http_req_duration', {}).get('p(95)', 0))" 2>/dev/null || echo "0")
            echo -e "  ${BLUE}  p95 latency: ${P95}ms${NC}"
        fi
    else
        echo -e "  ${RED}✗ Load tests failed${NC}"
        update_status "load_status" "FAIL"
    fi
else
    echo -e "  ${YELLOW}⚠ k6 not installed, skipping load tests${NC}"
    echo -e "  ${YELLOW}  Install: brew install k6 (mac) or sudo apt-get install k6 (linux)${NC}"
    update_status "load_status" "SKIPPED"
fi

# ============================================================================
# STAGE 7: Security Tests
# ============================================================================

echo -e "${YELLOW}▶ Stage 7: Security Tests${NC}"

# Basic security check: scan for secrets in logs
if grep -r "api_key\|password\|secret\|token" artifacts/logs/ 2>/dev/null; then
    echo -e "  ${RED}✗ Potential secrets found in logs${NC}"
    update_status "security_status" "WARNING"
else
    echo -e "  ${GREEN}✓ No obvious secrets in logs${NC}"
    update_status "security_status" "PASS"
fi

# ============================================================================
# STAGE 8: E2E Flow
# ============================================================================

echo -e "${YELLOW}▶ Stage 8: End-to-End Flow${NC}"
echo -e "  ${YELLOW}⚠ Manual verification required (see runbook)${NC}"
update_status "e2e_status" "MANUAL"

# ============================================================================
# STAGE 9: Observability
# ============================================================================

echo -e "${YELLOW}▶ Stage 9: Observability Verification${NC}"
echo -e "  ${YELLOW}⚠ Manual verification required (see runbook)${NC}"
update_status "obs_status" "MANUAL"

# ============================================================================
# STAGE 10: Disaster Recovery
# ============================================================================

echo -e "${YELLOW}▶ Stage 10: Disaster Recovery Tests${NC}"
echo -e "  ${YELLOW}⚠ Manual verification required (see runbook)${NC}"
update_status "dr_status" "MANUAL"

# ============================================================================
# FINAL: Generate Report
# ============================================================================

echo ""
echo -e "${YELLOW}▶ Generating Final Report${NC}"

# Update overall status
if [ "$OVERALL_PASS" = true ]; then
    update_status "overall_status" "PASS"
else
    update_status "overall_status" "FAIL"
fi

# Generate markdown report
if python3 scripts/save_test_report.py "$ARTIFACTS_DIR/results.json" 2>&1 | tee "$ARTIFACTS_DIR/report_generation.log"; then
    echo -e "  ${GREEN}✓ Report generated${NC}"
else
    echo -e "  ${RED}✗ Report generation failed${NC}"
fi

# Create symlink to latest
ln -sfn "$ARTIFACTS_DIR" "${PROJECT_ROOT}/artifacts/latest"

# ============================================================================
# SUMMARY
# ============================================================================

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                      AUDIT COMPLETE                        ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Run ID: $RUN_ID"
echo "Artifacts: $ARTIFACTS_DIR"
echo "Latest symlink: artifacts/latest -> $RUN_ID"
echo ""

# Print status summary
python3 << EOF
import json
with open('$ARTIFACTS_DIR/results.json', 'r') as f:
    data = json.load(f)

print("Status Summary:")
print(f"  Overall: {data.get('overall_status', 'UNKNOWN')}")
print(f"  Unit Tests: {data.get('unit_status', 'UNKNOWN')}")
print(f"  Integration: {data.get('integration_status', 'UNKNOWN')}")
print(f"  Determinism: {data.get('determinism_status', 'UNKNOWN')}")
print(f"  Concurrency: {data.get('concurrency_status', 'UNKNOWN')}")
print(f"  Load Tests: {data.get('load_status', 'UNKNOWN')}")
print(f"  Security: {data.get('security_status', 'UNKNOWN')}")
EOF

echo ""
echo -e "${GREEN}Final Report:${NC}"
ls -1 "$ARTIFACTS_DIR"/windsurf_test_report_*.md 2>/dev/null || echo "  Report not found"
echo ""

# Determine exit code
if [ "$OVERALL_PASS" = true ]; then
    echo -e "${GREEN}✓ All automated tests passed!${NC}"
    echo -e "${YELLOW}Note: Manual tests (crash, E2E, observability, DR) require separate verification${NC}"
    exit 0
else
    echo -e "${RED}✗ Some tests failed. Review logs in $ARTIFACTS_DIR${NC}"
    echo -e "${YELLOW}Run triage: python3 scripts/triage_failures.py --input $ARTIFACTS_DIR/results.json${NC}"
    exit 1
fi
