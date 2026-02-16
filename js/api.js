console.log("[API] Single API Layer Active");

window.API_BASE = "http://127.0.0.1:8000";

window.getToken = function () {
    return localStorage.getItem("access_token");
};

window.clearToken = function () {
    localStorage.removeItem("access_token");
    localStorage.removeItem("user_role");
};

window.apiRequest = async function (path, options = {}) {
    const token = window.getToken();

    const headers = {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.headers || {})
    };

    const response = await fetch(`${window.API_BASE}${path}`, {
        ...options,
        headers
    });

    if (response.status === 401) {
        console.warn("[AUTH] Token invalid or expired.");
        window.clearToken();
        window.location.href = "/html/login.html";
        return null;
    }

    if (!response.ok) {
        let err = null;
        try {
            err = await response.json();
        } catch {}
        throw new Error(err?.message || "API Error");
    }

    return response.json();
};

// Legacy API object for backward compatibility
window.api = {
    async request(endpoint, options = {}) {
        return window.apiRequest(endpoint, options);
    },

    async get(endpoint) {
        return window.apiRequest(endpoint, { method: "GET" });
    },

    async post(endpoint, body) {
        return window.apiRequest(endpoint, {
            method: "POST",
            body: JSON.stringify(body)
        });
    },

    // --- Subject Context Endpoints ---
    async getSubjects() {
        return this.get('/subjects');
    },

    async selectSubject(subjectId) {
        return this.post(`/subjects/${subjectId}/select`);
    },

    async getResumeContext(subjectId) {
        return this.get(`/subjects/${subjectId}/resume`);
    },

    // --- Dashboard Stats Endpoints ---
    async getDashboardStats() {
        return this.get('/api/dashboard/stats');
    },

    async getLastActivity() {
        return this.get('/api/dashboard/last-activity');
    },

    // --- Student Content & Modules ---
    async getSubjectModules(subjectId) {
        return this.get(`/api/student/subject/${subjectId}/modules`);
    },

    async getModuleContent(moduleId) {
        return this.get(`/api/student/module/${moduleId}/content`);
    },

    async getModuleResume(moduleId) {
        return this.get(`/api/student/module/${moduleId}/resume`);
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
