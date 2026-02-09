# Phase 6A: Team Structure & Membership - Implementation Summary

## Overview
Phase 6A introduces foundational team structure and membership management for Juris AI moot court platform. This phase establishes teams as first-class entities that own moot projects, with proper invitation-based membership and captain authority.

## Key Features Implemented

### 1. Team Roles (Separate from Global RBAC)
- **CAPTAIN**: Full control over team (invite/remove members, change roles, transfer captaincy)
- **SPEAKER**: Writes IRAC + oral rounds (Phase 6B)
- **RESEARCHER**: Writes IRAC only (Phase 6B)
- **OBSERVER**: Read-only access

### 2. ORM Models Created/Extended

#### `backend/orm/team.py` Extensions:
- **TeamRole** enum: CAPTAIN, SPEAKER, RESEARCHER, OBSERVER
- **InvitationStatus** enum: PENDING, ACCEPTED, REJECTED, EXPIRED
- **TeamMember**: Proper membership model with role tracking
- **TeamInvitation**: Invitation-based membership workflow
- **TeamAuditLog**: Comprehensive audit logging for all team actions

#### `backend/orm/moot_project.py`:
- Already has `team_id` field linking MootProject to Team (from Phase 5C)

### 3. API Endpoints

#### Team Management (`backend/routes/teams.py`):
| Endpoint | Method | Description | Auth Required |
|----------|--------|-------------|---------------|
| `/teams/{team_id}/invite` | POST | Captain invites user to team | Captain only |
| `/teams/invitations/{id}/accept` | POST | User accepts invitation | Invitee only |
| `/teams/invitations/{id}/reject` | POST | User rejects invitation | Invitee only |
| `/teams/{team_id}/members/{user_id}` | DELETE | Captain removes member | Captain only |
| `/teams/{team_id}/members/{user_id}/role` | PATCH | Captain changes member role | Captain only |
| `/teams/{team_id}/transfer-captain` | POST | Captain transfers authority | Captain only |
| `/teams/{team_id}/members` | GET | List team members | Team members only |
| `/teams/invitations/pending` | GET | List user's pending invitations | Any user |

### 4. Security & Data Integrity

#### Institution Isolation:
- All team models scoped to `institution_id`
- Cross-institution access is blocked (403 Forbidden)
- Users can only join teams within their institution

#### Captain Authority Enforcement:
- Only captains can invite, remove, or change roles
- Cannot remove the last captain
- Cannot demote the last captain
- Captain transfer requires new captain to be existing member

#### Audit Logging:
Every team action is logged with:
- Actor ID and role at time of action
- Target user ID (if applicable)
- Old/new roles (for role changes)
- IP address
- Timestamp
- Reason (if provided)

### 5. Invitation Flow

```
Captain invites user → Invitation PENDING (7-day expiry)
                           ↓
         ┌─────────────┴─────────────┐
         ↓                           ↓
    Invitee ACCEPTS            Invitee REJECTS
         ↓                           ↓
  TeamMember created          Invitation REJECTED
  Invitation ACCEPTED
```

## Files Created/Modified

### Created:
- `/backend/routes/teams.py` - Team management API routes

### Modified:
- `/backend/orm/team.py` - Added TeamRole, InvitationStatus, TeamMember, TeamInvitation, TeamAuditLog models
- `/backend/main.py` - Registered team routes

## Constraints Respected

✅ No real-time collaboration implemented  
✅ No concurrent editing implemented  
✅ IRAC logic unchanged  
✅ Phase 5D submission locking unchanged  
✅ Institution isolation preserved  
✅ RBAC roles unchanged  
✅ Auditability enforced  
✅ No data deleted or reset  

## Success Criteria Met

1. ✅ Teams exist as first-class entities
2. ✅ Members managed via invitation system
3. ✅ Captain authority enforced throughout
4. ✅ Institution isolation preserved
5. ✅ No editing logic changed (Phase 6B responsibility)
6. ✅ Phase 5D deadlines/locks unchanged
7. ✅ No collaboration features added
8. ✅ Comprehensive audit logging implemented

## Next Phase (6B) Responsibilities

- Implement editing permission guards based on team roles
- SPEAKER/RESEARCHER write access enforcement
- OBSERVER read-only enforcement
- Integration with existing Phase 5D lock system

## Notes

- MootProject already linked to Team via `team_id` (from Phase 5C)
- Team creation will be handled when creating a new MootProject (Phase 6B)
- All endpoints return proper HTTP status codes (403 for auth violations, 404 for not found)
- Invitation expiry is 7 days by default
