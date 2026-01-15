/**
 * module-content.js
 * Phase 4.2: Module Content Display
 * Fetches and renders content items from backend
 */

// ============================================================================
// MODULE CONTENT FETCHING
// ============================================================================

/**
 * Fetch content for a specific module
 * @param {number} moduleId - Module ID to fetch
 * @returns {Promise<Object>} Module content data
 */
async function fetchModuleContent(moduleId) {
    try {
        const token = window.auth.getToken();
        if (!token) {
            throw new Error('Not authenticated');
        }

        const response = await fetch(`http://127.0.0.1:8000/api/modules/${moduleId}/content`, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            const errorData = await response.json();
            
            if (response.status === 403) {
                return {
                    success: false,
                    error: errorData.detail || 'Access denied',
                    locked: true
                };
            } else if (response.status === 404) {
                return {
                    success: false,
                    error: errorData.detail || 'Module not found',
                    notFound: true
                };
            }
            
            throw new Error(errorData.detail || 'Failed to fetch module content');
        }

        const data = await response.json();
        return {
            success: true,
            data: data
        };

    } catch (error) {
        console.error('Error fetching module content:', error);
        return {
            success: false,
            error: error.message || 'Network error'
        };
    }
}

// ============================================================================
// MODULE CONTENT RENDERING
// ============================================================================

/**
 * Render module content page
 * @param {number} moduleId - Module ID to display
 */
async function renderModuleContent(moduleId) {
    const container = document.getElementById('moduleContentContainer');
    if (!container) {
        console.error('Module content container not found');
        return;
    }

    // Show loading state
    container.innerHTML = `
        <div style="text-align: center; padding: 60px 20px;">
            <div style="font-size: 48px; margin-bottom: 16px;">📚</div>
            <p style="color: #64748b; font-size: 16px;">Loading module content...</p>
        </div>
    `;

    // Fetch content
    const result = await fetchModuleContent(moduleId);

    if (!result.success) {
        // Handle errors
        if (result.locked) {
            showLockedModule(container, result.error);
        } else if (result.notFound) {
            showNotFoundModule(container, result.error);
        } else {
            showErrorModule(container, result.error);
        }
        return;
    }

    const moduleData = result.data;

    // Render module header and content
    renderModuleHeader(container, moduleData);
    renderContentList(container, moduleData);
}

/**
 * Render module header with metadata
 */
function renderModuleHeader(container, moduleData) {
    const { module, subject, total_items, completed_items, completion_percentage } = moduleData;

    const headerHTML = `
        <div class="module-header">
            <button onclick="goBackToDashboard()" class="back-button">
                ← Back to Dashboard
            </button>
            
            <div class="module-info">
                <div class="subject-badge">${subject.code}</div>
                <h1 class="module-title">${module.title}</h1>
                <p class="subject-name">${subject.title}</p>
                ${module.description ? `<p class="module-description">${module.description}</p>` : ''}
            </div>

            <div class="module-progress-card">
                <div class="progress-stats">
                    <div class="progress-stat">
                        <span class="stat-value">${completed_items}/${total_items}</span>
                        <span class="stat-label">Completed</span>
                    </div>
                    <div class="progress-stat">
                        <span class="stat-value">${completion_percentage}%</span>
                        <span class="stat-label">Progress</span>
                    </div>
                </div>
                <div class="progress-bar-container">
                    <div class="progress-bar-fill" style="width: ${completion_percentage}%"></div>
                </div>
            </div>
        </div>
    `;

    const headerDiv = document.createElement('div');
    headerDiv.innerHTML = headerHTML;
    container.appendChild(headerDiv);
}

/**
 * Render content list based on module type
 */
function renderContentList(container, moduleData) {
    const { content, module } = moduleData;

    if (!content || content.length === 0) {
        const emptyHTML = `
            <div class="empty-state">
                <div style="font-size: 64px; margin-bottom: 16px;">📭</div>
                <h3>No Content Available</h3>
                <p>This module doesn't have any content yet. Check back later!</p>
            </div>
        `;
        const emptyDiv = document.createElement('div');
        emptyDiv.innerHTML = emptyHTML;
        container.appendChild(emptyDiv);
        return;
    }

    // Render content list
    const contentListDiv = document.createElement('div');
    contentListDiv.className = 'content-list';

    if (module.module_type === 'learn') {
        renderLearnContent(contentListDiv, content);
    } else if (module.module_type === 'cases') {
        renderCasesContent(contentListDiv, content);
    } else if (module.module_type === 'practice') {
        renderPracticeContent(contentListDiv, content);
    }

    container.appendChild(contentListDiv);
}

/**
 * Render LEARN content items
 */
function renderLearnContent(container, items) {
    items.forEach(item => {
        const itemCard = document.createElement('div');
        itemCard.className = `content-item ${item.is_completed ? 'completed' : ''}`;
        itemCard.onclick = () => openContentDetail('learn', item.id);

        itemCard.innerHTML = `
            <div class="content-icon">📖</div>
            <div class="content-details">
                <h3 class="content-title">${item.title}</h3>
                ${item.summary ? `<p class="content-summary">${item.summary}</p>` : ''}
                <div class="content-meta">
                    ${item.estimated_time_minutes ? 
                        `<span class="meta-item">⏱️ ${item.estimated_time_minutes} min</span>` : ''}
                    ${item.is_completed ? 
                        `<span class="meta-item completed-badge">✓ Completed</span>` : 
                        `<span class="meta-item">Not started</span>`}
                </div>
            </div>
            <div class="content-arrow">→</div>
        `;

        container.appendChild(itemCard);
    });
}

/**
 * Render CASES content items
 */
function renderCasesContent(container, items) {
    items.forEach(item => {
        const itemCard = document.createElement('div');
        itemCard.className = `content-item ${item.is_completed ? 'completed' : ''}`;
        itemCard.onclick = () => openContentDetail('case', item.id);

        const importanceColor = {
            'high': '#ef4444',
            'medium': '#f59e0b',
            'low': '#64748b'
        }[item.exam_importance] || '#64748b';

        itemCard.innerHTML = `
            <div class="content-icon">⚖️</div>
            <div class="content-details">
                <h3 class="content-title">${item.case_name}</h3>
                ${item.citation ? `<p class="content-summary">${item.citation} (${item.year})</p>` : ''}
                <div class="content-meta">
                    <span class="meta-item" style="color: ${importanceColor}; font-weight: 600;">
                        ${item.exam_importance.toUpperCase()} Importance
                    </span>
                    ${item.tags && item.tags.length > 0 ? 
                        `<span class="meta-item">🏷️ ${item.tags.slice(0, 3).join(', ')}</span>` : ''}
                    ${item.is_completed ? 
                        `<span class="meta-item completed-badge">✓ Completed</span>` : 
                        `<span class="meta-item">Not started</span>`}
                </div>
            </div>
            <div class="content-arrow">→</div>
        `;

        container.appendChild(itemCard);
    });
}

/**
 * Render PRACTICE content items
 */
function renderPracticeContent(container, items) {
    items.forEach((item, index) => {
        const itemCard = document.createElement('div');
        itemCard.className = `content-item ${item.is_completed ? 'completed' : ''}`;
        itemCard.onclick = () => openContentDetail('practice', item.id);

        const difficultyColor = {
            'easy': '#10b981',
            'medium': '#f59e0b',
            'hard': '#ef4444'
        }[item.difficulty] || '#64748b';

        const questionTypeLabel = {
            'mcq': 'Multiple Choice',
            'short_answer': 'Short Answer',
            'essay': 'Essay',
            'case_analysis': 'Case Analysis'
        }[item.question_type] || item.question_type;

        itemCard.innerHTML = `
            <div class="content-icon">✏️</div>
            <div class="content-details">
                <h3 class="content-title">Question ${index + 1}</h3>
                <p class="content-summary">${item.question.substring(0, 120)}${item.question.length > 120 ? '...' : ''}</p>
                <div class="content-meta">
                    <span class="meta-item">${questionTypeLabel}</span>
                    <span class="meta-item" style="color: ${difficultyColor}; font-weight: 600;">
                        ${item.difficulty.charAt(0).toUpperCase() + item.difficulty.slice(1)}
                    </span>
                    <span class="meta-item">${item.marks} marks</span>
                    ${item.is_completed ? 
                        `<span class="meta-item completed-badge">✓ Attempted</span>` : 
                        `<span class="meta-item">Not attempted</span>`}
                </div>
            </div>
            <div class="content-arrow">→</div>
        `;

        container.appendChild(itemCard);
    });
}

// ============================================================================
// ERROR STATE RENDERING
// ============================================================================

function showLockedModule(container, message) {
    container.innerHTML = `
        <div class="error-state locked">
            <div style="font-size: 64px; margin-bottom: 16px;">🔒</div>
            <h2>Module Locked</h2>
            <p>${message}</p>
            <button onclick="goBackToDashboard()" class="primary-button">
                Back to Dashboard
            </button>
        </div>
    `;
}

function showNotFoundModule(container, message) {
    container.innerHTML = `
        <div class="error-state">
            <div style="font-size: 64px; margin-bottom: 16px;">❌</div>
            <h2>Module Not Found</h2>
            <p>${message}</p>
            <button onclick="goBackToDashboard()" class="primary-button">
                Back to Dashboard
            </button>
        </div>
    `;
}

function showErrorModule(container, message) {
    container.innerHTML = `
        <div class="error-state">
            <div style="font-size: 64px; margin-bottom: 16px;">⚠️</div>
            <h2>Error Loading Content</h2>
            <p>${message}</p>
            <button onclick="location.reload()" class="primary-button">
                Try Again
            </button>
        </div>
    `;
}

// ============================================================================
// NAVIGATION HANDLERS
// ============================================================================

/**
 * Open content detail page (Phase 4.3)
 */
function openContentDetail(contentType, contentId) {
    console.log(`[Phase 4.3] Opening ${contentType} content: ${contentId}`);
    
    // Navigate to appropriate detail page
    if (contentType === 'learn') {
        window.location.href = `/html/learn-content.html?id=${contentId}`;
    } else if (contentType === 'case') {
        window.location.href = `/html/case-content.html?id=${contentId}`;
    } else if (contentType === 'practice') {
        window.location.href = `/html/practice-content.html?id=${contentId}`;
    } else {
        console.error('Unknown content type:', contentType);
        alert('Invalid content type');
    }
}

/**
 * Go back to dashboard
 */
function goBackToDashboard() {
    window.location.href = '/html/dashboard-student.html';
}

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Check if we're on the module content page
    const moduleContentContainer = document.getElementById('moduleContentContainer');
    if (moduleContentContainer) {
        // Get module ID from URL params
        const urlParams = new URLSearchParams(window.location.search);
        const moduleId = urlParams.get('moduleId');

        if (moduleId) {
            renderModuleContent(parseInt(moduleId));
        } else {
            showErrorModule(moduleContentContainer, 'No module ID provided');
        }
    }
});

// ============================================================================
// GLOBAL EXPORTS
// ============================================================================

window.moduleContent = {
    fetchModuleContent,
    renderModuleContent,
    openContentDetail,
    goBackToDashboard
};