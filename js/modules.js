/**
 * modules.js
 * Phase 4: Subject Modules List with Progress
 */

(function() {
    'use strict';

    const state = {
        subjectId: null,
        subjectName: '',
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
            state.subjectName = response.subject_name;
            state.isLoading = false;
            
            document.getElementById('subjectTitle').textContent = state.subjectName;
            
            renderModules();
        } catch (error) {
            console.error('Failed to load modules:', error);
            modulesList.innerHTML = `
                <div class="error-state" style="text-align: center; padding: 40px;">
                    <div style="font-size: 48px; margin-bottom: 16px;">⚠️</div>
                    <p style="color: #ef4444; margin-bottom: 16px;">Failed to load modules. ${escapeHtml(error.message)}</p>
                    <button onclick="window.location.reload()" style="background: #0066ff; color: white; border: none; padding: 12px 24px; border-radius: 8px; cursor: pointer; font-weight: 600;">Retry</button>
                </div>
            `;
        }
    }

    function renderModules() {
        const modulesList = document.getElementById('modulesList');
        if (!modulesList) return;

        if (state.modules.length === 0) {
            modulesList.innerHTML = `
                <div class="empty-state" style="text-align: center; padding: 40px; background: white; border-radius: 12px; border: 1px solid #e2e8f0;">
                    <div style="font-size: 48px; margin-bottom: 16px;">📚</div>
                    <h3 style="margin: 0 0 8px 0; color: #0f172a;">No Modules Added Yet</h3>
                    <p style="color: #64748b; margin: 0;">Learning modules for this subject are being prepared. Check back soon!</p>
                </div>
            `;
            return;
        }

        modulesList.innerHTML = state.modules.map(module => {
            const hasContent = module.total_contents > 0;
            const progressPercent = module.total_contents > 0 
                ? Math.round((module.completed_contents / module.total_contents) * 100) 
                : 0;
            
            const buttonText = module.completed_contents === 0 ? 'Start' : 
                              module.is_completed ? 'Review' : 'Continue';
            const buttonClass = module.is_completed ? 'secondary' : '';
            
            return `
                <div class="module-card ${!hasContent ? 'no-content' : ''}" ${hasContent ? `onclick="navigateToModule(${module.module_id})"` : ''}>
                    <div class="module-card-header">
                        <div class="module-info">
                            <h3>${escapeHtml(module.title)}</h3>
                            <div class="module-meta">
                                Module ${module.sequence_order} • ${module.total_contents} lesson${module.total_contents !== 1 ? 's' : ''}
                            </div>
                        </div>
                        <div class="module-status">
                            ${module.is_completed ? '<span class="completion-badge">Completed</span>' : ''}
                            ${hasContent ? `<button class="module-action-btn ${buttonClass}" onclick="event.stopPropagation(); navigateToModule(${module.module_id})">${buttonText}</button>` : ''}
                        </div>
                    </div>
                    ${hasContent ? `
                        <div class="progress-section">
                            <div class="progress-bar">
                                <div class="progress-fill ${module.is_completed ? 'completed' : ''}" style="width: ${progressPercent}%"></div>
                            </div>
                            <div class="progress-text">${module.completed_contents} of ${module.total_contents} completed (${progressPercent}%)</div>
                        </div>
                    ` : `
                        <div class="no-content-msg">Content for this module is being prepared...</div>
                    `}
                </div>
            `;
        }).join('');
    }

    window.navigateToModule = async function(moduleId) {
        try {
            const resumeData = await api.getModuleResume(moduleId);
            
            if (resumeData.next_content_id) {
                window.location.href = `learn-content.html?id=${resumeData.next_content_id}&module_id=${moduleId}&subject_id=${state.subjectId}`;
            } else {
                alert(resumeData.message || 'No content available in this module yet.');
            }
        } catch (error) {
            console.error('Failed to get module resume:', error);
            window.location.href = `module-content.html?module_id=${moduleId}&subject_id=${state.subjectId}`;
        }
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
