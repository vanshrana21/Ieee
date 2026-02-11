#!/bin/bash
echo "🔍 Testing oral round ORM imports..."
python3 -c "
from backend.orm.oral_round import (
    OralRound, OralResponse, BenchQuestion, 
    RoundTranscript, RoundStage, RoundStatus
)
print('✅ All oral round ORM classes import successfully')
" 2>&1 && exit 0 || echo "❌ Import failed" && exit 1
