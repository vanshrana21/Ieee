# Phase 7 — Classroom Mode (Moot Court) Implementation

## Overview

Phase 7 implements a production-grade classroom mode for Juris AI, enabling teachers to conduct live moot court sessions with students. The system supports real-time pairing, state machine-driven rounds, WebSocket communication, and comprehensive audit logging.

## 📁 Deliverables

### Database Models
- `backend/orm/classroom_round.py` - Individual moot court rounds
- `backend/orm/classroom_round_action.py` - Immutable event logging

### State Machine
- `backend/state_machines/round_state.py` - Strict server-side state enforcement

### Services
- `backend/services/classroom/pairing_engine.py` - Intelligent student pairing (4 modes)
- `backend/services/classroom/websocket.py` - Real-time WebSocket communication
- `backend/services/classroom/tasks.py` - Celery background tasks
- `backend/services/classroom/security.py` - Rate limiting, audit logging, security

### API Routes
- `backend/routes/classroom.py` - REST endpoints for session/round management

### Tests
- `backend/tests/test_classroom_phase7.py` - Comprehensive test suite

### Migration
- `backend/alembic/versions/classroom_phase7_migration.py` - Database migration

---

## 🚀 Quick Start

### 1. Apply Database Migration

```bash
cd /Users/vanshrana/Desktop/IEEE
alembic upgrade classroom_phase7
```

### 2. Start Celery Workers

```bash
celery -A backend.celery_app worker -l info
celery -A backend.celery_app beat -l info  # For periodic tasks
```

### 3. Start WebSocket Server

WebSocket endpoints are automatically available through FastAPI:
- `ws://localhost:8000/ws/classroom/session/{session_id}?token=JWT`
- `ws://localhost:8000/ws/classroom/round/{round_id}?token=JWT`

### 4. Environment Variables

Add to `.env`:
```
# Classroom Mode Settings
CLASSROOM_JOIN_CODE_TTL=86400
CLASSROOM_DEFAULT_MAX_CAPACITY=32
CLASSROOM_PAIRING_CONCURRENCY_LIMIT=10

# Redis (for WebSocket pub/sub and Celery)
REDIS_URL=redis://localhost:6379/0

# Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

---

## 📊 Data Model

### ClassroomRound

| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer | Primary key |
| `session_id` | Integer | FK to classroom_sessions |
| `petitioner_id` | Integer | FK to users (can be AI) |
| `respondent_id` | Integer | FK to users (can be AI) |
| `judge_id` | Integer | FK to users (can be AI) |
| `state` | Enum | Round state (waiting, argument_petitioner, etc.) |
| `time_limit_seconds` | Integer | Phase timer duration |
| `phase_start_timestamp` | DateTime | Server-authoritative timer start |
| `logs` | JSON | Event log array |
| `transcript` | Text | Full round transcript |
| `version` | Integer | Optimistic locking |

### ClassroomRoundAction (Audit Log)

| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer | Primary key |
| `round_id` | Integer | FK to classroom_rounds |
| `action_type` | Enum | Type of action performed |
| `from_state` | String | Previous state (for transitions) |
| `to_state` | String | New state (for transitions) |
| `payload` | JSON | Arbitrary action data |
| `ip_address` | String | Client IP for audit |
| `user_agent` | String | Client user agent |

---

## 🔄 State Machine

### Round States

```
WAITING → ARGUMENT_PETITIONER → ARGUMENT_RESPONDENT → REBUTTAL → SUR_REBUTTAL → JUDGE_QUESTIONS → SCORING → COMPLETED
   ↓         ↓                      ↓                  ↓           ↓              ↓              ↓
CANCELLED  PAUSED ←→ (resume to previous state)
```

### Valid Transitions

- `WAITING` → `ARGUMENT_PETITIONER`, `CANCELLED`
- `ARGUMENT_PETITIONER` → `ARGUMENT_RESPONDENT`, `PAUSED`, `CANCELLED`
- `ARGUMENT_RESPONDENT` → `REBUTTAL`, `PAUSED`, `CANCELLED`
- `REBUTTAL` → `SUR_REBUTTAL`, `JUDGE_QUESTIONS`, `PAUSED`, `CANCELLED`
- `SUR_REBUTTAL` → `JUDGE_QUESTIONS`, `PAUSED`, `CANCELLED`
- `JUDGE_QUESTIONS` → `SCORING`, `PAUSED`, `CANCELLED`
- `SCORING` → `COMPLETED`, `PAUSED`
- `PAUSED` → (resume to `previous_state`)

### Usage

```python
from backend.state_machines.round_state import RoundStateMachine, RoundState

# Get state machine for a round
machine = await RoundStateMachine.get_machine(db, round_id)

# Transition
round_obj = await machine.transition(
    actor_id=teacher_id,
    new_state=RoundState.ARGUMENT_PETITIONER,
    payload={"started_by": "teacher"}
)
```

---

## 🎯 Pairing Engine

### Modes

1. **RANDOM**: Shuffle and pair sequentially
2. **MANUAL**: Teacher-specified pairs
3. **SKILL**: ELO-based pairing (similar skill levels)
4. **AI_FALLBACK**: Random + AI opponents for odd students

### Usage

```python
from backend.services.classroom.pairing_engine import PairingEngine, PairingMode

engine = PairingEngine(db)

# Random pairing
pairs = await engine.pair_participants(
    session_id=session_id,
    mode=PairingMode.RANDOM
)

# Create rounds from pairs
rounds = await engine.create_rounds_from_pairs(
    session_id=session_id,
    pairs=pairs
)
```

---

## 🔌 WebSocket API

### Connection

**Session-level updates:**
```javascript
const ws = new WebSocket(
  `ws://localhost:8000/ws/classroom/session/${session_id}?token=${jwt}`
);
```

**Round-level updates:**
```javascript
const ws = new WebSocket(
  `ws://localhost:8000/ws/classroom/round/${round_id}?token=${jwt}`
);
```

### Message Protocol

**Client → Server:**
```json
{"type": "ping"}
{"type": "presence.heartbeat"}
{"type": "chat.message", "text": "Hello"}
{"type": "objection.raise", "objection_type": "relevance"}
```

**Server → Client:**
```json
{"type": "session.init", "session": {...}}
{"type": "round.state_change", "from_state": "waiting", "to_state": "argument_petitioner"}
{"type": "chat.message", "user_id": 123, "text": "Hello", "timestamp": "..."}
{"type": "objection.raised", "raised_by": 123, "objection_type": "relevance"}
```

---

## 🔒 Security

### Rate Limiting

- WebSocket: 5 messages/second per user
- API: 30 requests/minute per endpoint per user

### Audit Logging

All privileged actions are logged:
- Session create/start/end
- Round transitions
- Scoring submissions
- Participant management
- Pairing updates

### Authorization

- Teachers: Full control
- Judges: Round control, scoring
- Students: Arguments, objections
- Observers: Read-only

---

## 🧪 Testing

### Run Tests

```bash
cd /Users/vanshrana/Desktop/IEEE
pytest backend/tests/test_classroom_phase7.py -v
```

### Test Coverage

- State machine transitions (valid & invalid)
- Pairing algorithms (all 4 modes)
- Round lifecycle (full workflow)
- Security (authorization, rate limiting)
- Edge cases (empty sessions, odd participants)
- Concurrent modification prevention

---

## 📈 Monitoring & Observability

### Metrics

- `classroom_sessions_total`
- `classroom_rounds_total`
- `round_state_transitions_total{from,to}`
- `pairing_jobs_run_total`
- `ws_connections`
- `ws_messages_total`

### Logs

Structured JSON logging with:
- `session_id`
- `round_id`
- `user_id`
- `action_type`
- `timestamp`

---

## 🚢 Deployment

### Pre-deployment Checklist

- [ ] Run database migration
- [ ] Start Redis server
- [ ] Start Celery workers & beat
- [ ] Verify WebSocket endpoint accessibility
- [ ] Configure rate limiting
- [ ] Enable audit logging
- [ ] Test in staging environment

### Rollout Strategy

1. Apply migration (backward compatible)
2. Deploy new code with feature flag
3. Enable for beta users
4. Full rollout

---

## 📚 API Reference

### Key Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/classroom/sessions` | Create session |
| POST | `/api/classroom/sessions/join` | Join with code |
| POST | `/api/classroom/sessions/{id}/pair` | Trigger pairing |
| GET | `/api/classroom/sessions/{id}/rounds` | List rounds |
| POST | `/api/classroom/rounds/{id}/transition` | Change state |
| POST | `/api/classroom/rounds/{id}/score` | Submit scores |

See `backend/routes/classroom.py` for full API specification.

---

## 🔧 Troubleshooting

### Common Issues

**SQLAlchemy "Table already defined" Error:**
- Ensure no duplicate model definitions
- Check `__tablename__` uniqueness
- Verify Alembic migration applied

**WebSocket Connection Failures:**
- Check JWT token validity
- Verify session/round exists
- Confirm user has access permissions

**Celery Tasks Not Running:**
- Verify Redis connection
- Check worker processes are running
- Review task queue in Flower (if enabled)

---

## 📞 Support

For issues or questions:
1. Check test suite for examples
2. Review audit logs for action history
3. Enable debug logging: `LOG_LEVEL=DEBUG`

---

## 📝 Changelog

### Phase 7 (Current)
- Added ClassroomRound model
- Added ClassroomRoundAction audit logging
- Implemented RoundStateMachine with strict transitions
- Created PairingEngine (random, manual, skill, AI-fallback)
- Added WebSocket real-time communication
- Implemented Celery background tasks
- Added security middleware (rate limiting, audit logging)
- Comprehensive test suite

---

**End of Phase 7 Implementation**
