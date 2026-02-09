# Juris AI - Phase 5D Implementation Summary

## Evaluation and Scoring System with Conflict Resolution

### Overview
Phase 5D implements comprehensive judge scoring with numeric criteria, per-criterion notes, publish control, and conflict resolution for when judges disagree. Scores are stored per-judge with NO aggregation or ranking computation.

---

## Core Entities

### JudgeScore (Individual Judge Evaluation)
| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer | Primary key |
| `institution_id` | Integer | Institution scoping (Phase 5B) |
| `competition_id` | Integer | Competition scoping |
| `team_id` | Integer | Team being evaluated |
| `submission_id` | Integer | Related submission (optional) |
| `slot_id` | Integer | Related oral round slot (optional) |
| `judge_id` | Integer | Evaluating judge |
| `status` | Enum | draft / submitted / published / disputed / resolved |
| `conflict_status` | Enum | none / pending / resolved / overridden |

### Scoring Criteria (0-10 Scale)
| Criterion | Field | Description |
|-----------|-------|-------------|
| Issue Framing | `issue_framing_score` | Issue identification & framing (0-10) |
| Legal Reasoning | `legal_reasoning_score` | Legal reasoning & application (0-10) |
| Use of Authority | `use_of_authority_score` | Use of authorities & precedents (0-10) |
| Structure & Clarity | `structure_clarity_score` | Structure & clarity of argument (0-10) |
| Oral Advocacy | `oral_advocacy_score` | Oral advocacy skills (0-10, optional) |
| Responsiveness | `responsiveness_score` | Responsiveness to bench (0-10, optional) |

### Computed Fields
| Field | Description |
|-------|-------------|
| `total_score` | Sum of all criteria scores |
| `max_possible` | 60 (6 criteria × 10 points) |
| `percentage` | (total / max) × 100 |

### Per-Criterion Notes (Phase 5D)
| Field | Purpose |
|-------|---------|
| `issue_framing_notes` | Judge notes on issue framing |
| `legal_reasoning_notes` | Judge notes on legal reasoning |
| `use_of_authority_notes` | Judge notes on authority usage |
| `structure_clarity_notes` | Judge notes on structure |
| `oral_advocacy_notes` | Judge notes on oral advocacy |
| `responsiveness_notes` | Judge notes on bench responsiveness |

### Overall Evaluation
| Field | Purpose |
|-------|---------|
| `overall_assessment` | Judge's holistic assessment |
| `strengths` | JSON array of team strengths |
| `improvements` | JSON array of improvement areas |

### Publication Control (Phase 5D)
| Field | Purpose |
|-------|---------|
| `is_published` | Boolean - visible to students? |
| `published_at` | Timestamp of publication |
| `published_by` | Admin who published |
| `is_final` | Judge has finalized (locked for editing) |
| `finalized_at` | Finalization timestamp |

---

## Scoring Workflow

### 1. Create Score (Judge)
```
POST /api/scoring
- Judge enters scores for each criterion (0-10)
- Adds per-criterion notes
- Writes overall assessment
- Status: DRAFT
- Not visible to students
```

### 2. Update Score (While DRAFT)
```
PATCH /api/scoring/{id}
- Judge can edit any fields
- System recalculates total
- Audit log tracks changes
```

### 3. Finalize Score
```
POST /api/scoring/{id}/finalize
- Judge marks evaluation complete
- Status: SUBMITTED
- No further edits (unless admin unlocks)
- System checks for conflicts with other judges
```

### 4. Publish Score (Admin/Faculty)
```
POST /api/scoring/{id}/publish
- Admin/Faculty reviews
- Makes visible to students
- Status: PUBLISHED
- Students can now see their evaluation
```

### 5. Unpublish Score (Admin Only)
```
POST /api/scoring/{id}/unpublish?reason=X
- Admin can hide if error discovered
- Students lose visibility
- Status: SUBMITTED
- Reason logged in audit trail
```

---

## Conflict Detection System (Phase 5D)

### Automatic Conflict Detection
```python
async def detect_score_conflicts(competition_id, team_id, db):
    scores = await get_all_judge_scores(team_id)
    
    # Calculate variance for each criterion
    for criterion in CRITERIA:
        values = [getattr(s, criterion) for s in scores]
        var = variance(values)
        
        # If variance > threshold (e.g., 4.0), flag conflict
        if var >= 4.0:  # ~2 point average difference
            conflict = ScoreConflict(
                criterion_in_conflict=criterion,
                score_variance=var,
                max_difference=max(values) - min(values),
                judge_score_ids=[s.id for s in scores],
                status="pending"
            )
            await save(conflict)
            
            # Mark all involved scores as disputed
            for score in scores:
                score.conflict_status = ScoreConflictStatus.PENDING
```

### Conflict Resolution (Admin)
```
POST /api/scoring/conflicts/{id}/resolve
- Admin reviews conflicting scores
- Can select which judge's score to use (override_score_id)
- Or provide resolution notes for both to remain
- Status: resolved / overridden
- All actions logged
```

---

## Privacy & Access Control (Phase 5D)

### Student View
```python
# Students ONLY see published scores
query = select(JudgeScore).where(
    JudgeScore.is_published == True  # CRITICAL
)
# Unpublished scores return 404 (don't reveal existence)
```

### Judge View
```python
# Judges see:
# - Their own scores (published or not)
# - Published scores from other judges
# - NOT unpublished scores from other judges
query = select(JudgeScore).where(
    or_(
        JudgeScore.judge_id == current_user.id,
        JudgeScore.is_published == True
    )
)
```

### Admin/Faculty View
```python
# Admins see all scores (published or not)
query = select(JudgeScore)
# Can filter by publication status
```

---

## API Endpoints

### Scoring CRUD
| Endpoint | Method | Access | Description |
|----------|--------|--------|-------------|
| `/api/scoring` | POST | Judge+ | Create new evaluation |
| `/api/scoring` | GET | All (scoped) | List scores |
| `/api/scoring/{id}` | GET | All (privacy controlled) | Get specific score |
| `/api/scoring/{id}` | PATCH | Judge (own) or Admin | Update score |
| `/api/scoring/{id}/finalize` | POST | Judge (own) | Finalize evaluation |

### Publication Control
| Endpoint | Method | Access | Description |
|----------|--------|--------|-------------|
| `/api/scoring/{id}/publish` | POST | Faculty/Admin | Make visible to students |
| `/api/scoring/{id}/unpublish` | POST | Admin | Hide from students |

### Conflict Resolution
| Endpoint | Method | Access | Description |
|----------|--------|--------|-------------|
| `/api/scoring/conflicts` | GET | Faculty/Admin | List all conflicts |
| `/api/scoring/conflicts/{id}/resolve` | POST | Admin | Resolve conflict |

---

## NO RANKING / NO AGGREGATION (Phase 5D Requirement)

### What We Store
- ✅ Individual judge scores (per-criterion)
- ✅ Per-judge total and percentage
- ✅ Per-criterion notes
- ✅ Multiple judges per team

### What We DON'T Compute
- ❌ Average across judges
- ❌ Team ranking/leaderboard
- ❌ Competition-wide standings
- ❌ Automated winner selection

```python
# Per-judge calculation ONLY
def calculate_total(self):
    scores = [self.issue_framing_score, self.legal_reasoning_score, ...]
    self.total_score = sum(scores)
    self.percentage = (self.total_score / self.max_possible) * 100

# NO cross-judge aggregation
# NO team rankings
# NO leaderboards
```

---

## Files Created

### Models
| File | Description |
|------|-------------|
| `/backend/orm/scoring.py` | JudgeScore, ScoreConflict, ScoreAuditLog |

### Routes
| File | Description |
|------|-------------|
| `/backend/routes/scoring.py` | CRUD, publish/unpublish, conflict resolution |
| `/backend/main.py` | Registered scoring routes |

---

## STOP - Phase 5D Complete

**Phase 5D is complete.** Do not implement ranking computation, leaderboards, or automated winner selection (Phase 5E+) unless explicitly requested.

The scoring system is now:
- ✅ Numeric scoring (0-10 per criterion)
- ✅ Per-criterion judge notes
- ✅ Overall assessment and feedback
- ✅ Finalization workflow
- ✅ Publish/unpublish control
- ✅ Students only see published scores
- ✅ Conflict detection (variance-based)
- ✅ Conflict resolution (admin override)
- ✅ Complete audit trail
- ✅ NO ranking computation
- ✅ NO cross-judge aggregation

**STOP** - This phase establishes evaluation privacy and conflict resolution. ALL future phases must respect publish control and audit requirements.
