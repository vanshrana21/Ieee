/**
 * ai-moot-api.js
 * Phase 3: AI Moot Court API wrapper
 * 
 * Handles AI Practice mode API calls with proper error handling
 */

if (!window.API_BASE_URL) {
    window.API_BASE_URL = 'http://127.0.0.1:8000';
}

const aiMootApi = {
    /**
     * Get auth token from localStorage
     */
    getToken() {
        return localStorage.getItem('access_token');
    },

    /**
     * Handle 401 errors → redirect to login
     */
    handleAuthError() {
        localStorage.removeItem('access_token');
        window.location.href = '/html/login.html';
    },

    /**
     * Base request helper for AI Moot endpoints
     */
    async request(endpoint, options = {}) {
        const token = this.getToken();
        
        if (!token) {
            this.handleAuthError();
            return { error: 'Authentication required. Please login.' };
        }

        const headers = {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
            ...options.headers
        };

        try {
            const response = await fetch(`${API_BASE_URL}${endpoint}`, {
                ...options,
                headers
            });

            // Handle 401 - redirect to login
            if (response.status === 401) {
                this.handleAuthError();
                return { error: 'Session expired. Please login again.' };
            }

            const data = await response.json();

            if (!response.ok) {
                return { 
                    error: data.detail || data.message || `Request failed (${response.status})` 
                };
            }

            return data;

        } catch (error) {
            // Network error
            console.error('AI Moot API Error:', error);
            return { 
                error: 'Network error. Check internet connection.' 
            };
        }
    },

    /**
     * GET /api/ai-moot/problems
     * Get 3 pre-loaded Indian moot problems
     */
    async getValidationProblems() {
        return this.request('/api/ai-moot/problems', { method: 'GET' });
    },

    /**
     * POST /api/ai-moot/sessions
     * Create a new AI practice session
     * 
     * @param {string} problemType - "validation_1", "validation_2", "validation_3", or "custom"
     * @param {string} side - "petitioner" or "respondent"
     * @param {number} problemId - Required if problemType is "custom"
     */
    async createAISession(problemType, side, problemId = 1) {
        const body = {
            problem_id: problemId,
            side: side,
            problem_type: problemType
        };
        
        return this.request('/api/ai-moot/sessions', {
            method: 'POST',
            body: JSON.stringify(body)
        });
    },

    /**
     * POST /api/ai-moot/sessions/{id}/turns
     * Submit argument and get AI judge feedback
     * 
     * @param {string} sessionId - Session UUID
     * @param {string} argument - User's argument text (20-250 chars)
     */
    async submitArgument(sessionId, argument) {
        const body = {
            argument: argument
        };
        
        return this.request(`/api/ai-moot/sessions/${sessionId}/turns`, {
            method: 'POST',
            body: JSON.stringify(body)
        });
    },

    /**
     * GET /api/ai-moot/sessions/{id}
     * Get session details with all turns
     * 
     * @param {string} sessionId - Session UUID
     */
    async getSessionDetails(sessionId) {
        return this.request(`/api/ai-moot/sessions/${sessionId}`, { method: 'GET' });
    }
};

// Make available globally
window.aiMootApi = aiMootApi;
