/**
 * tutor-panel.js
 * Phase 10.6: Tutor UX Discipline
 * 
 * CORE PRINCIPLES:
 * - Learning content is PRIMARY
 * - Tutor interaction is SECONDARY and OPTIONAL
 * - Mentor aesthetic, NOT chatbot
 * - Always dismissible, never blocking
 * - No open-ended conversation loops
 * - No "ask me anything" prompts
 * 
 * INTERACTION MODEL:
 * - Contextual (linked to current content)
 * - Short-lived (not long chat threads)
 * - Action-specific (explain, clarify, feedback)
 */

const TUTOR_API_BASE = 'http://127.0.0.1:8000/api';

window.TutorPanel = (function() {
    'use strict';

    let modalOverlay = null;
    let isInitialized = false;

    function init() {
        if (isInitialized) return;
        createModalContainer();
        isInitialized = true;
    }

    function createModalContainer() {
        if (document.getElementById('explanation-modal-overlay')) return;

        const overlay = document.createElement('div');
        overlay.id = 'explanation-modal-overlay';
        overlay.className = 'explanation-modal-overlay';
        overlay.innerHTML = `
            <div class="explanation-modal" role="dialog" aria-modal="true" aria-labelledby="explanation-modal-title">
                <div class="explanation-modal-header">
                    <div class="explanation-modal-title" id="explanation-modal-title">
                        <div class="tutor-panel-icon">AI</div>
                        <span>Explanation</span>
                    </div>
                    <button class="explanation-modal-close" aria-label="Close explanation" onclick="TutorPanel.closeModal()">&times;</button>
                </div>
                <div class="explanation-modal-body">
                    <div id="explanation-content" class="explanation-content"></div>
                </div>
                <div class="explanation-modal-footer">
                    <span class="explanation-meta" id="explanation-meta"></span>
                    <div class="explanation-actions">
                        <button class="explanation-action-btn primary" onclick="TutorPanel.closeModal()">Got it</button>
                    </div>
                </div>
            </div>
        `;

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                closeModal();
            }
        });

        document.body.appendChild(overlay);
        modalOverlay = overlay;

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && modalOverlay.classList.contains('visible')) {
                closeModal();
            }
        });
    }

    function getToken() {
        return localStorage.getItem('access_token');
    }

    async function requestExplanation(options) {
        const {
            contentType,
            contentId,
            moduleId,
            subjectId,
            explanationType = 'simplified',
            buttonElement = null
        } = options;

        if (buttonElement) {
            buttonElement.classList.add('loading');
            buttonElement.disabled = true;
        }

        try {
            const token = getToken();
            if (!token) throw new Error('Not authenticated');

            const response = await fetch(`${TUTOR_API_BASE}/ai/explain`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    content_type: contentType,
                    content_id: contentId,
                    module_id: moduleId,
                    subject_id: subjectId,
                    explanation_type: explanationType
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to get explanation');
            }

            const data = await response.json();
            showExplanationModal(data.explanation, explanationType);

        } catch (error) {
            console.error('[TutorPanel] Explanation error:', error);
            showErrorMessage(error.message);
        } finally {
            if (buttonElement) {
                buttonElement.classList.remove('loading');
                buttonElement.disabled = false;
            }
        }
    }

    function showExplanationModal(content, explanationType) {
        init();

        const contentEl = document.getElementById('explanation-content');
        const metaEl = document.getElementById('explanation-meta');
        const titleEl = modalOverlay.querySelector('.explanation-modal-title span');

        const typeLabels = {
            'simplified': 'Simplified Explanation',
            'detailed': 'Detailed Explanation',
            'exam_focused': 'Exam-Focused Explanation',
            'example_heavy': 'Explanation with Examples'
        };

        titleEl.textContent = typeLabels[explanationType] || 'Explanation';
        contentEl.innerHTML = formatMarkdown(content);
        metaEl.textContent = 'AI-generated explanation based on your syllabus';

        modalOverlay.classList.add('visible');
        document.body.style.overflow = 'hidden';

        const closeBtn = modalOverlay.querySelector('.explanation-modal-close');
        closeBtn.focus();
    }

    function closeModal() {
        if (modalOverlay) {
            modalOverlay.classList.remove('visible');
            document.body.style.overflow = '';
        }
    }

    function createExplainButton(options) {
        const {
            contentType,
            contentId,
            moduleId,
            subjectId,
            text = 'Explain',
            explanationType = 'simplified'
        } = options;

        const btn = document.createElement('button');
        btn.className = 'explain-btn';
        btn.innerHTML = `<span class="explain-btn-icon">💡</span> ${text}`;
        btn.setAttribute('aria-label', `Get AI explanation for this content`);

        btn.addEventListener('click', () => {
            requestExplanation({
                contentType,
                contentId,
                moduleId,
                subjectId,
                explanationType,
                buttonElement: btn
            });
        });

        return btn;
    }

    function createHintCard(message, onDismiss) {
        const card = document.createElement('div');
        card.className = 'hint-card';
        card.setAttribute('role', 'alert');
        card.innerHTML = `
            <div class="hint-card-icon">💡</div>
            <div class="hint-card-content">${escapeHtml(message)}</div>
            <button class="hint-card-dismiss" aria-label="Dismiss hint">&times;</button>
        `;

        const dismissBtn = card.querySelector('.hint-card-dismiss');
        dismissBtn.addEventListener('click', () => {
            card.remove();
            if (onDismiss) onDismiss();
        });

        return card;
    }

    function createMemoryNote(message, onDismiss) {
        const note = document.createElement('div');
        note.className = 'memory-note';
        note.setAttribute('role', 'note');
        note.innerHTML = `
            <span class="memory-note-icon">📝</span>
            <span class="memory-note-text">${escapeHtml(message)}</span>
            <button class="memory-note-dismiss" aria-label="Dismiss">&times;</button>
        `;

        const dismissBtn = note.querySelector('.memory-note-dismiss');
        dismissBtn.addEventListener('click', () => {
            note.remove();
            if (onDismiss) onDismiss();
        });

        return note;
    }

    function createFeedbackPanel(options) {
        const {
            isCorrect,
            explanation = '',
            correctAnswer = '',
            onExpand = null
        } = options;

        const panel = document.createElement('div');
        panel.className = `feedback-panel ${isCorrect ? 'correct' : 'incorrect'}`;

        panel.innerHTML = `
            <div class="feedback-panel-header">
                <div class="feedback-result ${isCorrect ? 'correct' : 'incorrect'}">
                    <span class="feedback-result-icon">${isCorrect ? '✓' : '✗'}</span>
                    <span>${isCorrect ? 'Correct!' : 'Incorrect'}</span>
                </div>
                <div class="feedback-panel-actions">
                    ${explanation ? `
                        <button class="feedback-expand-btn" aria-expanded="false">
                            <span>View explanation</span>
                            <span>▼</span>
                        </button>
                    ` : ''}
                </div>
            </div>
            ${explanation ? `
                <div class="feedback-panel-body">
                    <div class="feedback-explanation">
                        ${!isCorrect && correctAnswer ? `<p><strong>Correct answer:</strong> ${escapeHtml(correctAnswer)}</p>` : ''}
                        ${formatMarkdown(explanation)}
                    </div>
                </div>
            ` : ''}
        `;

        const expandBtn = panel.querySelector('.feedback-expand-btn');
        if (expandBtn) {
            expandBtn.addEventListener('click', () => {
                const isExpanded = panel.classList.toggle('expanded');
                expandBtn.setAttribute('aria-expanded', isExpanded);
                expandBtn.querySelector('span:last-child').textContent = isExpanded ? '▲' : '▼';
                expandBtn.querySelector('span:first-child').textContent = isExpanded ? 'Hide explanation' : 'View explanation';
                if (onExpand && isExpanded) onExpand();
            });
        }

        return panel;
    }

    function createTutorPanel(options) {
        const {
            title = 'AI Tutor',
            content = '',
            collapsed = true,
            onToggle = null
        } = options;

        const panel = document.createElement('div');
        panel.className = `tutor-panel ${collapsed ? 'collapsed' : ''}`;

        panel.innerHTML = `
            <div class="tutor-panel-header" role="button" aria-expanded="${!collapsed}" tabindex="0">
                <div class="tutor-panel-title">
                    <div class="tutor-panel-icon">AI</div>
                    <span>${escapeHtml(title)}</span>
                </div>
                <div class="tutor-panel-toggle">▼</div>
            </div>
            <div class="tutor-panel-body">
                ${content}
            </div>
        `;

        const header = panel.querySelector('.tutor-panel-header');
        header.addEventListener('click', () => {
            const isCollapsed = panel.classList.toggle('collapsed');
            header.setAttribute('aria-expanded', !isCollapsed);
            if (onToggle) onToggle(!isCollapsed);
        });

        header.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                header.click();
            }
        });

        return panel;
    }

    function createLoadingIndicator() {
        const loading = document.createElement('div');
        loading.className = 'tutor-loading';
        loading.innerHTML = `
            <div class="tutor-loading-spinner"></div>
            <span>Getting explanation...</span>
        `;
        return loading;
    }

    async function getAdaptiveHint(subjectId, moduleId, questionText) {
        try {
            const token = getToken();
            if (!token) return null;

            const response = await fetch(`${TUTOR_API_BASE}/adaptive/hint`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    subject_id: subjectId,
                    module_id: moduleId,
                    question_text: questionText
                })
            });

            if (!response.ok) return null;

            const data = await response.json();
            return data.hint_available ? data.message : null;

        } catch (error) {
            console.error('[TutorPanel] Hint error:', error);
            return null;
        }
    }

    async function getMemoryContext(subjectId) {
        try {
            const token = getToken();
            if (!token) return null;

            const response = await fetch(`${TUTOR_API_BASE}/memory/${subjectId}/context`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });

            if (!response.ok) return null;

            return await response.json();

        } catch (error) {
            console.error('[TutorPanel] Memory error:', error);
            return null;
        }
    }

    function formatMarkdown(text) {
        if (!text) return '';

        let html = text
            .replace(/^### (.*$)/gm, '<h3>$1</h3>')
            .replace(/^## (.*$)/gm, '<h3>$1</h3>')
            .replace(/^# (.*$)/gm, '<h3>$1</h3>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/^> (.*$)/gm, '<blockquote>$1</blockquote>')
            .replace(/^\* (.*$)/gm, '<li>$1</li>')
            .replace(/^- (.*$)/gm, '<li>$1</li>')
            .replace(/^\d+\. (.*$)/gm, '<li>$1</li>');

        html = html.replace(/(<li>.*<\/li>\n?)+/g, (match) => `<ul>${match}</ul>`);
        html = html.replace(/\n\n/g, '</p><p>');
        html = html.replace(/\n/g, '<br>');

        if (!html.startsWith('<')) {
            html = '<p>' + html + '</p>';
        }

        return html;
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function showErrorMessage(message) {
        init();

        const contentEl = document.getElementById('explanation-content');
        const metaEl = document.getElementById('explanation-meta');
        const titleEl = modalOverlay.querySelector('.explanation-modal-title span');

        titleEl.textContent = 'Unable to Load';
        contentEl.innerHTML = `<p>${escapeHtml(message)}</p><p>Please try again later.</p>`;
        metaEl.textContent = '';

        modalOverlay.classList.add('visible');
        document.body.style.overflow = 'hidden';
    }

    return {
        init,
        requestExplanation,
        showExplanationModal,
        closeModal,
        createExplainButton,
        createHintCard,
        createMemoryNote,
        createFeedbackPanel,
        createTutorPanel,
        createLoadingIndicator,
        getAdaptiveHint,
        getMemoryContext,
        formatMarkdown,
        escapeHtml
    };

})();

document.addEventListener('DOMContentLoaded', () => {
    if (document.querySelector('[data-tutor-enabled]')) {
        TutorPanel.init();
    }
});
