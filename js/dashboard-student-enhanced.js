/**
 * dashboard-student-enhanced.js
 * Phase 4.2 Enhancement: Subject cards now clickable to show modules
 */

// ============================================================================
// PROTECTION & INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', async () => {
    // Enforce authentication
    if (!window.auth.isAuthenticated()) {
        window.location.href = '/html/login.html';
        return;
    }

    // Enforce enrollment
    const isEnrolled = localStorage.getItem('is_enrolled') === 'true';
    if (!isEnrolled) {
        window.location.href = '/html/onboarding.html';
        return;
    }

    // Initialize dashboard
    await loadDashboard();
    
    // Initialize UI handlers
    initializeSidebar();
});

// ============================================================================
// MAIN DASHBOARD LOADER
// ============================================================================

async function loadDashboard() {
    try {
        // Fetch curriculum data from backend
        const result = await window.auth.getUserCurriculum();
        
        if (!result.success) {
            console.error('Failed to load curriculum:', result.error);
            showError('Failed to load dashboard data. Please try refreshing the page.');
            return;
        }
        
        const dashboardData = result.data;
        
        // Render all dashboard components
        displayUserInfo(dashboardData);
        renderSubjectProgress(dashboardData.subjects || []);
        
    } catch (error) {
        console.error('Dashboard initialization error:', error);
        showError('An error occurred while loading the dashboard.');
    }
}

// ============================================================================
// USER INFO DISPLAY
// ============================================================================

function displayUserInfo(data) {
    // Display user name in welcome section
    const studentNameElement = document.getElementById('studentName');
    if (studentNameElement) {
        const firstName = window.auth.getUserFirstName();
        if (firstName) {
            studentNameElement.textContent = `, ${firstName}`;
        }
    }
    
    // Display course and semester badges
    const studentInfoDiv = document.querySelector('.student-info');
    if (studentInfoDiv) {
        const courseName = data.course || 'Not Enrolled';
        const semester = data.semester || 'N/A';
        const totalSemesters = data.totalSemesters || '?';
        
        studentInfoDiv.innerHTML = `
            <span class="badge">📚 ${courseName}</span>
            <span class="badge">Semester ${semester}/${totalSemesters}</span>
        `;
    }
}

// ============================================================================
// SUBJECT PROGRESS RENDERING (ENHANCED WITH MODULES)
// ============================================================================

function renderSubjectProgress(subjects) {
    const container = document.querySelector('.subject-progress');
    
    if (!container) {
        console.error('Subject progress container not found');
        return;
    }
    
    // Clear existing content
    container.innerHTML = '';
    
    if (!subjects || subjects.length === 0) {
        container.innerHTML = `
            <div style="text-align: center; padding: 30px; color: #64748b;">
                <p style="font-size: 16px; margin-bottom: 8px;">📚 No subjects available</p>
                <p style="font-size: 14px;">Subjects will appear here once you're enrolled in a course and semester.</p>
            </div>
        `;
        return;
    }
    
    // Group subjects by semester for better organization
    const subjectsBySemester = {};
    subjects.forEach(subject => {
        const sem = subject.semester || 'Unknown';
        if (!subjectsBySemester[sem]) {
            subjectsBySemester[sem] = [];
        }
        subjectsBySemester[sem].push(subject);
    });
    
    // Render subjects grouped by semester (descending order - most recent first)
    const semesters = Object.keys(subjectsBySemester).sort((a, b) => b - a);
    
    semesters.forEach(semester => {
        // Add semester header
        const semesterHeader = document.createElement('div');
        semesterHeader.style.cssText = `
            font-size: 13px;
            font-weight: 600;
            color: #475569;
            margin: 20px 0 12px 0;
            padding-bottom: 8px;
            border-bottom: 1px solid #e2e8f0;
        `;
        semesterHeader.textContent = `Semester ${semester}`;
        container.appendChild(semesterHeader);
        
        // Render subjects for this semester
        subjectsBySemester[semester].forEach(subject => {
            const subjectElement = createSubjectElement(subject);
            container.appendChild(subjectElement);
        });
    });
}

function createSubjectElement(subject) {
    const subjectDiv = document.createElement('div');
    subjectDiv.className = 'subject-item clickable';
    
    const percentage = subject.completion_percentage || 0;
    const isLocked = subject.is_locked || false;
    const status = subject.status || 'active';
    
    // Status badge
    let statusBadge = '';
    if (status === 'archived') {
        statusBadge = '<span style="font-size: 11px; background: #e2e8f0; color: #475569; padding: 2px 8px; border-radius: 4px; margin-left: 8px;">Archive</span>';
    } else if (status === 'active') {
        statusBadge = '<span style="font-size: 11px; background: #dbeafe; color: #1e40af; padding: 2px 8px; border-radius: 4px; margin-left: 8px;">Current</span>';
    }
    
    subjectDiv.innerHTML = `
        <div class="subject-header">
            <span class="subject-name">
                ${isLocked ? '🔒 ' : ''}${subject.name || subject.title || 'Unknown Subject'}
                ${statusBadge}
            </span>
            <span class="subject-percentage">${percentage}%</span>
        </div>
        <div class="progress-bar">
            <div class="progress-fill" style="width: ${percentage}%"></div>
        </div>
        ${subject.modules && subject.modules.length > 0 ? renderModuleButtons(subject.modules) : ''}
    `;
    
    // Add click handler to expand/show modules
    subjectDiv.addEventListener('click', (e) => {
        // Don't trigger if clicking on a module button
        if (!e.target.closest('.module-btn')) {
            toggleSubjectModules(subjectDiv);
        }
    });
    
    return subjectDiv;
}

/**
 * Render module buttons for a subject
 */
function renderModuleButtons(modules) {
    if (!modules || modules.length === 0) return '';
    
    const moduleButtonsHTML = modules.map(module => {
        const icon = {
            'learn': '📖',
            'cases': '⚖️',
            'practice': '✏️',
            'notes': '📝'
        }[module.module_type] || '📚';
        
        const lockIcon = module.is_locked ? '🔒 ' : '';
        
        return `
            <button 
                class="module-btn ${module.is_locked ? 'locked' : ''}" 
                onclick="navigateToModule(event, ${module.id}, ${module.is_locked})"
                ${module.is_locked ? 'disabled' : ''}>
                ${icon} ${lockIcon}${module.title}
            </button>
        `;
    }).join('');
    
    return `
        <div class="module-buttons" style="display: none; margin-top: 12px; padding-top: 12px; border-top: 1px solid #e2e8f0;">
            ${moduleButtonsHTML}
        </div>
    `;
}

/**
 * Toggle showing/hiding modules for a subject
 */
function toggleSubjectModules(subjectDiv) {
    const moduleButtons = subjectDiv.querySelector('.module-buttons');
    if (!moduleButtons) return;
    
    const isVisible = moduleButtons.style.display !== 'none';
    moduleButtons.style.display = isVisible ? 'none' : 'flex';
    
    // Add/remove expanded class
    if (isVisible) {
        subjectDiv.classList.remove('expanded');
    } else {
        subjectDiv.classList.add('expanded');
    }
}

/**
 * Navigate to module content page
 */
function navigateToModule(event, moduleId, isLocked) {
    event.stopPropagation();
    
    if (isLocked) {
        alert('This module is locked. Upgrade to premium or progress further to unlock.');
        return;
    }
    
    // Navigate to module content page
    window.location.href = `/html/module-content.html?moduleId=${moduleId}`;
}

// Make function globally available
window.navigateToModule = navigateToModule;

// ============================================================================
// STATUS BADGE HELPER
// ============================================================================

function getStatusBadge(status) {
    const badges = {
        'not_started': { text: 'Not Started', color: '#94a3b8' },
        'in_progress': { text: 'In Progress', color: '#3b82f6' },
        'completed': { text: 'Completed', color: '#10b981' }
    };
    
    return badges[status] || badges['not_started'];
}

// ============================================================================
// NAVIGATION HOOKS
// ============================================================================

function startStudying() {
    console.log('[Phase 4.2] Start Studying clicked - showing first available subject');
    alert('Click on any subject card below to view its modules and content!');
}

function openCaseSimplifier() {
    console.log('[Phase 4] Case Simplifier clicked');
    alert('Case Simplifier feature coming soon');
}

function practiceAnswers() {
    console.log('[Phase 4] Answer Practice clicked');
    alert('Answer Writing Practice coming soon');
}

function openNotes() {
    console.log('[Phase 4] My Notes clicked');
    alert('My Notes feature coming soon');
}

function askAI() {
    const query = document.getElementById('aiQuery')?.value;
    console.log('[Phase 4] AI Query:', query);
    alert('AI Study Assistant coming soon');
}

function setQuery(element) {
    const query = element.textContent.trim();
    const input = document.getElementById('aiQuery');
    if (input) {
        input.value = query;
    }
}

function toggleCheck(element) {
    element.classList.toggle('completed');
    const checkbox = element.querySelector('.checkbox');
    if (checkbox) {
        checkbox.classList.toggle('checked');
    }
}

function openItem(itemId) {
    console.log('[Phase 4] Open item:', itemId);
    alert('Item viewing coming in Phase 4');
}

// ============================================================================
// SIDEBAR (MOBILE)
// ============================================================================

function initializeSidebar() {
    const hamburgerBtn = document.getElementById('hamburgerBtn');
    const sidebar = document.getElementById('sidebar');
    const sidebarOverlay = document.getElementById('sidebarOverlay');
    const mainWrapper = document.getElementById('mainWrapper');
    
    if (hamburgerBtn && sidebar && sidebarOverlay) {
        hamburgerBtn.addEventListener('click', () => {
            sidebar.classList.toggle('active');
            sidebarOverlay.classList.toggle('active');
            mainWrapper.classList.toggle('sidebar-open');
        });
        
        sidebarOverlay.addEventListener('click', () => {
            sidebar.classList.remove('active');
            sidebarOverlay.classList.remove('active');
            mainWrapper.classList.remove('sidebar-open');
        });
    }
}

// ============================================================================
// ERROR HANDLING
// ============================================================================

function showError(message) {
    const container = document.querySelector('.container');
    if (container) {
        const errorDiv = document.createElement('div');
        errorDiv.style.cssText = `
            background-color: #fee2e2;
            border: 1px solid #fecaca;
            color: #991b1b;
            padding: 16px;
            border-radius: 8px;
            margin: 20px 0;
            text-align: center;
        `;
        errorDiv.textContent = message;
        container.insertBefore(errorDiv, container.firstChild);
    }
}

// ============================================================================
// GLOBAL EXPORTS
// ============================================================================

window.dashboardStudent = {
    loadDashboard,
    startStudying,
    openCaseSimplifier,
    practiceAnswers,
    openNotes,
    askAI,
    setQuery,
    toggleCheck,
    openItem,
    navigateToModule
};