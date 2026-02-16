# Phase 4: AI Judge Engine — Implementation & API Documentation

## Overview

The AI Judge Engine provides structured, weighted rubric-based evaluation of moot court arguments using LLMs. It ensures:

- **Deterministic scoring**: Same inputs → same outputs (for same AI version)
- **Immutability**: Frozen rubric versions, append-only audit trail
- **Full audit trail**: Every evaluation attempt and faculty action logged
- **Robust validation**: Strict JSON schema enforcement with retries
- **Faculty oversight**: Override capabilities with justification requirements

## Table of Contents

1. [Architecture](#architecture)
2. [Database Schema](#database-schema)
3. [API Endpoints](#api-endpoints)
4. [Feature Flags](#feature-flags)
5. [Rubric System](#rubric-system)
6. [LLM Contract](#llm-contract)
7. [Retry & Safety Policy](#retry--safety-policy)
8. [Faculty Override Flow](#faculty-override-flow)
9. [Examples](#examples)
10. [Migration & Rollback](#migration--rollback)
11. [Testing](#testing)
12. [Observability](#observability)
13. [Troubleshooting](#troubleshooting)

---

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                    AI Judge Engine                           │
├─────────────────────────────────────────────────────────────┤
│  Service Layer          │  ai_evaluation_service.py          │
│  Router Layer           │  ai_judge.py                         │
│  Validator              │  ai_judge_validator.py               │
│  LLM Adapter            │  ai_judge_llm.py                     │
│  ORM Models             │  ai_rubrics.py, ai_evaluations.py    │
│  Schemas                │  ai_judge.py (schemas)               │
└─────────────────────────────────────────────────────────────┘
```

### Concurrency Model

Per-session asyncio.Lock prevents duplicate evaluations for the same participant/round combination.

---

## Database Schema

### ai_rubrics

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment ID |
| name | VARCHAR(255) | Rubric name |
| description | TEXT | Description |
| rubric_type | VARCHAR(32) | Type (oral_argument, memorial, etc.) |
| definition_json | TEXT | Mutable JSON definition |
| current_version | INTEGER | Current version number |
| created_by_faculty_id | INTEGER FK | Creator |
| institution_id | INTEGER FK | Institution (optional) |
| created_at | DATETIME | Creation timestamp |
| updated_at | DATETIME | Last update |
| is_active | INTEGER | Soft delete flag |

### ai_rubric_versions (Immutable Snapshots)

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment ID |
| rubric_id | INTEGER FK | Source rubric |
| version_number | INTEGER | Version number |
| name | VARCHAR(255) | Snapshot name |
| frozen_json | TEXT | Immutable JSON |
| criteria_summary | VARCHAR(500) | Short summary for indexing |
| created_at | DATETIME | Snapshot timestamp |

### ai_evaluations (Core Results)

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment ID |
| session_id | INTEGER FK | Classroom session |
| round_id | INTEGER FK | Round evaluated |
| participant_id | INTEGER FK | Participant evaluated |
| turn_id | INTEGER FK | Specific turn (optional) |
| rubric_version_id | INTEGER FK | Frozen rubric used |
| final_score | DECIMAL(5,2) | Computed final score |
| score_breakdown | TEXT | JSON per-criterion scores |
| weights_used | TEXT | JSON weights applied |
| ai_model | VARCHAR(100) | LLM model name |
| ai_model_version | VARCHAR(100) | Model version |
| status | VARCHAR(32) | pending, completed, malformed, requires_review, overridden |
| canonical_attempt_id | INTEGER FK | Successful attempt |
| finalized_by_faculty_id | INTEGER FK | Override faculty (if any) |
| finalized_at | DATETIME | Finalization timestamp |

### ai_evaluation_attempts (Raw LLM Responses)

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment ID |
| evaluation_id | INTEGER FK | Parent evaluation |
| attempt_number | INTEGER | 1, 2, 3... |
| prompt_sent | TEXT | Full prompt sent to LLM |
| prompt_hash | VARCHAR(64) | SHA256 hash of prompt |
| llm_raw_response | TEXT | Raw LLM output |
| parsed_json | TEXT | Parsed JSON (if valid) |
| parse_status | VARCHAR(32) | ok, malformed, timeout, error, validation_failed |
| parse_errors | TEXT | JSON array of errors |
| ai_model | VARCHAR(100) | Model used |
| ai_model_version | VARCHAR(100) | Version |
| llm_latency_ms | INTEGER | Response time |
| llm_token_usage_input | INTEGER | Input tokens |
| llm_token_usage_output | INTEGER | Output tokens |
| is_canonical | INTEGER | 1 if successful attempt |
| created_at | DATETIME | Attempt start |
| completed_at | DATETIME | Attempt end |

### faculty_overrides (Immutable Override Records)

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment ID |
| ai_evaluation_id | INTEGER FK | Evaluation overridden |
| previous_score | DECIMAL(5,2) | Original AI score |
| new_score | DECIMAL(5,2) | Override score |
| previous_breakdown | TEXT | Original breakdown JSON |
| new_breakdown | TEXT | Override breakdown JSON |
| faculty_id | INTEGER FK | Override author |
| reason | TEXT | Required justification |
| created_at | DATETIME | Override timestamp |

### ai_evaluation_audit (Lifecycle Events)

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment ID |
| evaluation_id | INTEGER FK | Target evaluation |
| attempt_id | INTEGER FK | Related attempt (optional) |
| action | VARCHAR(32) | Event type |
| actor_user_id | INTEGER FK | User who acted |
| payload_json | TEXT | Additional context |
| created_at | DATETIME | Event timestamp |

**Audit Actions:**
- `EVALUATION_STARTED` - Evaluation triggered
- `EVALUATION_COMPLETED` - Successfully completed
- `ATTEMPT_FAILED` - LLM call failed
- `ATTEMPT_MALFORMED` - Response invalid
- `EVALUATION_REQUIRES_REVIEW` - Needs faculty intervention
- `EVALUATION_OVERRIDDEN` - Faculty override applied

---

## API Endpoints

### Rubrics

**Create Rubric**
```
POST /api/ai-judge/rubrics
Authorization: Bearer <FACULTY_TOKEN>
Content-Type: application/json

{
    "name": "Advanced Oral Argument",
    "description": "Detailed rubric for advanced mooting",
    "rubric_type": "oral_argument",
    "definition": {
        "name": "Advanced Oral Argument v1",
        "version": 1,
        "criteria": [
            {"id": "substance", "label": "Substance & Law", "weight": 0.4, "type": "numeric", "scale": [0, 100]},
            {"id": "structure", "label": "Structure & Flow", "weight": 0.2, "type": "numeric", "scale": [0, 100]},
            {"id": "citations", "label": "Use of Authorities", "weight": 0.2, "type": "numeric", "scale": [0, 100]},
            {"id": "delivery", "label": "Delivery & Demeanour", "weight": 0.2, "type": "numeric", "scale": [0, 100]}
        ],
        "instructions_for_llm": "Return ONLY JSON matching the schema: {scores: {...}, comments: {...}, pass_fail: boolean, meta: {confidence: float}}."
    }
}
```

**List Rubrics**
```
GET /api/ai-judge/rubrics?rubric_type=oral_argument
Authorization: Bearer <TOKEN>
```

### Evaluation

**Trigger Evaluation**
```
POST /api/ai-judge/sessions/{session_id}/rounds/{round_id}/evaluate
Authorization: Bearer <FACULTY_TOKEN>
Content-Type: application/json

{
    "participant_id": 101,
    "turn_id": 15,
    "rubric_version_id": 3,
    "transcript_text": null
}
```

Response (Success):
```json
{
    "evaluation_id": 42,
    "status": "completed",
    "score": 82.5,
    "breakdown": {
        "substance": 33.0,
        "structure": 16.4,
        "citations": 16.6,
        "delivery": 16.5
    },
    "ai_model": "gemini-1.5-pro",
    "ai_model_version": "2024-02"
}
```

Response (Requires Review):
```json
{
    "success": false,
    "error": "EVALUATION_FAILED",
    "message": "All 3 attempts produced invalid output",
    "requires_review": true,
    "evaluation_id": 43,
    "last_errors": ["Missing key: scores.substance", "Invalid type for citations"]
}
```

**Get Evaluation Details**
```
GET /api/ai-judge/evaluations/{evaluation_id}
Authorization: Bearer <TOKEN>
```

**List Session Evaluations**
```
GET /api/ai-judge/sessions/{session_id}/evaluations?status=completed
Authorization: Bearer <TOKEN>
```

### Faculty Override

**Create Override**
```
POST /api/ai-judge/evaluations/{evaluation_id}/override
Authorization: Bearer <FACULTY_TOKEN>
Content-Type: application/json

{
    "new_score": 85.0,
    "new_breakdown": {
        "substance": 34.0,
        "structure": 17.0,
        "citations": 17.0,
        "delivery": 17.0
    },
    "reason": "Student demonstrated exceptional understanding of recent case law developments not captured in transcript."
}
```

### Leaderboard

**Get Session Leaderboard**
```
GET /api/ai-judge/sessions/{session_id}/leaderboard
Authorization: Bearer <TOKEN>
```

Response:
```json
{
    "session_id": 7,
    "entries": [
        {
            "participant_id": 101,
            "user_id": 201,
            "user_name": "Alice Smith",
            "side": "PETITIONER",
            "speaker_number": 1,
            "final_score": 87.3,
            "rank": 1,
            "evaluations_count": 3,
            "has_override": false
        },
        {
            "participant_id": 102,
            "user_id": 202,
            "user_name": "Bob Jones",
            "side": "RESPONDENT",
            "speaker_number": 1,
            "final_score": 82.1,
            "rank": 2,
            "evaluations_count": 3,
            "has_override": true
        }
    ],
    "generated_at": "2026-02-13T16:45:00Z"
}
```

---

## Feature Flags

| Flag | Default | Description |
|------|---------|-------------|
| FEATURE_AI_JUDGE_EVALUATION | False | Enable AI Judge evaluation engine |
| FEATURE_AI_EVAL_AUTO_RETRY | True | Automatic retry on malformed responses |
| FEATURE_AI_EVAL_REQUIRES_REVIEW | True | Route failures to manual review |

Environment:
```bash
FEATURE_AI_JUDGE_EVALUATION=True
FEATURE_AI_EVAL_AUTO_RETRY=True
```

---

## Rubric System

### Rubric Definition JSON

```json
{
  "name": "Standard Oral Argument v1",
  "version": 1,
  "criteria": [
    {
      "id": "substance",
      "label": "Substance & Law",
      "weight": 0.4,
      "type": "numeric",
      "scale": [0, 100]
    },
    {
      "id": "structure",
      "label": "Structure & Flow",
      "weight": 0.2,
      "type": "numeric",
      "scale": [0, 100]
    },
    {
      "id": "citations",
      "label": "Use of Authorities",
      "weight": 0.2,
      "type": "numeric",
      "scale": [0, 100]
    },
    {
      "id": "delivery",
      "label": "Delivery & Demeanour",
      "weight": 0.2,
      "type": "numeric",
      "scale": [0, 100]
    }
  ],
  "instructions_for_llm": "Return ONLY JSON matching the schema: {scores: {substance: int, structure: int, citations: int, delivery: int}, comments: {substance: string, structure: string, citations: string, delivery: string}, pass_fail: boolean, meta: {confidence: float}}. Scores must be integers 0-100."
}
```

### Immutability

When a rubric is used in an evaluation:
1. Current definition is copied to `ai_rubric_versions`
2. Evaluation references the version ID
3. Original rubric can be edited without affecting past evaluations

---

## LLM Contract

### Expected JSON Format

```json
{
  "scores": {
    "substance": 82,
    "structure": 74,
    "citations": 90,
    "delivery": 68
  },
  "weights": {
    "substance": 0.4,
    "structure": 0.2,
    "citations": 0.2,
    "delivery": 0.2
  },
  "comments": {
    "substance": "Strong grasp of statutory interpretation...",
    "structure": "Organised, but transitions were abrupt...",
    "citations": "Used leading case law, missing recent authority...",
    "delivery": "Steady pace, some filler words."
  },
  "pass_fail": true,
  "meta": {
    "confidence": 0.87
  }
}
```

### Validation Steps

1. **Parse**: Must be valid JSON
2. **Schema**: Must match expected keys and types
3. **Ranges**: Scores must be within scale bounds
4. **Weights**: Server-side weights take precedence (logged if different)
5. **Compute**: Final score calculated server-side: `Σ(score_i × weight_i)`

---

## Retry & Safety Policy

### Configuration

- **Max Attempts**: 3
- **Auto-Retries**: 2 (on malformed or timeout)
- **Backoff**: 1s → 2s exponential
- **Timeout**: 30 seconds per attempt

### Failure Handling

1. **Attempt 1 fails** → Wait 1s → Retry
2. **Attempt 2 fails** → Wait 2s → Retry
3. **Attempt 3 fails** → Mark `requires_review`

### Manual Review

When all attempts fail:
- Evaluation status = `requires_review`
- Faculty notified via UI/API
- All attempts preserved for debugging
- Faculty can manually score or retry

---

## Faculty Override Flow

### Process

1. Faculty reviews evaluation
2. Faculty submits override with:
   - New total score
   - New per-criterion breakdown
   - Required justification (min 10 chars)
3. System creates `faculty_overrides` record
4. System updates `ai_evaluations`:
   - `status` = `overridden`
   - `final_score` = new score
   - `score_breakdown` = new breakdown
   - `finalized_by_faculty_id` = faculty ID
5. Audit entry created: `EVALUATION_OVERRIDDEN`

### Immutability Guarantee

- Original AI evaluation attempt remains unchanged
- Override creates new record
- Full history preserved

---

## Examples

### Complete Evaluation Flow

```bash
# 1. Faculty creates rubric
curl -X POST http://localhost:8000/api/ai-judge/rubrics \
  -H "Authorization: Bearer $FACULTY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Final Round Rubric",
    "rubric_type": "oral_argument",
    "definition": { ... }
  }'

# 2. Faculty triggers evaluation
curl -X POST http://localhost:8000/api/ai-judge/sessions/7/rounds/3/evaluate \
  -H "Authorization: Bearer $FACULTY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "participant_id": 101,
    "rubric_version_id": 3
  }'

# 3. Get evaluation details
curl http://localhost:8000/api/ai-judge/evaluations/42 \
  -H "Authorization: Bearer $FACULTY_TOKEN"

# 4. Faculty overrides if needed
curl -X POST http://localhost:8000/api/ai-judge/evaluations/42/override \
  -H "Authorization: Bearer $FACULTY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "new_score": 90.0,
    "new_breakdown": {"substance": 36, "structure": 18, "citations": 18, "delivery": 18},
    "reason": "Exceptional argument quality not fully captured by AI."
  }'

# 5. View leaderboard
curl http://localhost:8000/api/ai-judge/sessions/7/leaderboard \
  -H "Authorization: Bearer $TOKEN"
```

---

## Migration & Rollback

### Migration

```bash
# Backup
cp /Users/vanshrana/Desktop/IEEE/legalai.db /Users/vanshrana/Desktop/IEEE/legalai.db.pre_phase4_backup

# Run migration
python3 backend/scripts/migrate_phase4.py --db /Users/vanshrana/Desktop/IEEE/legalai.db

# Enable feature
export FEATURE_AI_JUDGE_EVALUATION=True
```

### Rollback

```bash
# Disable feature
unset FEATURE_AI_JUDGE_EVALUATION

# Restore if needed
cp /Users/vanshrana/Desktop/IEEE/legalai.db.pre_phase4_backup /Users/vanshrana/Desktop/IEEE/legalai.db
```

---

## Testing

### Unit Tests

```bash
pytest backend/tests/test_ai_judge_unit.py -v
```

Tests include:
- JSON schema validation
- Score computation accuracy
- Prompt hash reproducibility
- Rubric definition validation

### Integration Tests

```bash
pytest backend/tests/test_ai_judge_integration.py -v
```

Tests include:
- Happy path: valid LLM response
- Malformed path: retries → manual review
- Concurrency: duplicate evaluation prevention
- Override flow: faculty override creation

---

## Observability

### Metrics (Prometheus-compatible)

| Metric | Type | Description |
|--------|------|-------------|
| ai_eval_requests_total | Counter | Total evaluation requests |
| ai_eval_success_total | Counter | Successful evaluations |
| ai_eval_failure_total | Counter | Failed evaluations |
| ai_eval_malformed_total | Counter | Malformed LLM outputs |
| ai_eval_retry_total | Counter | Retry attempts |
| ai_eval_latency_seconds | Histogram | Evaluation latency |
| ai_eval_override_total | Counter | Faculty overrides |

### Logging

All actions logged with:
- Evaluation ID
- Attempt number
- Prompt hash
- LLM model/version
- Parse status
- Latency

### Audit Trail

Every lifecycle event in `ai_evaluation_audit`:
- Timestamp
- Actor (user ID)
- Action type
- Payload (JSON)

---

## Troubleshooting

### "Evaluation requires review" errors
- Check `ai_evaluation_attempts` for specific errors
- Verify LLM API keys (GEMINI_API_KEY, GROQ_API_KEY)
- Check rubric definition validity

### Duplicate evaluation errors
- Only one evaluation per round/participant pair allowed
- Check existing evaluations before triggering new one

### Low scores or unexpected results
- Verify rubric weights sum to 1.0
- Check `score_breakdown` JSON for per-criterion detail
- Review LLM raw response in attempts table

### Faculty override not working
- Ensure user has FACULTY or ADMIN role
- Check override reason meets minimum length (10 chars)
- Verify evaluation exists and is in valid state

---

## PostgreSQL Migration Notes

When migrating from SQLite to PostgreSQL:

1. **Replace TEXT with JSONB** for:
   - `ai_evaluations.score_breakdown`
   - `ai_evaluations.weights_used`
   - `ai_evaluation_attempts.parsed_json`
   - `ai_evaluation_audit.payload_json`

2. **Add indexes**:
   ```sql
   CREATE INDEX idx_eval_scores ON ai_evaluations USING GIN (score_breakdown);
   CREATE INDEX idx_attempts_parsed ON ai_evaluation_attempts USING GIN (parsed_json);
   ```

3. **Replace SQLite locks**:
   - Remove asyncio.Lock per session
   - Use `SELECT FOR UPDATE` on evaluation row

4. **Use Celery/Redis** instead of asyncio for retries in production.
