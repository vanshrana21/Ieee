#!/bin/bash
#
# Manual Round Engine Flow Demo — Phase 3
#
# This script demonstrates a complete round flow using curl.
# Run this with: bash backend/tests/manual_round_flow.sh
#

set -e  # Exit on error

echo "=========================================="
echo "Phase 3 Round Engine — Manual Flow Demo"
echo "=========================================="
echo ""

# Configuration
BASE_URL="http://127.0.0.1:8000"
FACULTY_EMAIL="faculty@gmail.com"
FACULTY_PASS="password123"
STUDENT1_EMAIL="student1@gmail.com"
STUDENT1_PASS="password123"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}Step 1: Faculty Login${NC}"
echo "----------------------------------------"

FACULTY_TOKEN=$(curl -s -X POST "${BASE_URL}/api/auth/login" \
    -d "username=${FACULTY_EMAIL}" \
    -d "password=${FACULTY_PASS}" | \
    python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null || echo "")

if [ -z "$FACULTY_TOKEN" ]; then
    echo "❌ Faculty login failed"
    exit 1
fi

echo "✓ Faculty logged in (token: ${FACULTY_TOKEN:0:20}...)"
echo ""

echo -e "${BLUE}Step 2: Student Login${NC}"
echo "----------------------------------------"

STUDENT1_TOKEN=$(curl -s -X POST "${BASE_URL}/api/auth/login" \
    -d "username=${STUDENT1_EMAIL}" \
    -d "password=${STUDENT1_PASS}" | \
    python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null || echo "")

if [ -z "$STUDENT1_TOKEN" ]; then
    echo "❌ Student login failed"
    exit 1
fi

echo "✓ Student 1 logged in (token: ${STUDENT1_TOKEN:0:20}...)"
echo ""

echo -e "${BLUE}Step 3: Create Classroom Session${NC}"
echo "----------------------------------------"

SESSION_RESPONSE=$(curl -s -X POST "${BASE_URL}/api/classroom/sessions" \
    -H "Authorization: Bearer ${FACULTY_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{
        "case_id": 1,
        "topic": "Demo Round Engine",
        "category": "Demo",
        "prep_time_minutes": 5,
        "oral_time_minutes": 10
    }')

SESSION_ID=$(echo "$SESSION_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null || echo "")
SESSION_CODE=$(echo "$SESSION_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('session_code', ''))" 2>/dev/null || echo "")

if [ -z "$SESSION_ID" ]; then
    echo "❌ Session creation failed"
    echo "Response: $SESSION_RESPONSE"
    exit 1
fi

echo "✓ Session created: ID=$SESSION_ID, Code=$SESSION_CODE"
echo ""

echo -e "${BLUE}Step 4: Student Joins Session${NC}"
echo "----------------------------------------"

JOIN_RESPONSE=$(curl -s -X POST "${BASE_URL}/api/classroom/sessions/join" \
    -H "Authorization: Bearer ${STUDENT1_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"session_code\": \"${SESSION_CODE}\"}")

PARTICIPANT_ID=$(echo "$JOIN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('user_id', '') or json.load(sys.stdin).get('participant_id', ''))" 2>/dev/null || echo "")

if [ -z "$PARTICIPANT_ID" ]; then
    echo "❌ Student join failed"
    echo "Response: $JOIN_RESPONSE"
    exit 1
fi

echo "✓ Student joined: Participant ID=$PARTICIPANT_ID"
echo ""

echo -e "${BLUE}Step 5: Transition to PREPARING${NC}"
echo "----------------------------------------"

TRANSITION_RESPONSE=$(curl -s -X POST "${BASE_URL}/api/classroom/sessions/${SESSION_ID}/transition" \
    -H "Authorization: Bearer ${FACULTY_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{
        "target_state": "PREPARING",
        "reason": "Demo"
    }')

echo "✓ Session transitioned to PREPARING"
echo ""

echo -e "${BLUE}Step 6: Create Round${NC}"
echo "----------------------------------------"

ROUND_RESPONSE=$(curl -s -X POST "${BASE_URL}/api/classroom/rounds" \
    -H "Authorization: Bearer ${FACULTY_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{
        \"session_id\": ${SESSION_ID},
        \"round_index\": 1,
        \"round_type\": \"PETITIONER_MAIN\",
        \"default_turn_seconds\": 60
    }")

ROUND_ID=$(echo "$ROUND_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null || echo "")

if [ -z "$ROUND_ID" ]; then
    echo "❌ Round creation failed"
    echo "Response: $ROUND_RESPONSE"
    exit 1
fi

echo "✓ Round created: ID=$ROUND_ID"
echo ""

echo "Round details:"
echo "$ROUND_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$ROUND_RESPONSE"
echo ""

echo -e "${BLUE}Step 7: Start Round${NC}"
echo "----------------------------------------"

START_RESPONSE=$(curl -s -X POST "${BASE_URL}/api/classroom/rounds/${ROUND_ID}/start" \
    -H "Authorization: Bearer ${FACULTY_TOKEN}")

echo "Start response:"
echo "$START_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$START_RESPONSE"
echo ""

echo -e "${BLUE}Step 8: Get Round Details (with turns)${NC}"
echo "----------------------------------------"

GET_RESPONSE=$(curl -s -X GET "${BASE_URL}/api/classroom/rounds/${ROUND_ID}" \
    -H "Authorization: Bearer ${FACULTY_TOKEN}")

echo "Round details:"
echo "$GET_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$GET_RESPONSE"
echo ""

echo -e "${YELLOW}Note: To continue the demo, you need:${NC}"
echo "1. A second student to join the session"
echo "2. Students to start their turns via:"
echo "   curl -X POST ${BASE_URL}/api/classroom/turns/{turn_id}/start -H 'Authorization: Bearer {token}'"
echo "3. Students to submit their turns via:"
echo "   curl -X POST ${BASE_URL}/api/classroom/turns/{turn_id}/submit -H 'Authorization: Bearer {token}' -d '{...}'"
echo ""

echo -e "${BLUE}Step 9: List Session Rounds${NC}"
echo "----------------------------------------"

LIST_RESPONSE=$(curl -s -X GET "${BASE_URL}/api/classroom/sessions/${SESSION_ID}/rounds" \
    -H "Authorization: Bearer ${FACULTY_TOKEN}")

echo "Rounds list:"
echo "$LIST_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$LIST_RESPONSE"
echo ""

echo -e "${GREEN}✅ Demo complete!${NC}"
echo ""
echo "Summary:"
echo "  - Session ID: $SESSION_ID"
echo "  - Session Code: $SESSION_CODE"
echo "  - Round ID: $ROUND_ID"
echo ""
echo "Next steps:"
echo "  1. Have more students join with:"
echo "     curl -X POST ${BASE_URL}/api/classroom/sessions/join -H 'Authorization: Bearer {token}' -d '{\"session_code\": \"${SESSION_CODE}\"}'"
echo "  2. Start and submit turns as described above"
echo "  3. Faculty can force submit with:"
echo "     curl -X POST ${BASE_URL}/api/classroom/turns/{turn_id}/force_submit -H 'Authorization: Bearer ${FACULTY_TOKEN}' -d '{...}'"
echo ""
