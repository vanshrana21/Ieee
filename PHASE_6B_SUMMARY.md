# Phase 6B: Permission-Aware Editing & Lock Enforcement - Implementation Summary

## Overview
Phase 6B enforces role-based editing permissions within moot projects, building on Phase 6A (team structure) and respecting Phase 5D (submission locks). This phase ensures that only authorized team members can perform specific actions based on their team role.

## Permission Matrix (Enforced)

| Team Role   | IRAC Write | Issue CRUD | Oral Responses | Read |
|-------------|------------|------------|----------------|------|
| CAPTAIN     | ✅         | ✅         | ✅             | ✅   |
| SPEAKER     | ✅         | ✅         | ✅             | ✅   |
| RESEARCHER  | ✅         | ❌         | ❌             | ✅   |
| OBSERVER    | ❌         | ❌         | ❌             | ✅   |

**Phase 5D overrides all roles**: If project is locked → NO WRITES FOR ANY ROLE

## Implementation

### 1. Permission Guards Service (`backend/services/permission_guards.py`)

Core helper function `require_team_permission()` checks in strict order:
1. **Phase 5D Lock Check**: Project/competition locks first
2. **Institution Isolation**: User must belong to same institution as project
3. **Super Admin Bypass**: SUPER_ADMIN bypasses remaining checks
4. **Team Membership**: User must be member of project's team
5. **Role Verification**: User's role must be in allowed roles list

#### Convenience Functions:
- `require_irac_write_permission()`: CAPTAIN, SPEAKER, RESEARCHER
- `require_issue_crud_permission()`: CAPTAIN, SPEAKER  
- `require_oral_response_permission()`: CAPTAIN, SPEAKER
- `require_read_permission()`: All roles (no lock check)

### 2. Audit Logging

All permission denials are logged to in-memory store (`PermissionDeniedLog`):
- user_id
- team_id
- project_id
- attempted_action
- role
- reason
- timestamp

Note: For production, this should be persisted to database.

### 3. Routes Updated with Phase 6B Guards

#### `backend/routes/moot_projects.py`:
| Endpoint | Permission Required | Allowed Roles |
|----------|---------------------|---------------|
| `PATCH /{project_id}` | issue_crud | CAPTAIN, SPEAKER |
| `DELETE /{project_id}` | issue_crud | CAPTAIN, SPEAKER |
| `POST /{project_id}/issues` | issue_crud | CAPTAIN, SPEAKER |
| `PATCH /{project_id}/issues/{id}` | issue_crud | CAPTAIN, SPEAKER |
| `DELETE /{project_id}/issues/{id}` | issue_crud | CAPTAIN, SPEAKER |
| `POST /{project_id}/irac` | irac_write | CAPTAIN, SPEAKER, RESEARCHER |

#### `backend/routes/oral_rounds.py`:
| Endpoint | Permission Required | Allowed Roles |
|----------|---------------------|---------------|
| `POST /{round_id}/responses` | oral_response | CAPTAIN, SPEAKER |

### 4. Error Responses

All violations return **HTTP 403 Forbidden** with descriptive messages:
- `"Project is locked: Project has been submitted"`
- `"Cross-institution access denied"`
- `"You are not a member of this project's team"`
- `"Your role (observer) cannot perform this action. Required: captain, speaker"`

## Files Created/Modified

### Created:
- `/backend/services/permission_guards.py` - Core permission enforcement service

### Modified:
- `/backend/routes/moot_projects.py` - Added permission guard imports and checks to write endpoints
- `/backend/routes/oral_rounds.py` - Added permission guard import and check to response submission

## Constraints Respected

✅ **No real-time editing** - Not implemented  
✅ **No comments/chat/feeds** - Not implemented  
✅ **Phase 6A unchanged** - Team membership logic untouched  
✅ **Phase 5D locks enforced** - First check in all permission guards  
✅ **Backend enforcement only** - No frontend trust  
✅ **Institution isolation** - Enforced in all checks  
✅ **RBAC preserved** - Super admin bypass maintained  
✅ **No schema changes** - Used existing tables

## Security Guarantees

1. **Observers cannot write ANYTHING**
2. **Researchers cannot touch issues or oral rounds**
3. **Speakers cannot edit locked submissions**
4. **Captains have full access (until locked)**
5. **Deadline locks override all roles**
6. **All violations return 403 with clear messages**
7. **No cross-institution leakage possible**
8. **All denials logged for audit**

## Testing Checklist

- [ ] OBSERVER role gets 403 on IRAC save
- [ ] RESEARCHER role gets 403 on issue create
- [ ] RESEARCHER role gets 403 on oral response submit
- [ ] SPEAKER can write IRAC, issues, oral responses
- [ ] CAPTAIN can do everything (when not locked)
- [ ] Locked project returns 403 for all write attempts
- [ ] Cross-institution access returns 403
- [ ] Non-team-member returns 403
- [ ] Read endpoints work for all team members
- [ ] Audit logs capture denied actions

## STOP CONDITION

Phase 6B is complete. Do NOT implement:
- Phase 6C (collaboration features)
- Activity feeds
- Notifications
- Real-time features
