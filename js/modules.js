/**
 * modules.js
 * Phase 4: Subject Modules List
 */

(function() {
    'use strict';

    const state = {
        subjectId: null,
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

    async function loadModules() {
        const modulesList = document.getElementById('modulesList');
        if (!modulesList) return;

        try {
            const response = await api.getSubjectModules(state.subjectId);
            state.modules = response.modules;
            state.isLoading = false;
            renderModules();
        } catch (error) {
            console.error('Failed to load modules:', error);
            modulesList.innerHTML = `
                <div class="error-state" style="text-align: center; padding: 40px;">
                    <p style="color: #ef4444;">Failed to load modules. Please try again.</p>
                    <button onclick="window.location.reload()" class="btn btn-primary">Retry</button>
                </div>
            `;
        }
    }

    function renderModules() {
        const modulesList = document.getElementById('modulesList');
        if (!modulesList) return;

        if (state.modules.length === 0) {
            modulesList.innerHTML = `
                <div class="empty-state" style="text-align: center; padding: 40px;">
                    <div style="font-size: 48px; margin-bottom: 16px;">📚</div>
                    <h3>No Modules Found</h3>
                    <p>There are no learning modules available for this subject yet.</p>
                </div>
            `;
            return;
        }

        modulesList.innerHTML = state.modules.map(module => {
            const isDisabled = module.content_count === 0;
            return `
                <div class="module-card ${isDisabled ? 'disabled' : ''}" onclick="navigateToModule(${module.module_id}, ${isDisabled})">
                    <div class="module-info">
                        <h3>${escapeHtml(module.title)}</h3>
                        <div class="module-meta">
                            <span class="content-count">
                                📖 ${module.content_count} Lessons
                            </span>
                            ${module.is_completed ? '<span class="completion-badge">Completed</span>' : ''}
                        </div>
                    </div>
                    <div class="module-arrow">
                        ${isDisabled ? '🔒' : '→'}
                    </div>
                </div>
            `;
        }).join('');
    }

    window.navigateToModule = function(moduleId, isDisabled) {
        if (isDisabled) return;
        window.location.href = `module-content.html?module_id=${moduleId}&subject_id=${state.subjectId}`;
    };

    function init() {
        const urlParams = new URLSearchParams(window.location.search);
        state.subjectId = urlParams.get('subject_id');

        if (!state.subjectId) {
            window.location.href = 'start-studying.html';
            return;
        }

        const backLink = document.getElementById('backToSubject');
        if (backLink) {
            backLink.href = `start-studying.html?subject=${state.subjectId}`;
        }

        loadModules();
    }

    document.addEventListener('DOMContentLoaded', init);
})();
