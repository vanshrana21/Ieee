# Frontend Integration Introspection Report

**Generated:** February 15, 2026  
**Scope:** Full Backend System (Phases 14-21)  
**Purpose:** Zero-guesswork frontend integration reference

---

## Table of Contents

1. [Full Project Tree](#1-full-project-tree)
2. [All Registered Routes](#2-all-registered-routes)
3. [Auth System Details](#3-auth-system-details)
4. [Feature Flags](#4-feature-flags)
5. [Database Enums](#5-database-enums)
6. [Standard Response Format](#6-standard-response-format)
7. [Guarded Operations](#7-guarded-operations)
8. [Cross-Phase Dependencies](#8-cross-phase-dependencies)
9. [Pagination & Filter Support](#9-pagination--filter-support)
10. [Time-Sensitive Endpoints](#10-time-sensitive-endpoints)
11. [Test Environment Requirements](#11-test-environment-requirements)

---

## 1. Full Project Tree

```
backend/
├── alembic/                          # Database migrations
├── ai/                               # AI integration modules
├── cli/                              # Command line tools
├── config/                           # Configuration files
│   └── feature_flags.py              # Feature flag definitions
├── core/                             # Core utilities
├── database.py                       # Database connection setup
├── docs/                             # Documentation
├── errors.py                         # Error handling & codes
├── exceptions.py                     # Custom exceptions
├── knowledge_base/                   # Knowledge base modules
├── logging/                          # Logging configuration
├── main.py                           # FastAPI application entry point
├── middleware/                       # FastAPI middleware
├── migrations/                       # Database migration scripts
├── models/                           # SQLAlchemy model definitions
├── orm/                              # ORM layer (176 files)
│   ├── base.py                       # Base ORM model
│   ├── user.py                       # User model & UserRole enum
│   ├── phase14_round_engine.py       # Round engine enums & models
│   ├── phase15_ai_evaluation.py     # AI evaluation models
│   ├── phase16_analytics.py          # Analytics enums & models
│   ├── phase17_appeals.py            # Appeals enums & models
│   ├── phase18_scheduling.py           # Scheduling enums & models
│   ├── phase19_moot_operations.py     # Session enums & models
│   ├── phase20_tournament_lifecycle.py # Lifecycle enums & models
│   └── phase21_admin_center.py       # Admin action logs
├── rbac.py                           # Role-based access control
├── realtime/                         # Realtime/WebSocket modules
├── routes/                           # API route definitions (173 files)
│   ├── auth.py                       # Authentication routes
│   ├── phase14_round_engine.py       # Round engine routes
│   ├── phase15_ai_judge.py           # AI judge routes
│   ├── phase16_analytics.py          # Analytics routes
│   ├── phase17_appeals.py            # Appeals routes
│   ├── phase18_scheduling.py         # Scheduling routes
│   ├── phase19_moot_operations.py     # Session routes
│   ├── phase20_lifecycle.py          # Lifecycle routes
│   └── phase21_admin_center.py       # Admin routes
├── schemas/                          # Pydantic schemas
├── scripts/                          # Utility scripts
├── security/                         # Security utilities
├── seed/                             # Seed data
├── services/                         # Business logic (181 files)
│   ├── phase14_round_service.py
│   ├── phase15_shadow_service.py
│   ├── phase15_official_service.py
│   ├── phase16_analytics_service.py
│   ├── phase17_appeal_service.py
│   ├── phase18_schedule_service.py
│   ├── phase19_session_service.py
│   ├── phase20_lifecycle_service.py
│   └── phase21_admin_service.py
├── state_machines/                   # State machine definitions
├── tasks/                            # Background tasks
├── tests/                            # Test suite (67 files)
├── uploads/                          # File upload storage
├── utils/                            # Utility functions
└── websockets/                       # WebSocket handlers
```

---

## 2. All Registered Routes

### Auth Routes

| METHOD | FULL PATH | ROUTER FILE | REQUIRED ROLE | FEATURE FLAG | DESCRIPTION |
|--------|-----------|-------------|---------------|--------------|-------------|
| POST | /api/auth/register | auth.py | PUBLIC | None | Register new user with role |
| POST | /api/auth/login | auth.py | PUBLIC | None | Login with JSON credentials |
| POST | /api/auth/login/form | auth.py | PUBLIC | None | OAuth2 form login |
| GET | /api/auth/me | auth.py | ANY | None | Get current user info |
| POST | /api/auth/refresh | auth.py | ANY | None | Refresh access token |
| POST | /api/auth/logout | auth.py | ANY | None | Logout and invalidate token |
| POST | /api/auth/change-password | auth.py | ANY | None | Change user password |

### Phase 14 — Round Engine Routes

| METHOD | FULL PATH | ROUTER FILE | REQUIRED ROLE | FEATURE FLAG | DESCRIPTION |
|--------|-----------|-------------|---------------|--------------|-------------|
| POST | /api/round-engine/tournaments/{tournament_id}/rounds | phase14_round_engine.py | ADMIN, JUDGE | FEATURE_CLASSROOM_ROUND_ENGINE | Create new round |
| POST | /api/round-engine/rounds/{round_id}/matches | phase14_round_engine.py | ADMIN, JUDGE | FEATURE_CLASSROOM_ROUND_ENGINE | Assign matches to round |
| POST | /api/round-engine/matches/{match_id}/turns | phase14_round_engine.py | ADMIN, JUDGE | FEATURE_CLASSROOM_ROUND_ENGINE | Generate speaker turns |
| POST | /api/round-engine/matches/{match_id}/advance | phase14_round_engine.py | JUDGE, ADMIN | FEATURE_CLASSROOM_ROUND_ENGINE | Advance to next turn |
| POST | /api/round-engine/matches/{match_id}/freeze | phase14_round_engine.py | JUDGE, ADMIN | FEATURE_CLASSROOM_ROUND_ENGINE | Freeze match (irreversible) |
| GET | /api/round-engine/matches/{match_id}/integrity | phase14_round_engine.py | ANY | FEATURE_CLASSROOM_ROUND_ENGINE | Verify match integrity |
| GET | /api/round-engine/matches/{match_id}/timer | phase14_round_engine.py | ANY | FEATURE_CLASSROOM_ROUND_ENGINE | Get timer state |
| POST | /api/round-engine/matches/{match_id}/timer/pause | phase14_round_engine.py | JUDGE | FEATURE_CLASSROOM_ROUND_ENGINE | Pause timer |
| POST | /api/round-engine/matches/{match_id}/timer/resume | phase14_round_engine.py | JUDGE | FEATURE_CLASSROOM_ROUND_ENGINE | Resume timer |
| POST | /api/round-engine/matches/{match_id}/timer/tick | phase14_round_engine.py | SYSTEM | FEATURE_CLASSROOM_ROUND_ENGINE | Timer tick (system) |
| GET | /api/round-engine/crash-recovery | phase14_round_engine.py | ADMIN | FEATURE_CLASSROOM_ROUND_ENGINE | Get live matches for recovery |

### Phase 15 — AI Judge Routes

| METHOD | FULL PATH | ROUTER FILE | REQUIRED ROLE | FEATURE FLAG | DESCRIPTION |
|--------|-----------|-------------|---------------|--------------|-------------|
| POST | /api/ai/shadow/{match_id} | phase15_ai_judge.py | JUDGE, ADMIN | FEATURE_AI_EVALUATION | Generate shadow scoring |
| POST | /api/ai/official/{match_id} | phase15_ai_judge.py | JUDGE, ADMIN | FEATURE_AI_EVALUATION | Generate official evaluation |
| GET | /api/ai/evaluations/{match_id}/history | phase15_ai_judge.py | JUDGE, ADMIN | FEATURE_AI_EVALUATION | Get evaluation history |
| POST | /api/ai/evaluations/{match_id}/verify | phase15_ai_judge.py | JUDGE, ADMIN | FEATURE_AI_EVALUATION | Verify evaluation integrity |
| GET | /api/ai/snapshot/{match_id} | phase15_ai_judge.py | JUDGE, ADMIN | FEATURE_AI_EVALUATION | Get match snapshot |
| GET | /api/ai/models | phase15_ai_judge.py | ANY | FEATURE_AI_EVALUATION | List available AI models |

### Phase 16 — Analytics Routes

| METHOD | FULL PATH | ROUTER FILE | REQUIRED ROLE | FEATURE FLAG | DESCRIPTION |
|--------|-----------|-------------|---------------|--------------|-------------|
| POST | /api/analytics/recompute/speakers | phase16_analytics.py | ADMIN | FEATURE_ANALYTICS_RECOMPUTE | Recompute speaker stats |
| POST | /api/analytics/recompute/teams | phase16_analytics.py | ADMIN | FEATURE_ANALYTICS_RECOMPUTE | Recompute team stats |
| POST | /api/analytics/recompute/batch | phase16_analytics.py | ADMIN | FEATURE_ANALYTICS_RECOMPUTE | Batch recompute all |
| GET | /api/analytics/rankings/speakers | phase16_analytics.py | ANY | FEATURE_RANKING_ENGINE | Get speaker rankings |
| GET | /api/analytics/rankings/teams | phase16_analytics.py | ANY | FEATURE_RANKING_ENGINE | Get team rankings |
| GET | /api/analytics/rankings/tiers | phase16_analytics.py | ANY | FEATURE_RANKING_ENGINE | Get tier distribution |
| GET | /api/analytics/speakers/{speaker_id}/profile | phase16_analytics.py | ANY | FEATURE_ANALYTICS_DASHBOARD | Get speaker profile |
| GET | /api/analytics/teams/{team_id}/profile | phase16_analytics.py | ANY | FEATURE_ANALYTICS_DASHBOARD | Get team profile |
| GET | /api/analytics/judges/{judge_id}/profile | phase16_analytics.py | JUDGE, ADMIN | FEATURE_JUDGE_ANALYTICS | Get judge analytics |
| GET | /api/analytics/trends | phase16_analytics.py | ANY | FEATURE_TREND_ENGINE | Get trending analytics |

### Phase 17 — Appeals Routes

| METHOD | FULL PATH | ROUTER FILE | REQUIRED ROLE | FEATURE FLAG | DESCRIPTION |
|--------|-----------|-------------|---------------|--------------|-------------|
| POST | /api/appeals | phase17_appeals.py | TEAM | FEATURE_APPEALS_ENGINE | File new appeal |
| GET | /api/appeals/{appeal_id} | phase17_appeals.py | ANY | FEATURE_APPEALS_ENGINE | Get appeal details |
| GET | /api/appeals/match/{match_id} | phase17_appeals.py | ANY | FEATURE_APPEALS_ENGINE | Get match appeals |
| POST | /api/appeals/{appeal_id}/reviews | phase17_appeals.py | JUDGE | FEATURE_APPEALS_ENGINE | Submit judge review |
| GET | /api/appeals/{appeal_id}/reviews | phase17_appeals.py | ADMIN | FEATURE_APPEALS_ENGINE | Get all reviews |
| POST | /api/appeals/{appeal_id}/finalize | phase17_appeals.py | ADMIN | FEATURE_APPEALS_ENGINE | Finalize appeal decision |
| GET | /api/appeals/queue/pending | phase17_appeals.py | ADMIN, JUDGE | FEATURE_APPEALS_ENGINE | Get pending appeals queue |
| GET | /api/appeals/integrity/{appeal_id} | phase17_appeals.py | ANY | FEATURE_APPEALS_ENGINE | Verify appeal integrity |

### Phase 18 — Scheduling Routes

| METHOD | FULL PATH | ROUTER FILE | REQUIRED ROLE | FEATURE FLAG | DESCRIPTION |
|--------|-----------|-------------|---------------|--------------|-------------|
| POST | /api/schedule/days | phase18_scheduling.py | ADMIN | FEATURE_SCHEDULING | Create schedule day |
| GET | /api/schedule/days/{tournament_id} | phase18_scheduling.py | ANY | FEATURE_SCHEDULING | Get schedule days |
| POST | /api/schedule/slots | phase18_scheduling.py | ADMIN | FEATURE_SCHEDULING | Create time slot |
| GET | /api/schedule/slots/{day_id} | phase18_scheduling.py | ANY | FEATURE_SCHEDULING | Get time slots |
| POST | /api/schedule/courtrooms | phase18_scheduling.py | ADMIN | FEATURE_SCHEDULING | Create courtroom |
| GET | /api/schedule/courtrooms/{tournament_id} | phase18_scheduling.py | ANY | FEATURE_SCHEDULING | Get courtrooms |
| POST | /api/schedule/assignments | phase18_scheduling.py | ADMIN | FEATURE_SCHEDULING | Assign match to slot |
| GET | /api/schedule/assignments/{tournament_id} | phase18_scheduling.py | ANY | FEATURE_SCHEDULING | Get all assignments |
| GET | /api/schedule/assignments/{assignment_id}/details | phase18_scheduling.py | ANY | FEATURE_SCHEDULING | Get assignment details |
| POST | /api/schedule/days/{day_id}/freeze | phase18_scheduling.py | ADMIN | FEATURE_SCHEDULING | Freeze schedule day |
| POST | /api/schedule/assignments/{assignment_id}/unassign | phase18_scheduling.py | ADMIN | FEATURE_SCHEDULING | Unassign match |
| GET | /api/schedule/verify/{day_id} | phase18_scheduling.py | ANY | FEATURE_SCHEDULING | Verify schedule integrity |

### Phase 19 — Moot Operations Routes

| METHOD | FULL PATH | ROUTER FILE | REQUIRED ROLE | FEATURE FLAG | DESCRIPTION |
|--------|-----------|-------------|---------------|--------------|-------------|
| POST | /api/session | phase19_moot_operations.py | JUDGE, ADMIN | FEATURE_MOOT_OPERATIONS | Create session |
| GET | /api/session/{session_id} | phase19_moot_operations.py | ANY | FEATURE_MOOT_OPERATIONS | Get session details |
| POST | /api/session/{session_id}/start | phase19_moot_operations.py | JUDGE, ADMIN | FEATURE_MOOT_OPERATIONS | Start session |
| POST | /api/session/{session_id}/end | phase19_moot_operations.py | JUDGE, ADMIN | FEATURE_MOOT_OPERATIONS | End session |
| POST | /api/session/{session_id}/participants | phase19_moot_operations.py | ANY | FEATURE_MOOT_OPERATIONS | Join as participant |
| DELETE | /api/session/{session_id}/participants | phase19_moot_operations.py | ANY | FEATURE_MOOT_OPERATIONS | Leave session |
| POST | /api/session/{session_id}/observers | phase19_moot_operations.py | ANY | FEATURE_MOOT_OPERATIONS | Join as observer |
| DELETE | /api/session/{session_id}/observers | phase19_moot_operations.py | ANY | FEATURE_MOOT_OPERATIONS | Leave as observer |
| POST | /api/session/{session_id}/events | phase19_moot_operations.py | ANY | FEATURE_MOOT_OPERATIONS | Log session event |
| GET | /api/session/{session_id}/events | phase19_moot_operations.py | ANY | FEATURE_MOOT_OPERATIONS | Get session events |
| GET | /api/session/{session_id}/logs | phase19_moot_operations.py | ANY | FEATURE_MOOT_OPERATIONS | Get audit logs |
| GET | /api/session/tournament/{tournament_id} | phase19_moot_operations.py | ANY | FEATURE_MOOT_OPERATIONS | Get tournament sessions |
| POST | /api/session/{session_id}/verify-logs | phase19_moot_operations.py | ANY | FEATURE_MOOT_OPERATIONS | Verify log integrity |

### Phase 20 — Tournament Lifecycle Routes

| METHOD | FULL PATH | ROUTER FILE | REQUIRED ROLE | FEATURE FLAG | DESCRIPTION |
|--------|-----------|-------------|---------------|--------------|-------------|
| POST | /api/lifecycle/create/{tournament_id} | phase20_lifecycle.py | ADMIN, SUPER_ADMIN | FEATURE_TOURNAMENT_LIFECYCLE | Create lifecycle |
| GET | /api/lifecycle/{tournament_id} | phase20_lifecycle.py | ANY | FEATURE_TOURNAMENT_LIFECYCLE | Get lifecycle status |
| POST | /api/lifecycle/{tournament_id}/transition | phase20_lifecycle.py | ADMIN | FEATURE_TOURNAMENT_LIFECYCLE | Transition status |
| GET | /api/lifecycle/{tournament_id}/verify | phase20_lifecycle.py | ANY | FEATURE_TOURNAMENT_LIFECYCLE | Verify standings hash |
| GET | /api/lifecycle/{tournament_id}/standings-hash | phase20_lifecycle.py | ANY | FEATURE_TOURNAMENT_LIFECYCLE | Get standings hash |
| GET | /api/lifecycle/{tournament_id}/check-operation/{operation} | phase20_lifecycle.py | ANY | FEATURE_TOURNAMENT_LIFECYCLE | Check if operation allowed |
| GET | /api/lifecycle/{tournament_id}/guards | phase20_lifecycle.py | ANY | FEATURE_TOURNAMENT_LIFECYCLE | Get lifecycle guards |

### Phase 21 — Admin Command Center Routes

| METHOD | FULL PATH | ROUTER FILE | REQUIRED ROLE | FEATURE FLAG | DESCRIPTION |
|--------|-----------|-------------|---------------|--------------|-------------|
| GET | /api/admin/overview/{tournament_id} | phase21_admin_center.py | ADMIN, SUPER_ADMIN | FEATURE_ADMIN_COMMAND_CENTER | Tournament overview |
| GET | /api/admin/guards/{tournament_id} | phase21_admin_center.py | ADMIN, SUPER_ADMIN | FEATURE_ADMIN_COMMAND_CENTER | Cross-phase guard status |
| GET | /api/admin/appeals-queue/{tournament_id} | phase21_admin_center.py | ADMIN, SUPER_ADMIN | FEATURE_ADMIN_COMMAND_CENTER | Appeals queue |
| GET | /api/admin/sessions/{tournament_id} | phase21_admin_center.py | ADMIN, SUPER_ADMIN | FEATURE_ADMIN_COMMAND_CENTER | Session monitor |
| GET | /api/admin/sessions-summary/{tournament_id} | phase21_admin_center.py | ADMIN, SUPER_ADMIN | FEATURE_ADMIN_COMMAND_CENTER | Session summary |
| GET | /api/admin/integrity/{tournament_id} | phase21_admin_center.py | ADMIN, SUPER_ADMIN | FEATURE_ADMIN_COMMAND_CENTER | Integrity check |
| POST | /api/admin/log-action | phase21_admin_center.py | ADMIN, SUPER_ADMIN | FEATURE_ADMIN_COMMAND_CENTER | Log admin action |
| GET | /api/admin/action-logs/{tournament_id} | phase21_admin_center.py | ADMIN, SUPER_ADMIN | FEATURE_ADMIN_COMMAND_CENTER | View action logs |
| POST | /api/admin/verify-log/{log_id} | phase21_admin_center.py | ADMIN, SUPER_ADMIN | FEATURE_ADMIN_COMMAND_CENTER | Verify log integrity |
| GET | /api/admin/global-overview | phase21_admin_center.py | SUPER_ADMIN | FEATURE_ADMIN_COMMAND_CENTER | Global overview |
| POST | /api/admin/clear-cache | phase21_admin_center.py | SUPER_ADMIN | FEATURE_ADMIN_COMMAND_CENTER | Clear system cache |

### Health Check Routes

| METHOD | FULL PATH | ROUTER FILE | REQUIRED ROLE | FEATURE FLAG | DESCRIPTION |
|--------|-----------|-------------|---------------|--------------|-------------|
| GET | /api/health | main.py | PUBLIC | None | System health check |
| GET | /api/health/db | main.py | PUBLIC | None | Database health check |
| GET | /api/health/ready | main.py | PUBLIC | None | Readiness probe |

---

## 3. Auth System Details

### JWT Structure

**Token Payload (Claims):**
```json
{
  "sub": "user@example.com",
  "user_id": 123,
  "role": "judge",
  "institution_id": 456,
  "exp": 1708012800,
  "iat": 1708011000
}
```

**Claims:**
- `sub` (string): User email address
- `user_id` (integer): Internal user ID
- `role` (string): User role (see Role Enum below)
- `institution_id` (integer|null): Institution context
- `exp` (integer): Expiration timestamp (Unix)
- `iat` (integer): Issued at timestamp (Unix)

### Role Enum Values

| Role | Value | Description | Typical Access |
|------|-------|-------------|--------------|
| STUDENT | "student" | Law student | Own profile, view rankings |
| JUDGE | "judge" | Competition judge | Score matches, file appeals |
| FACULTY | "faculty" | Faculty member | View analytics, moderate |
| EXTERNAL_EXAMINER | "external_examiner" | External reviewer | Read-only access |
| HOD | "hod" | Head of Department | Institution-level admin |
| ADMIN | "admin" | System admin | Full tournament management |
| SUPER_ADMIN | "super_admin" | Super administrator | Global operations |
| RECRUITER | "recruiter" | Legal recruiter | View anonymized rankings |

### Role Validation

**Dependency Injection Pattern:**
```python
# Require specific role
@router.post("/endpoint", dependencies=[Depends(require_role([UserRole.ADMIN]))])

# Require minimum role (hierarchy)
@router.post("/endpoint", dependencies=[Depends(require_min_role(UserRole.JUDGE))])

# Any authenticated user
@router.get("/endpoint", dependencies=[Depends(get_current_user)])
```

**Role Hierarchy (lowest to highest):**
1. STUDENT
2. JUDGE
3. FACULTY
4. EXTERNAL_EXAMINER
5. HOD
6. ADMIN
7. SUPER_ADMIN

### Token Configuration

| Setting | Value |
|---------|-------|
| Algorithm | HS256 |
| Access Token Expiry | 30 minutes |
| Refresh Token Expiry | 7 days |
| Secret Source | JWT_SECRET_KEY env var |

### Required Headers

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

### Error Response Behavior

**401 Unauthorized:**
```json
{
  "success": false,
  "error": "Unauthorized",
  "message": "Invalid or expired token",
  "code": "AUTH_EXPIRED"
}
```

**403 Forbidden:**
```json
{
  "success": false,
  "error": "Forbidden",
  "message": "Insufficient permissions",
  "code": "ACCESS_DENIED"
}
```

### Token Refresh Flow

1. **Request:** POST `/api/auth/refresh` with refresh_token
2. **Success:** Returns new access_token + refresh_token
3. **Failure:** 401 if refresh token expired/invalid

---

## 4. Feature Flags

### All Feature Flags

| FLAG NAME | DEFAULT | USED IN FILE | DESCRIPTION |
|-----------|---------|--------------|-------------|
| `FEATURE_CLASSROOM_ROUND_ENGINE` | False | phase14_round_engine.py | Phase 14 round engine |
| `FEATURE_AI_EVALUATION` | False | phase15_ai_judge.py | Phase 15 AI judge |
| `FEATURE_ANALYTICS_RECOMPUTE` | False | phase16_analytics.py | Phase 16 analytics recompute |
| `FEATURE_RANKING_ENGINE` | False | phase16_analytics.py | Phase 16 rankings |
| `FEATURE_ANALYTICS_DASHBOARD` | False | phase16_analytics.py | Phase 16 dashboard |
| `FEATURE_JUDGE_ANALYTICS` | False | phase16_analytics.py | Phase 16 judge analytics |
| `FEATURE_TREND_ENGINE` | False | phase16_analytics.py | Phase 16 trends |
| `FEATURE_APPEALS_ENGINE` | False | phase17_appeals.py | Phase 17 appeals |
| `FEATURE_SCHEDULING` | False | phase18_scheduling.py | Phase 18 scheduling |
| `FEATURE_MOOT_OPERATIONS` | False | phase19_moot_operations.py | Phase 19 sessions |
| `FEATURE_TOURNAMENT_LIFECYCLE` | False | phase20_lifecycle.py | Phase 20 lifecycle |
| `FEATURE_ADMIN_COMMAND_CENTER` | False | phase21_admin_center.py | Phase 21 admin center |

### Feature Flag Behavior

**When Disabled:**
- Returns HTTP 403 Forbidden
- Error message: "[Feature] is disabled"

**Check Method (from config/feature_flags.py):**
```python
from backend.config.feature_flags import feature_flags

if not feature_flags.FEATURE_X:
    raise HTTPException(status_code=403, detail="Feature disabled")
```

---

## 5. Database Enums

### Phase 14 — Round Engine Enums

```python
class RoundType(str, Enum):
    PRELIMINARY = "preliminary"
    QUARTERFINAL = "quarterfinal"
    SEMIFINAL = "semifinal"
    FINAL = "final"

class RoundStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ONGOING = "ongoing"
    COMPLETED = "completed"

class MatchStatus(str, Enum):
    SCHEDULED = "scheduled"
    ONGOING = "ongoing"
    PAUSED = "paused"
    FROZEN = "frozen"
    COMPLETED = "completed"

class TurnStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    TIMED_OUT = "timed_out"

class SpeakerRole(str, Enum):
    PETITIONER_PRIMARY = "petitioner_primary"
    PETITIONER_REBUTTAL = "petitioner_rebuttal"
    RESPONDENT_PRIMARY = "respondent_primary"
    RESPONDENT_SUR_REBUTTAL = "respondent_sur_rebuttal"
    JUDGE = "judge"
```

### Phase 16 — Analytics Enums

```python
class EntityType(str, Enum):
    SPEAKER = "speaker"
    TEAM = "team"

class RankingTier(str, Enum):
    S = "S"
    A = "A"
    B = "B"
    C = "C"
    D = "D"

class StreakType(str, Enum):
    WINNING = "winning"
    LOSING = "losing"
    UNRANKED = "unranked"
```

### Phase 17 — Appeals Enums

```python
class AppealReasonCode(str, Enum):
    SCORING_ERROR = "scoring_error"
    PROCEDURAL_ERROR = "procedural_error"
    JUDGE_BIAS = "judge_bias"
    TECHNICAL_ISSUE = "technical_issue"

class AppealStatus(str, Enum):
    PENDING = "pending"
    UNDER_REVIEW = "under_review"
    REVIEWED = "reviewed"
    DECISION_PENDING = "decision_pending"
    UPHELD = "upheld"
    MODIFIED = "modified"
    REVERSED = "reversed"
    DISMISSED = "dismissed"

class RecommendedAction(str, Enum):
    UPHOLD = "uphold"
    MODIFY_SCORE = "modify_score"
    REVERSE_WINNER = "reverse_winner"

class WinnerSide(str, Enum):
    PETITIONER = "petitioner"
    RESPONDENT = "respondent"
    DRAW = "draw"
```

### Phase 18 — Scheduling Enums

```python
class ScheduleStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    FROZEN = "frozen"

class AssignmentStatus(str, Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
```

### Phase 19 — Moot Operations Enums

```python
class SessionStatus(str, Enum):
    PENDING = "pending"
    STARTING = "starting"
    ACTIVE = "active"
    PAUSED = "paused"
    ENDING = "ending"
    COMPLETED = "completed"
    ABORTED = "aborted"

class ParticipantRole(str, Enum):
    SPEAKER = "speaker"
    TEAM_LEAD = "team_lead"
    JUDGE = "judge"
    CLERK = "clerk"
    MODERATOR = "moderator"

class ParticipantStatus(str, Enum):
    INVITED = "invited"
    JOINING = "joining"
    ACTIVE = "active"
    AWAY = "away"
    DISCONNECTED = "disconnected"
    LEFT = "left"
```

### Phase 20 — Tournament Lifecycle Enums

```python
class TournamentStatus(str, Enum):
    DRAFT = "draft"
    REGISTRATION_OPEN = "registration_open"
    REGISTRATION_CLOSED = "registration_closed"
    PRELIMINARY = "preliminary"
    ELIMINATION = "elimination"
    FINALS = "finals"
    SCORING_LOCKED = "scoring_locked"
    COMPLETED = "completed"
    ARCHIVED = "archived"
```

### User Role Enum (from orm/user.py)

```python
class UserRole(str, Enum):
    STUDENT = "student"
    JUDGE = "judge"
    FACULTY = "faculty"
    EXTERNAL_EXAMINER = "external_examiner"
    HOD = "hod"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"
    RECRUITER = "recruiter"
```

---

## 6. Standard Response Format

### Success Response

**With Data:**
```json
{
  "status": "success",
  "data": { ... },
  "message": "Operation completed successfully"
}
```

**List Response:**
```json
{
  "status": "success",
  "data": [
    { ... },
    { ... }
  ],
  "meta": {
    "total": 100,
    "page": 1,
    "per_page": 20,
    "pages": 5
  }
}
```

### Error Response

```json
{
  "success": false,
  "error": "ErrorType",
  "message": "Human-readable error description",
  "code": "ERROR_CODE",
  "details": { ... }  // Optional additional info
}
```

### Common Error Codes

| Code | HTTP Status | Meaning |
|------|-------------|---------|
| AUTH_EXPIRED | 401 | Token expired |
| AUTH_INVALID | 401 | Invalid token |
| ACCESS_DENIED | 403 | Insufficient role |
| FEATURE_DISABLED | 403 | Feature flag off |
| NOT_FOUND | 404 | Resource not found |
| INVALID_INPUT | 400 | Validation error |
| CONFLICT | 409 | State conflict |
| RATE_LIMITED | 429 | Too many requests |

### Timestamp Format

- **All timestamps:** ISO 8601 format (UTC)
- **Example:** `"2026-02-15T10:30:00Z"`
- **Pattern:** `YYYY-MM-DDTHH:MM:SSZ`

### UUID Format

- **Format:** String (36 characters)
- **Example:** `"550e8400-e29b-41d4-a716-446655440000"`
- **Pattern:** `xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx`

---

## 7. Guarded Operations

### Lifecycle Guards (Phase 20)

Operations blocked by tournament lifecycle status:

| Operation | Blocked When | Error Code |
|-----------|--------------|------------|
| File Appeal | ARCHIVED | TOURNAMENT_CLOSED |
| Schedule Match | COMPLETED, ARCHIVED | TOURNAMENT_CLOSED |
| Modify Score | SCORING_LOCKED, COMPLETED, ARCHIVED | SCORING_LOCKED |
| Start Session | ARCHIVED | TOURNAMENT_CLOSED |
| Ranking Recompute | ARCHIVED | TOURNAMENT_CLOSED |

### Match Freeze Guards (Phase 14)

| Operation | Blocked When | Error Code |
|-----------|--------------|------------|
| Advance Turn | FROZEN | MATCH_FROZEN |
| Modify Score | FROZEN | MATCH_FROZEN |
| Pause Timer | FROZEN | MATCH_FROZEN |
| Add Turn | FROZEN | MATCH_FROZEN |

### Schedule Freeze Guards (Phase 18)

| Operation | Blocked When | Error Code |
|-----------|--------------|------------|
| Unassign Match | FROZEN | SCHEDULE_FROZEN |
| Modify Slot | FROZEN | SCHEDULE_FROZEN |
| Add Courtroom | FROZEN | SCHEDULE_FROZEN |

### Feature Flag Guards

| Phase | Feature Flag | Blocked Operations |
|-------|--------------|-------------------|
| Phase 14 | FEATURE_CLASSROOM_ROUND_ENGINE | All round engine operations |
| Phase 15 | FEATURE_AI_EVALUATION | AI scoring, evaluation |
| Phase 16 | FEATURE_RANKING_ENGINE | Rankings, recomputation |
| Phase 17 | FEATURE_APPEALS_ENGINE | Appeal filing, review |
| Phase 18 | FEATURE_SCHEDULING | Schedule management |
| Phase 19 | FEATURE_MOOT_OPERATIONS | Session management |
| Phase 20 | FEATURE_TOURNAMENT_LIFECYCLE | Lifecycle transitions |
| Phase 21 | FEATURE_ADMIN_COMMAND_CENTER | Admin operations |

### Role Guards Summary

| Operation | Required Role |
|-----------|---------------|
| Create Tournament | ADMIN, SUPER_ADMIN |
| Create Round | ADMIN, JUDGE |
| Freeze Match | JUDGE, ADMIN |
| AI Evaluation | JUDGE, ADMIN |
| File Appeal | TEAM (own team only) |
| Review Appeal | JUDGE |
| Finalize Appeal | ADMIN |
| Schedule Management | ADMIN |
| Session Control | JUDGE, ADMIN |
| Lifecycle Transition | ADMIN |
| Admin Operations | ADMIN, SUPER_ADMIN |

---

## 8. Cross-Phase Dependencies

### Phase Dependency Graph

```
Phase 14 (Round Engine)
  ↓ Data flow
Phase 15 (AI Judge) ← reads match data from Phase 14
  ↓
Phase 16 (Analytics) ← reads scores from Phase 14, 15
  ↓
Phase 17 (Appeals) ← reads match data from Phase 14
  ↓ Can modify
Phase 16 (Analytics) ← appeals can trigger recompute
  ↑
Phase 18 (Scheduling) ← reads matches from Phase 14
  ↓
Phase 19 (Sessions) ← reads assignments from Phase 18
  ↓
Phase 20 (Lifecycle) ← guards all phases above
  ↓
Phase 21 (Admin) ← reads from all phases
```

### Service Dependencies

| Service | Reads From | Writes To |
|---------|-----------|-----------|
| Phase14 RoundService | - | Round, Match, Turn |
| Phase15 ShadowService | Match, Turn | AIMatchEvaluation |
| Phase16 RankingEngine | Match, SpeakerStats | Ranking |
| Phase17 AppealService | Match, AIMatchEvaluation | Appeal, AppealDecision |
| Phase18 ScheduleService | Match | ScheduleDay, TimeSlot, Assignment |
| Phase19 SessionService | Assignment | CourtroomSession, SessionLogEntry |
| Phase20 LifecycleService | All above | TournamentLifecycle |
| Phase21 AdminService | All above | AdminActionLog |

### Async Background Tasks

| Task | Trigger | Phase |
|------|---------|-------|
| Timer tick | Scheduled | Phase 14 |
| AI evaluation | Match freeze | Phase 15 |
| Ranking recompute | Schedule/Appeal | Phase 16 |
| Session log batch | Session events | Phase 19 |

### No Circular Dependencies

All dependencies are acyclic (verified):
- Lower phases don't import higher phases
- Services use dependency injection
- Cross-phase guards use service layer abstraction

---

## 9. Pagination & Filter Support

### Query Parameters (Standard)

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `page` | integer | 1 | Page number (1-indexed) |
| `per_page` | integer | 20 | Items per page |
| `sort_by` | string | created_at | Field to sort by |
| `sort_order` | string | desc | Sort direction (asc/desc) |

### List Endpoints with Pagination

| Endpoint | Supports | Notes |
|----------|----------|-------|
| GET /api/analytics/rankings/{type} | page, per_page, sort | Sort by rank_position |
| GET /api/appeals/queue/pending | page, per_page | Filter by status |
| GET /api/schedule/assignments/{id} | page, per_page | By tournament |
| GET /api/session/tournament/{id} | page, per_page | By status filter |
| GET /api/admin/action-logs/{id} | page, per_page | By timestamp |

### Filter Parameters

| Endpoint | Filter Params |
|----------|---------------|
| GET /api/analytics/rankings/speakers | tier, institution_id, min_score |
| GET /api/analytics/rankings/teams | tier, institution_id |
| GET /api/appeals/match/{match_id} | status |
| GET /api/session/tournament/{id} | status, date_from, date_to |

### Pagination Response Format

```json
{
  "status": "success",
  "data": [ ... ],
  "meta": {
    "total": 100,
    "page": 1,
    "per_page": 20,
    "pages": 5,
    "has_next": true,
    "has_prev": false
  }
}
```

---

## 10. Time-Sensitive Endpoints

### Timer-Dependent Endpoints

| Endpoint | Time Dependency | Auto-Refresh Needed |
|----------|-----------------|---------------------|
| GET /api/round-engine/matches/{id}/timer | remaining_seconds changes every tick | Yes (1s interval) |
| POST /api/round-engine/matches/{id}/advance | Must check turn expiry | Yes |
| POST /api/round-engine/matches/{id}/timer/tick | Server-side timer event | No (internal) |
| GET /api/session/{id} | Session duration tracking | Yes (5s interval) |

### Expiry Windows

| Entity | Expiry Window | Action on Expiry |
|--------|---------------|------------------|
| Access Token | 30 minutes | Refresh required |
| Refresh Token | 7 days | Re-login required |
| Turn Timer | Configurable (default 10 min) | Auto-complete turn |
| Session | Match duration | Auto-end session |
| Appeal Window | 24 hours post-freeze | Appeal filing blocked |

### Auto-Close Logic

| Scenario | Trigger | Result |
|----------|---------|--------|
| Turn timeout | remaining_seconds <= 0 | Turn auto-completed, next turn activated |
| Session idle | 30 min no activity | Session marked ABORTED |
| Appeal deadline | 24h after match freeze | Appeal filing returns 403 |
| Token expiry | exp claim passed | 401 response |

### Recommended Frontend Polling

| Endpoint | Poll Interval | Use Case |
|----------|---------------|----------|
| /api/round-engine/matches/{id}/timer | 1 second | Live timer display |
| /api/session/{id} | 5 seconds | Session status monitoring |
| /api/round-engine/matches/{id}/integrity | 10 seconds | Freeze status check |
| /api/lifecycle/{id} | 30 seconds | Tournament status |
| /api/analytics/rankings/* | 5 minutes | Rankings refresh |

---

## 11. Test Environment Requirements

### Required Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost/mootcourt
# or for SQLite
DATABASE_URL=sqlite:///./data/dev.db

# JWT
JWT_SECRET_KEY=your-secret-key-here

# Optional: Feature flags (enable all for testing)
FEATURE_CLASSROOM_ROUND_ENGINE=true
FEATURE_AI_EVALUATION=true
FEATURE_RANKING_ENGINE=true
FEATURE_APPEALS_ENGINE=true
FEATURE_SCHEDULING=true
FEATURE_MOOT_OPERATIONS=true
FEATURE_TOURNAMENT_LIFECYCLE=true
FEATURE_ADMIN_COMMAND_CENTER=true
```

### Required Feature Flags for Full Testing

Enable all feature flags in `backend/config/feature_flags.py`:

```python
class FeatureFlags:
    FEATURE_CLASSROOM_ROUND_ENGINE = True
    FEATURE_AI_EVALUATION = True
    FEATURE_RANKING_ENGINE = True
    FEATURE_APPEALS_ENGINE = True
    FEATURE_SCHEDULING = True
    FEATURE_MOOT_OPERATIONS = True
    FEATURE_TOURNAMENT_LIFECYCLE = True
    FEATURE_ADMIN_COMMAND_CENTER = True
```

### Required Seeding

```bash
# Seed test data
python scripts/seed_test_data.py --teams 100 --tournaments 1 --matches 500
```

### Minimum Roles for Testing

| Test Scenario | Roles Needed |
|---------------|--------------|
| Full round flow | ADMIN (create), JUDGE (run), STUDENT (view) |
| Appeal testing | TEAM (file), JUDGE (review), ADMIN (finalize) |
| Admin operations | ADMIN, SUPER_ADMIN |
| Scheduling | ADMIN only |
| Lifecycle | ADMIN only |

### Test User Creation

```bash
# Create admin
curl -X POST /api/auth/register -d '{
  "email": "admin@test.com",
  "password": "password",
  "name": "Test Admin",
  "role": "admin"
}'

# Create judge
curl -X POST /api/auth/register -d '{
  "email": "judge@test.com",
  "password": "password",
  "name": "Test Judge",
  "role": "judge"
}'

# Create student
curl -X POST /api/auth/register -d '{
  "email": "student@test.com",
  "password": "password",
  "name": "Test Student",
  "role": "student"
}'
```

### Verification Steps

1. Health check: `GET /api/health` → 200 OK
2. Auth test: `POST /api/auth/login` → Token received
3. Feature check: Each phase endpoint → 200 (not 403)
4. Database: Verify tables created

---

## Frontend Integration Notes

### Button-to-Endpoint Mapping

| UI Button | Endpoint | Required Role | Disable When |
|-----------|----------|---------------|--------------|
| "Create Round" | POST /api/round-engine/tournaments/{id}/rounds | ADMIN/JUDGE | Lifecycle >= COMPLETED |
| "Freeze Match" | POST /api/round-engine/matches/{id}/freeze | JUDGE/ADMIN | Already FROZEN |
| "File Appeal" | POST /api/appeals | TEAM | Match not FROZEN, Lifecycle >= ARCHIVED |
| "Review Appeal" | POST /api/appeals/{id}/reviews | JUDGE | Appeal not in PENDING/UNDER_REVIEW |
| "Finalize Decision" | POST /api/appeals/{id}/finalize | ADMIN | Appeal not in REVIEWED/DECISION_PENDING |
| "Transition Status" | POST /api/lifecycle/{id}/transition | ADMIN | Lifecycle status locked |

### Status Display Mapping

| Backend Status | UI Display | Color |
|----------------|------------|-------|
| SCHEDULED | Scheduled | Blue |
| ONGOING | In Progress | Green |
| PAUSED | Paused | Yellow |
| FROZEN | Frozen (Locked) | Red |
| COMPLETED | Completed | Gray |
| PENDING | Pending | Blue |
| UNDER_REVIEW | Under Review | Yellow |
| UPHELD | Upheld | Green |
| REVERSED | Reversed | Red |

### WebSocket Events (if applicable)

| Event | Payload | Handler |
|-------|---------|---------|
| `timer.tick` | `{match_id, remaining_seconds}` | Update timer display |
| `session.event` | `{session_id, event_type, data}` | Update session log |
| `match.frozen` | `{match_id, frozen_hash}` | Disable edit buttons |
| `appeal.status_change` | `{appeal_id, new_status}` | Update appeal card |

---

## Document Information

- **Generated:** February 15, 2026
- **Backend Version:** Phases 14-21 Complete
- **Scope:** Full API surface for frontend integration
- **Maintainer:** Backend Team

---

*End of Frontend Integration Introspection Report*
