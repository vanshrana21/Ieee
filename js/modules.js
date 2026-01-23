(function() {
    'use strict';

    const API_BASE = window.__API_BASE__ || (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' ? `${window.location.protocol}//${window.location.hostname}:8000` : '');

    const state = {
        subjectId: null,
        subjectName: '',
        courseName: '',
        semester: 1,
        modules: [],
        isLoading: true
    };

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    async function fetchJson(url, opts = {}) {
        const token = window.auth?.getToken?.() || localStorage.getItem('access_token');
        
        if (!token) {
            window.location.href = 'login.html';
            throw new Error('Not authenticated');
        }
        
        const headers = { ...opts.headers };
        headers['Authorization'] = `Bearer ${token}`;
        headers['Content-Type'] = headers['Content-Type'] || 'application/json';

        const resp = await fetch(url, { ...opts, headers });
        
        if (resp.status === 401) {
            localStorage.removeItem('access_token');
            window.location.href = 'login.html';
            throw new Error('Session expired');
        }
        
        const text = await resp.text();
        let json;
        try { json = text ? JSON.parse(text) : null; } catch { json = null; }
        if (!resp.ok) throw new Error(json?.detail || json?.error || resp.statusText);
        return json;
    }

    async function loadModules() {
        const modulesList = document.getElementById('modulesList');
        if (!modulesList) return;

        try {
            const profile = await fetchJson(`${API_BASE}/api/student/academic-profile`).catch(() => ({}));
            state.courseName = profile.course_name || '';
            state.semester = profile.current_semester || 1;

            const response = await fetchJson(`${API_BASE}/api/student/subject/${state.subjectId}/modules`);
            const modulesArray = response.units || response.modules || [];
            
            state.modules = modulesArray.map(m => ({
                ...m,
                total_contents: m.total_contents || 0
            }));
            state.subjectName = response.subject_name || 'Subject';

            state.isLoading = false;
            
            document.getElementById('subjectTitle').textContent = state.subjectName;
            document.getElementById('semesterBadge').textContent = `Semester ${state.semester}`;
            document.getElementById('headerSubtitle').textContent = 'Select a module to begin learning';
            
            renderModules();
        } catch (error) {
            console.error('Failed to load modules:', error);
            modulesList.innerHTML = `
                <div class="error-state">
                    <p>Failed to load modules. ${escapeHtml(error.message)}</p>
                    <button class="retry-btn" onclick="window.location.reload()">Retry</button>
                </div>
            `;
        }
    }

    function renderModules() {
        const modulesList = document.getElementById('modulesList');
        if (!modulesList) return;

        if (state.modules.length === 0) {
            modulesList.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                            <line x1="9" y1="7" x2="15" y2="7"/>
                            <line x1="9" y1="11" x2="15" y2="11"/>
                        </svg>
                    </div>
                    <h3 class="empty-title">No modules found for this subject</h3>
                    <p class="empty-subtitle">Modules will be added soon.</p>
                </div>
            `;
            return;
        }

        modulesList.innerHTML = state.modules.map((module, index) => {
            const moduleNumber = module.order_index || (index + 1);
            const moduleId = module.module_id || module.id;
            const totalContents = module.total_contents || 0;
            const subtitle = totalContents > 0 
                ? `${totalContents} lesson${totalContents !== 1 ? 's' : ''} available`
                : 'Lessons coming soon';

            return `
                <div class="module-card" onclick="window.modulesPage.navigateToModule(${moduleId})">
                    <div class="module-header">
                        <div class="module-info">
                            <p class="module-number">Module ${moduleNumber}</p>
                            <h3 class="module-title">${escapeHtml(module.title)}</h3>
                            <p class="module-subtitle">${subtitle}</p>
                        </div>
                        <div class="module-actions">
                            <button class="module-cta" onclick="event.stopPropagation(); window.modulesPage.navigateToModule(${moduleId})">
                                Open Module
                            </button>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    }

    async function navigateToModule(moduleId) {
        window.location.href = `learn-content.html?module_id=${moduleId}&subject_id=${state.subjectId}`;
    }

    function init() {
        const urlParams = new URLSearchParams(window.location.search);
        state.subjectId = urlParams.get('subject_id');

        if (!state.subjectId) {
            window.location.href = 'dashboard-student.html';
            return;
        }

        loadModules();
    }

    window.modulesPage = {
        navigateToModule
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
