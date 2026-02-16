# Phase: Case Library Upgrade

**Date:** 2026-02-15  
**Status:** ✅ COMPLETE  
**Objective:** Upgrade moot_cases system to support 30 structured High Court cases without breaking classroom session flow.

---

## Executive Summary

Successfully upgraded the Moot Case Library with structured High Court cases including citation, constitutional articles, key issues, and complexity levels. All changes maintain backward compatibility with existing classroom session creation flow.

---

## Schema Changes

### New Columns Added to `moot_cases` Table

| Column | Type | Nullable | Default | Purpose |
|--------|------|----------|---------|---------|
| `citation` | VARCHAR(255) | YES | NULL | Legal citation (e.g., "AIR 2023 SC 1234") |
| `short_proposition` | TEXT | YES | NULL | One-line case summary |
| `constitutional_articles` | JSON | YES | NULL | Array of relevant articles (e.g., ["Article 14", "Article 21"]) |
| `key_issues` | JSON | YES | NULL | Array of legal issues (e.g., ["Right to Privacy"]) |
| `landmark_cases_expected` | JSON | YES | NULL | Array of expected landmark citations |
| `complexity_level` | INTEGER | NO | 3 | 1-5 complexity rating |

### Migration Strategy

```sql
-- SQLite ALTER TABLE statements used:
ALTER TABLE moot_cases ADD COLUMN citation VARCHAR(255);
ALTER TABLE moot_cases ADD COLUMN short_proposition TEXT;
ALTER TABLE moot_cases ADD COLUMN constitutional_articles JSON;
ALTER TABLE moot_cases ADD COLUMN key_issues JSON;
ALTER TABLE moot_cases ADD COLUMN landmark_cases_expected JSON;
ALTER TABLE moot_cases ADD COLUMN complexity_level INTEGER DEFAULT 3;
```

**Safe Migration Applied:**
- No table drops
- No data loss
- Column-by-column addition with logging
- Graceful handling of existing data

---

## Files Modified

### 1. `backend/orm/moot_case.py`
**Changes:**
- Added 6 new columns to `MootCase` model
- Added JSON import from sqlalchemy
- Maintained backward compatibility with existing fields

### 2. `backend/database.py`
**Changes:**
- Added `check_and_migrate_moot_cases_columns()` function
- Integrated migration call in `init_db()` sequence
- Safe ALTER TABLE logic with column existence checks

### 3. `backend/services/case_library_service.py` (NEW)
**Contents:**
- 30 structured High Court cases defined
- `seed_high_court_cases()` async function
- Deterministic uniqueness check (by title)
- Atomic transaction - commit once at end
- Idempotent - skips existing cases

### 4. `backend/main.py`
**Changes:**
- Added import for `seed_high_court_cases`
- Called seeder after database init
- Logs inserted count on startup

### 5. `backend/routes/classroom.py`
**Changes:**
- Updated `GET /api/classroom/moot-cases` endpoint
- Returns structured data with all new fields
- Orders by complexity_level descending

---

## API Changes

### GET `/api/classroom/moot-cases`

**Before:**
```json
[
  {
    "id": 1,
    "title": "...",
    "category": "constitutional",
    "difficulty": "intermediate"
  }
]
```

**After:**
```json
[
  {
    "id": 1,
    "title": "Right to Privacy in Digital Age",
    "citation": "AIR 2023 SC 1234",
    "short_proposition": "Whether right to privacy extends to digital data",
    "topic": "constitutional",
    "difficulty": "advanced",
    "complexity_level": 4,
    "constitutional_articles": ["Article 21", "Article 19(1)(a)"],
    "key_issues": ["Right to Privacy", "Data Protection"],
    "landmark_cases_expected": ["Justice K.S. Puttaswamy", "Navtej Singh Johar"]
  }
]
```

---

## Verification Results

### Schema Migration
```
✓ Database initialized
✓ All new columns present in moot_cases:
  - citation
  - short_proposition  
  - constitutional_articles
  - key_issues
  - landmark_cases_expected
  - complexity_level
```

### Session Creation Flow
- ✅ POST `/api/classroom/sessions` accepts `case_id` (integer)
- ✅ Join code generation still produces `JURIS-XXXXXX`
- ✅ Cryptographically random (secrets.token_urlsafe)
- ✅ No hardcoded values
- ✅ case_id validation intact

### API Endpoints
- ✅ GET `/api/classroom/moot-cases` returns HTTP 200
- ✅ Returns structured data with new fields
- ✅ No 500 errors
- ✅ No OperationalError

---

## Determinism & Integrity

| Requirement | Status | Details |
|-------------|--------|---------|
| No duplicate case_id | ✅ | Checked by title uniqueness |
| Atomic transactions | ✅ | Single commit for all 30 inserts |
| Idempotent seeding | ✅ | Skips existing cases |
| Join code generation | ✅ | Server-side only, secrets module |
| Session creation | ✅ | case_id maps to MootCase.id (integer) |
| Backward compatible | ✅ | Old fields still present and populated |

---

## Case Library Contents

30 High Court structured cases covering:

1. **Constitutional Law** (12 cases)
   - Right to Privacy, Free Speech, Gender Justice
   - Reservation, UCC, Climate Change

2. **Corporate/Commercial** (6 cases)
   - Insolvency, Antitrust, CSR, E-commerce

3. **Cyber/Tech** (6 cases)
   - AI Liability, Data Protection, Cryptocurrency

4. **Criminal** (3 cases)
   - Mental health defenses, Death penalty

5. **Environmental** (2 cases)
   - Climate litigation, Clearance violations

6. **Civil/Family** (1 case)
   - Live-in relationships, Property rights

---

## Commands for Verification

```bash
# Check schema
sqlite3 legalai.db "PRAGMA table_info(moot_cases);"

# Count cases
curl -s http://localhost:8000/api/classroom/moot-cases | jq '. | length'

# Test session creation
curl -X POST http://localhost:8000/api/classroom/sessions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"case_id":1,"topic":"Test","category":"civil","prep_time_minutes":10,"oral_time_minutes":5}'
```

---

## Compliance Checklist

- ✅ No existing business logic removed
- ✅ No hardcoded frontend arrays
- ✅ No database validation bypassed
- ✅ Deterministic integrity maintained
- ✅ Join code generation preserved
- ✅ Session creation flow intact
- ✅ All 30 cases seeded deterministically
- ✅ No feature removals

---

## Post-Upgrade State

| Component | Before | After |
|-----------|--------|-------|
| moot_cases columns | 6 | 12 |
| Total cases | 1 | 31 (1 default + 30 High Court) |
| API response | Basic | Structured |
| Citation support | No | Yes |
| Complexity tracking | No | Yes (1-5) |
| JSON fields | 0 | 3 |

---

## Timestamp
**Completed:** 2026-02-15 20:45 IST  
**Status:** Production-ready ✅
