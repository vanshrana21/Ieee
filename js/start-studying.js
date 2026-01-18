(function() {
    'use strict';

    const API_BASE = window.__API_BASE__ || 'http://127.0.0.1:8000';

    const state = {
        subjects: [],
        archiveSubjects: [],
        currentSubject: null,
        currentMode: '',
        isLoading: true,
        error: null,
        contentAvailability: {
            has_learning_content: false,
            has_cases: false,
            has_practice: false,
            has_notes: true,
            first_learning_content_id: null,
            first_case_id: null,
            first_practice_id: null,
            learn_count: 0,
            cases_count: 0,
            practice_count: 0
        }
    };

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    async function fetchJson(url, opts = {}) {
        const token = window.auth?.getToken?.() || localStorage.getItem('access_token');
        
        if (!token) {
            if (window.JurisSessionManager) {
                window.JurisSessionManager.requireAuth();
            } else {
                window.location.href = 'login.html';
            }
            throw new Error('Not authenticated');
        }
        
        const headers = { ...opts.headers };
        headers['Authorization'] = `Bearer ${token}`;
        headers['Content-Type'] = headers['Content-Type'] || 'application/json';

        const resp = await fetch(url, { ...opts, headers });
        
        if (resp.status === 401) {
            if (window.JurisErrorHandler) {
                window.JurisErrorHandler.handleAuthError();
            } else {
                localStorage.removeItem('access_token');
                localStorage.removeItem('user_role');
                window.location.href = 'login.html';
            }
            throw new Error('Session expired. Please log in again.');
        }
        
        const text = await resp.text();
        let json;
        try { json = text ? JSON.parse(text) : null; } catch { json = null; }
        if (!resp.ok) throw new Error(json?.detail || json?.error || resp.statusText);
        return json;
    }

    function getCategoryIcon(category) {
        const icons = {
            'foundation': '📘',
            'core': '⚖️',
            'procedural': '📋',
            'elective': '🎯',
            'practical': '✍️'
        };
        return icons[(category || '').toLowerCase()] || '📚';
    }

    function showLoading() {
        const grid = document.querySelector('.subject-grid');
        if (grid) {
            grid.innerHTML = `
                <div style="grid-column: 1 / -1; text-align: center; padding: 4rem;">
                    <div style="width: 40px; height: 40px; border: 3px solid #E2E8F0; border-top-color: #0066FF; border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 16px;"></div>
                    <p style="color: #64748b; font-size: 15px;">Loading your subjects...</p>
                </div>
                <style>@keyframes spin { to { transform: rotate(360deg); } }</style>
            `;
        }
    }

    function showError(message) {
        const grid = document.querySelector('.subject-grid');
        if (grid) {
            grid.innerHTML = `
                <div style="grid-column: 1 / -1; text-align: center; padding: 4rem;">
                    <div style="font-size: 48px; margin-bottom: 16px;">⚠️</div>
                    <h3 style="color: #0F172A; margin-bottom: 8px;">Unable to Load Subjects</h3>
                    <p style="color: #64748b; margin-bottom: 20px; max-width: 400px; margin-left: auto; margin-right: auto;">${escapeHtml(message)}</p>
                    <button onclick="window.location.reload()" style="background: #0066FF; color: white; border: none; padding: 12px 24px; border-radius: 8px; cursor: pointer; font-weight: 600;">Try Again</button>
                </div>
            `;
        }
    }

    function showEmptyState() {
        const grid = document.querySelector('.subject-grid');
        if (grid) {
            grid.innerHTML = `
                <div style="grid-column: 1 / -1; text-align: center; padding: 4rem;">
                    <div style="font-size: 48px; margin-bottom: 16px;">📚</div>
                    <h3 style="color: #0F172A; margin-bottom: 8px;">No Subjects Available</h3>
                    <p style="color: #64748b; margin-bottom: 20px;">Your curriculum hasn't been set up yet. Please contact your administrator.</p>
                    <a href="dashboard-student.html" style="background: #0066FF; color: white; border: none; padding: 12px 24px; border-radius: 8px; cursor: pointer; font-weight: 600; text-decoration: none; display: inline-block;">Back to Dashboard</a>
                </div>
            `;
        }
    }

    function createSubjectCard(subject) {
        const progress = Math.round(subject.completion_percentage || 0);
        const icon = getCategoryIcon(subject.category);
        const moduleCount = (subject.modules || []).length;

        return `
            <div class="subject-card" data-subject-id="${subject.id}" onclick="window.studyApp.selectSubject(${subject.id})">
                <div class="subject-icon">${icon}</div>
                <h3>${escapeHtml(subject.title)}</h3>
                <p>${escapeHtml(subject.description || 'Explore this subject')}</p>
                <div class="card-footer">
                    <span class="topic-count">${moduleCount} Modules</span>
                    <span class="progress-badge">${progress}%</span>
                </div>
                ${subject.semester ? `<div class="semester-badge">Semester ${subject.semester}</div>` : ''}
                <div class="progress-bar-mini">
                    <div class="progress-fill" style="width: ${progress}%"></div>
                </div>
            </div>
        `;
    }

    function renderSubjects() {
        const grid = document.querySelector('.subject-grid');
        if (!grid) return;

        const allSubjects = [...state.subjects, ...state.archiveSubjects];

        if (allSubjects.length === 0) {
            showEmptyState();
            return;
        }

        const grouped = {};
        allSubjects.forEach(subject => {
            const sem = subject.semester || 'Other';
            if (!grouped[sem]) grouped[sem] = [];
            grouped[sem].push(subject);
        });

        const sortedSemesters = Object.keys(grouped).sort((a, b) => {
            if (a === 'Other') return 1;
            if (b === 'Other') return -1;
            return Number(a) - Number(b);
        });

        let html = '';

        sortedSemesters.forEach(semester => {
            const subjects = grouped[semester];
            const isCurrentSem = state.subjects.some(s => s.semester === Number(semester));

            html += `
                <div class="category-header">
                    <h2>Semester ${semester} ${isCurrentSem ? '<span class="current-badge">Current</span>' : ''}</h2>
                    <p>${subjects.length} subject${subjects.length !== 1 ? 's' : ''}</p>
                </div>
            `;

            subjects.forEach(subject => {
                html += createSubjectCard(subject);
            });
        });

        grid.innerHTML = html;
    }

    async function fetchContentAvailability(subjectId) {
        try {
            const data = await fetchJson(`${API_BASE}/api/student/subject/${subjectId}/availability`);
            state.contentAvailability = data;
            return data;
        } catch (err) {
            console.error('Failed to fetch content availability:', err);
            state.contentAvailability = {
                has_learning_content: false,
                has_cases: false,
                has_practice: false,
                has_notes: true,
                first_learning_content_id: null,
                first_case_id: null,
                first_practice_id: null,
                learn_count: 0,
                cases_count: 0,
                practice_count: 0
            };
            return state.contentAvailability;
        }
    }

    function updateStudyModeCards() {
        const modeCards = document.querySelectorAll('.mode-card');
        const modes = ['concepts', 'cases', 'practice', 'notes'];
        
        const modeMapping = {
            concepts: {
                available: state.contentAvailability.has_learning_content,
                count: state.contentAvailability.learn_count,
                enabledText: `${state.contentAvailability.learn_count} lessons available`,
                disabledText: 'Learning content is being prepared for this subject. Check back soon!'
            },
            cases: {
                available: state.contentAvailability.has_cases,
                count: state.contentAvailability.cases_count,
                enabledText: `${state.contentAvailability.cases_count} cases available`,
                disabledText: 'Case studies will be available once they are added to this subject.'
            },
            practice: {
                available: state.contentAvailability.has_practice,
                count: state.contentAvailability.practice_count,
                enabledText: `${state.contentAvailability.practice_count} questions available`,
                disabledText: 'Practice questions will unlock once they are added for this subject.'
            },
            notes: {
                available: true,
                count: state.contentAvailability.notes_count || 0,
                enabledText: 'Create and organize your personal study notes',
                disabledText: ''
            }
        };

        modeCards.forEach((card, index) => {
            const mode = modes[index];
            if (!mode) return;
            
            const config = modeMapping[mode];
            const isAvailable = config.available;
            
            card.classList.remove('mode-card-disabled', 'mode-card-enabled');
            const existingBadge = card.querySelector('.mode-availability-badge');
            if (existingBadge) existingBadge.remove();
            
            if (isAvailable) {
                card.classList.add('mode-card-enabled');
                card.onclick = () => window.studyApp.openMode(mode);
                card.style.cursor = 'pointer';
                
                const badge = document.createElement('div');
                badge.className = 'mode-availability-badge mode-available';
                badge.innerHTML = `
                    <span class="availability-icon">✓</span>
                    <span class="availability-text">${config.enabledText}</span>
                `;
                card.appendChild(badge);
            } else {
                card.classList.add('mode-card-disabled');
                card.onclick = null;
                card.style.cursor = 'not-allowed';
                
                const badge = document.createElement('div');
                badge.className = 'mode-availability-badge mode-unavailable';
                badge.innerHTML = `
                    <span class="availability-icon">🔒</span>
                    <span class="availability-text">${config.disabledText}</span>
                `;
                card.appendChild(badge);
            }
        });
        
        updateContentComingSoonSection();
    }
    
    function updateContentComingSoonSection() {
        const studyMapContainer = document.getElementById('studyMapContainer');
        if (!studyMapContainer) return;
        
        const hasAnyContent = state.contentAvailability.has_learning_content || 
                             state.contentAvailability.has_cases || 
                             state.contentAvailability.has_practice;
        
        if (!hasAnyContent) {
            studyMapContainer.innerHTML = `
                <div class="content-coming-soon">
                    <div class="coming-soon-icon">📝</div>
                    <h4>Content Coming Soon</h4>
                    <p>We're preparing learning materials for <strong>${escapeHtml(state.currentSubject?.title || 'this subject')}</strong>.</p>
                    <div class="coming-soon-suggestion">
                        <strong>What you can do now:</strong><br>
                        Use the <strong>My Notes</strong> feature to start creating your own study materials while you wait.
                    </div>
                </div>
            `;
        } else {
            let availableItems = [];
            if (state.contentAvailability.has_learning_content) {
                availableItems.push(`${state.contentAvailability.learn_count} learning lessons`);
            }
            if (state.contentAvailability.has_cases) {
                availableItems.push(`${state.contentAvailability.cases_count} case studies`);
            }
            if (state.contentAvailability.has_practice) {
                availableItems.push(`${state.contentAvailability.practice_count} practice questions`);
            }
            
            studyMapContainer.innerHTML = `
                <div class="content-available">
                    <div class="available-icon">✅</div>
                    <h4>Ready to Learn</h4>
                    <p>Select a study mode above to begin learning.</p>
                    <div class="available-summary">
                        <strong>Available:</strong> ${availableItems.join(' • ')}
                    </div>
                </div>
            `;
        }
    }

    async function selectSubject(subjectId) {
        const allSubjects = [...state.subjects, ...state.archiveSubjects];
        const subject = allSubjects.find(s => s.id === subjectId);

        if (!subject) {
            console.error('Subject not found:', subjectId);
            return;
        }

        state.currentSubject = subject;

        document.getElementById('subjectSelection').classList.add('hidden');

        const studyHub = document.getElementById('studyHub');
        studyHub.classList.remove('hidden');

        document.getElementById('currentSubject').textContent = subject.title;
        document.getElementById('subjectTitle').textContent = subject.title;

        document.getElementById('contentArea').classList.add('hidden');
        
        const studyMapContainer = document.getElementById('studyMapContainer');
        if (studyMapContainer) {
            studyMapContainer.innerHTML = `
                <div style="text-align: center; padding: 2rem;">
                    <div style="width: 32px; height: 32px; border: 3px solid #E2E8F0; border-top-color: #0066FF; border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 12px;"></div>
                    <p style="color: #64748b; font-size: 14px;">Checking available content...</p>
                </div>
            `;
        }
        
        await fetchContentAvailability(subjectId);
        updateStudyModeCards();
    }

    function backToSubjects() {
        document.getElementById('studyHub').classList.add('hidden');
        document.getElementById('subjectSelection').classList.remove('hidden');
        state.currentSubject = null;
        state.currentMode = '';
        state.contentAvailability = {
            has_learning_content: false,
            has_cases: false,
            has_practice: false,
            has_notes: true,
            first_learning_content_id: null,
            first_case_id: null,
            first_practice_id: null,
            learn_count: 0,
            cases_count: 0,
            practice_count: 0
        };
    }

    function goBackToDashboard() {
        window.location.href = 'dashboard-student.html';
    }

    function openMode(mode) {
        const subject = state.currentSubject;
        if (!subject) return;
        
        if (mode === 'concepts') {
            if (state.contentAvailability.has_learning_content && state.contentAvailability.first_learning_content_id) {
                window.location.href = `learn.html?content_id=${state.contentAvailability.first_learning_content_id}&subject_id=${subject.id}`;
            }
            return;
        }
        
        if (mode === 'cases') {
            if (state.contentAvailability.has_cases) {
                window.location.href = `cases.html?subject_id=${subject.id}`;
            }
            return;
        }
        
        if (mode === 'practice') {
            if (state.contentAvailability.has_practice) {
                window.location.href = `practice.html?subject_id=${subject.id}`;
            }
            return;
        }
        
        if (mode === 'notes') {
            window.location.href = `notes.html?subject_id=${subject.id}`;
            return;
        }
    }

    function backToModes() {
        document.getElementById('contentArea').classList.add('hidden');
        state.currentMode = '';
    }

    async function init() {
        if (window.JurisSessionManager && !window.JurisSessionManager.checkAuth()) {
            window.JurisSessionManager.requireAuth();
            return;
        }

        showLoading();

        const subjectSelection = document.getElementById('subjectSelection');
        if (subjectSelection) subjectSelection.classList.remove('hidden');

        const studyHub = document.getElementById('studyHub');
        if (studyHub) studyHub.classList.add('hidden');

        try {
            const data = await fetchJson(`${API_BASE}/api/curriculum/dashboard`);

            state.subjects = data.active_subjects || [];
            state.archiveSubjects = data.archive_subjects || [];
            state.isLoading = false;

            renderSubjects();

            const urlParams = new URLSearchParams(window.location.search);
            const subjectId = urlParams.get('subject');
            if (subjectId) {
                const validId = window.JurisNavigationGuard 
                    ? window.JurisNavigationGuard.validateId(subjectId)
                    : parseInt(subjectId, 10);
                    
                if (validId) {
                    selectSubject(validId);
                } else {
                    if (window.JurisErrorHandler) {
                        window.JurisErrorHandler.showToast('Invalid subject ID. Please select a subject.', 'warning');
                    }
                }
            }

        } catch (err) {
            console.error('Failed to load curriculum:', err);
            state.isLoading = false;
            state.error = err.message;

            const displayError = "We're having trouble loading study content. Please try again.";

            if (window.JurisErrorHandler) {
                window.JurisErrorHandler.showToast(displayError, 'error');
            }
            
            showError(displayError);
        }
    }

    window.studyApp = {
        selectSubject,
        backToSubjects,
        goBackToDashboard,
        openMode,
        backToModes,
        getContentAvailability: () => state.contentAvailability
    };

    window.selectSubject = selectSubject;
    window.backToSubjects = backToSubjects;
    window.goBackToDashboard = goBackToDashboard;
    window.openMode = openMode;
    window.backToModes = backToModes;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
