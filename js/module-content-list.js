/**
 * module-content-list.js
 * Phase 4: Module Topics List
 */

(function() {
    'use strict';

    const state = {
        moduleId: null,
        subjectId: null,
        content: [],
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

    async function loadContent() {
        const contentList = document.getElementById('contentList');
        if (!contentList) return;

        try {
            const response = await api.getModuleContent(state.moduleId);
            state.content = response.content;
            state.isLoading = false;
            renderContent();
        } catch (error) {
            console.error('Failed to load content:', error);
            contentList.innerHTML = `
                <div class="error-state" style="text-align: center; padding: 40px;">
                    <p style="color: #ef4444;">Failed to load topics. Please try again.</p>
                    <button onclick="window.location.reload()" class="btn btn-primary">Retry</button>
                </div>
            `;
        }
    }

    function renderContent() {
        const contentList = document.getElementById('contentList');
        if (!contentList) return;

        if (state.content.length === 0) {
            contentList.innerHTML = `
                <div class="empty-state" style="text-align: center; padding: 40px;">
                    <div style="font-size: 48px; margin-bottom: 16px;">📖</div>
                    <h3>No Topics Found</h3>
                    <p>There is no learning content available in this module yet.</p>
                </div>
            `;
            return;
        }

        contentList.innerHTML = state.content.map(item => {
            return `
                <div class="content-card" onclick="navigateToContent(${item.content_id})">
                    <div class="card-left">
                        <div class="completion-dot ${item.is_completed ? 'completed' : ''}"></div>
                        <div class="content-info">
                            <h3>${escapeHtml(item.title)}</h3>
                            <div class="content-meta">
                                Lesson ${item.sequence_order}
                            </div>
                        </div>
                    </div>
                    <div class="content-arrow">→</div>
                </div>
            `;
        }).join('');
    }

    window.navigateToContent = function(contentId) {
        window.location.href = `learn-content.html?id=${contentId}&module_id=${state.moduleId}&subject_id=${state.subjectId}`;
    };

    function init() {
        const urlParams = new URLSearchParams(window.location.search);
        state.moduleId = urlParams.get('module_id');
        state.subjectId = urlParams.get('subject_id');

        if (!state.moduleId) {
            window.location.href = 'start-studying.html';
            return;
        }

        const backLink = document.getElementById('backToModules');
        if (backLink) {
            backLink.href = `modules.html?subject_id=${state.subjectId}`;
        }

        loadContent();
    }

    document.addEventListener('DOMContentLoaded', init);
})();
