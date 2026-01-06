/**
 * auth.js
 * Complete authentication module for LegalAI Research
 * Handles login, signup, logout, token management, and role-based routing
 * 
 * CHANGES MADE:
 * - Added role storage in localStorage
 * - Modified register() to include role field
 * - Modified login() to store user role
 * - Added role-based redirect logic after authentication
 * - All existing functionality preserved
 */

const API_BASE_URL = 'http://127.0.0.1:8000';
const TOKEN_KEY = 'access_token';
const ROLE_KEY = 'user_role'; // NEW: Store user role

// ============================================================================
// TOKEN MANAGEMENT (Unchanged)
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
        localStorage.removeItem('user_info');
        localStorage.removeItem(ROLE_KEY); // NEW: Remove role on logout
        return true;
    } catch (error) {
        console.error('Failed to remove token:', error);
        return false;
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
// ROLE MANAGEMENT (NEW)
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
 * @param {string} role - 'lawyer' or 'student'
 * @returns {string} - Dashboard URL
 */
function getDashboardUrl(role) {
    if (role === 'lawyer') {
        return '/html/dashboard-lawyer.html';
    } else if (role === 'student') {
        return '/html/dashboard-student.html';
    } else {
        // Fallback to default dashboard
        return '/html/dashboard.html';
    }
}

// ============================================================================
// API REQUEST (Unchanged)
// ============================================================================

async function apiRequest(endpoint, options = {}) {
    const url = `${API_BASE_URL}${endpoint}`;
    const token = getToken();
    
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };
    
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    
    const config = {
        ...options,
        headers
    };
    
    try {
        const response = await fetch(url, config);
        const data = await response.json();
        
        if (!response.ok) {
            if (response.status === 401) {
                removeToken();
                if (!window.location.pathname.includes('login.html')) {
                    window.location.href = '/html/login.html';
                }
            }
            
            return {
                success: false,
                error: data.detail || data.message || 'Request failed',
                status: response.status
            };
        }
        
        return {
            success: true,
            data: data
        };
        
    } catch (error) {
        console.error('API request failed:', error);
        return {
            success: false,
            error: 'Network error. Please check if the backend is running.',
            originalError: error
        };
    }
}

async function authenticatedFetch(url, options = {}) {
    const token = getToken();
    
    if (!token) {
        throw new Error('No authentication token available');
    }
    
    const headers = {
        ...options.headers,
        'Authorization': `Bearer ${token}`
    };
    
    const response = await fetch(url, {
        ...options,
        headers
    });
    
    if (response.status === 401) {
        clearAccessToken();
        window.location.href = '/html/login.html';
        throw new Error('Session expired. Please login again.');
    }
    
    return response;
}

// ============================================================================
// REGISTER (Updated with role)
// ============================================================================

/**
 * Register new user with role
 * CHANGES: Now includes role field in registration
 */
async function register(fullName, email, password, role) {
    const registerResult = await apiRequest('/api/auth/register', {
        method: 'POST',
        body: JSON.stringify({
            full_name: fullName,
            email: email,
            password: password,
            name: fullName,
            role: role // NEW: Include role in registration
        })
    });

    if (!registerResult.success) {
        return registerResult;
    }

    // Store token and role
    if (registerResult.data.access_token) {
        setToken(registerResult.data.access_token);
        
        // NEW: Store role from registration response
        if (registerResult.data.role) {
            setUserRole(registerResult.data.role);
        }
        
        return {
            success: true,
            data: registerResult.data
        };
    }

    return registerResult;
}

// ============================================================================
// LOGIN (Updated with role)
// ============================================================================

/**
 * Login user and store role
 * CHANGES: Now stores user role from login response
 */
async function login(email, password) {
    try {
        const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: new URLSearchParams({
                username: email,
                password: password
            })
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            return {
                success: false,
                error: data.detail || 'Login failed',
                status: response.status
            };
        }
        
        if (data.access_token) {
            localStorage.setItem('access_token', data.access_token);
            
            // NEW: Store user role from login response
            if (data.role) {
                setUserRole(data.role);
            }
            
            return {
                success: true,
                data: data
            };
        } else {
            return {
                success: false,
                error: 'No access token received from server'
            };
        }
        
    } catch (error) {
        console.error('Login error:', error);
        return {
            success: false,
            error: 'Network error. Please check if the backend is running.'
        };
    }
}

// ============================================================================
// LOGIN HANDLER (Updated with role-based redirect)
// ============================================================================

/**
 * Handle login form submission
 * CHANGES: Now redirects to role-specific dashboard
 */
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
            // NEW: Role-based redirect
            const role = getUserRole();
            const dashboardUrl = getDashboardUrl(role);
            window.location.href = dashboardUrl;
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
// LOGOUT (Unchanged)
// ============================================================================

function logout() {
    removeToken();
    window.location.href = '/html/login.html';
}

// ============================================================================
// USER INFO (Unchanged)
// ============================================================================

async function getCurrentUser() {
    const result = await apiRequest('/api/users/me', {
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
    const result = await apiRequest('/api/users/credits', {
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
// ROUTE PROTECTION (Updated with role-based redirect)
// ============================================================================

function requireAuth() {
    if (!isAuthenticated()) {
        window.location.href = '/html/login.html';
        return false;
    }
    return true;
}

/**
 * Redirect authenticated users to appropriate dashboard
 * CHANGES: Now redirects to role-specific dashboard
 */
function redirectIfAuthenticated() {
    if (isAuthenticated()) {
        const role = getUserRole();
        const dashboardUrl = getDashboardUrl(role);
        window.location.href = dashboardUrl;
        return true;
    }
    return false;
}

// ============================================================================
// DOM INITIALIZATION (Updated with role handling)
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
            
            const fullName = document.getElementById('fullname').value;
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;
            const confirmPassword = document.getElementById('confirm-password').value;
            const role = document.getElementById('role').value; // NEW: Get role value
            const submitBtn = signupForm.querySelector('.auth-submit');
            
            // Validate role selection
            if (!role) {
                alert('Please select your role (Lawyer or Law Student)');
                return;
            }
            
            if (password !== confirmPassword) {
                alert('Passwords do not match!');
                return;
            }
            
            submitBtn.disabled = true;
            submitBtn.textContent = 'Creating Account...';
            
            // NEW: Pass role to register function
            const result = await register(fullName, email, password, role);
            
            if (result.success) {
                // NEW: Role-based redirect after signup
                const userRole = getUserRole();
                const dashboardUrl = getDashboardUrl(userRole);
                window.location.href = dashboardUrl;
            } else {
                alert(result.error || 'Registration failed. Please try again.');
                submitBtn.disabled = false;
                submitBtn.textContent = 'Create Account';
            }
        });
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
// EXPORTS (Updated with new functions)
// ============================================================================

window.auth = {
    register,
    login,
    logout,
    handleLogin,
    handleLogout,
    getCurrentUser,
    getUserCredits,
    isAuthenticated,
    requireAuth,
    redirectIfAuthenticated,
    getToken,
    getAccessToken,
    setToken,
    saveAccessToken,
    removeToken,
    clearAccessToken,
    authenticatedFetch,
    getUserRole,      // NEW: Export role getter
    setUserRole,      // NEW: Export role setter
    getDashboardUrl   // NEW: Export dashboard URL helper
};