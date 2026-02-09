# Juris AI - Phase 5C Implementation Summary

## Moot Project Persistence (Replaces localStorage)

### Overview
Phase 5C replaces all client-side/localStorage storage with robust backend persistence. This ensures data durability, enables multi-user collaboration, maintains audit history, and preserves institutional isolation.

---

## Core Entities Persisted

### 1. MootProject (Replaces localStorage Projects)
| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer | Primary key |
| `institution_id` | Integer | Institution scoping (Phase 5B) |
| `competition_id` | Integer | Associated competition (optional) |
| `team_id` | Integer | Associated team (optional) |
| `title` | String | Project title |
| `proposition` | Text | Moot proposition |
| `side` | String | petitioner/respondent |
| `court` | String | Court name |
| `domain` | String | Subject domain |
| `status` | Enum | draft/active/completed/archived |
| `created_by` | Integer | User who created the project |
| `deleted_at` | DateTime | Soft delete timestamp |

### 2. MootIssue (Replaces localStorage Issues)
| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer | Primary key |
| `project_id` | Integer | Parent project |
| `issue_order` | Integer | Display order |
| `title` | String | Issue title |
| `description` | Text | Issue description |
| `status` | Enum | not_started/partial/complete |

### 3. IRACBlock (Versioned - No Overwrites)
| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer | Primary key |
| `issue_id` | Integer | Associated issue |
| `block_type` | String | issue/rule/application/conclusion |
| `content` | Text | IRAC content |
| `version` | Integer | Version number (auto-incremented) |
| `is_active` | Boolean | Latest version flag |
| `created_by` | Integer | Who saved this version |

**Key Principle:** Each save creates a NEW version. Previous versions are preserved for audit.

### 4. OralRound (Immutable After Completion)
| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer | Primary key |
| `project_id` | Integer | Parent project |
| `stage` | Enum | petitioner/respondent/rebuttal/surrebuttal |
| `status` | Enum | scheduled/in_progress/completed/cancelled |
| `started_at` | DateTime | Round start time |
| `ended_at` | DateTime | Round end time |
| `is_locked` | Boolean | Immutable flag |
| `locked_at` | DateTime | Lock timestamp |

### 5. OralResponse (Chronological Record)
| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer | Primary key |
| `round_id` | Integer | Parent round |
| `speaker_role` | String | petitioner_counsel/respondent_counsel/etc |
| `text` | Text | Spoken content |
| `timestamp` | DateTime | When spoken |
| `elapsed_seconds` | Integer | Time into round |

### 6. BenchQuestion (Judge Questions)
| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer | Primary key |
| `round_id` | Integer | Parent round |
| `judge_name` | String | Judge identifier |
| `question_text` | Text | Question asked |
| `timestamp` | DateTime | When asked |
| `was_answered` | Boolean | Whether answered |

### 7. RoundTranscript (Auto-Generated, Immutable)
| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer | Primary key |
| `round_id` | Integer | Parent round (unique) |
| `transcript_items` | Text | JSON chronological sequence |
| `full_text` | Text | Plain text transcript |
| `is_final` | Boolean | Always true once generated |

### 8. MootEvaluation (Draft/Final Workflow)
| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer | Primary key |
| `project_id` | Integer | Project being evaluated |
| `judge_id` | Integer | Evaluating judge |
| `issue_framing_score` | Float | 0-10 scale |
| `legal_reasoning_score` | Float | 0-10 scale |
| `use_of_authority_score` | Float | 0-10 scale |
| `structure_clarity_score` | Float | 0-10 scale |
| `oral_advocacy_score` | Float | 0-10 scale |
| `responsiveness_score` | Float | 0-10 scale |
| `is_draft` | Boolean | Editable if true |
| `is_locked` | Boolean | Immutable if finalized |
| `finalized_at` | DateTime | Finalization timestamp |

---

## API Endpoints

### Moot Projects
| Endpoint | Method | Access | Description |
|----------|--------|--------|-------------|
| `/api/moot-projects` | POST | All | Create project |
| `/api/moot-projects` | GET | All (scoped) | List projects |
| `/api/moot-projects/{id}` | GET | All (owner) | Get project |
| `/api/moot-projects/{id}` | PATCH | Owner/Admin | Update project |
| `/api/moot-projects/{id}` | DELETE | Owner/Admin | Soft delete |

### Issues
| Endpoint | Method | Access | Description |
|----------|--------|--------|-------------|
| `/api/moot-projects/{id}/issues` | POST | Owner | Add issue |
| `/api/moot-projects/{id}/issues` | GET | Owner | List issues |
| `/api/moot-projects/{id}/issues/{issue_id}` | PATCH | Owner | Update issue |
| `/api/moot-projects/{id}/issues/{issue_id}` | DELETE | Owner | Delete issue |

### IRAC (Versioned)
| Endpoint | Method | Access | Description |
|----------|--------|--------|-------------|
| `/api/moot-projects/{id}/irac` | POST | Owner | Save IRAC (new version) |
| `/api/moot-projects/{id}/irac/history` | GET | Owner | Get version history |

### Oral Rounds
| Endpoint | Method | Access | Description |
|----------|--------|--------|-------------|
| `/api/oral-rounds` | POST | Owner | Start round |
| `/api/oral-rounds` | GET | Owner | List rounds |
| `/api/oral-rounds/{id}` | GET | Owner | Get round |
| `/api/oral-rounds/{id}/complete` | POST | Owner | Complete and lock |
| `/api/oral-rounds/{id}/responses` | POST | Owner | Submit response |
| `/api/oral-rounds/{id}/questions` | POST | Judge | Submit question |
| `/api/oral-rounds/{id}/transcript` | POST | Owner | Generate transcript |

### Evaluations
| Endpoint | Method | Access | Description |
|----------|--------|--------|-------------|
| `/api/moot-evaluations` | POST | Judge+ | Create evaluation |
| `/api/moot-evaluations` | GET | Judge/Student | List evaluations |
| `/api/moot-evaluations/{id}` | GET | Judge/Student | Get evaluation |
| `/api/moot-evaluations/{id}` | PATCH | Judge (draft) | Update evaluation |
| `/api/moot-evaluations/{id}/finalize` | POST | Judge | Finalize (lock) |
| `/api/moot-evaluations/{id}` | DELETE | Judge (draft) | Delete |

---

## Data Integrity Rules

### Versioning (IRAC)
```python
# Each save creates NEW version
new_version = max_version + 1
previous_versions.mark_inactive()
```

### Immutability (Oral Rounds)
```python
if round.is_locked:
    raise HTTPException(400, "Cannot modify locked round")
```

### Finalization (Evaluations)
```python
evaluation.is_draft = False
evaluation.finalized_at = now()
evaluation.is_locked = True  # Forever immutable
```

### Soft Deletes
```python
project.is_active = False
project.deleted_at = now()
# Data preserved, not shown in queries
```

---

## Institution Isolation

**ALL queries are scoped by institution_id:**
```python
query = select(MootProject).where(
    MootProject.institution_id == current_user.institution_id
)
```

**Access Control:**
- Students: Only their own projects
- Judges: Can evaluate, see assigned projects
- Admins: All projects in their institution
- SUPER_ADMIN: All institutions (explicit)

---

## Files Created/Modified

### ORM Models
| File | Description |
|------|-------------|
| `/backend/orm/moot_project.py` | MootProject, MootIssue, IRACBlock |
| `/backend/orm/oral_round.py` | OralRound, OralResponse, BenchQuestion, RoundTranscript |
| `/backend/orm/moot_evaluation.py` | MootEvaluation |

### API Routes
| File | Description |
|------|-------------|
| `/backend/routes/moot_projects.py` | Projects, Issues, IRAC |
| `/backend/routes/oral_rounds.py` | Rounds, Responses, Questions, Transcripts |
| `/backend/routes/moot_evaluations.py` | Evaluations |
| `/backend/main.py` | Route registration |

---

## SUCCESS CRITERIA (Met)

✅ **Refreshing the page loses ZERO data** - All data persisted to database
✅ **Logging out and back in restores state** - User's projects retrieved on login
✅ **Multiple users can work concurrently** - No localStorage conflicts
✅ **All data is institution-isolated** - institution_id filtering on all queries
✅ **Audit history is preserved** - IRAC versions, timestamps on all records
✅ **localStorage is no longer required** - Backend is source of truth

---

## STOP - Phase 5C Complete

**Phase 5C is complete.** This phase successfully:
- Replaced localStorage with database persistence
- Implemented versioning for IRAC content
- Enforced immutability for completed oral rounds
- Created draft/final workflow for evaluations
- Maintained institution isolation throughout
- Preserved audit trails for all data changes

**STOP** - Do not proceed to Phase 5D or beyond.
