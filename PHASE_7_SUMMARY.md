# Phase 7: Faculty Oversight & Academic Monitoring - Implementation Summary

## Overview
Phase 7 introduces a comprehensive, read-only faculty oversight layer that enables academic monitoring and mentoring without compromising student autonomy. Faculty can view all student progress, provide advisory notes, and track engagement—while being explicitly prevented from editing work, influencing submissions, or affecting outcomes.

## Core Philosophy
**Mentoring, Not Control**
- Faculty observe and guide
- Students retain full authorship
- No evaluative power in faculty hands
- Transparent audit trail for all faculty actions

## Components Implemented

### 1. FacultyNote ORM Model (`backend/orm/faculty_note.py`)

**Schema:**
- `id` - Primary key
- `institution_id` - Institution scoping (mandatory)
- `faculty_id` - Note author (User FK)
- `project_id` - Project context (MootProject FK)
- `note_text` - Advisory content
- `created_at`, `updated_at` - Timestamps
- `is_private` - Visibility control (currently always private to faculty)

**Purpose:**
- Private mentoring notes
- Non-evaluative guidance
- Does not affect student work in any way
- Clearly labeled as "Faculty Guidance (Non-Evaluative)"

### 2. Progress Calculator Service (`backend/services/progress_calculator.py`)

**Computed Metrics (Objective Only):**
- **IRAC Completeness**: % of required blocks filled (Issue/Rule/Application/Conclusion)
- **Issues Count**: Number of issues defined
- **Issues Completed**: Issues marked as completed
- **Oral Rounds**: Count of practice rounds
- **Oral Responses**: Count of recorded responses
- **Transcript Status**: Whether transcript exists
- **Last Activity**: Timestamp of most recent team action
- **Faculty Notes Count**: Number of notes by viewing faculty

**No Subjective Scoring:**
- No AI evaluation
- No grades or scores
- No quality assessment
- Purely quantitative metrics

### 3. Faculty Routes (`backend/routes/faculty.py`)

**Permission Model:**
| Action | Faculty | Admin | Super Admin |
|--------|---------|-------|-------------|
| View Dashboard | ✅ | ✅ | ✅ |
| View All Projects | ✅ | ✅ | ✅ |
| View IRAC Content | ✅ | ✅ | ✅ |
| View Oral Transcripts | ✅ | ✅ | ✅ |
| View Activity Logs | ✅ | ✅ | ✅ |
| Add Advisory Notes | ✅ | ✅ | ✅ |
| Edit Student Work | ❌ | ❌ | ❌ |
| Submit/Lock/Unlock | ❌ | ❌ | ❌ |
| Extend Deadlines | ❌ | ❌ | ❌ |
| Score/Evaluate | ❌ | ❌ | ❌ |

**Institution Isolation:**
- Faculty can only view projects within their own institution
- Cross-institution access returns 403 Forbidden
- Strict enforcement at every endpoint

**Endpoints:**
- `GET /api/faculty/dashboard` - Institution overview with metrics and team list
- `GET /api/faculty/projects` - List all projects with progress metrics
- `GET /api/faculty/projects/{id}` - Full project view (read-only)
- `GET /api/faculty/projects/{id}/irac` - IRAC content viewing
- `GET /api/faculty/projects/{id}/oral-rounds/{id}/transcript` - Transcript viewing
- `GET /api/faculty/projects/{id}/activity` - Activity log viewing
- `POST /api/faculty/projects/{id}/notes` - Add advisory note
- `GET /api/faculty/projects/{id}/notes` - List own notes
- `PATCH /api/faculty/notes/{id}` - Edit own note
- `DELETE /api/faculty/notes/{id}` - Delete own note

### 4. Activity Logger Updates (`backend/services/activity_logger.py`)

**New Action Types:**
- `FACULTY_VIEW` - Logged when faculty views project/irac/transcript
- `FACULTY_NOTE_ADDED` - Logged when faculty adds advisory note

**Convenience Functions:**
- `log_faculty_view(db, project, actor, ip_address)`
- `log_faculty_note_added(db, project, actor, note_id, ip_address)`

All faculty actions are auditable and appear in team activity logs.

### 5. Frontend Pages

**Faculty Dashboard (`html/faculty-dashboard.html`):**
- Institution-wide metrics cards
- Teams list with member/project counts
- Projects grid with progress indicators
- Recent faculty activity
- Guidelines modal explaining faculty permissions
- Warning banner: READ-ONLY MODE

**Faculty Project View (`html/faculty-project.html`):**
- Progress overview section
- IRAC content viewer (read-only text areas)
- Issues list with status
- Oral rounds with transcript links
- Complete activity log
- Faculty notes panel (add/edit/delete)
- Persistent red warning banner

## Security Guarantees

✅ **Read-Only Enforcement**
- All faculty views use GET requests only
- No edit endpoints for faculty
- Explicit rejection of write attempts

✅ **Institution Isolation**
- Strict `institution_id` checking on every request
- Faculty cannot escape their institution scope
- 403 Forbidden for cross-institution attempts

✅ **Audit Trail**
- Every faculty view is logged
- Every note is logged
- IP addresses captured for accountability

✅ **No Impersonation**
- Faculty actions clearly tagged in logs
- Cannot masquerade as students
- Cannot submit on behalf of students

## What Faculty CANNOT Do (Hard Blocks)

❌ Edit IRAC content
❌ Create/modify/delete issues
❌ Submit projects
❌ Lock/unlock projects
❌ Extend deadlines
❌ Override competition settings
❌ Score or evaluate
❌ Use AI on behalf of students
❌ View other faculty's private notes
❌ Access other institutions

## Files Created/Modified

### Created:
- `/backend/orm/faculty_note.py` - FacultyNote ORM model
- `/backend/services/progress_calculator.py` - Objective progress metrics
- `/backend/routes/faculty.py` - Faculty API routes
- `/html/faculty-dashboard.html` - Faculty dashboard frontend
- `/html/faculty-project.html` - Faculty project view frontend

### Modified:
- `/backend/orm/team_activity.py` - Added FACULTY_VIEW and FACULTY_NOTE_ADDED action types
- `/backend/services/activity_logger.py` - Added faculty logging convenience functions
- `/backend/main.py` - Registered faculty routes

## Success Criteria Achieved

✅ Faculty can monitor all student progress within institution
✅ Faculty can view IRAC, issues, oral transcripts (read-only)
✅ Faculty can add advisory, non-evaluative notes
✅ Students retain full authorship and control
✅ No deadline or submission control leakage to faculty
✅ Institution isolation preserved
✅ All faculty actions auditable
✅ Progress metrics are computed, not subjective
✅ Clear UI warnings about read-only nature
✅ No AI evaluation or scoring by faculty

## STOP CONDITION

Phase 7 is complete. Do NOT implement:
- Phase 8 or beyond
- AI-powered faculty recommendations
- Faculty-to-student messaging
- Real-time notifications
- Analytics dashboards
- Export/reporting features

## Compliance with Hard Constraints

| Constraint | Status |
|------------|--------|
| Faculty NEVER edits IRAC | ✅ Enforced - read-only views only |
| Faculty NEVER unlocks submissions | ✅ Enforced - no lock/unlock endpoints |
| Faculty NEVER scores/evaluates | ✅ Enforced - no scoring endpoints |
| Faculty NEVER uses AI on behalf of students | ✅ Enforced - no AI features in faculty routes |
| Faculty NEVER impersonates students | ✅ Enforced - distinct role and logging |
| No reuse of admin permissions | ✅ Enforced - explicit FACULTY role checks |

This phase enables academic trust through transparency while preserving student autonomy and preventing any possibility of faculty interference in outcomes.
