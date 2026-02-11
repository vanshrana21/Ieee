#!/bin/bash
echo "🔍 Testing for circular import resolution..."
echo ""

# Try importing database module
echo -n "Testing database.py import... "
python3 -c "from backend.database import Base, engine, SessionLocal; print('✓ database.py imports successfully')" 2>&1
if [ $? -eq 0 ]; then
    echo "✅ PASSED: database.py imports cleanly"
else
    echo "❌ FAILED: database.py has import error"
    exit 1
fi

# Try importing competition model
echo -n "Testing competition.py import... "
python3 -c "from backend.orm.competition import Competition; print('✓ competition.py imports successfully')" 2>&1
if [ $? -eq 0 ]; then
    echo "✅ PASSED: competition.py imports cleanly"
else
    echo "❌ FAILED: competition.py has import error"
    exit 1
fi

# Try importing team model
echo -n "Testing team.py import... "
python3 -c "from backend.orm.team import Team, TeamMember; print('✓ team.py imports successfully')" 2>&1
if [ $? -eq 0 ]; then
    echo "✅ PASSED: team.py imports cleanly"
else
    echo "❌ FAILED: team.py has import error"
    exit 1
fi

# Try importing memorial model
echo -n "Testing memorial.py import... "
python3 -c "from backend.orm.memorial import MemorialSubmission; print('✓ memorial.py imports successfully')" 2>&1
if [ $? -eq 0 ]; then
    echo "✅ PASSED: memorial.py imports cleanly"
else
    echo "❌ FAILED: memorial.py has import error"
    exit 1
fi

# Try importing oral_round model
echo -n "Testing oral_round.py import... "
python3 -c "from backend.orm.oral_round import OralRound; print('✓ oral_round.py imports successfully')" 2>&1
if [ $? -eq 0 ]; then
    echo "✅ PASSED: oral_round.py imports cleanly"
else
    echo "❌ FAILED: oral_round.py has import error"
    exit 1
fi

echo ""
echo "✅ ALL CIRCULAR IMPORT TESTS PASSED"
echo "Next: Restart backend with 'cd backend && python main.py'"
