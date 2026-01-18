(function() {
    'use strict';

    const API_BASE = window.__API_BASE__ || 'http://127.0.0.1:8000';

    let subjectId = null;
    let subjectTitle = '';

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
        if (!resp.ok) throw new Error(json?.detail || resp.statusText);
        return json;
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function showError(message) {
        const container = document.getElementById('modulesContainer');
        container.innerHTML = `
            <div class="error-state">
                <div style="font-size: 48px; margin-bottom: 16px;">⚠️</div>
                <h2>Error Loading Modules</h2>
                <p>${escapeHtml(message)}</p>
                <button class="primary-button" onclick="goBack()">Go Back</button>
            </div>
        `;
    }

    function renderModules(data) {
        const container = document.getElementById('modulesContainer');
        subjectTitle = data.subject_title;

        if (!data.modules || data.modules.length === 0) {
            container.innerHTML = `
                <div class="subject-header">
                    <h1 class="subject-title">${escapeHtml(data.subject_title)}</h1>
                    <p class="subject-subtitle">Learning Modules</p>
                </div>
                <div class="no-content">
                    <div style="font-size: 48px; margin-bottom: 16px;">📚</div>
                    <h3>No Modules Available</h3>
                    <p>Learning content is being prepared for this subject. Check back soon!</p>
                </div>
            `;
            return;
        }

        let modulesHtml = data.modules.map(module => {
            const progress = module.content_count > 0 
                ? Math.round((module.completed_count / module.content_count) * 100) 
                : 0;
            const isCompleted = module.is_completed;
            const isDisabled = module.content_count === 0;
            
            let statusText = `${module.completed_count}/${module.content_count} lessons`;
            if (isCompleted) statusText = 'Completed';
            if (isDisabled) statusText = 'No content yet';

            return `
                <div class="module-card ${isCompleted ? 'completed' : ''} ${isDisabled ? 'disabled' : ''}" 
                     onclick="${isDisabled ? '' : `openModule(${module.module_id})`}"
                     data-module-id="${module.module_id}">
                    <div class="module-card-header">
                        <div class="module-icon">${isCompleted ? '✓' : '📖'}</div>
                        <div class="module-info">
                            <h3 class="module-card-title">${escapeHtml(module.title)}</h3>
                            <p class="module-meta">${module.content_count} lesson${module.content_count !== 1 ? 's' : ''}</p>
                        </div>
                    </div>
                    <div class="module-progress">
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: ${progress}%"></div>
                        </div>
                        <span class="progress-text">${statusText}</span>
                    </div>
                </div>
            `;
        }).join('');

        container.innerHTML = `
            <div class="subject-header">
                <h1 class="subject-title">${escapeHtml(data.subject_title)}</h1>
                <p class="subject-subtitle">Select a module to start learning</p>
            </div>
            <div class="modules-list">
                ${modulesHtml}
            </div>
        `;
    }

    async function loadModules() {
        const urlParams = new URLSearchParams(window.location.search);
        subjectId = urlParams.get('subject_id');

        if (!subjectId) {
            showError('No subject selected. Please go back and select a subject.');
            return;
        }

        try {
            const data = await fetchJson(`${API_BASE}/api/student/subject/${subjectId}/modules`);
            renderModules(data);
        } catch (error) {
            console.error('Failed to load modules:', error);
            showError(error.message || 'Failed to load modules. Please try again.');
        }
    }

    window.openModule = function(moduleId) {
        window.location.href = `module-content.html?module_id=${moduleId}&subject_id=${subjectId}`;
    };

    window.goBack = function() {
        if (subjectId) {
            window.location.href = `start-studying.html?subject=${subjectId}`;
        } else {
            window.location.href = 'start-studying.html';
        }
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', loadModules);
    } else {
        loadModules();
    }
})();
