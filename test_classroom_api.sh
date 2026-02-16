#!/bin/bash
# Test Classroom API Endpoints
# This script tests the complete classroom flow

API_BASE="http://127.0.0.1:8000"
DB_PATH="./legalai.db"

echo "=== Classroom API Test Suite ==="
echo

# Check database exists
if [ ! -f "$DB_PATH" ]; then
    echo "❌ Database not found at $DB_PATH"
    exit 1
fi

echo "✓ Database found at $DB_PATH"

# Check classroom_sessions table exists
echo "Checking database schema..."
sqlite3 "$DB_PATH" "SELECT name FROM sqlite_master WHERE type='table' AND name='classroom_sessions';" | grep classroom_sessions > /dev/null
if [ $? -eq 0 ]; then
    echo "✓ classroom_sessions table exists"
else
    echo "❌ classroom_sessions table missing"
    exit 1
fi

# Check is_active column exists
sqlite3 "$DB_PATH" "PRAGMA table_info(classroom_sessions);" | grep is_active > /dev/null
if [ $? -eq 0 ]; then
    echo "✓ is_active column exists"
else
    echo "❌ is_active column missing"
    exit 1
fi

echo
echo "=== Testing API Endpoints ==="

# Test 1: Create session (should work without auth for testing)
echo "Test 1: Creating a new session..."
CREATE_RESPONSE=$(curl -s -X POST "$API_BASE/api/classroom/sessions" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Test Session - Right to Privacy",
    "category": "constitutional",
    "max_participants": 40,
    "prep_time_minutes": 15,
    "oral_time_minutes": 10,
    "ai_judge_mode": "hybrid"
  }')

echo "Create Response: $CREATE_RESPONSE"

# Extract session code
SESSION_CODE=$(echo "$CREATE_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('session_code', ''))
except:
    print('')
")

if [ -n "$SESSION_CODE" ]; then
    echo "✓ Session created with code: $SESSION_CODE"
else
    echo "❌ Failed to create session"
    echo "Response: $CREATE_RESPONSE"
fi

echo

# Test 2: List all sessions (debug endpoint)
echo "Test 2: Listing all sessions..."
DEBUG_RESPONSE=$(curl -s "$API_BASE/api/classroom/debug/sessions")
echo "Debug Response: $DEBUG_RESPONSE"

# Count sessions
SESSION_COUNT=$(echo "$DEBUG_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('total_sessions', 0))
except:
    print(0)
")

echo "✓ Total sessions in database: $SESSION_COUNT"

echo

# Test 3: Join session (if we have a session code)
if [ -n "$SESSION_CODE" ]; then
    echo "Test 3: Joining session with code: $SESSION_CODE"
    JOIN_RESPONSE=$(curl -s -X POST "$API_BASE/api/classroom/sessions/join" \
      -H "Content-Type: application/json" \
      -d "{\"session_code\": \"$SESSION_CODE\"}")
    
    echo "Join Response: $JOIN_RESPONSE"
    
    # Check if join was successful
    JOIN_SUCCESS=$(echo "$JOIN_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if 'session_code' in data:
        print('SUCCESS')
    else:
        print('FAILED')
except:
    print('ERROR')
")
    
    if [ "$JOIN_SUCCESS" = "SUCCESS" ]; then
        echo "✓ Successfully joined session"
    else
        echo "❌ Failed to join session"
    fi
else
    echo "⚠️ Skipping join test - no session code available"
fi

echo

# Test 4: Get specific session by code (if we have one)
if [ -n "$SESSION_CODE" ]; then
    echo "Test 4: Getting session by code: $SESSION_CODE"
    GET_RESPONSE=$(curl -s "$API_BASE/api/classroom/debug/session/$SESSION_CODE")
    echo "Get Response: $GET_RESPONSE"
    
    # Check if session was found
    GET_SUCCESS=$(echo "$GET_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if 'session_code' in data and data['session_code'] == '$SESSION_CODE':
        print('SUCCESS')
    else:
        print('NOT_FOUND')
except:
    print('ERROR')
")
    
    if [ "$GET_SUCCESS" = "SUCCESS" ]; then
        echo "✓ Session retrieved successfully"
    else
        echo "⚠️ Session not found or error"
    fi
fi

echo
echo "=== Database Verification ==="
echo "Checking sessions in database..."
sqlite3 "$DB_PATH" "SELECT id, session_code, topic, is_active FROM classroom_sessions ORDER BY id DESC LIMIT 5;"

echo
echo "=== Test Complete ==="
