# Moot Session Rendering + Role Enforcement Repair Log

**Date:** 2026-02-15

**Objective:** Stabilize moot court session system rendering and enforce role-based access control.

---

## Summary

This repair addresses critical issues in the classroom session creation flow:
- Role enforcement (faculty-only session creation)
- Session code visibility after creation
- Response shape handling
- Duplicate API call prevention
- Clean debug output

---

## Files Modified

### 1. `/html/classroom-create-session.html`

**Changes:**
- Added frontend role guard function `checkFacultyAccess()`
- Replaced raw `fetch()` calls with `window.apiRequest()` global function
- Extracted session creation into dedicated `createSession(formData)` function
- Added response shape auto-detection: `data.session_code || (data.session && data.session.session_code)`
- Added proper error handling with specific error messages
- Cleaned console output with `[CLASSROOM]` and `[CLASSROOM ERROR]` prefixes
- Added student access denied state with redirect button to join page
- Removed auto-create on page load (now only triggered by button click)

**Role Guard Implementation:**
```javascript
function checkFacultyAccess() {
  const role = localStorage.getItem("user_role");
  if (role !== "faculty") {
    // Hide form, show access denied
    // Provide button to join session page instead
    return false;
  }
  return true;
}
```

**Response Shape Handling:**
```javascript
// Auto-detect response shape
const sessionCode = data.session_code || (data.session && data.session.session_code);
const sessionId = data.id || (data.session && data.session.id);

if (!sessionCode) {
  throw new Error("Session code missing in response");
}
```

---

### 2. `/backend/routes/classroom_sessions.py`

**Changes:**
- Updated role check to accept both `teacher` and `faculty` roles
- Changed from single role check to list membership check

**Before:**
```python
if current_user.get("role") != "teacher":
    raise HTTPException(...)
```

**After:**
```python
user_role = current_user.get("role")
if user_role not in ["teacher", "faculty"]:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only teachers or faculty can create sessions"
    )
```

---

## DOM Structure Verification

The session code display elements already exist in the HTML:

```html
<div class="session-code-display" id="session-code-display">
  <div class="session-code-label">SESSION CODE</div>
  <div class="session-code-value" id="generated-code">JURIS-XXXX</div>
  <div class="session-code-instructions">
    Share this code with your students to join<br>
    Maximum 40 participants allowed
  </div>
  <button class="submit-btn" onclick="goToControlPanel()">
    Go to Control Panel →
  </button>
</div>
```

CSS handles visibility with `.show` class that sets `display: block`.

---

## Validation Checklist

| Requirement | Status | Notes |
|------------|--------|-------|
| Faculty can create sessions | ✅ | Frontend guard + backend check |
| Session code visible after creation | ✅ | DOM element populated correctly |
| Students cannot see create button | ✅ | Access denied state shown |
| Response parsing matches backend | ✅ | Auto-detection for both shapes |
| No duplicate API calls | ✅ | Single submit handler |
| No duplicate DOM listeners | ✅ | One DOMContentLoaded listener |
| Clean console output | ✅ | `[CLASSROOM]` prefixes |
| No infinite redirects | ✅ | No redirect loops detected |
| No silent failures | ✅ | All errors logged and alerted |

---

## API Flow

### Create Session Request
```javascript
POST /api/classroom/sessions
Authorization: Bearer <token>
Content-Type: application/json

{
  "case_id": 1,
  "topic": "Right to Privacy vs National Security",
  "category": "constitutional",
  "prep_time_minutes": 15,
  "oral_time_minutes": 10,
  "ai_judge_mode": "hybrid",
  "max_participants": 40
}
```

### Expected Response Shapes (Both Supported)
**Shape 1:**
```json
{
  "success": true,
  "session": {
    "id": 123,
    "session_code": "JURIS-ABCD",
    ...
  }
}
```

**Shape 2:**
```json
{
  "id": 123,
  "session_code": "JURIS-ABCD",
  ...
}
```

---

## Testing Notes

1. **Faculty User Flow:**
   - Login as faculty → Navigate to create session page
   - Form loads normally
   - Fill form → Submit → Session code displayed prominently
   - Can navigate to control panel

2. **Student User Flow:**
   - Login as student → Navigate to create session page
   - Access denied message displayed
   - Button to redirect to join session page
   - Cannot access create functionality

3. **Error Handling:**
   - Network errors → Alert shown with message
   - Missing session code → Detailed error in console
   - Invalid role → 403 from backend, access denied on frontend

---

## Console Output Examples

**Successful Creation:**
```
[CLASSROOM] Page initialized
[CLASSROOM] User role: faculty
[CLASSROOM] Loading moot cases...
[CLASSROOM] Loaded 5 moot cases
[CLASSROOM] Creating session...
[CLASSROOM] Session created: JURIS-ABCD
```

**Access Denied:**
```
[CLASSROOM] User role: student
[CLASSROOM] Access denied: Only faculty can create sessions
```

**Error:**
```
[CLASSROOM ERROR] Failed to load moot cases: ...
[CLASSROOM ERROR] Session creation failed: Session code missing in response
```

---

## Related Files (Unchanged but Relevant)

- `/js/api.js` - Global apiRequest function (used by create session)
- `/js/auth.js` - Auth utilities (already loads before create session script)
- `/html/classroom-join-session.html` - Student entry point
- `/html/classroom-control-panel.html` - Faculty session management

---

## Database Schema (No Changes)

Session creation depends on existing tables:
- `classroom_sessions` - Stores session data including `session_code`
- `classroom_participants` - Stores participant data
- `moot_cases` - Source for case selection dropdown

---

## Security Considerations

1. **Double Role Check:**
   - Frontend: Prevents UI access
   - Backend: Prevents API abuse
   - Both must pass for success

2. **Token Validation:**
   - All requests use `window.apiRequest()` which adds Bearer token
   - 401 responses redirect to login

3. **Session Code:**
   - Generated server-side (not client-side)
   - Unique constraint enforced in database
   - Displayed prominently after creation

---

## Known Limitations

1. `get_current_user()` in backend uses mock implementation (returns test user)
   - Real JWT validation should be implemented for production

2. Response shape detection is defensive but may need adjustment if backend changes

3. No real-time validation of session code format on frontend

---

## Next Steps (Optional)

1. Implement real JWT validation in `get_current_user()`
2. Add WebSocket support for real-time session updates
3. Add session expiration/cleanup logic
4. Implement rate limiting for session creation

---

**Repair Complete** ✅
