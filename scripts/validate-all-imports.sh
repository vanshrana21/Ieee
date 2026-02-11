#!/bin/bash
echo "🔍 Validating ALL ORM imports..."
errors=0

test_import() {
    if python3 -c "$1" 2>/dev/null; then
        echo "✅ $2"
    else
        echo "❌ $2"
        errors=$((errors+1))
    fi
}

test_import "from backend.orm.team import TeamInvitation, TeamAuditLog, InvitationStatus" "Team placeholders"
test_import "from backend.orm.competition import CompetitionRound" "CompetitionRound"
test_import "from backend.orm.oral_round import OralResponse, BenchQuestion, RoundTranscript, RoundStage, RoundStatus" "Oral round placeholders"
test_import "from backend.orm.moot_project import MootProjectRound, MootProjectSubmission" "MootProject placeholders"
test_import "from backend.orm.submission import SubmissionVersion, SubmissionReview" "Submission placeholders"
test_import "from backend.routes.competitions import router" "Competition routes"

echo ""
if [ $errors -eq 0 ]; then
    echo "✅ ALL IMPORTS VALIDATED SUCCESSFULLY"
    exit 0
else
    echo "❌ $errors IMPORT(S) FAILED"
    exit 1
fi
