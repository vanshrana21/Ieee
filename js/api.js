/**
 * api.js
 * Global API wrapper for JurisAI
 */

const API_BASE_URL = 'http://127.0.0.1:8000';

const api = {
    /**
     * Helper for making authenticated requests
     */
    async request(endpoint, options = {}) {
        const token = localStorage.getItem('access_token');
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

        const response = await fetch(`${API_BASE_URL}${endpoint}`, config);
        const data = await response.json();

        if (!response.ok) {
            if (response.status === 401) {
                localStorage.removeItem('access_token');
                window.location.href = '/html/login.html';
            }
            throw new Error(data.detail || data.message || 'API Request failed');
        }

        return data;
    },

    /**
     * GET request
     */
    async get(endpoint) {
        return this.request(endpoint, { method: 'GET' });
    },

    /**
     * POST request
     */
    async post(endpoint, body) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(body)
        });
    },

    // --- Subject Context Endpoints (Phase 9.1 & 9.2) ---
    async getSubjects() {
        return this.get('/subjects');
    },

    async selectSubject(subjectId) {
        return this.post(`/subjects/${subjectId}/select`);
    },

    async getResumeContext(subjectId) {
        return this.get(`/subjects/${subjectId}/resume`);
    },

    // --- Dashboard Stats Endpoints (Phase 9.3) ---
    async getDashboardStats() {
        return this.get('/api/dashboard/stats');
    },

    async getLastActivity() {
        return this.get('/api/dashboard/last-activity');
    },

    // --- Student Content & Modules (Phase 4) ---
    async getSubjectModules(subjectId) {
        return this.get(`/api/student/subject/${subjectId}/modules`);
    },

    async getModuleContent(moduleId) {
        return this.get(`/api/student/module/${moduleId}/content`);
    },

    async getContentDetail(contentId) {
        return this.get(`/api/student/content/${contentId}`);
    },

    async markContentComplete(contentId) {
        return this.post(`/api/student/content/${contentId}/complete`, {});
    },

    async getSubjectAvailability(subjectId) {
        return this.get(`/api/student/subject/${subjectId}/availability`);
    }
};

window.api = api;
