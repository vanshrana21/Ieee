/**
 * js/sso-login-controller.js
 * Phase 6: SSO authentication controller for Google/Microsoft login
 */

class SSOLoginController {
    constructor() {
        this.baseUrl = 'http://localhost:8000/api';
        this.institutionCode = null;
        
        this.init();
    }

    init() {
        // Check if we're on the SSO callback page
        this.handleCallbackIfPresent();
        
        // Auto-detect institution from email input if exists
        this.setupEmailDetection();
    }

    /**
     * Initiate Google SSO login
     */
    async initiateGoogleSSO() {
        const institutionCode = this.getInstitutionCode();
        if (!institutionCode) {
            alert('Please enter your institution code or email first.');
            return;
        }
        
        try {
            // Get SSO login URL from backend
            const response = await fetch(
                `${this.baseUrl}/auth/sso/google/login-url?institution_code=${institutionCode}`
            );
            
            if (response.ok) {
                const data = await response.json();
                // Redirect to Google OAuth
                window.location.href = data.login_url;
            } else {
                const error = await response.json();
                alert('SSO not configured for this institution: ' + (error.detail || 'Unknown error'));
            }
        } catch (error) {
            console.error('SSO initiation error:', error);
            alert('Failed to initiate SSO login.');
        }
    }

    /**
     * Initiate Microsoft SSO login
     */
    async initiateMicrosoftSSO() {
        const institutionCode = this.getInstitutionCode();
        if (!institutionCode) {
            alert('Please enter your institution code or email first.');
            return;
        }
        
        try {
            const response = await fetch(
                `${this.baseUrl}/auth/sso/microsoft/login-url?institution_code=${institutionCode}`
            );
            
            if (response.ok) {
                const data = await response.json();
                window.location.href = data.login_url;
            } else {
                const error = await response.json();
                alert('SSO not configured for this institution: ' + (error.detail || 'Unknown error'));
            }
        } catch (error) {
            console.error('SSO initiation error:', error);
            alert('Failed to initiate SSO login.');
        }
    }

    /**
     * Get institution code from various sources
     */
    getInstitutionCode() {
        // Check if already detected
        if (this.institutionCode) {
            return this.institutionCode;
        }
        
        // Check URL parameter
        const urlParams = new URLSearchParams(window.location.search);
        const fromUrl = urlParams.get('institution');
        if (fromUrl) {
            this.institutionCode = fromUrl.toLowerCase();
            return this.institutionCode;
        }
        
        // Check email input
        const emailInput = document.getElementById('email');
        if (emailInput && emailInput.value) {
            const fromEmail = this.detectInstitutionFromEmail(emailInput.value);
            if (fromEmail) {
                this.institutionCode = fromEmail;
                return fromEmail;
            }
        }
        
        // Check institution code input
        const codeInput = document.getElementById('institution-code');
        if (codeInput && codeInput.value) {
            this.institutionCode = codeInput.value.toLowerCase();
            return this.institutionCode;
        }
        
        return null;
    }

    /**
     * Auto-detect institution from email domain
     */
    detectInstitutionFromEmail(email) {
        return InstitutionBranding.detectFromEmail(email);
    }

    /**
     * Setup email input detection
     */
    setupEmailDetection() {
        const emailInput = document.getElementById('email');
        if (!emailInput) return;
        
        emailInput.addEventListener('blur', () => {
            const email = emailInput.value;
            if (email && email.includes('@')) {
                const institution = this.detectInstitutionFromEmail(email);
                if (institution) {
                    this.institutionCode = institution;
                    
                    // Show detected institution
                    this.showDetectedInstitution(institution);
                    
                    // Auto-select SSO if available
                    this.checkSSOAvailability(institution);
                }
            }
        });
    }

    showDetectedInstitution(institution) {
        // Show a notification that institution was detected
        const container = document.getElementById('institution-detected');
        if (container) {
            container.textContent = `Institution detected: ${institution.toUpperCase()}`;
            container.style.display = 'block';
        }
        
        // Update institution code input if exists
        const codeInput = document.getElementById('institution-code');
        if (codeInput) {
            codeInput.value = institution;
        }
    }

    async checkSSOAvailability(institution) {
        try {
            const response = await fetch(
                `${this.baseUrl}/institutions/${institution}/branding`
            );
            
            if (response.ok) {
                // Institution exists, SSO might be available
                // Show SSO buttons if hidden
                const ssoSection = document.getElementById('sso-section');
                if (ssoSection) {
                    ssoSection.style.display = 'block';
                }
            }
        } catch (error) {
            console.error('Error checking SSO availability:', error);
        }
    }

    /**
     * Handle SSO callback after redirect from provider
     */
    handleCallbackIfPresent() {
        const urlParams = new URLSearchParams(window.location.search);
        const token = urlParams.get('token');
        const institution = urlParams.get('institution');
        const error = urlParams.get('error');
        
        if (error) {
            this.handleSSOError(error, urlParams.get('message'));
            return;
        }
        
        if (token) {
            // Store token
            localStorage.setItem('access_token', token);
            
            // Store institution
            if (institution) {
                localStorage.setItem('institution_code', institution);
            }
            
            // Redirect to dashboard
            window.location.href = 'admin-institution-dashboard.html';
        }
    }

    handleSSOError(error, message) {
        let userMessage = 'SSO login failed.';
        
        switch (error) {
            case 'invalid_state':
                userMessage = 'Invalid session. Please try again.';
                break;
            case 'institution_not_found':
                userMessage = 'Institution not found. Please check your institution code.';
                break;
            case 'sso_not_configured':
                userMessage = 'SSO is not configured for your institution.';
                break;
            case 'email_domain_mismatch':
                userMessage = 'Your email domain does not match this institution.';
                break;
            case 'token_exchange_failed':
                userMessage = 'Failed to authenticate with the provider.';
                break;
            case 'user_info_failed':
                userMessage = 'Failed to retrieve your profile information.';
                break;
            case 'user_creation_failed':
                userMessage = 'Failed to create your account. Please contact support.';
                break;
            default:
                userMessage = message || 'An error occurred during SSO login.';
        }
        
        // Show error to user
        const errorContainer = document.getElementById('sso-error');
        if (errorContainer) {
            errorContainer.textContent = userMessage;
            errorContainer.style.display = 'block';
        } else {
            alert(userMessage);
        }
        
        // Log error
        console.error('SSO Error:', error, message);
    }

    /**
     * Exchange OAuth2 code for token (called on callback page)
     */
    async handleCallback(code, state) {
        try {
            const response = await fetch(
                `${this.baseUrl}/auth/sso/callback?code=${code}&state=${state}`
            );
            
            if (response.redirected) {
                // Follow redirect (should contain token)
                window.location.href = response.url;
            } else {
                const data = await response.json();
                if (data.error) {
                    this.handleSSOError(data.error, data.message);
                }
            }
        } catch (error) {
            console.error('Callback handling error:', error);
            this.handleSSOError('sso_error');
        }
    }

    /**
     * Logout and clear SSO session
     */
    logout() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('institution_code');
        localStorage.removeItem('refresh_token');
        
        // Clear any SSO-specific cookies if needed
        document.cookie.split(';').forEach(cookie => {
            const [name] = cookie.split('=');
            document.cookie = `${name.trim()}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;`;
        });
        
        window.location.href = 'login.html';
    }
}

// Auto-initialize on page load
if (typeof window !== 'undefined') {
    window.ssoLoginController = new SSOLoginController();
}
