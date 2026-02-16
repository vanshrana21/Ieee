# Phase 3: Round Engine — Implementation & API Documentation

## Overview

The Round Engine implements structured, timed speaking rounds for classroom moot sessions. It provides:

- **Deterministic turn order**: PETITIONER #1 → RESPONDENT #1 → PETITIONER #2 → RESPONDENT #2
- **Server-side timing**: Authoritative timers with auto-advance
- **Full audit trail**: Every action logged for accountability
- **Concurrency safety**: SQLite-compatible locking prevents race conditions
- **Faculty oversight**: Force controls and real-time monitoring

## Table of Contents

1. [Architecture](#architecture)
2. [Database Schema](#database-schema)
3. [API Endpoints](#api-endpoints)
4. [Feature Flags](#feature-flags)
5. [Timer Strategy](#timer-strategy)
6. [Examples](#examples)
7. [Migration & Rollback](#migration--rollback)
8. [Testing](#testing)
9. [Metrics](#metrics)
10. [Troubleshooting](#troubleshooting)

---

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Round Engine                              │
├─────────────────────────────────────────────────────────────┤
│  Service Layer          │  round_engine_service.py           │
│  Router Layer           │  classroom_rounds.py               │
│  ORM Models             │  classroom_turn.py                 │
│                         │  classroom_turn_audit.py           │
│  Schemas                │  classroom_rounds.py (schemas)     │
└─────────────────────────────────────────────────────────────┘
```

### Concurrency Model

For SQLite compatibility, the Round Engine uses:

1. **Per-session asyncio.Lock**: Serializes concurrent operations per session
2. **Retry logic**: 3 attempts with exponential backoff on IntegrityError
3. **Optimistic locking**: Versioning for conflict detection

For PostgreSQL (production):
- Replace with `SELECT ... FOR UPDATE` for row-level locking
- Remove session-level locks

---

## Database Schema

### classroom_rounds

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment ID |
| session_id | INTEGER FK | References classroom_sessions(id) |
| round_index | INTEGER | 1-based ordering within session |
| round_type | VARCHAR(32) | PETITIONER_MAIN, RESPONDENT_MAIN, REBUTTAL, OTHER |
| status | VARCHAR(20) | PENDING, ACTIVE, COMPLETED, ABORTED |
| current_speaker_participant_id | INTEGER FK | Currently active participant |
| started_at | DATETIME | When round started |
| ended_at | DATETIME | When round ended |
| created_at | DATETIME | Creation timestamp |
| updated_at | DATETIME | Last update timestamp |

**Constraints:**
- UNIQUE(session_id, round_index)
- INDEX on session_id, status

### classroom_turns

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment ID |
| round_id | INTEGER FK | References classroom_rounds(id) |
| participant_id | INTEGER FK | References classroom_participants(id) |
| turn_order | INTEGER | 1-based order within round |
| allowed_seconds | INTEGER | Speaking time limit |
| started_at | DATETIME | When turn started |
| submitted_at | DATETIME | When transcript submitted |
| transcript | TEXT | Speaking transcript |
| word_count | INTEGER | Word count of transcript |
| is_submitted | BOOLEAN | Whether turn is complete |
| created_at | DATETIME | Creation timestamp |
| updated_at | DATETIME | Last update timestamp |

**Constraints:**
- UNIQUE(round_id, turn_order)
- UNIQUE(round_id, participant_id)
- INDEX on round_id, participant_id

### classroom_turn_audit

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment ID |
| turn_id | INTEGER FK | References classroom_turns(id) |
| action | VARCHAR(32) | START, SUBMIT, AUTO_SUBMIT, TIME_EXPIRED, OVERRIDE |
| actor_user_id | INTEGER | User who performed action |
| payload_json | TEXT | JSON with additional data |
| created_at | DATETIME | When action occurred |

**Constraints:**
- INDEX on turn_id, created_at

---

## API Endpoints

### Create Round
```
POST /api/classroom/rounds
Authorization: Bearer <FACULTY_TOKEN>
Content-Type: application/json

{
    "session_id": 7,
    "round_index": 1,
    "round_type": "PETITIONER_MAIN",
    "default_turn_seconds": 300,
    "turns": null  // Auto-generate from participants
}
```

Response 201:
```json
{
    "id": 11,
    "session_id": 7,
    "round_index": 1,
    "round_type": "PETITIONER_MAIN",
    "status": "PENDING",
    "current_speaker_participant_id": null,
    "started_at": null,
    "ended_at": null,
    "turns": [
        {
            "id": 101,
            "participant_id": 21,
            "turn_order": 1,
            "allowed_seconds": 300,
            "started_at": null,
            "submitted_at": null,
            "is_submitted": false
        },
        ...
    ]
}
```

### Start Round
```
POST /api/classroom/rounds/{round_id}/start
Authorization: Bearer <FACULTY_TOKEN>
```

Response 200:
```json
{
    "success": true,
    "round_id": 11,
    "status": "ACTIVE",
    "current_speaker_participant_id": 101
}
```

### Start Turn
```
POST /api/classroom/turns/{turn_id}/start
Authorization: Bearer <STUDENT_TOKEN>
```

Response 200:
```json
{
    "turn_id": 101,
    "started_at": "2026-02-13T16:31:00Z",
    "allowed_seconds": 300,
    "remaining_seconds": 300
}
```

### Submit Turn
```
POST /api/classroom/turns/{turn_id}/submit
Authorization: Bearer <STUDENT_TOKEN>
Content-Type: application/json

{
    "turn_id": 101,
    "transcript": "My argument is that the precedent clearly supports...",
    "word_count": 320
}
```

Response 200:
```json
{
    "success": true,
    "turn_id": 101,
    "submitted_at": "2026-02-13T16:36:20Z",
    "next_current_speaker_participant_id": 102,
    "round_status": "ACTIVE"
}
```

### Force Submit (Faculty)
```
POST /api/classroom/turns/{turn_id}/force_submit
Authorization: Bearer <FACULTY_TOKEN>
Content-Type: application/json

{
    "turn_id": 101,
    "transcript": "Faculty override - student disconnected",
    "word_count": 5,
    "reason": "Technical issue"
}
```

### Get Round
```
GET /api/classroom/rounds/{round_id}
Authorization: Bearer <TOKEN>
```

### List Session Rounds
```
GET /api/classroom/sessions/{session_id}/rounds
Authorization: Bearer <TOKEN>
```

### Get Turn Audit
```
GET /api/classroom/turns/{turn_id}/audit
Authorization: Bearer <TOKEN>
```

### Abort Round
```
POST /api/classroom/rounds/{round_id}/abort
Authorization: Bearer <FACULTY_TOKEN>
Content-Type: application/json

{
    "reason": "Technical difficulties"
}
```

---

## Feature Flags

All flags in `backend/config/feature_flags.py`:

| Flag | Default | Description |
|------|---------|-------------|
| FEATURE_CLASSROOM_ROUND_ENGINE | False | Enable/disable entire Round Engine |
| FEATURE_AUTO_SUBMIT_ON_TIMEOUT | False | Auto-submit empty transcript on timeout |
| FEATURE_ALLOW_LATE_SUBMISSION | False | Accept submissions after time expires |

Environment variable format:
```bash
FEATURE_CLASSROOM_ROUND_ENGINE=True
FEATURE_AUTO_SUBMIT_ON_TIMEOUT=False
FEATURE_ALLOW_LATE_SUBMISSION=False
```

---

## Timer Strategy

### Current Implementation (Dev/SQLite)

Uses in-process asyncio scheduling:

1. When turn starts: `schedule_turn_timeout(turn_id, due_at)`
2. Creates `asyncio.Task` that sleeps until timeout
3. On timeout: checks if already submitted
4. If not submitted: creates TIME_EXPIRED audit, optionally auto-submits
5. Calls `advance_after_submit()` to move to next turn

**Limitations:**
- Lost on server restart
- Not distributed
- Best for single-node dev

### Production Strategy (PostgreSQL + Celery/Redis)

Replace with:

```python
# Instead of asyncio.sleep, use Celery
celery_app.send_task(
    'round_engine.auto_advance_on_timeout',
    args=[turn_id],
    countdown=turn.allowed_seconds
)
```

Benefits:
- Persists through restarts
- Distributed across workers
- Reliable delivery

---

## Examples

### Full Round Flow (curl)

See `backend/tests/manual_round_flow.sh` for complete script.

Quick example:

```bash
# 1. Login as faculty
FACULTY_TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
    -d "username=faculty@gmail.com&password=password123" | jq -r '.access_token')

# 2. Create round
curl -X POST http://localhost:8000/api/classroom/rounds \
    -H "Authorization: Bearer $FACULTY_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "session_id": 1,
        "round_index": 1,
        "round_type": "PETITIONER_MAIN",
        "default_turn_seconds": 300
    }'

# 3. Start round
curl -X POST http://localhost:8000/api/classroom/rounds/1/start \
    -H "Authorization: Bearer $FACULTY_TOKEN"

# 4. Student starts turn
curl -X POST http://localhost:8000/api/classroom/turns/1/start \
    -H "Authorization: Bearer $STUDENT_TOKEN"

# 5. Student submits
curl -X POST http://localhost:8000/api/classroom/turns/1/submit \
    -H "Authorization: Bearer $STUDENT_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "turn_id": 1,
        "transcript": "My argument...",
        "word_count": 150
    }'
```

---

## Migration & Rollback

### Migration

```bash
# Backup first
cp /Users/vanshrana/Desktop/IEEE/legalai.db /Users/vanshrana/Desktop/IEEE/legalai.db.pre_phase3_backup

# Run migration
python3 backend/scripts/migrate_phase3.py --db /Users/vanshrana/Desktop/IEEE/legalai.db

# Enable feature flag
export FEATURE_CLASSROOM_ROUND_ENGINE=True
```

### Rollback

If critical issue detected:

```bash
# 1. Disable feature flag
unset FEATURE_CLASSROOM_ROUND_ENGINE

# 2. If data loss acceptable, restore from backup
cp /Users/vanshrana/Desktop/IEEE/legalai.db.pre_phase3_backup /Users/vanshrana/Desktop/IEEE/legalai.db

# 3. Restart server
```

---

## Testing

### Unit Tests

```bash
cd /Users/vanshrana/Desktop/IEEE
export DATABASE_URL="sqlite:////Users/vanshrana/Desktop/IEEE/legalai_test.db"
pytest backend/tests/test_round_engine_unit.py -v
```

Expected: 9+ tests passing

### Integration Tests

Start server first:
```bash
export FEATURE_CLASSROOM_ROUND_ENGINE=True
uvicorn backend.main:app --reload --env-file .env
```

Run tests:
```bash
pytest backend/tests/test_round_engine_integration.py -v
```

Tests include:
- Full round flow with 4 participants
- Concurrent turn start attempts
- Timeout handling
- Faculty force submit

---

## Metrics

Available metrics (Prometheus-compatible):

| Metric | Type | Description |
|--------|------|-------------|
| rounds_started_total | Counter | Total rounds started |
| rounds_completed_total | Counter | Total rounds completed |
| turns_submitted_total | Counter | Total turns submitted |
| turns_timed_out_total | Counter | Total turns that timed out |
| avg_turn_duration_seconds | Gauge | Average turn duration |
| percent_turns_late | Gauge | % of late submissions |

Access via metrics endpoint (add to your monitoring stack):
```python
# In your metrics handler
from backend.services.round_engine_service import get_metrics
metrics = await get_metrics()
```

---

## Troubleshooting

### "Round not found" errors
- Verify round_id exists: `GET /api/classroom/rounds/{id}`
- Check session_id matches

### "Not current speaker" errors
- Verify `round.current_speaker_participant_id` matches turn participant
- Check round status is ACTIVE

### Timeouts not firing
- Check `FEATURE_AUTO_SUBMIT_ON_TIMEOUT` flag
- Verify server is running (asyncio tasks lost on restart)
- For production: implement Celery/Redis

### Duplicate turn_order errors
- Each round can only have one turn per order
- Auto-generation handles this automatically

### Feature flag not working
- Check `.env` file: `FEATURE_CLASSROOM_ROUND_ENGINE=True`
- Restart server after changing env vars
- Verify import: `from backend.config.feature_flags import feature_flags`

---

## Development Notes

### Design Tradeoffs

1. **SQLite Locks vs FOR UPDATE**
   - Tradeoff: Simplicity vs production robustness
   - Recommendation: Use PostgreSQL + FOR UPDATE for production

2. **Asyncio Timers vs Celery**
   - Tradeoff: Dev convenience vs reliability
   - Recommendation: Celery for production deployments

3. **Per-Session Locks vs Global Lock**
   - Tradeoff: Concurrency vs correctness
   - Current: Per-session allows parallel operations on different sessions

### Security Considerations

1. **JWT Validation**: All endpoints check token expiry
2. **Role Enforcement**: Faculty-only operations verified
3. **Participant Ownership**: Students can only access their own turns
4. **Rate Limiting**: Consider adding to `/api/classroom/turns/{id}/submit`
5. **No PII in Logs**: User IDs logged, not emails

---

## Contact & Support

For issues or questions:
1. Check this documentation
2. Review test files for examples
3. Examine audit logs for troubleshooting
4. Check feature flags are correctly set

---

## Changelog

### Phase 3 Initial Release
- Round creation with auto-generated turns
- Server-side timing with auto-advance
- Full audit trail
- Faculty controls (start, abort, force submit)
- SQLite-compatible locking
- Comprehensive test coverage
