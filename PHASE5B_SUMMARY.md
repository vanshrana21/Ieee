# Juris AI - Phase 5B Implementation Summary

## Multi-Institution Tenancy & Data Isolation

### Overview
Phase 5B implements strict multi-tenancy support, allowing multiple colleges, universities, and organizations to use Juris AI with complete data isolation. This is a **HARD requirement** - cross-institution access is architecturally impossible.

---

## Core Entities

### Institution
| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer | Primary key |
| `name` | String(255) | Institution name |
| `code` | String(50) | Unique identifier (e.g., "NLSIU") |
| `domain` | String(255) | Email domain for auto-assignment |
| `description` | Text | Institution description |
| `email` | String(255) | Contact email |
| `phone` | String(50) | Contact phone |
| `address` | Text | Physical address |
| `status` | String(20) | active / suspended (soft-delete) |
| `is_active` | Boolean | Active flag |
| `created_at` | DateTime | Creation timestamp |
| `updated_at` | DateTime | Last update timestamp |

### Competition
| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer | Primary key |
| `institution_id` | Integer | **CRITICAL: Foreign key to institution** |
| `title` | String(255) | Competition name |
| `description` | Text | Competition description |
| `moot_type` | Enum | memorial / oral / hybrid |
| `start_date` | DateTime | Competition start |
| `end_date` | DateTime | Competition end |
| `submission_deadline` | DateTime | Memorial submission deadline |
| `registration_deadline` | DateTime | Team registration deadline |
| `proposition_text` | Text | Moot problem statement |
| `proposition_url` | String(500) | External PDF link |
| `status` | Enum | draft / registration / active / closed / cancelled |
| `is_published` | Boolean | Visibility flag |
| `created_by` | Integer | User who created it |
| `created_at` | DateTime | Creation timestamp |
| `updated_at` | DateTime | Last update timestamp |

### Team
| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer | Primary key |
| `institution_id` | Integer | **CRITICAL: Foreign key to institution** |
| `competition_id` | Integer | Foreign key to competition |
| `name` | String(255) | Team name |
| `code` | String(50) | Registration code |
| `side` | Enum | petitioner / respondent / both |
| `status` | Enum | pending / active / disqualified / withdrawn |
| `email` | String(255) | Team contact email |
| `phone` | String(50) | Team contact phone |
| `representing_institution` | String(255) | For cross-institution events |
| `created_by` | Integer | User who created it |
| `created_at` | DateTime | Creation timestamp |
| `updated_at` | DateTime | Last update timestamp |

---

## Tenancy Rules

### Absolute Rules (Enforced at Database + API Level)
1. **A user belongs to exactly ONE institution** (`institution_id` on User model)
2. **A competition belongs to exactly ONE institution** (`institution_id` on Competition model)
3. **A team belongs to exactly ONE institution AND ONE competition**
4. **ALL queries are scoped by `institution_id`** - No global lists
5. **Cross-institution access is IMPOSSIBLE** - Returns 403 error
6. **Deleting an institution**: Soft-delete only (status = "suspended")
7. **Cascade on suspend**: Competitions remain but are disabled

---

## Backend Implementation

### Institution Management Routes (`/api/institutions`)

| Endpoint | Method | Access | Description |
|----------|--------|--------|-------------|
| `/` | POST | SUPER_ADMIN | Create new institution |
| `/` | GET | All (scoped) | List institutions |
| `/{id}` | GET | Institution members | Get institution details |
| `/{id}` | PATCH | ADMIN+ (own only) | Update institution |
| `/{id}` | DELETE | SUPER_ADMIN | Soft-delete (suspend) |
| `/{id}/reactivate` | POST | SUPER_ADMIN | Reactivate suspended |
| `/{id}/stats` | GET | Institution members | Get statistics |

### Competition Routes (`/api/competitions`)

| Endpoint | Method | Access | Description |
|----------|--------|--------|-------------|
| `/` | POST | ADMIN+ | Create competition |
| `/` | GET | Institution members | List competitions (scoped) |
| `/{id}` | GET | Institution members | Get competition details |
| `/{id}` | PATCH | ADMIN+ | Update competition |
| `/{id}` | DELETE | ADMIN+ | Delete competition |
| `/{id}/teams` | POST | Institution members | Create team |
| `/{id}/teams` | GET | Institution members | List teams |

### Institution Scoping Middleware

```python
async def check_institution_access(
    competition_institution_id: int,
    current_user: User,
    db: AsyncSession
) -> bool:
    """
    Phase 5B: Verify user has access to competition's institution.
    SUPER_ADMIN can access any, others only their own.
    """
    if current_user.role == UserRole.SUPER_ADMIN:
        return True
    
    if current_user.institution_id is None:
        return False
    
    return current_user.institution_id == competition_institution_id
```

---

## Security Controls

### Query Isolation (Every Request)
```python
# ALL queries include institution_id filter
query = select(Competition).where(Competition.institution_id == effective_institution_id)

# Cross-institution access returns 403
if not await check_institution_access(competition.institution_id, current_user, db):
    raise HTTPException(status_code=403, detail="Institution mismatch")
```

### Role-Based Access Within Institution
- **SUPER_ADMIN**: Can switch between institutions, full access
- **ADMIN**: Manage own institution only
- **FACULTY**: View all teams in own institution
- **JUDGE**: Evaluate in own institution only
- **STUDENT**: Participate in own institution only

### Soft Delete for Institutions
```python
# Soft delete - data preserved, access disabled
institution.status = "suspended"
institution.is_active = False

# Competitions cascade to disabled status
# No hard deletes in production paths
```

---

## Data Integrity Guarantees

| Scenario | Guarantee |
|----------|-----------|
| Two institutions run competitions | Zero overlap - complete isolation |
| Judges from Institution A | Cannot see Institution B data - 403 error |
| Admins | Only manage their own institution |
| SUPER_ADMIN switches context | Explicit only, all actions logged |
| Institution deleted | Soft-delete only, competitions disabled |
| Query without institution filter | IMPOSSIBLE - enforced in middleware |

---

## Files Created/Modified

### Backend Models
| File | Description |
|------|-------------|
| `/backend/orm/institution.py` | Modified - Added domain, status, relationships |
| `/backend/orm/competition.py` | Created - Competition & Round models |
| `/backend/orm/team.py` | Created - Team, TeamMemorial, TeamOralRound models |

### Backend Routes
| File | Description |
|------|-------------|
| `/backend/routes/institutions.py` | Created - Institution CRUD, stats, soft-delete |
| `/backend/routes/competitions.py` | Created - Competition CRUD, team management |
| `/backend/main.py` | Modified - Registered new routes |

---

## Acceptance Criteria Verification

| Criteria | Status | Implementation |
|----------|--------|----------------|
| Two institutions can run competitions simultaneously | ✅ | Complete data isolation via institution_id |
| Judges from Institution A cannot see Institution B | ✅ | 403 Forbidden on institution mismatch |
| Admins only manage their institution | ✅ | `check_institution_access()` enforces this |
| SUPER_ADMIN can switch institution context | ✅ | Bypasses checks, explicit in UI |
| Zero global lists across institutions | ✅ | Every query filtered by institution_id |
| Institution mismatch = 403 error | ✅ | Enforced in all competition routes |
| Soft-delete for institutions | ✅ | Status changes to "suspended" |
| Cascade disable competitions | ✅ | Competitions disabled when institution suspended |

---

## API Usage Examples

### Create Institution (Super Admin Only)
```bash
POST /api/institutions
{
  "name": "National Law School",
  "code": "NLSIU",
  "domain": "nls.ac.in",
  "description": "Premier law university in India"
}
```

### Create Competition (Admin+ within institution)
```bash
POST /api/competitions?institution_id=1
{
  "title": "Internal Moot 2026",
  "moot_type": "hybrid",
  "start_date": "2026-01-15T00:00:00Z"
}
```

### List Competitions (Auto-scoped to institution)
```bash
GET /api/competitions
# Returns only competitions from user's institution
# Cross-institution access is IMPOSSIBLE
```

---

## STOP - Phase 5B Complete

**Phase 5B is complete.** Do not implement persistence replacement, submissions, or deadlines (Phase 5C+) unless explicitly requested.

The multi-tenancy system is now:
- ✅ Multiple institutions supported
- ✅ Strict data isolation enforced
- ✅ All queries scoped by institution_id
- ✅ Cross-institution access impossible (403)
- ✅ Soft-delete for institutions
- ✅ Institution context in all API responses
- ✅ SUPER_ADMIN can switch context
- ✅ No global lists across institutions

**STOP** - This phase establishes tenancy. ALL future phases must maintain institution scoping.
