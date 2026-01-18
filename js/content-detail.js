/**
 * content-detail.js
 * Phase 4.3: Content Detail Display and Progress Tracking
 * Handles Learn, Case, and Practice content detail pages
 */

const API_BASE_URL = 'http://127.0.0.1:8000';

// ============================================================================
// API CALLS
// ============================================================================

/**
 * Fetch learn content details
 */
async function fetchLearnContent(contentId) {
    try {
        const token = window.auth.getToken();
        if (!token) throw new Error('Not authenticated');

        const response = await fetch(`${API_BASE_URL}/api/content/learn/${contentId}`, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to fetch content');
        }

        return await response.json();
    } catch (error) {
        console.error('Error fetching learn content:', error);
        throw error;
    }
}

/**
 * Fetch case content details
 */
async function fetchCaseContent(contentId) {
    try {
        const token = window.auth.getToken();
        if (!token) throw new Error('Not authenticated');

        const response = await fetch(`${API_BASE_URL}/api/content/case/${contentId}`, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to fetch content');
        }

        return await response.json();
    } catch (error) {
        console.error('Error fetching case content:', error);
        throw error;
    }
}

/**
 * Fetch practice content details
 */
async function fetchPracticeContent(contentId) {
    try {
        const token = window.auth.getToken();
        if (!token) throw new Error('Not authenticated');

        const response = await fetch(`${API_BASE_URL}/api/content/practice/${contentId}`, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to fetch content');
        }

        return await response.json();
    } catch (error) {
        console.error('Error fetching practice content:', error);
        throw error;
    }
}

/**
 * Mark content as complete
 */
async function markContentComplete(contentType, contentId, timeSpent = null) {
    try {
        const token = window.auth.getToken();
        if (!token) throw new Error('Not authenticated');

        const body = timeSpent ? { time_spent_seconds: timeSpent } : {};

        const response = await fetch(
            `${API_BASE_URL}/api/content/${contentType}/${contentId}/complete`,
            {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(body)
            }
        );

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to mark complete');
        }

        return await response.json();
    } catch (error) {
        console.error('Error marking content complete:', error);
        throw error;
    }
}

// ============================================================================
// LEARN CONTENT RENDERING
// ============================================================================

async function loadLearnContent(contentId) {
    const container = document.getElementById('contentContainer');
    if (!container) return;

    try {
        const data = await fetchLearnContent(contentId);
        renderLearnContent(container, data);
    } catch (error) {
        showError(container, error.message);
    }
}

function renderLearnContent(container, data) {
    const { content, progress, module, subject } = data;

    container.innerHTML = `
        <div class="content-header">
            <button onclick="goBackToModule(${module.id})" class="back-button">
                ← Back to Module
            </button>
            
            <div class="breadcrumb">
                <span>${subject.code}</span>
                <span class="separator">›</span>
                <span>${module.title}</span>
            </div>
            
            <div class="content-title-section">
                <div class="content-icon-large">📖</div>
                <div>
                    <h1 class="content-title">${content.title}</h1>
                    ${content.summary ? `<p class="content-subtitle">${content.summary}</p>` : ''}
                    <div class="content-metadata">
                        ${content.estimated_time_minutes ? 
                            `<span class="meta-badge">⏱️ ${content.estimated_time_minutes} min read</span>` : ''}
                        ${progress.is_completed ? 
                            `<span class="meta-badge completed">✓ Completed</span>` : 
                            `<span class="meta-badge">In Progress</span>`}
                        ${progress.view_count > 1 ? 
                            `<span class="meta-badge">👁️ Viewed ${progress.view_count} times</span>` : ''}
                    </div>
                </div>
            </div>
        </div>

        <div class="content-body">
            <div class="tutor-actions-bar" id="tutorActionsBar"></div>
            <div class="content-text markdown-content">
                ${formatMarkdown(content.body)}
            </div>
        </div>

        <div class="content-actions">
            ${!progress.is_completed ? `
                <button onclick="handleMarkComplete('learn', ${content.id})" class="complete-button">
                    ✓ Mark as Complete
                </button>
            ` : `
                <button class="complete-button completed-state" disabled>
                    ✓ Completed
                </button>
            `}
            <button onclick="goBackToModule(${module.id})" class="secondary-button">
                Back to Module
            </button>
        </div>
    `;

    addTutorExplainButtons('learn', content.id, module.id, subject.id);
}

// ============================================================================
// CASE CONTENT RENDERING
// ============================================================================

async function loadCaseContent(contentId) {
    const container = document.getElementById('contentContainer');
    if (!container) return;

    try {
        const data = await fetchCaseContent(contentId);
        renderCaseContent(container, data);
    } catch (error) {
        showError(container, error.message);
    }
}

function renderCaseContent(container, data) {
    const { content, progress, module, subject } = data;

    const importanceColors = {
        'high': '#ef4444',
        'medium': '#f59e0b',
        'low': '#64748b'
    };
    const importanceColor = importanceColors[content.exam_importance] || '#64748b';

    container.innerHTML = `
        <div class="content-header">
            <button onclick="goBackToModule(${module.id})" class="back-button">
                ← Back to Module
            </button>
            
            <div class="breadcrumb">
                <span>${subject.code}</span>
                <span class="separator">›</span>
                <span>${module.title}</span>
            </div>
            
            <div class="content-title-section">
                <div class="content-icon-large">⚖️</div>
                <div>
                    <h1 class="content-title">${content.case_name}</h1>
                    ${content.citation ? 
                        `<p class="content-subtitle">${content.citation} (${content.year})</p>` : 
                        `<p class="content-subtitle">${content.year}</p>`}
                    <div class="content-metadata">
                        ${content.court ? 
                            `<span class="meta-badge">🏛️ ${content.court}</span>` : ''}
                        <span class="meta-badge" style="color: ${importanceColor}; font-weight: 600;">
                            ${content.exam_importance.toUpperCase()} Importance
                        </span>
                        ${progress.is_completed ? 
                            `<span class="meta-badge completed">✓ Completed</span>` : 
                            `<span class="meta-badge">Not Reviewed</span>`}
                        ${content.tags && content.tags.length > 0 ? 
                            `<span class="meta-badge">🏷️ ${content.tags.join(', ')}</span>` : ''}
                    </div>
                </div>
            </div>
        </div>

        <div class="content-body">
            <div class="tutor-actions-bar" id="tutorActionsBar"></div>
            
            <div class="case-section">
                <h2 class="section-title">📋 Facts</h2>
                <div class="section-content">
                    ${formatMarkdown(content.facts)}
                </div>
            </div>

            <div class="case-section">
                <h2 class="section-title">❓ Issue</h2>
                <div class="section-content">
                    ${formatMarkdown(content.issue)}
                </div>
            </div>

            <div class="case-section">
                <h2 class="section-title">⚖️ Judgment</h2>
                <div class="section-content">
                    ${formatMarkdown(content.judgment)}
                </div>
            </div>

            <div class="case-section highlight">
                <h2 class="section-title">⭐ Ratio Decidendi</h2>
                <div class="section-content">
                    ${formatMarkdown(content.ratio)}
                </div>
            </div>
        </div>

        <div class="content-actions">
            ${!progress.is_completed ? `
                <button onclick="handleMarkComplete('case', ${content.id})" class="complete-button">
                    ✓ Mark as Reviewed
                </button>
            ` : `
                <button class="complete-button completed-state" disabled>
                    ✓ Reviewed
                </button>
            `}
            <button onclick="goBackToModule(${module.id})" class="secondary-button">
                Back to Module
            </button>
        </div>
    `;

    addTutorExplainButtons('case', content.id, module.id, subject.id);
}

// ============================================================================
// PRACTICE CONTENT RENDERING
// ============================================================================

async function loadPracticeContent(contentId) {
    const container = document.getElementById('contentContainer');
    if (!container) return;

    try {
        const data = await fetchPracticeContent(contentId);
        renderPracticeContent(container, data);
    } catch (error) {
        showError(container, error.message);
    }
}

function renderPracticeContent(container, data) {
    const { content, progress, module, subject } = data;

    const difficultyColors = {
        'easy': '#10b981',
        'medium': '#f59e0b',
        'hard': '#ef4444'
    };
    const difficultyColor = difficultyColors[content.difficulty] || '#64748b';

    const questionTypeLabels = {
        'mcq': 'Multiple Choice Question',
        'short_answer': 'Short Answer',
        'essay': 'Essay Question',
        'case_analysis': 'Case Analysis'
    };

    container.innerHTML = `
        <div class="content-header">
            <button onclick="goBackToModule(${module.id})" class="back-button">
                ← Back to Module
            </button>
            
            <div class="breadcrumb">
                <span>${subject.code}</span>
                <span class="separator">›</span>
                <span>${module.title}</span>
            </div>
            
            <div class="content-title-section">
                <div class="content-icon-large">✏️</div>
                <div>
                    <h1 class="content-title">Practice Question</h1>
                    <div class="content-metadata">
                        <span class="meta-badge">${questionTypeLabels[content.question_type] || content.question_type}</span>
                        <span class="meta-badge" style="color: ${difficultyColor}; font-weight: 600;">
                            ${content.difficulty.charAt(0).toUpperCase() + content.difficulty.slice(1)}
                        </span>
                        <span class="meta-badge">📊 ${content.marks} marks</span>
                        ${progress.is_completed ? 
                            `<span class="meta-badge completed">✓ Attempted</span>` : 
                            `<span class="meta-badge">Not Attempted</span>`}
                    </div>
                </div>
            </div>
        </div>

        <div class="content-body">
            <div class="question-section">
                <h2 class="section-title">Question</h2>
                <div class="question-text">
                    ${formatMarkdown(content.question)}
                </div>
            </div>

            ${content.question_type === 'mcq' ? renderMCQOptions(content) : renderAnswerArea()}

            ${content.tags && content.tags.length > 0 ? `
                <div class="tags-section">
                    <strong>Topics:</strong>
                    ${content.tags.map(tag => `<span class="tag">${tag}</span>`).join('')}
                </div>
            ` : ''}
        </div>

        <div class="content-actions">
            ${!progress.is_completed ? `
                <button onclick="handleMarkComplete('practice', ${content.id})" class="complete-button">
                    ✓ Mark as Attempted
                </button>
            ` : `
                <button class="complete-button completed-state" disabled>
                    ✓ Attempted
                </button>
            `}
            <button onclick="goBackToModule(${module.id})" class="secondary-button">
                Back to Module
            </button>
        </div>

        <div class="practice-note">
            <p><strong>Note:</strong> Answer submission and grading will be available in Phase 8.</p>
        </div>
    `;
}

function renderMCQOptions(content) {
    return `
        <div class="mcq-options">
            <div class="mcq-option">
                <span class="option-label">A.</span>
                <span class="option-text">${content.option_a}</span>
            </div>
            <div class="mcq-option">
                <span class="option-label">B.</span>
                <span class="option-text">${content.option_b}</span>
            </div>
            <div class="mcq-option">
                <span class="option-label">C.</span>
                <span class="option-text">${content.option_c}</span>
            </div>
            <div class="mcq-option">
                <span class="option-label">D.</span>
                <span class="option-text">${content.option_d}</span>
            </div>
        </div>
    `;
}

function renderAnswerArea() {
    return `
        <div class="answer-area">
            <h3>Your Answer</h3>
            <textarea class="answer-textarea" placeholder="Write your answer here..." rows="10" disabled></textarea>
            <p class="answer-note">Answer submission will be enabled in Phase 8</p>
        </div>
    `;
}

// ============================================================================
// COMPLETION HANDLER
// ============================================================================

async function handleMarkComplete(contentType, contentId) {
    const button = event.target;
    const originalText = button.textContent;
    
    try {
        button.disabled = true;
        button.textContent = 'Marking...';

        await markContentComplete(contentType, contentId);

        // Update UI
        button.textContent = '✓ Completed';
        button.classList.add('completed-state');

        // Show success message
        showSuccessMessage('Content marked as complete!');

        // Refresh after 1 second to show updated progress
        setTimeout(() => {
            location.reload();
        }, 1000);

    } catch (error) {
        button.disabled = false;
        button.textContent = originalText;
        alert(`Failed to mark as complete: ${error.message}`);
    }
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

function formatMarkdown(text) {
    if (!text) return '';
    
    // Simple markdown formatting (can be enhanced with markdown library)
    return text
        .replace(/\n\n/g, '</p><p>')
        .replace(/\n/g, '<br>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .split('</p><p>').map(p => `<p>${p}</p>`).join('');
}

function showError(container, message) {
    container.innerHTML = `
        <div class="error-state">
            <div class="error-icon">⚠️</div>
            <h2>Error Loading Content</h2>
            <p>${message}</p>
            <button onclick="history.back()" class="secondary-button">
                Go Back
            </button>
        </div>
    `;
}

function showSuccessMessage(message) {
    const toast = document.createElement('div');
    toast.className = 'success-toast';
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 3000);
}

function goBackToModule(moduleId) {
    window.location.href = `/html/module-content.html?moduleId=${moduleId}`;
}

// ============================================================================
// TUTOR PANEL INTEGRATION (Phase 10.6)
// Optional, contextual, non-blocking
// ============================================================================

function addTutorExplainButtons(contentType, contentId, moduleId, subjectId) {
    const actionsBar = document.getElementById('tutorActionsBar');
    if (!actionsBar || !window.TutorPanel) return;

    actionsBar.style.cssText = 'display: flex; gap: 0.5rem; margin-bottom: 1rem; flex-wrap: wrap;';

    const simplifiedBtn = TutorPanel.createExplainButton({
        contentType,
        contentId,
        moduleId,
        subjectId,
        text: 'Explain Simply',
        explanationType: 'simplified'
    });

    const examBtn = TutorPanel.createExplainButton({
        contentType,
        contentId,
        moduleId,
        subjectId,
        text: 'Exam Focus',
        explanationType: 'exam_focused'
    });

    actionsBar.appendChild(simplifiedBtn);
    actionsBar.appendChild(examBtn);
}

// ============================================================================
// GLOBAL EXPORTS
// ============================================================================

window.contentDetail = {
    loadLearnContent,
    loadCaseContent,
    loadPracticeContent,
    handleMarkComplete,
    goBackToModule,
    addTutorExplainButtons
};