#!/bin/bash
echo "✅ Validating Phase 2 Competition Infrastructure"
echo "==============================================="

ERRORS=0

# Check database tables
echo -n "Checking database tables... "
if sqlite3 legalai.db ".tables" | grep -q "competitions"; then
    echo "✓ competitions table exists"
else
    echo "✗ competitions table MISSING"
    ERRORS=$((ERRORS+1))
fi

if sqlite3 legalai.db ".tables" | grep -q "teams"; then
    echo "✓ teams table exists"
else
    echo "✗ teams table MISSING"
    ERRORS=$((ERRORS+1))
fi

if sqlite3 legalai.db ".tables" | grep -q "memorial_submissions"; then
    echo "✓ memorial_submissions table exists"
else
    echo "✗ memorial_submissions table MISSING"
    ERRORS=$((ERRORS+1))
fi

# Check upload directory
echo -n "Checking upload directory... "
if [ -d "uploads/memorials" ]; then
    echo "✓ uploads/memorials directory exists"
else
    mkdir -p uploads/memorials
    echo "✓ Created uploads/memorials directory"
fi

# Check API routes file
echo -n "Checking competition routes... "
if [ -f "backend/routes/competitions.py" ]; then
    echo "✓ competitions.py exists"
else
    echo "✗ competitions.py MISSING"
    ERRORS=$((ERRORS+1))
fi

# Final result
if [ $ERRORS -eq 0 ]; then
    echo ""
    echo "==============================================="
    echo "✅ ALL PHASE 2 VALIDATIONS PASSED"
    echo "Next: Restart backend and test competition flow"
    exit 0
else
    echo ""
    echo "==============================================="
    echo "❌ $ERRORS VALIDATION(S) FAILED"
    exit 1
fi
