/**
 * Phase 0: Virtual Courtroom Infrastructure - Frontend Authentication Context
 * 
 * Manages authentication state and permissions in the frontend.
 * Provides role-based UI rendering and permission checking.
 */

class CourtroomAuth {
    /**
     * Creates a new CourtroomAuth instance.
     * @param {CourtroomStatePersistence} persistence - State persistence instance
     */
    constructor(persistence) {
        this.persistence = persistence;
        
        // Current user data
        this.user = {
            id: null,
            name: null,
            role: null, // "judge" | "student" | "admin"
            teamId: null,
            token: null
        };
        
        // Permission matrix (mirrors backend)
        this.permissionMatrix = {
            // Timer controls - Judges and Admins only
            start_timer: ['judge', 'admin'],
            pause_timer: ['judge', 'admin'],
            resume_timer: ['judge', 'admin'],
            reset_timer: ['judge', 'admin'],
            
            // Objections - Teams raise, Judges rule
            raise_objection: ['petitioner', 'respondent'],
            rule_on_objection: ['judge', 'admin'],
            
            // Scoring - Judges and Admins only
            submit_score: ['judge', 'admin'],
            view_draft_scores: ['judge', 'admin'],
            view_submitted_scores: ['judge', 'admin', 'petitioner', 'respondent'],
            
            // Recording - All participants
            start_recording: ['judge', 'petitioner', 'respondent', 'admin'],
            stop_recording: ['judge', 'petitioner', 'respondent', 'admin'],
            
            // Transcripts - Judges control, all view
            finalize_transcript: ['judge', 'admin'],
            view_live_transcript: ['judge', 'admin', 'petitioner', 'respondent', 'observer'],
            
            // AI Opponent - Teams only
            enable_ai_opponent: ['petitioner', 'respondent'],
            
            // Round management - Judges and Admins only
            change_speaker: ['judge', 'admin'],
            complete_round: ['judge', 'admin']
        };
        
        // Bind methods
        this.initialize = this.initialize.bind(this);
        this.getCurrentUser = this.getCurrentUser.bind(this);
        this.hasRole = this.hasRole.bind(this);
        this.hasPermission = this.hasPermission.bind(this);
        this.isJudge = this.isJudge.bind(this);
        this.isTeamMember = this.isTeamMember.bind(this);
        this.getToken = this.getToken.bind(this);
        this.setToken = this.setToken.bind(this);
        this.logout = this.logout.bind(this);
    }
    
    /**
     * Initialize auth from localStorage and validate token.
     * @returns {Promise<Object|null>} User data if valid, null otherwise
     */
    async initialize() {
        // Load from persistence
        const userData = this.persistence.getUser();
        const token = this.persistence.getToken();
        
        if (!userData || !token) {
            console.log('[CourtroomAuth] No stored session found');
            return null;
        }
        
        // Validate token (in production, decode JWT and check expiry)
        const isValid = await this.validateToken(token);
        
        if (!isValid) {
            console.warn('[CourtroomAuth] Stored token is invalid or expired');
            this.logout();
            return null;
        }
        
        // Set user data
        this.user = {
            ...this.user,
            ...userData,
            token: token
        };
        
        console.log(`[CourtroomAuth] Initialized user ${this.user.id} (${this.user.role})`);
        return this.getCurrentUser();
    }
    
    /**
     * Validate JWT token.
     * @param {string} token - JWT token
     * @returns {Promise<boolean>} True if valid
     */
    async validateToken(token) {
        // TODO: Implement actual JWT validation
        // For Phase 0, simple check that token exists
        return !!token && token.length > 0;
    }
    
    /**
     * Get current user data.
     * @returns {Object|null} User data or null if not authenticated
     */
    getCurrentUser() {
        if (!this.user.id || !this.user.token) {
            return null;
        }
        return { ...this.user };
    }
    
    /**
     * Check if user has specific role.
     * @param {string} role - Role to check
     * @returns {boolean} True if user has role
     */
    hasRole(role) {
        return this.user.role === role;
    }
    
    /**
     * Check if user can perform action.
     * @param {string} action - Action to check (e.g., "start_timer")
     * @returns {boolean} True if permitted
     */
    hasPermission(action) {
        if (!this.user.role) {
            return false;
        }
        
        const allowedRoles = this.permissionMatrix[action] || [];
        return allowedRoles.includes(this.user.role);
    }
    
    /**
     * Check if user is a judge.
     * @returns {boolean} True if judge
     */
    isJudge() {
        return this.user.role === 'judge' || this.user.role === 'admin';
    }
    
    /**
     * Check if user is an admin.
     * @returns {boolean} True if admin
     */
    isAdmin() {
        return this.user.role === 'admin';
    }
    
    /**
     * Check if user belongs to a specific team.
     * @param {number} teamId - Team ID to check
     * @returns {boolean} True if user is on team
     */
    isTeamMember(teamId) {
        return this.user.teamId === teamId;
    }
    
    /**
     * Check if user is on petitioner team.
     * @returns {boolean} True if petitioner
     */
    isPetitioner() {
        return this.user.role === 'petitioner';
    }
    
    /**
     * Check if user is on respondent team.
     * @returns {boolean} True if respondent
     */
    isRespondent() {
        return this.user.role === 'respondent';
    }
    
    /**
     * Get JWT token for API calls.
     * @returns {string|null} JWT token or null
     */
    getToken() {
        return this.user.token;
    }
    
    /**
     * Set JWT token and save to persistence.
     * @param {string} token - JWT token
     */
    setToken(token) {
        this.user.token = token;
        this.persistence.saveToken(token);
    }
    
    /**
     * Set user data and save to persistence.
     * @param {Object} userData - User data object
     */
    setUser(userData) {
        this.user = {
            ...this.user,
            ...userData
        };
        this.persistence.saveUser({
            id: this.user.id,
            name: this.user.name,
            role: this.user.role,
            teamId: this.user.teamId
        });
    }
    
    /**
     * Clear auth state and redirect to login.
     * @param {string} redirectUrl - URL to redirect to (default: '/login')
     */
    logout(redirectUrl = '/login') {
        // Clear user data
        this.user = {
            id: null,
            name: null,
            role: null,
            teamId: null,
            token: null
        };
        
        // Clear persistence
        this.persistence.clearToken();
        this.persistence.clearUser();
        
        console.log('[CourtroomAuth] Logged out, redirecting to login');
        
        // Redirect
        window.location.href = redirectUrl;
    }
    
    /**
     * Get API request headers with authorization.
     * @returns {Object} Headers object with Authorization
     */
    getAuthHeaders() {
        const token = this.getToken();
        return {
            'Content-Type': 'application/json',
            'Authorization': token ? `Bearer ${token}` : ''
        };
    }
    
    /**
     * Get all permissions for current user.
     * @returns {string[]} List of allowed actions
     */
    getPermissions() {
        if (!this.user.role) {
            return [];
        }
        
        return Object.entries(this.permissionMatrix)
            .filter(([_, roles]) => roles.includes(this.user.role))
            .map(([action, _]) => action);
    }
    
    /**
     * UI helper: Render element only if user has permission.
     * @param {string} action - Required action permission
     * @param {Function} renderFn - Function that returns HTML/element
     * @returns {*} Rendered content or null
     */
    renderIfPermitted(action, renderFn) {
        if (this.hasPermission(action)) {
            return renderFn();
        }
        return null;
    }
    
    /**
     * UI helper: Disable/enable button based on permission.
     * @param {HTMLElement} button - Button element
     * @param {string} action - Required action permission
     */
    setButtonPermission(button, action) {
        const hasPerm = this.hasPermission(action);
        button.disabled = !hasPerm;
        
        if (!hasPerm) {
            button.classList.add('disabled');
            button.title = 'You do not have permission for this action';
        } else {
            button.classList.remove('disabled');
            button.title = '';
        }
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CourtroomAuth;
}
