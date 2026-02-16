# Phase 5 — Immutable Leaderboard Engine

## Summary

Production-grade immutable leaderboard snapshotting system for institutional-grade auditability.

---

## Files Created

### ORM Models
- `backend/orm/session_leaderboard.py`
  - `SessionLeaderboardSnapshot` — Immutable snapshot of leaderboard state
  - `SessionLeaderboardEntry` — Individual participant ranking record
  - `SessionLeaderboardAudit` — Audit trail for leaderboard operations
  - `LeaderboardSide` — Enum for participant side (PETITIONER/RESPONDENT)

### Service Layer
- `backend/services/leaderboard_service.py`
  - `freeze_leaderboard()` — Core freeze operation with strict validation
  - `freeze_leaderboard_idempotent()` — Retry-safe idempotent version
  - `get_leaderboard()` — Retrieve frozen snapshot
  - `get_leaderboard_with_integrity_check()` — Retrieve with checksum verification
  - `can_freeze_leaderboard()` — Pre-flight readiness check
  - `delete_leaderboard()` — Admin-only emergency deletion with audit

### Router
- `backend/routes/leaderboard.py`
  - `POST /sessions/{id}/leaderboard/freeze` — Faculty-only freeze endpoint
  - `GET /sessions/{id}/leaderboard` — Retrieve leaderboard
  - `GET /sessions/{id}/leaderboard/status` — Check freeze readiness

### Migration
- `backend/scripts/migrate_phase5.py`
  - Creates all tables with constraints
  - PostgreSQL-compatible with JSONB support
  - Verifies table creation

### Tests
- `backend/tests/test_leaderboard.py`
  - API-level integration tests with httpx
  - Unit tests for ranking and checksum
  - Concurrency safety documentation

### Documentation
- `backend/docs/phase5_leaderboard_summary.md` — This file

---

## Files Modified

1. `backend/orm/__init__.py`
   - Added exports for `SessionLeaderboardSnapshot`, `SessionLeaderboardEntry`, `SessionLeaderboardAudit`, `LeaderboardSide`

2. `backend/orm/classroom_session.py`
   - Added `leaderboard_snapshots` relationship to `ClassroomSession`
   - Added `leaderboard_entries` relationship to `ClassroomParticipant`

3. `backend/config/feature_flags.py`
   - Added `FEATURE_LEADERBOARD_ENGINE` flag
   - Added `FEATURE_LEADERBOARD_AUTO_FREEZE` flag (future use)

4. `backend/main.py`
   - Registered Phase 5 router conditionally via feature flag

---

## Database Schema

### Table: session_leaderboard_snapshots

| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER (PK) | Auto-increment |
| session_id | INTEGER NOT NULL | UNIQUE, FK → classroom_sessions(id) ON DELETE RESTRICT |
| frozen_by_faculty_id | INTEGER NOT NULL | FK → users(id) ON DELETE RESTRICT |
| rubric_version_id | INTEGER NOT NULL | FK → ai_rubric_versions(id) ON DELETE RESTRICT |
| frozen_at | TIMESTAMP NOT NULL | |
| ai_model_version | VARCHAR(100) | Nullable |
| total_participants | INTEGER NOT NULL | |
| checksum_hash | VARCHAR(64) NOT NULL | SHA256 hex |
| created_at | TIMESTAMP NOT NULL | Default: now() |

**Constraints:**
- `UNIQUE(session_id)` — One snapshot per session, enforced at DB level
- All foreign keys use `ON DELETE RESTRICT`

**Indexes:**
- `idx_snapshots_session` on `session_id`
- `idx_snapshots_faculty` on `frozen_by_faculty_id`
- `idx_snapshots_frozen_at` on `frozen_at`

### Table: session_leaderboard_entries

| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER (PK) | Auto-increment |
| snapshot_id | INTEGER NOT NULL | FK → session_leaderboard_snapshots(id) ON DELETE CASCADE |
| participant_id | INTEGER NOT NULL | FK → classroom_participants(id) ON DELETE RESTRICT |
| side | VARCHAR(20) NOT NULL | Enum: PETITIONER/RESPONDENT |
| speaker_number | INTEGER | Nullable |
| total_score | NUMERIC(10,2) NOT NULL | |
| tie_breaker_score | NUMERIC(10,4) NOT NULL DEFAULT 0 | |
| rank | INTEGER NOT NULL | Dense rank |
| score_breakdown_json | TEXT (JSONB in PG) | Nullable |
| evaluation_ids_json | TEXT (JSONB in PG) | Nullable |
| created_at | TIMESTAMP NOT NULL | Default: now() |

**Constraints:**
- `UNIQUE(snapshot_id, participant_id)` — One entry per participant per snapshot
- Foreign keys use RESTRICT except snapshot uses CASCADE for cleanup

**Indexes:**
- `idx_entries_snapshot` on `snapshot_id`
- `idx_entries_snapshot_rank` on `(snapshot_id, rank)`
- `idx_entries_snapshot_score` on `(snapshot_id, total_score)`
- `idx_entries_participant` on `participant_id`

### Table: session_leaderboard_audit

| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER (PK) | Auto-increment |
| snapshot_id | INTEGER NOT NULL | FK → session_leaderboard_snapshots(id) ON DELETE RESTRICT |
| action | VARCHAR(50) NOT NULL | e.g., LEADERBOARD_FROZEN, LEADERBOARD_DELETED |
| actor_user_id | INTEGER | FK → users(id) ON DELETE SET NULL |
| payload_json | TEXT (JSONB in PG) | Nullable |
| created_at | TIMESTAMP NOT NULL | Default: now() |

**Indexes:**
- `idx_audit_snapshot` on `snapshot_id`
- `idx_audit_action` on `action`
- `idx_audit_actor` on `actor_user_id`
- `idx_audit_created` on `created_at`

---

## Constraints Added

1. **session_leaderboard_snapshots**
   - `UNIQUE(session_id)` — Prevents duplicate snapshots for same session
   - `ON DELETE RESTRICT` on all foreign keys — Prevents accidental deletion of referenced records

2. **session_leaderboard_entries**
   - `UNIQUE(snapshot_id, participant_id)` — Prevents duplicate participant entries
   - `ON DELETE CASCADE` on snapshot_id — Cleans up entries when snapshot deleted
   - `ON DELETE RESTRICT` on participant_id — Prevents deletion of participants with leaderboard entries

3. **session_leaderboard_audit**
   - `ON DELETE RESTRICT` on snapshot_id — Preserves audit history even if snapshot deleted

---

## Ranking Algorithm

### Primary Sort
1. `total_score` DESC (highest first)

### Tie-Breakers (in order)
1. `highest_single_round_score` DESC — Participant with best individual round wins tie
2. `earliest_submission_timestamp` ASC — Earlier submission wins tie
3. `participant_id` ASC — Deterministic final tie-breaker

### Dense Rank Implementation
- Tied participants receive same rank
- Next rank = previous rank + 1
- No gaps in ranking sequence

### Tie-Breaker Score Formula
```python
tie_breaker = (
    highest_round_score * 10000 +
    (0.1 - hash(timestamp) / 10000) +
    (1000000 - participant_id) / 100000000
)
```
All calculations use `Decimal` type, never `float`.

---

## Concurrency Safety

### Transaction Wrapping
```python
async with db.begin():
    # All operations inside single transaction
    # 1. Check for existing snapshot
    # 2. Validate all conditions
    # 3. Create snapshot
    # 4. Create all entries
    # 5. Compute checksum
    # 6. Create audit entry
    # Auto-commit at end
```

### DB-Level Idempotency
- `UNIQUE(session_id)` constraint at database level
- No global locks, no asyncio locks
- IntegrityError on duplicate handled by raising `AlreadyFrozenError`

### Race Condition Handling
If two faculty members attempt freeze simultaneously:
- First transaction commits successfully
- Second transaction hits unique constraint violation
- Second request receives `AlreadyFrozenError` with `existing_snapshot_id`

---

## Checksum Algorithm

### Format
```
participant_id|rank|total_score|tie_breaker_score
```

### Determinism Requirements
- Sort entries by `rank ASC`, then `participant_id ASC`
- Use `Decimal.quantize()` for fixed precision:
  - total_score: 2 decimal places
  - tie_breaker_score: 4 decimal places
- Concatenate with newline separator (`\n`)
- Compute SHA256 hash

### Example
```python
parts = []
for entry in sorted(entries, key=lambda e: (e.rank, e.participant_id)):
    total_score = Decimal(str(entry.total_score)).quantize(Decimal("0.01"))
    tie_breaker = Decimal(str(entry.tie_breaker_score)).quantize(Decimal("0.0001"))
    part = f"{entry.participant_id}|{entry.rank}|{total_score:.2f}|{tie_breaker:.4f}"
    parts.append(part)

combined = "\n".join(parts)
checksum = hashlib.sha256(combined.encode()).hexdigest()
```

---

## Immutability Enforcement

### Rules
1. Snapshot rows are NEVER updated after creation
2. Leaderboard entries are NEVER modified after freeze
3. No UPDATE endpoints exist in API
4. No cascade delete on audit entries
5. `ON DELETE RESTRICT` prevents accidental deletion

### Implementation
- Application code never calls `UPDATE` on these tables
- Audit log records all operations
- Checksum verification detects any tampering

### Admin Override
- `delete_leaderboard()` available for emergency data recovery
- Requires `ADMIN` role (not just faculty)
- Creates audit entry before deletion
- Irreversible operation

---

## PostgreSQL Compatibility

### SQLite → PostgreSQL Migration Path

| Feature | SQLite | PostgreSQL |
|---------|--------|------------|
| Primary Key | `INTEGER PRIMARY KEY AUTOINCREMENT` | `SERIAL PRIMARY KEY` |
| Timestamp | `DEFAULT CURRENT_TIMESTAMP` | `DEFAULT NOW()` |
| JSON | `TEXT` | `JSONB` |

### Migration Script Handles
- Auto-detects dialect via `conn.dialect.name`
- Replaces syntax for PostgreSQL
- Creates JSONB columns instead of TEXT for JSON fields

---

## Test Coverage

### API Tests (httpx)
1. `test_freeze_success` — Happy path freeze
2. `test_freeze_reject_not_completed` — Session not COMPLETED
3. `test_freeze_reject_missing_evaluation` — Missing evaluations
4. `test_freeze_reject_processing_evaluation` — PROCESSING status
5. `test_freeze_reject_requires_review` — REQUIRES_REVIEW status
6. `test_double_freeze_rejection` — Already frozen
7. `test_freeze_unauthorized_student` — RBAC enforcement
8. `test_get_leaderboard_success` — Retrieve with integrity check
9. `test_get_leaderboard_status` — Readiness check

### Unit Tests
1. `test_deterministic_ranking` — Dense rank with tie-breakers
2. `test_checksum_stability` — Reproducible checksums
3. `test_checksum_detects_tampering` — Integrity verification

---

## Known Limitations

1. **Session Status Dependency**
   - Requires session to have `status` attribute with value "COMPLETED"
   - If your `ClassroomSession` model doesn't have this field, freeze will fail

2. **PostgreSQL Upgrade**
   - Current migration creates tables, but full PostgreSQL support requires:
     - Using `JSONB` type (handled by migration)
     - SERIALIZABLE isolation for strictest consistency (not implemented)

3. **Concurrent Freeze Testing**
   - Integration tests document expected behavior
   - True concurrent testing requires multi-threaded test setup
   - DB unique constraint guarantees correctness

4. **Audit Entry Cleanup**
   - Audit entries use `ON DELETE RESTRICT` to preserve history
   - If you delete a snapshot, audit entries remain orphaned
   - This is intentional for compliance purposes

---

## PostgreSQL Production Isolation

For production PostgreSQL deployments, the freeze endpoint should use `SERIALIZABLE` isolation level to prevent all concurrency anomalies:

```sql
SET default_transaction_isolation = 'SERIALIZABLE';
```

### Implementation Note

In SQLAlchemy:

```python
from sqlalchemy import text

async with db.begin():
    await db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
    # ... freeze logic
```

### SQLite Limitation

SQLite does not fully support `SERIALIZABLE` isolation. The DB-level unique constraint on `session_id` provides sufficient protection for SQLite deployments.

### Recommendation

- **SQLite (development)**: Use default isolation + unique constraint
- **PostgreSQL (production)**: Use `SERIALIZABLE` for strictest consistency

---

## Phase 5 Hardening Improvements

This section documents the hardening improvements applied to Phase 5:

### 1. CASCADE Removed
- Changed `ON DELETE CASCADE` to `ON DELETE RESTRICT` on `session_leaderboard_entries.snapshot_id`
- Deletion must now be explicit in service code
- Prevents accidental data loss

### 2. Deterministic Tie-Breaker Fixed
- Removed Python `hash()` function (randomized per process)
- Replaced with deterministic formula using timestamp integer conversion
- All calculations use `Decimal` type exclusively

### 3. Dense Rank Verified
- Rewrote ranking algorithm explicitly using FULL tuple comparison
- Compares `(total_score, highest_round_score, timestamp, participant_id)` for tie-breaking
- No use of `enumerate()` or index-based ranking
- Pure Python deterministic computation
- Dense rank: no gaps in ranking sequence

### 4. Override Locked Post-Freeze
- Added check in `ai_evaluation_service.py` to prevent faculty override after leaderboard freeze
- Raises `InvalidStateError` if attempting override on frozen session
- Protects leaderboard integrity

### 5. Idempotent Freeze Behavior
- Removed pre-check for existing snapshot (race condition window)
- Implemented true idempotent freeze using `IntegrityError` handling
- On concurrent freeze: rollback transaction, query existing, return `(snapshot, already_frozen=True)`
- Safe for retry logic and multi-worker deployments

### 6. Audit Deletion Logic Corrected
- Explicit deletion order: audit entry → entries → snapshot
- No reliance on cascade behavior
- Audit entries preserved with `ON DELETE RESTRICT`

### 7. Checksum Pure Decimal
- Verified `Decimal.quantize()` for all formatting
- No `float()` conversion anywhere
- Deterministic across all platforms

---

## Security Considerations

### Backend Validation Only
- All freeze conditions validated server-side
- No trust in frontend input
- RBAC enforced at API level

### No Float Arithmetic
- All score calculations use `Decimal` type
- Prevents floating-point precision drift
- Deterministic across all platforms

### Audit Trail
- Every freeze operation logged
- Every admin deletion logged
- Payload JSON stores full context

---

## Performance Notes

### Queries
- Batch fetch all evaluations: `SELECT ... WHERE participant_id IN (...)`
- No N+1 query pattern
- Indexes on all foreign keys and common query patterns

### Memory
- Leaderboard entries created in memory before DB flush
- Typical session: 10-50 participants = minimal memory footprint
- Checksum computation: O(n log n) due to sorting

---

## Future Enhancements (Not Implemented)

1. **SERIALIZABLE Isolation** — For strictest PostgreSQL consistency
2. **Auto-freeze on session complete** — Trigger-based automatic freeze
3. **Leaderboard versioning** — Multiple snapshots per session with metadata
4. **Export functionality** — CSV/PDF export of frozen leaderboards
5. **Real-time updates** — WebSocket notifications on freeze completion

---

## Activation

```bash
# 1. Run migration
python backend/scripts/migrate_phase5.py

# 2. Enable feature flag
export FEATURE_LEADERBOARD_ENGINE=true

# 3. Start server
uvicorn backend.main:app --reload
```

---

## API Usage Examples

### Freeze Leaderboard
```bash
curl -X POST \
  http://localhost:8000/api/sessions/123/leaderboard/freeze \
  -H "Authorization: Bearer <faculty_token>"
```

### Get Leaderboard
```bash
curl http://localhost:8000/api/sessions/123/leaderboard \
  -H "Authorization: Bearer <token>"
```

### Check Status
```bash
curl http://localhost:8000/api/sessions/123/leaderboard/status \
  -H "Authorization: Bearer <token>"
```

---

## Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| SESSION_NOT_COMPLETE | 400 | Session status is not COMPLETED |
| MISSING_EVALUATIONS | 400 | Participant missing evaluation |
| INCOMPLETE_EVALUATIONS | 400 | Evaluation status not COMPLETED (PROCESSING, FAILED, PENDING) |
| REQUIRES_REVIEW | 400 | Evaluation requires manual review |
| IDEMPOTENT_FREEZE | 200 | Leaderboard already frozen (returns existing snapshot) |
| UNAUTHORIZED | 403 | User is not faculty |
| SESSION_NOT_FOUND | 404 | Session ID does not exist |
| NO_PARTICIPANTS | 400 | Session has no participants |
| SNAPSHOT_NOT_FOUND | 404 | No frozen leaderboard found |

---

*Generated: Phase 5 Production Hardening*
