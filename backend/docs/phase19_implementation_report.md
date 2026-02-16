# Phase 19 — Moot Courtroom Operations & Live Session Management Implementation Report

**Date:** February 15, 2026  
**Status:** ✅ COMPLETE  
**Layer:** Strictly on top of Phase 14–18

---

## Executive Summary

Phase 19 implements deterministic live courtroom session management with hash-chained audit logs for replay. The system tracks participant entry/exit, observer attendance, and all significant events in an immutable log chain. Completed sessions have integrity hashes for verification.

**Key Design Principles:**
- Deterministic replay of session events
- Hash-chained audit logs for tamper detection
- Immutable session records once completed
- No randomness anywhere
- SELECT FOR UPDATE for all mutations

---

## Files Created

### ORM Models
**File:** `backend/orm/phase19_moot_operations.py`

| Table | Purpose | Records |
|-------|---------|---------|
| `courtroom_sessions` | Live session metadata | 1 per scheduled match |
| `session_participations` | Participant join/exit tracking | 1+ per participant |
| `session_observations` | Observer (audience) tracking | 0+ per observer |
| `session_log_entries` | Immutable hash-chained audit logs | 1+ per event |

### Services

| File | Service | Purpose |
|------|---------|---------|
| `backend/services/phase19_session_service.py` | `SessionService` | Core session management |

### Routes

**File:** `backend/routes/phase19_moot_operations.py`

| Method | Route | Role | Description |
|--------|-------|------|-------------|
| POST | `/api/session/create` | Admin/Judge | Create session |
| GET | `/api/session/{id}` | Any | Get session details |
| POST | `/api/session/{id}/start` | Admin/Judge | Start session |
| POST | `/api/session/{id}/pause` | Admin/Judge | Pause session |
| POST | `/api/session/{id}/resume` | Admin/Judge | Resume session |
| POST | `/api/session/{id}/complete` | Admin/Judge | Complete session |
| POST | `/api/session/{id}/join` | Any | Join as participant |
| POST | `/api/session/{id}/leave` | Any | Leave session |
| GET | `/api/session/{id}/participants` | Any | List participants |
| POST | `/api/session/{id}/observe` | Any | Join as observer |
| POST | `/api/session/{id}/log` | Admin/Judge | Log custom event |
| GET | `/api/session/{id}/logs` | Any | Get session logs |
| GET | `/api/session/{id}/replay` | Any | Get replay delta |
| GET | `/api/session/{id}/verify` | Any | Verify log integrity |
| GET | `/api/session/active/list` | Any | List active sessions |

### Tests

**File:** `backend/tests/test_phase19_moot_operations.py`

**35 Tests Across 10 Classes:**

1. **TestStateMachine** (7 tests) - Session status transitions
2. **TestHashChain** (4 tests) - SHA256 hash chain determinism
3. **TestConcurrency** (2 tests) - Race condition handling
4. **TestParticipantManagement** (3 tests) - Join/leave tracking
5. **TestObserverManagement** (2 tests) - Observer tracking
6. **TestDeterminism** (3 tests) - Deterministic behavior
7. **TestIntegrityVerification** (3 tests) - Log chain verification
8. **TestReplay** (2 tests) - Replay delta functionality
9. **TestORMModels** (5 tests) - Model instantiation
10. **TestEdgeCases** (4 tests) - Edge case handling

### Audit

**File:** `backend/tests/phase19_determinism_audit.py`

Determinism verification tests:
- Log hash determinism
- Session integrity hash determinism
- State machine determinism
- JSON sort_keys determinism
- No randomness verification
- Constant-time comparison
- Hash chain linking

---

## Database Schema Details

### courtroom_sessions

**Fields:**
- `id` (UUID PK)
- `assignment_id` (FK match_schedule_assignments.id, unique)
- `status` (ENUM: pending, active, paused, completed)
- `started_at`, `ended_at` (timestamps)
- `recording_url` (string 500, nullable)
- `metadata` (JSON, nullable)
- `integrity_hash` (varchar 64, nullable)
- `created_at` (timestamp)

**Constraints:**
- `uq_session_assignment`: unique assignment_id
- `ck_session_status_valid`: status in valid set

**Indexes:**
- idx_session_assignment
- idx_session_status

### session_participations

**Fields:**
- `id` (UUID PK)
- `session_id` (FK courtroom_sessions.id)
- `user_id` (FK users.id)
- `role` (ENUM: petitioner, respondent, judge, moderator)
- `status` (ENUM: connected, disconnected, reconnecting)
- `joined_at`, `left_at` (timestamps)
- `connection_count` (int, default 1)
- `client_info` (JSON, nullable)
- `created_at` (timestamp)

**Constraints:**
- `ck_participant_role_valid`: role in valid set
- `ck_participant_status_valid`: status in valid set
- `ck_connection_count_positive`: connection_count > 0

**Indexes:**
- idx_participation_session
- idx_participation_user

### session_observations

**Fields:**
- `id` (UUID PK)
- `session_id` (FK courtroom_sessions.id)
- `user_id` (FK users.id, nullable for anonymous)
- `observed_at`, `left_at` (timestamps)
- `client_info` (JSON, nullable)
- `created_at` (timestamp)

**Indexes:**
- idx_observation_session
- idx_observation_user

### session_log_entries

**Fields:**
- `id` (UUID PK)
- `session_id` (FK courtroom_sessions.id)
- `timestamp` (timestamp, indexed)
- `event_type` (string 50, indexed)
- `actor_id` (FK users.id, nullable)
- `details` (JSON)
- `hash_chain` (varchar 64)
- `sequence_number` (int)
- `created_at` (timestamp)

**Constraints:**
- `uq_log_sequence`: unique (session_id, sequence_number)

**Indexes:**
- idx_log_session
- idx_log_timestamp
- idx_log_event_type
- idx_log_actor

---

## State Machine

### Session Status Flow

```
PENDING
  ↓ (start)
ACTIVE
  ↓ (pause)    ↓ (complete)
PAUSED → ACTIVE
  ↓ (complete)
COMPLETED (terminal)
```

### Valid Transitions

| From | To | Valid |
|------|-----|-------|
| PENDING | ACTIVE | ✅ |
| ACTIVE | PAUSED | ✅ |
| ACTIVE | COMPLETED | ✅ |
| PAUSED | ACTIVE | ✅ |
| PAUSED | COMPLETED | ✅ |
| PENDING | COMPLETED | ❌ |
| COMPLETED | ANY | ❌ |

Invalid transitions return HTTP 409.

---

## Hash Chain Logic

### Log Entry Hash

```python
sha256(
    json.dumps({
        "session_id": str(session_id),
        "timestamp": timestamp.isoformat(),
        "event_type": event_type,
        "details": json.dumps(details, sort_keys=True),
        "previous_hash": previous_hash or "0" * 64
    }, sort_keys=True)
)
```

### Session Integrity Hash

```python
sha256(
    json.dumps({
        "session_id": str(session.id),
        "assignment_id": str(session.assignment_id),
        "status": session.status,
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "participations": [...],
        "logs": [...]
    }, sort_keys=True)
)
```

---

## Concurrency Protections

### FOR UPDATE Locking

```python
# Lock session
query = select(CourtroomSession).where(...).with_for_update()

# Lock participation
query = select(SessionParticipation).where(...).with_for_update()
```

### Protected Operations

1. **Session state changes** - Start, pause, resume, complete
2. **Participant join/leave** - Prevents race conditions
3. **Log entry creation** - Sequence number allocation

---

## Replay Functionality

### Delta Replay

```python
# Get logs from sequence 100 onwards
delta = await SessionService.get_session_logs(
    db=db,
    session_id=session_id,
    start_sequence=100
)
```

### Replay Route

```
GET /api/session/{id}/replay?from_sequence=100
```

Returns all logs from specified sequence for live replay synchronization.

---

## Integrity Verification

### Log Chain Verification

```python
async def verify_log_integrity(session_id):
    logs = await get_session_logs(session_id)
    
    previous_hash = "0" * 64
    for log in logs:
        computed = compute_log_hash(..., previous_hash)
        if computed != log.hash_chain:
            return False  # Tampering detected
        previous_hash = log.hash_chain
    
    return True
```

### Constant-Time Comparison

Prevents timing attacks when comparing hashes:

```python
def _constant_time_compare(a, b):
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    return result == 0
```

---

## Stress Test Coverage

| Category | Tests | Coverage |
|----------|-------|----------|
| State Machine | 7 | All transitions |
| Hash Chain | 4 | Determinism, linking |
| Concurrency | 2 | Lock contention |
| Participants | 3 | Join/leave/reconnect |
| Observers | 2 | Anonymous/auth tracking |
| Determinism | 3 | JSON, timestamps |
| Integrity | 3 | Hash verification |
| Replay | 2 | Delta functionality |
| ORM | 5 | Model instantiation |
| Edge Cases | 4 | Nulls, boundaries |

**Total: 35 tests**

---

## Determinism Guarantees

1. **Log Hash Reproducibility** ✓
2. **Session Integrity Hash** ✓
3. **State Predictability** ✓
4. **JSON Determinism** ✓
5. **No Randomness** ✓
6. **Timing Safety** ✓
7. **Chain Integrity** ✓

---

## Feature Flags

```python
FEATURE_MOOT_OPERATIONS = False      # Master switch
FEATURE_SESSION_RECORDING = False    # Recording support
```

All routes return 403 if `FEATURE_MOOT_OPERATIONS` is disabled.

---

## RBAC Summary

| Action | Required Role |
|--------|--------------|
| Create session | ADMIN, SUPER_ADMIN, JUDGE |
| Start session | ADMIN, SUPER_ADMIN, JUDGE |
| Pause session | ADMIN, SUPER_ADMIN, JUDGE |
| Resume session | ADMIN, SUPER_ADMIN, JUDGE |
| Complete session | ADMIN, SUPER_ADMIN, JUDGE |
| Join/Leave | Any authenticated |
| List participants | Any authenticated |
| Observe | Any (including anonymous) |
| Log event | ADMIN, SUPER_ADMIN, JUDGE |
| Get logs | Any authenticated |
| Get replay | Any authenticated |
| Verify integrity | Any authenticated |
| List active | Any authenticated |

---

## Files Modified

| File | Change |
|------|--------|
| `backend/config/feature_flags.py` | Added Phase 19 flags |
| `backend/main.py` | Registered Phase 19 routes |

---

## Acceptance Criteria Status

| Criteria | Status |
|----------|--------|
| App boots cleanly | ✅ |
| No schema conflicts | ✅ |
| No circular imports | ✅ |
| 35+ stress tests pass | ✅ |
| Determinism audit passes | ✅ |
| Hash chain integrity verified | ✅ |
| Replay functionality works | ✅ |
| Concurrency conflicts handled | ✅ |
| Markdown report saved | ✅ |

---

## Production Deployment Checklist

- [ ] Set `FEATURE_MOOT_OPERATIONS=True`
- [ ] Set `FEATURE_SESSION_RECORDING=True` (optional)
- [ ] Create session from Phase 18 assignment
- [ ] Start session when ready
- [ ] Participants join with roles
- [ ] Log significant events
- [ ] Pause/resume as needed
- [ ] Complete session to finalize
- [ ] Verify session integrity hash
- [ ] Archive recording URL

---

## Architecture Summary

Phase 19 creates a **live session layer** on top of the scheduling system:

```
┌─────────────────────────────────────────┐
│   Phase 19: Moot Courtroom Operations    │
│      (Live sessions, replay, logs)       │
├─────────────────────────────────────────┤
│    Phase 18: Scheduling & Allocation     │
│         (Court/Slot assignments)         │
├─────────────────────────────────────────┤
│    Phase 17: Appeals & Governance        │
│          (Immutable appeals)             │
├─────────────────────────────────────────┤
│    Phase 16: Analytics & Ranking         │
│          (Deterministic rankings)        │
├─────────────────────────────────────────┤
│    Phase 15: AI Judge Intelligence       │
│          (Immutable evaluations)         │
├─────────────────────────────────────────┤
│    Phase 14: Deterministic Round Engine  │
│          (Immutable match records)       │
└─────────────────────────────────────────┘
```

The system is now:
- ✅ Deterministic (Phases 14-19)
- ✅ AI Evaluated (Phase 15)
- ✅ Ranked (Phase 16)
- ✅ Governed (Phase 17)
- ✅ Scheduled (Phase 18)
- ✅ Live Session (Phase 19)
- ✅ Immutable (all phases)
- ✅ Replayable (Phase 19)

---

**Implementation Complete:** February 15, 2026  
**Tests Passing:** 35/35  
**Determinism Audit:** Passed  
**Production Ready:** Yes
