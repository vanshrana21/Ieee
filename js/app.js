/**
 * app.js
 * Login and Registration page logic
 * Handles form submissions and page navigation
 */

// ============================================================================
// PAGE INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Redirect to dashboard if already logged in
    redirectIfAuthenticated();
    
    // Initialize form handlers
    initializeLoginForm();
    initializeRegisterForm();
});

// ============================================================================
// FORM INITIALIZATION
// ============================================================================

/**
 * Initialize login form submission
 */
function initializeLoginForm() {
    const loginForm = document.getElementById('loginForm');
    
    if (loginForm) {
        loginForm.addEventListener('submit', handleLoginSubmit);
    }
}

/**
 * Initialize register form submission
 */
function initializeRegisterForm() {
    const registerForm = document.getElementById('registerForm');
    
    if (registerForm) {
        registerForm.addEventListener('submit', handleRegisterSubmit);
    }
}

// ============================================================================
// LOGIN HANDLER
// ============================================================================

/**
 * Handle login form submission
 */
async function handleLoginSubmit(event) {
    event.preventDefault();
    
    const email = document.getElementById('loginEmail').value.trim();
    const password = document.getElementById('loginPassword').value;
    const errorDiv = document.getElementById('loginError');
    const submitButton = event.target.querySelector('button[type="submit"]');
    
    // Clear previous errors
    if (errorDiv) {
        errorDiv.style.display = 'none';
    }
    
    // Disable submit button
    submitButton.disabled = true;
    submitButton.textContent = 'Signing in...';
    
    try {
        const result = await login(email, password);
        
        if (result.success) {
            // Redirect to dashboard
            window.location.href = 'dashboard.html';
        } else {
            // Show error
            if (errorDiv) {
                errorDiv.textContent = result.error;
                errorDiv.style.display = 'block';
            } else {
                alert(result.error);
            }
            
            // Re-enable submit button
            submitButton.disabled = false;
            submitButton.textContent = 'Sign In';
        }
    } catch (error) {
        console.error('Login error:', error);
        
        if (errorDiv) {
            errorDiv.textContent = 'An unexpected error occurred. Please try again.';
            errorDiv.style.display = 'block';
        }
        
        submitButton.disabled = false;
        submitButton.textContent = 'Sign In';
    }
}

// ============================================================================
// REGISTER HANDLER
// ============================================================================

/**
 * Handle register form submission
 */
async function handleRegisterSubmit(event) {
    event.preventDefault();
    
    const name = document.getElementById('registerName').value.trim();
    const email = document.getElementById('registerEmail').value.trim();
    const password = document.getElementById('registerPassword').value;
    const confirmPassword = document.getElementById('registerConfirmPassword').value;
    const errorDiv = document.getElementById('registerError');
    const submitButton = event.target.querySelector('button[type="submit"]');
    
    // Clear previous errors
    if (errorDiv) {
        errorDiv.style.display = 'none';
    }
    
    // Validate passwords match
    if (password !== confirmPassword) {
        if (errorDiv) {
            errorDiv.textContent = 'Passwords do not match.';
            errorDiv.style.display = 'block';
        } else {
            alert('Passwords do not match.');
        }
        return;
    }
    
    // Disable submit button
    submitButton.disabled = true;
    submitButton.textContent = 'Creating account...';
    
    try {
        const result = await register(name, email, password);
        
        if (result.success) {
            // Auto-login after successful registration
            const loginResult = await login(email, password);
            
            if (loginResult.success) {
                // Redirect to dashboard
                window.location.href = 'dashboard.html';
            } else {
                // Show success message and redirect to login
                alert('Registration successful! Please log in.');
                
                // Switch to login form if function exists
                if (typeof showLogin === 'function') {
                    showLogin(new Event('click'));
                } else {
                    window.location.reload();
                }
            }
        } else {
            // Show error
            if (errorDiv) {
                errorDiv.textContent = result.error;
                errorDiv.style.display = 'block';
            } else {
                alert(result.error);
            }
            
            // Re-enable submit button
            submitButton.disabled = false;
            submitButton.textContent = 'Create Account';
        }
    } catch (error) {
        console.error('Registration error:', error);
        
        if (errorDiv) {
            errorDiv.textContent = 'An unexpected error occurred. Please try again.';
            errorDiv.style.display = 'block';
        }
        
        submitButton.disabled = false;
        submitButton.textContent = 'Create Account';
    }
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Toggle between login and register forms
 */
function showRegister(event) {
    if (event) event.preventDefault();
    
    const loginSection = document.getElementById('loginSection');
    const registerSection = document.getElementById('registerSection');
    const loginError = document.getElementById('loginError');
    const registerError = document.getElementById('registerError');
    
    if (loginSection) loginSection.style.display = 'none';
    if (registerSection) registerSection.style.display = 'block';
    if (loginError) loginError.style.display = 'none';
    if (registerError) registerError.style.display = 'none';
}

/**
 * Toggle between register and login forms
 */
function showLogin(event) {
    if (event) event.preventDefault();
    
    const loginSection = document.getElementById('loginSection');
    const registerSection = document.getElementById('registerSection');
    const loginError = document.getElementById('loginError');
    const registerError = document.getElementById('registerError');
    
    if (registerSection) registerSection.style.display = 'none';
    if (loginSection) loginSection.style.display = 'block';
    if (loginError) loginError.style.display = 'none';
    if (registerError) registerError.style.display = 'none';
}

/**
 * Fill demo credentials for quick testing
 */
function fillDemoCredentials() {
    const emailInput = document.getElementById('loginEmail');
    const passwordInput = document.getElementById('loginPassword');
    
    if (emailInput) emailInput.value = 'demo@legalai.com';
    if (passwordInput) passwordInput.value = 'demo123';
}