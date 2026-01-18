/**
 * learn-content.js
 * Phase 4: Learn Content Viewer with Progress Tracking
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

    function formatBody(text) {
        if (!text) return '';
        return text
            .replace(/\n\n/g, '</p><p>')
            .replace(/\n/g, '<br>')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.+?)\*/g, '<em>$1</em>');
    }

    async function loadContent() {
        const container = document.getElementById('contentContainer');
        if (!container) return;

        try {
            const data = await api.getContentDetail(state.contentId);
            state.content = data;
            state.isLoading = false;
            
            if (!state.moduleId) {
                state.moduleId = data.module_id;
            }
            
            renderContent(container);
        } catch (error) {
            console.error('Failed to load content:', error);
            container.innerHTML = `
                <div class="error-state">
                    <div style="font-size: 48px; margin-bottom: 16px;">⚠️</div>
                    <h3 style="margin: 0 0 8px 0; color: #0f172a;">Content Not Found</h3>
                    <p style="color: #64748b; margin: 0 0 20px 0;">This learning content does not exist or is unavailable.</p>
                    <a href="start-studying.html" class="btn btn-primary">Back to Study Hub</a>
                </div>
            `;
        }
    }

    function renderContent(container) {
        if (!state.content) return;

        const backUrl = state.moduleId 
            ? `modules.html?subject_id=${state.subjectId}`
            : 'start-studying.html';

        const backLink = document.getElementById('backLink');
        if (backLink) {
            backLink.href = backUrl;
            backLink.textContent = '← Back to Modules';
        }

        container.innerHTML = `
            <div class="content-card">
                <div class="content-header">
                    <h1 class="content-title">${escapeHtml(state.content.title)}</h1>
                    <div class="content-meta">
                        <span>Lesson ${state.content.sequence_order}</span>
                        ${state.content.is_completed ? '<span class="status-badge">Completed</span>' : ''}
                    </div>
                </div>

                <div class="content-body">
                    <p>${formatBody(state.content.body)}</p>
                </div>

                <div class="content-footer">
                    ${!state.content.is_completed ? `
                        <button id="completeBtn" class="btn btn-primary">
                            Mark as Completed
                        </button>
                    ` : `
                        <div class="completed-msg">
                            <span>✅</span> You have completed this lesson.
                        </div>
                    `}
                    <div class="navigation-actions">
                        <a href="${backUrl}" class="btn btn-secondary">
                            Back to Modules
                        </a>
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
        btn.textContent = 'Saving...';

        try {
            await api.markContentComplete(state.contentId);
            state.content.is_completed = true;
            renderContent(document.getElementById('contentContainer'));
        } catch (error) {
            console.error('Failed to mark complete:', error);
            btn.disabled = false;
            btn.textContent = 'Mark as Completed';
            alert('Failed to update progress. Please try again.');
        }
    }

    function init() {
        const urlParams = new URLSearchParams(window.location.search);
        state.contentId = urlParams.get('id');
        state.moduleId = urlParams.get('module_id');
        state.subjectId = urlParams.get('subject_id');

        if (!state.contentId) {
            window.location.href = 'start-studying.html';
            return;
        }

        loadContent();
    }

    document.addEventListener('DOMContentLoaded', init);
})();
