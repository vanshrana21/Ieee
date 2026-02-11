#!/bin/bash
# AI Moot Court Frontend Integration Test Script

set -e

API_BASE="http://localhost:8000"
FRONTEND_BASE="http://localhost:3000"

echo "🧪 AI Moot Court Frontend Integration Test"
echo "============================================"

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counters
PASSED=0
FAILED=0

# Helper function for tests
test_step() {
    local name="$1"
    local cmd="$2"
    
    echo -n "  Testing $name... "
    if eval "$cmd" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC}"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}✗${NC}"
        ((FAILED++))
        return 1
    fi
}

echo ""
echo "1. Testing Backend Health"
echo "---------------------------"
test_step "API is running" "curl -s $API_BASE/api/health | grep -q 'healthy\|ok' || curl -s -o /dev/null -w '%{http_code}' $API_BASE/api/health | grep -q '200'"
test_step "Auth endpoint exists" "curl -s -o /dev/null -w '%{http_code}' $API_BASE/api/auth/login | grep -q '405\|200\|422'"
test_step "AI Moot endpoints exist" "curl -s -o /dev/null -w '%{http_code}' $API_BASE/api/ai-moot/sessions | grep -q '401\|403\|200'"

echo ""
echo "2. Testing Frontend Files"
echo "-------------------------"
test_step "login.html exists" "[ -f /Users/vanshrana/Desktop/IEEE/html/login.html ]"
test_step "ai-practice.html exists" "[ -f /Users/vanshrana/Desktop/IEEE/html/ai-practice.html ]"
test_step "auth.js exists" "[ -f /Users/vanshrana/Desktop/IEEE/js/auth.js ]"
test_step "ai-judge-interface.js exists" "[ -f /Users/vanshrana/Desktop/IEEE/js/ai-judge-interface.js ]"
test_step "ai-practice.css exists" "[ -f /Users/vanshrana/Desktop/IEEE/css/ai-practice.css ]"

echo ""
echo "3. Testing JavaScript Functions"
echo "--------------------------------"
test_step "AIJudgeInterface class defined" "grep -q 'class AIJudgeInterface' /Users/vanshrana/Desktop/IEEE/js/ai-judge-interface.js"
test_step "init() method exists" "grep -q 'init()' /Users/vanshrana/Desktop/IEEE/js/ai-judge-interface.js"
test_step "startSession() method exists" "grep -q 'async startSession' /Users/vanshrana/Desktop/IEEE/js/ai-judge-interface.js"
test_step "submitArgument() method exists" "grep -q 'async submitArgument' /Users/vanshrana/Desktop/IEEE/js/ai-judge-interface.js"
test_step "displayFeedback() method exists" "grep -q 'displayFeedback' /Users/vanshrana/Desktop/IEEE/js/ai-judge-interface.js"

echo ""
echo "4. Testing Auth Token Management"
echo "---------------------------------"
test_step "getAuthToken() exists" "grep -q 'getAuthToken()' /Users/vanshrana/Desktop/IEEE/js/ai-judge-interface.js"
test_step "localStorage token key" "grep -q 'access_token' /Users/vanshrana/Desktop/IEEE/js/auth.js"
test_step "setToken() in auth.js" "grep -q 'function setToken' /Users/vanshrana/Desktop/IEEE/js/auth.js"

echo ""
echo "5. Testing UI Elements in HTML"
echo "------------------------------"
test_step "role-selection container" "grep -q 'id=\"role-selection\"' /Users/vanshrana/Desktop/IEEE/html/ai-practice.html"
test_step "argument-section container" "grep -q 'id=\"argument-section\"' /Users/vanshrana/Desktop/IEEE/html/ai-practice.html"
test_step "petitioner button" "grep -q 'id=\"petitioner-btn\"' /Users/vanshrana/Desktop/IEEE/html/ai-practice.html"
test_step "respondent button" "grep -q 'id=\"respondent-btn\"' /Users/vanshrana/Desktop/IEEE/html/ai-practice.html"
test_step "argument input" "grep -q 'id=\"argument-input\"' /Users/vanshrana/Desktop/IEEE/html/ai-practice.html"
test_step "submit argument button" "grep -q 'id=\"submit-argument-btn\"' /Users/vanshrana/Desktop/IEEE/html/ai-practice.html"
test_step "feedback container" "grep -q 'id=\"feedback-container\"' /Users/vanshrana/Desktop/IEEE/html/ai-practice.html"
test_step "loading spinner" "grep -q 'id=\"loading-spinner\"' /Users/vanshrana/Desktop/IEEE/html/ai-practice.html"

echo ""
echo "6. Testing CSS Classes"
echo "---------------------"
test_step "role-selection styles" "grep -q '.role-selection' /Users/vanshrana/Desktop/IEEE/css/ai-practice.css"
test_step "role-card styles" "grep -q '.role-card' /Users/vanshrana/Desktop/IEEE/css/ai-practice.css"
test_step "argument-section styles" "grep -q '.argument-section' /Users/vanshrana/Desktop/IEEE/css/ai-practice.css"
test_step "feedback styles" "grep -q '.feedback' /Users/vanshrana/Desktop/IEEE/css/ai-practice.css"
test_step "hidden class" "grep -q '.hidden' /Users/vanshrana/Desktop/IEEE/css/ai-practice.css"
test_step "spinner styles" "grep -q '.spinner' /Users/vanshrana/Desktop/IEEE/css/ai-practice.css || grep -q '.ai-spinner' /Users/vanshrana/Desktop/IEEE/css/ai-practice.css"

echo ""
echo "7. Testing API Integration Points"
echo "----------------------------------"
test_step "API_BASE_URL defined" "grep -q 'API_BASE_URL\|localhost:8000' /Users/vanshrana/Desktop/IEEE/js/ai-judge-interface.js"
test_step "Session endpoint" "grep -q '/api/ai-moot/sessions' /Users/vanshrana/Desktop/IEEE/js/ai-judge-interface.js"
test_step "Turns endpoint" "grep -q '/api/ai-moot/sessions' /Users/vanshrana/Desktop/IEEE/js/ai-judge-interface.js && grep -q '/turns' /Users/vanshrana/Desktop/IEEE/js/ai-judge-interface.js"
test_step "Authorization header" "grep -q 'Authorization' /Users/vanshrana/Desktop/IEEE/js/ai-judge-interface.js"
test_step "Content-Type header" "grep -q 'Content-Type.*application/json' /Users/vanshrana/Desktop/IEEE/js/ai-judge-interface.js"

echo ""
echo "8. Testing Error Handling"
echo "-------------------------"
test_step "Token expiry redirect" "grep -q 'login.html' /Users/vanshrana/Desktop/IEEE/js/ai-judge-interface.js"
test_step "Error alerts" "grep -q 'alert.*error\|catch.*error' /Users/vanshrana/Desktop/IEEE/js/ai-judge-interface.js"
test_step "Loading state management" "grep -q 'showLoading' /Users/vanshrana/Desktop/IEEE/js/ai-judge-interface.js"

echo ""
echo "============================================"
echo -e "Test Results: ${GREEN}$PASSED passed${NC}, ${RED}$FAILED failed${NC}"

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All integration tests passed!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Start backend: cd /Users/vanshrana/Desktop/IEEE/backend && python main.py"
    echo "  2. Start frontend: ./scripts/serve.sh"
    echo "  3. Open browser: http://localhost:3000/html/login.html"
    exit 0
else
    echo -e "${RED}✗ Some tests failed. Please review the issues above.${NC}"
    exit 1
fi
