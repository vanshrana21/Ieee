/**
 * auth.js
 * Complete authentication module for LegalAI Research - Phase 5A RBAC
 * Handles login, signup, logout, token management, and role-based access control
 * 
 * Phase 5A Updates:
 * - 5 roles: STUDENT, JUDGE, FACULTY, ADMIN, SUPER_ADMIN
 * - Permission matrix for moot court
 * - Refresh token support
 * - Role guards
 */

if (!window.API_BASE_URL) {
    window.API_BASE_URL = 'http://127.0.0.1:8000';
}

const TOKEN_KEY = 'access_token';
const REFRESH_TOKEN_KEY = 'refresh_token';
const ROLE_KEY = 'user_role';
const USER_KEY = 'user_info';
const USER_NAME_KEY = 'legalai_user_name';

// Phase 5A: Role definitions
const ROLES = {
    STUDENT: 'student',
    JUDGE: 'judge',
    FACULTY: 'faculty',
    ADMIN: 'admin',
    SUPER_ADMIN: 'super_admin'
};

// Phase 5A: Role hierarchy for permission checks
const ROLE_HIERARCHY = {
    [ROLES.SUPER_ADMIN]: 5,
    [ROLES.ADMIN]: 4,
    [ROLES.FACULTY]: 3,
    [ROLES.JUDGE]: 2,
    [ROLES.STUDENT]: 1
};

// Phase 5A: Moot Court Permission Matrix
const MOOT_COURT_PERMISSIONS = {
    CREATE_PROJECT: [ROLES.STUDENT],
    WRITE_IRAC: [ROLES.STUDENT],
    ORAL_ROUND_SPEAKER: [ROLES.STUDENT],
    ORAL_ROUND_BENCH: [ROLES.JUDGE, ROLES.FACULTY, ROLES.ADMIN, ROLES.SUPER_ADMIN],
    EVALUATE_AND_SCORE: [ROLES.JUDGE, ROLES.FACULTY, ROLES.ADMIN, ROLES.SUPER_ADMIN],
    VIEW_ALL_TEAMS: [ROLES.FACULTY, ROLES.ADMIN, ROLES.SUPER_ADMIN],
    CREATE_COMPETITIONS: [ROLES.ADMIN, ROLES.SUPER_ADMIN],
    MANAGE_INSTITUTIONS: [ROLES.SUPER_ADMIN],
    AI_COACH: [ROLES.STUDENT],
    AI_REVIEW: [ROLES.STUDENT],
    COUNTER_ARGUMENT: [ROLES.STUDENT],
    JUDGE_ASSIST: [ROLES.JUDGE, ROLES.FACULTY, ROLES.ADMIN, ROLES.SUPER_ADMIN],
    BENCH_QUESTIONS: [ROLES.JUDGE, ROLES.FACULTY, ROLES.ADMIN, ROLES.SUPER_ADMIN],
    FEEDBACK_SUGGEST: [ROLES.JUDGE, ROLES.FACULTY, ROLES.ADMIN, ROLES.SUPER_ADMIN]
};

// ============================================================================
// TOKEN MANAGEMENT
// ============================================================================

function setToken(token) {
    try {
        localStorage.setItem(TOKEN_KEY, token);
        return true;
    } catch (error) {
        console.error('Failed to store token:', error);
        return false;
    }
}

function getToken() {
    try {
        return localStorage.getItem(TOKEN_KEY);
    } catch (error) {
        console.error('Failed to retrieve token:', error);
        return null;
    }
}

function getAccessToken() {
    return getToken();
}

function removeToken() {
    try {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(REFRESH_TOKEN_KEY);
        localStorage.removeItem('user_info');
        localStorage.removeItem(ROLE_KEY);
        localStorage.removeItem(USER_NAME_KEY);
        localStorage.removeItem('is_enrolled');
        return true;
    } catch (error) {
        console.error('Failed to remove token:', error);
        return false;
    }
}

function setRefreshToken(token) {
    try {
        localStorage.setItem(REFRESH_TOKEN_KEY, token);
        return true;
    } catch (error) {
        console.error('Failed to store refresh token:', error);
        return false;
    }
}

function getRefreshToken() {
    try {
        return localStorage.getItem(REFRESH_TOKEN_KEY);
    } catch (error) {
        console.error('Failed to retrieve refresh token:', error);
        return null;
    }
}

function clearAccessToken() {
    return removeToken();
}

function saveAccessToken(token) {
    return setToken(token);
}

function isAuthenticated() {
    return !!getToken();
}

// ============================================================================
// USER NAME MANAGEMENT
// ============================================================================

/**
 * Store user's full name in localStorage
 * @param {string} name - User's full name
 */
function saveUserName(name) {
    if (!name || typeof name !== 'string') {
        console.warn('Invalid name provided to saveUserName');
        return false;
    }
    
    const trimmedName = name.trim();
    if (trimmedName.length === 0) {
        console.warn('Empty name provided to saveUserName');
        return false;
    }
    
    try {
        localStorage.setItem(USER_NAME_KEY, trimmedName);
        return true;
    } catch (error) {
        console.error('Failed to store user name:', error);
        return false;
    }
}

/**
 * Get stored user name
 * @returns {string|null} - User's name or null
 */
function getUserName() {
    try {
        return localStorage.getItem(USER_NAME_KEY);
    } catch (error) {
        console.error('Failed to retrieve user name:', error);
        return null;
    }
}

/**
 * Get user's first name for greeting
 * @returns {string|null} - User's first name or null
 */
function getUserFirstName() {
    const fullName = getUserName();
    if (!fullName) return null;
    
    const firstName = fullName.trim().split(' ')[0];
    return firstName || null;
}

// ============================================================================
// ROLE MANAGEMENT
// ============================================================================

/**
 * Store user role in localStorage
 * @param {string} role - 'lawyer' or 'student'
 */
function setUserRole(role) {
    try {
        localStorage.setItem(ROLE_KEY, role);
        return true;
    } catch (error) {
        console.error('Failed to store role:', error);
        return false;
    }
}

/**
 * Get stored user role
 * @returns {string|null} - 'lawyer', 'student', or null
 */
function getUserRole() {
    try {
        return localStorage.getItem(ROLE_KEY);
    } catch (error) {
        console.error('Failed to retrieve role:', error);
        return null;
    }
}

/**
 * Get dashboard URL based on user role
 * @param {string} role - User role
 * @returns {string} - Dashboard URL
 */
function getDashboardUrl(role) {
    // Map roles to their respective dashboards - only teacher and student
    const dashboardMap = {
        'teacher': '/html/faculty-dashboard.html',
        'student': '/html/dashboard-student.html'
    };
    
    return dashboardMap[role] || '/html/dashboard-student.html';
}

// ============================================================================
// AUTHENTICATED FETCH (Legacy - uses global window.apiRequest)
// ============================================================================

async function authenticatedFetch(url, options = {}) {
    const token = getToken();
    
    if (!token) {
        throw new Error('No authentication token available');
    }
    
    const headers = {
        ...options.headers,
        'Authorization': `Bearer ${token}`
    };
    
    return window.apiRequest(url, { ...options, headers });
}

// ============================================================================
// REGISTER
// ============================================================================

async function register(fullName, email, password, role) {
    try {
        const data = await window.apiRequest("/api/auth/register", {
            method: "POST",
            body: JSON.stringify({
                name: fullName,
                email: email,
                password: password,
                role: role
            })
        });

        if (!data || !data.access_token) {
            alert("Registration failed");
            return;
        }

        localStorage.setItem("access_token", data.access_token);
        localStorage.setItem("user_role", data.role);

        window.location.href = "/html/onboarding.html";

    } catch (err) {
        console.error("Registration error:", err);
        alert(err.message);
    }
}

// ============================================================================
// LOGIN
// ============================================================================

async function login(email, password) {
    try {
        const data = await window.apiRequest("/api/auth/login", {
            method: "POST",
            body: JSON.stringify({ email, password })
        });

        if (!data || !data.access_token) {
            alert("Invalid email or password");
            return;
        }

        localStorage.setItem("access_token", data.access_token);
        localStorage.setItem("user_role", data.role);

        if (data.role === "teacher") {
            window.location.href = "/html/faculty-dashboard.html";
        } else {
            window.location.href = "/html/dashboard-student.html";
        }

    } catch (err) {
        console.error("Login error:", err);
        alert(err.message);
    }
}

// ============================================================================
// LOGIN HANDLER
// ============================================================================

async function handleLogin(event) {
    if (event) {
        event.preventDefault();
    }
    
    const emailInput = document.getElementById('email');
    const passwordInput = document.getElementById('password');
    const errorMessage = document.getElementById('errorMessage');
    const loginButton = document.querySelector('.btn-primary[type="submit"], .auth-submit');
    
    if (errorMessage) {
        errorMessage.textContent = '';
        errorMessage.style.display = 'none';
    }
    
    const email = emailInput ? emailInput.value.trim() : '';
    const password = passwordInput ? passwordInput.value : '';
    
    if (!email || !password) {
        if (errorMessage) {
            errorMessage.textContent = 'Please enter both email and password';
            errorMessage.style.display = 'block';
        } else {
            alert('Please enter both email and password');
        }
        return;
    }
    
    if (loginButton) {
        loginButton.disabled = true;
        loginButton.textContent = 'Logging in...';
    }
    
    try {
        const result = await login(email, password);
        
        if (result.success) {
            const isEnrolled = localStorage.getItem('is_enrolled') === 'true';
            
            if (!isEnrolled) {
                window.location.href = '/html/onboarding.html';
            } else {
                if (window.JurisSessionManager) {
                    window.JurisSessionManager.handleLoginSuccess();
                } else {
                    const role = getUserRole();
                    const dashboardUrl = getDashboardUrl(role);
                    window.location.href = dashboardUrl;
                }
            }
        } else {
            throw new Error(result.error || 'Login failed');
        }
        
    } catch (error) {
        console.error('Login error:', error);
        
        if (errorMessage) {
            errorMessage.textContent = error.message || 'Login failed. Please try again.';
            errorMessage.style.display = 'block';
        } else {
            alert(error.message || 'Login failed. Please try again.');
        }
        
        if (loginButton) {
            loginButton.disabled = false;
            loginButton.textContent = 'Login';
        }
    }
}

// ============================================================================
// ENROLLMENT (PHASE 2)
// ============================================================================

/**
 * Enroll user with course and semester
 * @param {number} courseId - Course ID (1: BA LLB, 2: BBA LLB, 3: LLB)
 * @param {number} semester - Semester number (1-10)
 * @returns {Promise<Object>} - Success/error result
 */
async function enrollUser(courseId, semester) {
    const result = await window.apiRequest('/api/users/enroll', {
        method: 'POST',
        body: JSON.stringify({
            course_id: courseId,
            current_semester: semester  // ✅ Correct key
        })
    });
    
    if (result.success) {
        localStorage.setItem('is_enrolled', 'true');
        
        return {
            success: true,
            data: result.data
        };
    }
    
    return result;
}

// ============================================================================
// LOGOUT
// ============================================================================

function logout() {
    removeToken();
    window.location.href = '/html/login.html';
}

// ============================================================================
// USER INFO
// ============================================================================

async function getCurrentUser() {
    const result = await window.apiRequest('/api/users/me', {
        method: 'GET'
    });
    
    if (result.success) {
        return {
            success: true,
            data: result.data
        };
    } else {
        return {
            success: false,
            error: result.error
        };
    }
}

async function getUserCredits() {
    const result = await window.apiRequest('/api/users/credits', {
        method: 'GET'
    });
    
    if (result.success) {
        return {
            success: true,
            data: result.data
        };
    } else {
        return {
            success: false,
            error: result.error
        };
    }
}

// ============================================================================
// CURRICULUM (PHASE 3)
// ============================================================================

/**
 * Get user's curriculum dashboard data
 * Returns active subjects, archive subjects, course info, and current semester
 * @returns {Promise<Object>} - Dashboard data with subjects and progress
 */
async function getUserCurriculum() {
    const result = await window.apiRequest('/api/curriculum/dashboard', {
        method: 'GET'
    });
    
    if (result.success) {
        // Transform backend response to match frontend expectations
        const backendData = result.data;
        
        // Combine active and archive subjects into single array with status
        const allSubjects = [];
        
        // Add active subjects (current semester)
        if (backendData.active_subjects && Array.isArray(backendData.active_subjects)) {
            backendData.active_subjects.forEach(subject => {
                allSubjects.push({
                    id: subject.id,
                    name: subject.title,
                    code: subject.code,
                    semester: subject.semester,
                    category: subject.category,
                    is_elective: subject.is_elective,
                    description: subject.description,
                    status: 'active',
                    is_locked: false,
                    completion_percentage: 0 // Will be populated from progress tracking in Phase 8
                });
            });
        }
        
        // Add archive subjects (past semesters)
        if (backendData.archive_subjects && Array.isArray(backendData.archive_subjects)) {
            backendData.archive_subjects.forEach(subject => {
                allSubjects.push({
                    id: subject.id,
                    name: subject.title,
                    code: subject.code,
                    semester: subject.semester,
                    category: subject.category,
                    is_elective: subject.is_elective,
                    description: subject.description,
                    status: 'archived',
                    is_locked: false,
                    completion_percentage: 0 // Will be populated from progress tracking in Phase 8
                });
            });
        }
        
        return {
            success: true,
            data: {
                course: backendData.course?.name || 'Unknown Course',
                courseCode: backendData.course?.code,
                semester: backendData.current_semester,
                totalSemesters: backendData.course?.total_semesters,
                subjects: allSubjects,
                activeSubjects: backendData.active_subjects || [],
                archiveSubjects: backendData.archive_subjects || []
            }
        };
    } else {
        return {
            success: false,
            error: result.error || 'Failed to load curriculum data'
        };
    }
}

// ============================================================================
// PHASE 5A: RBAC - PERMISSION CHECKS
// ============================================================================

/**
 * Check if current user has specific role
 * @param {string} role - Role to check
 * @returns {boolean}
 */
function hasRole(role) {
    return getUserRole() === role;
}

/**
 * Check if current user has any of the specified roles
 * @param {string[]} roles - Array of roles
 * @returns {boolean}
 */
function hasAnyRole(roles) {
    const userRole = getUserRole();
    return roles.includes(userRole);
}

/**
 * Check if current user has minimum role level (hierarchy-based)
 * @param {string} minRole - Minimum required role
 * @returns {boolean}
 */
function hasMinRole(minRole) {
    const userRole = getUserRole();
    const userLevel = ROLE_HIERARCHY[userRole] || 0;
    const minLevel = ROLE_HIERARCHY[minRole] || 0;
    return userLevel >= minLevel;
}

/**
 * Check if user has specific moot court permission
 * @param {string} permission - Permission key from MOOT_COURT_PERMISSIONS
 * @returns {boolean}
 */
function hasPermission(permission) {
    const userRole = getUserRole();
    const allowedRoles = MOOT_COURT_PERMISSIONS[permission] || [];
    return allowedRoles.includes(userRole);
}

// ============================================================================
// PHASE 5A: RBAC - ROLE GUARDS
// ============================================================================

/**
 * Require specific role(s), redirect if not authorized
 * @param {string[]} roles - Allowed roles
 * @returns {boolean}
 */
function requireRole(roles) {
    if (!isAuthenticated()) {
        window.location.href = '/html/login.html?redirect=' + encodeURIComponent(window.location.pathname);
        return false;
    }
    
    if (!hasAnyRole(roles)) {
        window.location.href = '/html/unauthorized.html';
        return false;
    }
    return true;
}

/**
 * Guard: Students only
 * @returns {boolean}
 */
function guardStudentOnly() {
    return requireRole([ROLES.STUDENT]);
}

/**
 * Guard: Judges and above (faculty, admin, super_admin)
 * @returns {boolean}
 */
function guardJudgeAndAbove() {
    return requireRole([ROLES.JUDGE, ROLES.FACULTY, ROLES.ADMIN, ROLES.SUPER_ADMIN]);
}

/**
 * Guard: Faculty and above
 * @returns {boolean}
 */
function guardFacultyAndAbove() {
    return requireRole([ROLES.FACULTY, ROLES.ADMIN, ROLES.SUPER_ADMIN]);
}

/**
 * Guard: Admin and above
 * @returns {boolean}
 */
function guardAdminAndAbove() {
    return requireRole([ROLES.ADMIN, ROLES.SUPER_ADMIN]);
}

/**
 * Guard: Super admin only
 * @returns {boolean}
 */
function guardSuperAdminOnly() {
    return requireRole([ROLES.SUPER_ADMIN]);
}

// ============================================================================
// PHASE 5A: UI HELPERS
// ============================================================================

/**
 * Hide element if user doesn't have permission
 * @param {HTMLElement} element
 * @param {string} permission
 */
function hideIfNotPermitted(element, permission) {
    if (!hasPermission(permission)) {
        element.style.display = 'none';
    }
}

/**
 * Disable element if user doesn't have permission
 * @param {HTMLElement} element
 * @param {string} permission
 */
function disableIfNotPermitted(element, permission) {
    if (!hasPermission(permission)) {
        element.disabled = true;
        element.title = 'You do not have permission to use this feature';
        element.classList.add('disabled-by-permission');
    }
}

/**
 * Show/hide element based on permission
 * @param {HTMLElement} element
 * @param {string} permission
 */
function toggleElementByPermission(element, permission) {
    if (hasPermission(permission)) {
        element.style.display = '';
        element.disabled = false;
    } else {
        element.style.display = 'none';
        element.disabled = true;
    }
}

// ============================================================================
// PHASE 5A: TOKEN REFRESH
// ============================================================================

/**
 * Refresh access token using refresh token
 * @returns {Promise<boolean>}
 */
async function refreshAccessToken() {
    const refreshToken = getRefreshToken();
    if (!refreshToken) return false;

    try {
        const data = await window.apiRequest('/api/auth/refresh', {
            method: 'POST',
            body: JSON.stringify({ refresh_token: refreshToken })
        });

        if (!data) {
            throw new Error('Token refresh failed');
        }
        
        setToken(data.access_token);
        setRefreshToken(data.refresh_token);
        
        // Update user info
        const user = {
            id: data.user_id,
            role: data.role,
            institution_id: data.institution_id
        };
        localStorage.setItem(USER_KEY, JSON.stringify(user));
        
        return true;
    } catch (error) {
        console.error('Token refresh failed:', error);
        return false;
    }
}

/**
 * Schedule automatic token refresh
 */
function scheduleTokenRefresh() {
    // Refresh every 25 minutes (before 30-min expiry)
    setInterval(async () => {
        if (isAuthenticated()) {
            await refreshAccessToken();
        }
    }, 25 * 60 * 1000);
}

// ============================================================================
// ROUTE PROTECTION
// ============================================================================

function requireAuth() {
    if (!isAuthenticated()) {
        window.location.href = '/html/login.html';
        return false;
    }
    return true;
}

function redirectIfAuthenticated() {
    if (isAuthenticated()) {
        const role = getUserRole();
        const dashboardUrl = getDashboardUrl(role);
        window.location.href = dashboardUrl;
        return true;
    }
    return false;
}

/**
 * Redirect if user is already enrolled (Phase 2)
 * Prevents enrolled users from accessing onboarding page
 */
function redirectIfEnrolled() {
    const isEnrolled = localStorage.getItem('is_enrolled') === 'true';
    
    if (isEnrolled) {
        const role = getUserRole();
        const dashboardUrl = getDashboardUrl(role);
        window.location.href = dashboardUrl;
        return true;
    }
    return false;
}

// ============================================================================
// DOM INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    const loginForm = document.querySelector('.auth-form, #loginForm');
    if (loginForm && window.location.pathname.includes('login.html')) {
        redirectIfAuthenticated();
        loginForm.addEventListener('submit', handleLogin);
    }
    
    const signupForm = document.querySelector('.auth-form');
    if (signupForm && window.location.pathname.includes('signup.html')) {
        redirectIfAuthenticated();
        
        signupForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const fullNameEl = document.getElementById('fullname');
            const emailEl = document.getElementById('email');
            const passwordEl = document.getElementById('password');
            const confirmPasswordEl = document.getElementById('confirm-password');
            const roleEl = document.getElementById('role');
            const submitBtn = document.getElementById('signupBtn');
            
            if (!fullNameEl || !emailEl || !passwordEl || !confirmPasswordEl || !roleEl) {
                alert('Form elements not found. Please refresh the page.');
                return;
            }
            
            const fullName = fullNameEl.value.trim();
            const email = emailEl.value.trim();
            const password = passwordEl.value;
            const confirmPassword = confirmPasswordEl.value;
            const role = roleEl.value;
            
            if (!role) {
                alert('Please select your role (Lawyer or Law Student)');
                return;
            }
            
            if (!fullName) {
                alert('Please enter your full name');
                return;
            }
            
            if (password !== confirmPassword) {
                alert('Passwords do not match!');
                return;
            }
            
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = 'Creating Account...';
            }
            
            saveUserName(fullName);
            
            const result = await register(fullName, email, password, role);
            
            if (result.success) {
                const isEnrolled = localStorage.getItem('is_enrolled') === 'true';
                
                if (!isEnrolled) {
                    window.location.href = '/html/onboarding.html';
                } else {
                    const userRole = getUserRole();
                    const dashboardUrl = getDashboardUrl(userRole);
                    window.location.href = dashboardUrl;
                }
            } else {
                alert(result.error || 'Registration failed. Please try again.');
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Sign Up';
                }
            }
        });
    }
    
    // Phase 2: Onboarding page protection
    if (window.location.pathname.includes('onboarding.html')) {
        requireAuth();
        redirectIfEnrolled();
    }
    
    const logoutLinks = document.querySelectorAll('.logout-link, #logout-btn');
    logoutLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            if (confirm('Are you sure you want to logout?')) {
                logout();
            }
        });
    });
});

function handleLogout() {
    if (confirm('Are you sure you want to logout?')) {
        logout();
    }
}

// ============================================================================
// EXPORTS
// ============================================================================

window.auth = {
    // Auth operations
    register,
    login,
    logout,
    handleLogin,
    handleLogout,
    getCurrentUser,
    getUserCredits,
    getUserCurriculum,
    refreshAccessToken,
    scheduleTokenRefresh,
    
    // Auth checks
    isAuthenticated,
    requireAuth,
    redirectIfAuthenticated,
    redirectIfEnrolled,
    enrollUser,
    
    // Token management
    getToken,
    getAccessToken,
    getRefreshToken,
    setToken,
    setRefreshToken,
    saveAccessToken,
    removeToken,
    clearAccessToken,
    authenticatedFetch,
    
    // Role management
    getUserRole,
    setUserRole,
    getDashboardUrl,
    ROLES,
    ROLE_HIERARCHY,
    MOOT_COURT_PERMISSIONS,
    
    // Phase 5A: RBAC permission checks
    hasRole,
    hasAnyRole,
    hasMinRole,
    hasPermission,
    
    // Phase 5A: Role guards
    requireRole,
    guardStudentOnly,
    guardJudgeAndAbove,
    guardFacultyAndAbove,
    guardAdminAndAbove,
    guardSuperAdminOnly,
    
    // Phase 5A: UI helpers
    hideIfNotPermitted,
    disableIfNotPermitted,
    toggleElementByPermission,
    
    // User info
    getUserName,
    saveUserName,
    getUserFirstName
};