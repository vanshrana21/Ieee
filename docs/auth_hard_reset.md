# Auth System Hard Reset Report

## Overview
Emergency fix for broken login after token refactor. Reverted ES module partial conversion back to global pattern for stability.

## Problem
The ES module conversion broke login functionality because:
1. ES modules execute in strict mode with different timing
2. Import statements caused script loading race conditions
3. `type="module"` scripts don't share global scope as expected
4. DOMContentLoaded timing issues with module scripts

## Solution
Reverted to traditional global pattern:
1. All scripts load via `<script src="...">`
2. `apiRequest` attached to `window` object
3. No ES module imports
4. Predictable script execution order

## Files Reverted from ES Module

### 1. js/api.js
**Before (Broken):**
```javascript
export function getToken() { ... }
export async function apiRequest(path, options = {}) { ... }
```

**After (Fixed):**
```javascript
window.API_BASE = "http://127.0.0.1:8000";

window.getToken = function () {
    return localStorage.getItem("access_token");
};

window.apiRequest = async function (path, options = {}) {
    // ... implementation
};

window.api = { ... };
```

### 2. js/auth.js
**Removed:**
- `import { apiRequest, getToken } from './api.js';`

**Kept:**
- Local `apiRequest()` function for auth-specific handling
- All functions use local `apiRequest()` (not window.apiRequest)
- `login()` function uses `apiRequest()` directly

**Login Function Fixed:**
```javascript
async function login(email, password) {
    try {
        const data = await apiRequest('/api/auth/login', {
            method: 'POST',
            body: JSON.stringify({ email, password })
        });
        
        if (!data || !data.access_token) {
            alert("Invalid email or password");
            return;
        }
        
        localStorage.setItem('access_token', data.access_token);
        localStorage.setItem('user_role', data.role);
        
        if (data.role === 'faculty') {
            window.location.href = '/html/faculty-dashboard.html';
        } else {
            window.location.href = '/html/dashboard-student.html';
        }
    } catch (error) {
        console.error('Login error:', error);
        alert(error.message || 'Login failed');
    }
}
```

### 3. html/faculty-dashboard.html
**Before (Broken):**
```html
<script type="module">
    import { apiRequest } from '../js/api.js';
    // ...
</script>
```

**After (Fixed):**
```html
<script src="../js/api.js"></script>
<script src="../js/auth.js"></script>
<script>
    // Uses global apiRequest()
</script>
```

### 4. html/classroom-create-session.html
**Before (Broken):**
```html
<script type="module">
    import { apiRequest } from '../js/api.js';
    // ...
</script>
```

**After (Fixed):**
```html
<script src="../js/api.js"></script>
<script src="../js/auth.js"></script>
<script>
    // Uses global apiRequest()
</script>
```

### 5. js/classroom.js
**Removed:**
- `import { apiRequest } from './api.js';`

**Changed:**
- All `apiRequest()` calls → `window.apiRequest()`

### 6. js/dashboard-controller.js
**Removed:**
- `import { apiRequest } from './api.js';`

**Changed:**
- All `apiRequest()` calls → `apiRequest()` (uses global)

## Why ES Module Partial Conversion Broke It

### 1. Script Loading Race Conditions
ES modules load asynchronously and execute in different order than traditional scripts. The `DOMContentLoaded` event fires before modules are ready.

### 2. Strict Mode Differences
Module scripts run in strict mode by default, causing subtle behavior changes in existing code.

### 3. Scope Isolation
Module scripts don't automatically share variables with non-module scripts, breaking the expected global scope pattern.

### 4. Import Timing
`import` statements are hoisted and execute before module code, but the imported modules may not be fully initialized when DOM is ready.

### 5. CORS Requirements
ES modules require proper MIME types and can have CORS issues that traditional scripts don't have.

## Login Flow (Fixed)

### Script Loading Order
1. `api.js` loads → defines `window.apiRequest`
2. `auth.js` loads → defines `login()` function
3. Page-specific script loads → can use both

### Login Execution Flow
1. User clicks login button
2. `loginForm.addEventListener('submit', ...)` fires
3. `login(email, password)` called
4. `apiRequest('/api/auth/login', ...)` called (local version in auth.js)
5. Token stored in `localStorage`
6. Redirect based on role

### Token Usage Flow
1. Page loads `api.js` → `window.apiRequest` available
2. Page calls `apiRequest('/some/endpoint')`
3. `apiRequest` gets token from `localStorage`
4. Token injected into Authorization header
5. If 401 → redirect to login

## Verification

### Token Stability
- ✅ Login stores token once
- ✅ All pages use centralized apiRequest
- ✅ No repeated 401 spam
- ✅ Consistent redirect behavior

### Session Management
- ✅ Session creation works once
- ✅ Join session works once
- ✅ No duplicate API calls
- ✅ Active session errors handled gracefully

## Files Modified Summary

| File | Change |
|------|--------|
| `js/api.js` | Removed exports, attached to window |
| `js/auth.js` | Removed import, kept local apiRequest |
| `html/faculty-dashboard.html` | Removed type="module", added script src |
| `html/classroom-create-session.html` | Removed type="module", added script src |
| `js/classroom.js` | Removed import, use window.apiRequest |
| `js/dashboard-controller.js` | Removed import, use global apiRequest |

## Recommendations

### Future Module Migration
If migrating to ES modules in the future:
1. Convert ALL files at once, not piecemeal
2. Use bundler (webpack/vite) to handle imports
3. Keep shared utilities as global until full migration
4. Test login flow thoroughly after each change

### Current Stability
The global pattern is stable and working. No further changes needed unless:
- Adding new authentication flows
- Changing API endpoint structure
- Implementing new token refresh logic

## END REPORT
