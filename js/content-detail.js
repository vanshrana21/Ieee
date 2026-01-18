/**
 * content-detail.js
 * Phase 4.3: Content Detail Display and Progress Tracking
 */

(function() {
    'use strict';

    const state = {
        contentId: null,
        moduleId: null,
        subjectId: null,
        content: null,
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

    function formatMarkdown(text) {
        if (!text) return '';
        // Simple markdown formatting
        return text
            .replace(/\n\n/g, '</p><p>')
            .replace(/\n/g, '<br>')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            .split('</p><p>').map(p => `<p>${p}</p>`).join('');
    }

    async function loadContentDetail() {
        const container = document.getElementById('contentContainer');
        if (!container) return;

        try {
            const data = await api.getContentDetail(state.contentId);
            state.content = data;
            state.isLoading = false;
            renderContent(container);
        } catch (error) {
            console.error('Failed to load content detail:', error);
            container.innerHTML = `
                <div class="error-state" style="text-align: center; padding: 40px;">
                    <p style="color: #ef4444;">Failed to load content. ${error.message}</p>
                    <button onclick="window.location.reload()" class="btn btn-primary">Retry</button>
                </div>
            `;
        }
    }

    function renderContent(container) {
        if (!state.content) return;

        container.innerHTML = `
            <div class="content-view">
                <div class="content-header">
                    <h1 class="content-title">${escapeHtml(state.content.title)}</h1>
                    <div class="content-meta">
                        Lesson ${state.content.sequence_order}
                        ${state.content.is_completed ? '<span class="status-badge completed">✓ Completed</span>' : ''}
                    </div>
                </div>

                <div class="content-body">
                    ${formatMarkdown(state.content.body)}
                </div>

                <div class="content-footer">
                    ${!state.content.is_completed ? `
                        <button id="completeBtn" class="btn btn-primary btn-lg">
                            ✓ Mark as Completed
                        </button>
                    ` : `
                        <div class="completed-msg">
                            <span class="icon">✅</span> You have completed this lesson.
                        </div>
                    `}
                    <div class="navigation-actions">
                        ${state.moduleId ? `
                            <a href="module-content.html?module_id=${state.moduleId}&subject_id=${state.subjectId}" class="btn btn-secondary">
                                Back to Topics
                            </a>
                        ` : `
                            <a href="dashboard-student.html" class="btn btn-secondary">
                                Back to Dashboard
                            </a>
                        `}
                    </div>
                </div>
            </div>
        `;

        const completeBtn = document.getElementById('completeBtn');
        if (completeBtn) {
            completeBtn.addEventListener('click', handleMarkComplete);
        }
    }

    async function handleMarkComplete() {
        const btn = document.getElementById('completeBtn');
        if (!btn) return;

        btn.disabled = true;
        btn.textContent = 'Updating...';

        try {
            await api.markContentComplete(state.contentId);
            // Re-render or show success
            state.content.is_completed = true;
            renderContent(document.getElementById('contentContainer'));
        } catch (error) {
            console.error('Failed to mark complete:', error);
            btn.disabled = false;
            btn.textContent = '✓ Mark as Completed';
            alert('Failed to update progress. Please try again.');
        }
    }

    function init() {
        const urlParams = new URLSearchParams(window.location.search);
        state.contentId = urlParams.get('id');
        state.moduleId = urlParams.get('module_id');
        state.subjectId = urlParams.get('subject_id');

        if (!state.contentId) {
            window.location.href = 'dashboard-student.html';
            return;
        }

        loadContentDetail();
    }

    // Export for HTML consumption if needed
    window.contentDetail = {
        loadLearnContent: (id) => {
            state.contentId = id;
            loadContentDetail();
        }
    };

    document.addEventListener('DOMContentLoaded', init);
})();
