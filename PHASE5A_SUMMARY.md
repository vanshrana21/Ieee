# Juris AI - Phase 5A Implementation Summary

## Authentication & Role-Based Access Control (RBAC)

### Overview
Phase 5A implements a comprehensive authentication and authorization layer for the Juris AI platform. This is a **mandatory security layer** that ALL subsequent phases must respect. No feature may bypass these controls.

---

## Role System (5 Fixed Roles)

| Role | Level | Description |
|------|-------|-------------|
| `STUDENT` | 1 | Law students participating in moot courts |
| `JUDGE` | 2 | Judges and evaluators for moot court competitions |
| `FACULTY` | 3 | Professors and faculty overseeing student progress |
| `ADMIN` | 4 | Competition administrators managing events |
| `SUPER_ADMIN` | 5 | System administrators with full platform control |

---

## Authentication Features

### JWT-Based Authentication
- **Access Tokens**: 30-minute expiry, include `user_id`, `role`, `institution_id`
- **Refresh Tokens**: 7-day expiry, stored in database for invalidation
- **Token Refresh Flow**: Automatic refresh before expiry
- **Secure Logout**: Invalidates refresh tokens server-side

### API Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/register` | POST | Register with role selection |
| `/api/auth/login` | POST | Login with JSON credentials |
| `/api/auth/login/form` | POST | Login with form data (OAuth2) |
| `/api/auth/refresh` | POST | Refresh access token |
| `/api/auth/logout` | POST | Logout and invalidate tokens |
| `/api/auth/me` | GET | Get current user info |
| `/api/auth/change-password` | POST | Change password with verification |

---

## RBAC Middleware

### Core Functions (`backend/rbac.py`)

#### Authentication Dependencies
- `get_current_user()` - Extract and validate user from JWT
- `get_current_user_optional()` - Optional auth for public endpoints

#### Role Decorators
- `require_role([roles])` - Require specific role(s)
- `require_min_role(role)` - Require minimum hierarchy level
- `require_permission(permission)` - Check moot court permission matrix
- `require_institution_match()` - Enforce institution isolation

### Permission Matrix

| Feature | Student | Judge | Faculty | Admin | Super Admin |
|---------|:-------:|:-----:|:-------:|:-----:|:-----------:|
| Create moot project | ✅ | ❌ | ❌ | ❌ | ❌ |
| Write IRAC | ✅ | ❌ | ❌ | ❌ | ❌ |
| Oral rounds (speaker) | ✅ | ❌ | ❌ | ❌ | ❌ |
| Oral rounds (bench) | ❌ | ✅ | ✅ | ✅ | ✅ |
| Evaluate & score | ❌ | ✅ | ✅ | ✅ | ✅ |
| View all teams | ❌ | ❌ | ✅ | ✅ | ✅ |
| Create competitions | ❌ | ❌ | ❌ | ✅ | ✅ |
| Manage institutions | ❌ | ❌ | ❌ | ❌ | ✅ |
| AI Coach | ✅ | ❌ | ❌ | ❌ | ❌ |
| AI Review | ✅ | ❌ | ❌ | ❌ | ❌ |
| Counter-Argument | ✅ | ❌ | ❌ | ❌ | ❌ |
| Judge Assist | ❌ | ✅ | ✅ | ✅ | ✅ |
| Bench Questions | ❌ | ✅ | ✅ | ✅ | ✅ |
| Feedback Suggest | ❌ | ✅ | ✅ | ✅ | ✅ |

---

## Backend Changes

### Files Created
1. `/backend/rbac.py` - Complete RBAC middleware system
2. `/backend/orm/institution.py` - Institution model for multi-tenancy

### Files Modified
1. `/backend/orm/user.py`
   - Updated `UserRole` enum with 5 roles
   - Added `institution_id` foreign key
   - Added `refresh_token` and `refresh_token_expires` fields

2. `/backend/routes/auth.py`
   - Added refresh token support to login/register
   - Added `/auth/refresh` endpoint
   - Added `/auth/logout` endpoint
   - Added `/auth/change-password` endpoint
   - Token payload includes `user_id`, `role`, `institution_id`

3. `/backend/routes/debate.py`
   - Added RBAC imports
   - Protected all endpoints with role checks:
     - `POST /ai-coach` - STUDENT only
     - `POST /ai-review` - STUDENT only
     - `POST /counter-argument` - STUDENT only
     - `POST /judge-assist` - JUDGE+ only
     - `POST /bench-questions` - JUDGE+ only
     - `POST /feedback-suggest` - JUDGE+ only

---

## Frontend Changes

### Files Modified
1. `/js/auth.js`
   - Added `ROLES` constant with 5 role definitions
   - Added `ROLE_HIERARCHY` for level-based checks
   - Added `MOOT_COURT_PERMISSIONS` matrix
   - Added `hasRole()`, `hasAnyRole()`, `hasMinRole()`, `hasPermission()` functions
   - Added role guards: `guardStudentOnly()`, `guardJudgeAndAbove()`, etc.
   - Added UI helpers: `hideIfNotPermitted()`, `disableIfNotPermitted()`, etc.
   - Added refresh token functions
   - Added `requireRole()` for route protection

2. `/html/signup.html`
   - Updated role dropdown to 5 options:
     - Law Student (Student)
     - Judge / Evaluator
     - Faculty / Professor
     - Competition Admin
     - System Administrator

3. `/html/moot-court.html`
   - Added `auth.js` script
   - Added authentication check on load
   - Added role-based UI controls:
     - Students see: AI Coach, AI Review, Counter-Argument, Create Project
     - Judges see: Judge Assist, Evaluation, Bench Questions
     - Role-specific oral round views

### Files Created
1. `/html/unauthorized.html`
   - Access denied page with role information
   - Links to dashboard and login

---

## Security Features

### Data Isolation
- **Institution Context**: Every user belongs to an institution
- **Cross-Institution Protection**: Users cannot access other institutions' data
- **Super Admin Override**: Can access all institutions for management

### Token Security
- **Access Token**: Short-lived (30 min), includes full user context
- **Refresh Token**: Long-lived (7 days), stored hashed in database
- **Token Invalidation**: Logout clears refresh token, password change invalidates all sessions
- **Auto-Refresh**: Frontend automatically refreshes tokens before expiry

### Error Handling
- **401 Unauthorized**: Invalid or expired token
- **403 Forbidden**: Valid token but insufficient permissions
- **Explicit Errors**: No silent failures; all errors include clear messages

---

## Acceptance Criteria Verification

| Criteria | Status |
|----------|--------|
| Student cannot access judge/admin features via API | ✅ Protected with role checks |
| Judge cannot modify student submissions | ✅ No write permissions on student data |
| Faculty can only view, never edit | ✅ Read-only permissions configured |
| Admins manage structure, never content | ✅ Admin permissions limited to management |
| SUPER_ADMIN never impersonates silently | ✅ All actions logged with real user identity |

---

## Files Added/Modified Summary

### Backend
| File | Lines | Description |
|------|-------|-------------|
| `/backend/rbac.py` | 350+ | RBAC middleware, decorators, utilities |
| `/backend/orm/institution.py` | 60+ | Institution model |
| `/backend/orm/user.py` | Modified | 5 roles, institution_id, refresh tokens |
| `/backend/routes/auth.py` | Modified | Refresh token flow, logout, password change |
| `/backend/routes/debate.py` | Modified | All endpoints protected with RBAC |

### Frontend
| File | Lines | Description |
|------|-------|-------------|
| `/js/auth.js` | Modified | RBAC functions, permission checks, guards |
| `/html/signup.html` | Modified | 5 role options in dropdown |
| `/html/moot-court.html` | Modified | Auth guards, role-based UI |
| `/html/unauthorized.html` | New | Access denied page |

---

## STOP - Phase 5A Complete

**Phase 5A is complete.** Do not implement Phase 5B or beyond unless explicitly requested.

The authentication and RBAC layer is now:
- ✅ JWT-based with access + refresh tokens
- ✅ 5 fixed roles with hierarchy
- ✅ All moot-court endpoints protected
- ✅ Frontend role-aware UI rendering
- ✅ Institution-based data isolation
- ✅ Secure logout and session invalidation
- ✅ Automatic token refresh
- ✅ Explicit 403 errors for unauthorized access

**STOP** - This phase establishes the security foundation. ALL future phases must respect these controls.
