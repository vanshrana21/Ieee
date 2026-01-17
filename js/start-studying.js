(function() {
    'use strict';

    const API_BASE = window.__API_BASE__ || 'http://127.0.0.1:8000';

    const state = {
        subjects: [],
        archiveSubjects: [],
        currentSubject: null,
        currentMode: '',
        isLoading: true,
        error: null
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
            window.location.href = 'login.html';
            throw new Error('Not authenticated');
        }
        
        const headers = { ...opts.headers };
        headers['Authorization'] = `Bearer ${token}`;
        headers['Content-Type'] = headers['Content-Type'] || 'application/json';

        const resp = await fetch(url, { ...opts, headers });
        
        if (resp.status === 401) {
            localStorage.removeItem('access_token');
            localStorage.removeItem('user_role');
            window.location.href = 'login.html';
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

    function getCategoryColor(category) {
        const colors = {
            'foundation': 'blue',
            'core': 'purple',
            'procedural': 'green',
            'elective': 'orange',
            'practical': 'teal'
        };
        return colors[(category || '').toLowerCase()] || 'blue';
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
        const colorClass = getCategoryColor(subject.category);
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

    function selectSubject(subjectId) {
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
        
        loadStudyMap(subjectId);
    }
    
    async function loadStudyMap(subjectId) {
        const studyMapContainer = document.getElementById('studyMapContainer');
        if (!studyMapContainer) return;
        
        studyMapContainer.innerHTML = `
            <div style="text-align: center; padding: 2rem;">
                <div style="width: 32px; height: 32px; border: 3px solid #E2E8F0; border-top-color: #0066FF; border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 12px;"></div>
                <p style="color: #64748b; font-size: 14px;">Loading your personalized study map...</p>
            </div>
        `;
        
        try {
            const studyMapData = await fetchJson(`${API_BASE}/api/curriculum/subjects/${subjectId}/study-map`);
            renderStudyMap(studyMapContainer, studyMapData);
        } catch (err) {
            console.error('Failed to load study map:', err);
            studyMapContainer.innerHTML = `
                <div style="text-align: center; padding: 2rem;">
                    <div style="font-size: 32px; margin-bottom: 12px;">📋</div>
                    <p style="color: #64748b;">Unable to load study map. Continue with study modes above.</p>
                </div>
            `;
        }
    }
    
    function renderStudyMap(container, data) {
        if (!data.success) {
            container.innerHTML = `
                <div style="text-align: center; padding: 2rem;">
                    <p style="color: #ef4444;">${escapeHtml(data.error || 'Failed to load study map')}</p>
                </div>
            `;
            return;
        }
        
        const studyMap = data.study_map || [];
        
        if (studyMap.length === 0) {
            container.innerHTML = `
                <div class="study-map-empty">
                    <div style="font-size: 40px; margin-bottom: 12px;">🚀</div>
                    <h4>Getting Started</h4>
                    <p>${escapeHtml(data.message || 'Select a study mode above to begin learning this subject!')}</p>
                </div>
            `;
            return;
        }
        
        const html = `
            <div class="study-map-header">
                <h3>📍 Your Study Roadmap</h3>
                <p>Personalized modules ordered by priority</p>
            </div>
            <div class="study-map-modules">
                ${studyMap.map((module, index) => renderStudyMapModule(module, index)).join('')}
            </div>
        `;
        
        container.innerHTML = html;
    }
    
    function renderStudyMapModule(module, index) {
        const priorityColors = {
            'High': '#ef4444',
            'Medium': '#f59e0b',
            'Low': '#22c55e'
        };
        const priorityBg = {
            'High': '#fef2f2',
            'Medium': '#fffbeb',
            'Low': '#f0fdf4'
        };
        
        const priority = module.priority || 'Medium';
        const masteryPercent = Math.round(module.mastery_percent || 0);
        const moduleType = module.module_type || 'learn';
        const items = module.items || [];
        
        const typeIcons = {
            'learn': '📘',
            'cases': '⚖️',
            'practice': '✍️'
        };
        
        return `
            <div class="study-map-module" style="border-left: 4px solid ${priorityColors[priority]};">
                <div class="module-header">
                    <div class="module-rank">${index + 1}</div>
                    <div class="module-info">
                        <h4>${typeIcons[moduleType] || '📚'} ${escapeHtml(module.module_title)}</h4>
                        <div class="module-meta">
                            <span class="priority-badge" style="background: ${priorityBg[priority]}; color: ${priorityColors[priority]};">${priority} Priority</span>
                            <span class="mastery-badge">${masteryPercent}% mastery</span>
                            <span class="items-badge">${items.length} items</span>
                        </div>
                    </div>
                </div>
                <div class="module-why">
                    <span class="why-icon">💡</span>
                    <span>${escapeHtml(module.why || 'Recommended for your learning path')}</span>
                </div>
                ${items.length > 0 ? `
                    <div class="module-items">
                        ${items.slice(0, 5).map(item => renderStudyMapItem(item)).join('')}
                        ${items.length > 5 ? `<div class="more-items">+${items.length - 5} more items</div>` : ''}
                    </div>
                ` : ''}
                <div class="module-actions">
                    <button class="action-btn action-btn-primary" onclick="window.studyApp.openModuleContent(${module.module_id}, '${moduleType}')">
                        Start Learning →
                    </button>
                </div>
            </div>
        `;
    }
    
    function renderStudyMapItem(item) {
        const typeLabels = {
            'learn': '📖 Lesson',
            'case': '⚖️ Case',
            'practice': '✏️ Question'
        };
        const typeLabel = typeLabels[item.type] || item.type;
        
        return `
            <div class="study-item">
                <span class="item-type">${typeLabel}</span>
                <span class="item-title">${escapeHtml(item.title || 'Untitled')}</span>
            </div>
        `;
    }
    
    function openModuleContent(moduleId, moduleType) {
        const modeMap = {
            'learn': 'concepts',
            'cases': 'cases',
            'practice': 'practice'
        };
        const mode = modeMap[moduleType] || 'concepts';
        openMode(mode);
    }

    function backToSubjects() {
        document.getElementById('studyHub').classList.add('hidden');
        document.getElementById('subjectSelection').classList.remove('hidden');
        state.currentSubject = null;
        state.currentMode = '';
    }

    function goBackToDashboard() {
        window.location.href = 'dashboard-student.html';
    }

    function openMode(mode) {
        state.currentMode = mode;

        const contentArea = document.getElementById('contentArea');
        contentArea.classList.remove('hidden');

        const titles = {
            concepts: 'Learn Concepts',
            cases: 'Landmark Cases',
            practice: 'Answer Writing Practice',
            notes: 'My Notes'
        };

        document.getElementById('contentTitle').textContent = titles[mode] || mode;

        loadContent(mode);

        contentArea.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function backToModes() {
        document.getElementById('contentArea').classList.add('hidden');
        state.currentMode = '';
    }

    async function loadContent(mode) {
        const contentBody = document.getElementById('contentBody');
        const subject = state.currentSubject;

        if (!subject) {
            contentBody.innerHTML = '<p style="color: #64748b; text-align: center; padding: 2rem;">No subject selected</p>';
            return;
        }

        contentBody.innerHTML = `
            <div style="text-align: center; padding: 3rem;">
                <div style="width: 32px; height: 32px; border: 3px solid #E2E8F0; border-top-color: #0066FF; border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 16px;"></div>
                <p style="color: #64748b;">Loading content...</p>
            </div>
        `;

        try {
            if (mode === 'concepts') {
                const res = await fetchJson(`${API_BASE}/api/subjects/${subject.id}/learn`);
                renderLearnContent(contentBody, res);
            } else if (mode === 'cases') {
                const res = await fetchJson(`${API_BASE}/api/subjects/${subject.id}/cases`);
                renderCasesContent(contentBody, res);
            } else if (mode === 'practice') {
                const res = await fetchJson(`${API_BASE}/api/subjects/${subject.id}/practice`);
                renderPracticeContent(contentBody, res);
            } else if (mode === 'notes') {
                renderNotesEditor(contentBody, subject);
            }
        } catch (err) {
            console.error('Failed to load content:', err);
            contentBody.innerHTML = `
                <div style="text-align: center; padding: 3rem;">
                    <div style="font-size: 40px; margin-bottom: 12px;">📭</div>
                    <h3 style="color: #0F172A; margin-bottom: 8px;">Content Coming Soon</h3>
                    <p style="color: #64748b; max-width: 400px; margin: 0 auto;">
                        We're preparing comprehensive ${mode} content for <strong>${escapeHtml(subject.title)}</strong>. Check back soon!
                    </p>
                </div>
            `;
        }
    }

    function renderLearnContent(container, data) {
        const topics = data?.topics || data?.content || [];
        if (!topics.length) {
            container.innerHTML = `
                <div style="text-align: center; padding: 3rem;">
                    <div style="font-size: 40px; margin-bottom: 12px;">📖</div>
                    <p style="color: #64748b;">No learning content available yet.</p>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="topic-list">
                ${topics.map((topic, index) => `
                    <div class="topic-item">
                        <h4>${index + 1}. ${escapeHtml(topic.title)}</h4>
                        <p>${escapeHtml(topic.description || topic.content || '')}</p>
                    </div>
                `).join('')}
            </div>
        `;
    }

    function renderCasesContent(container, data) {
        const cases = data?.cases || data || [];
        if (!cases.length) {
            container.innerHTML = `
                <div style="text-align: center; padding: 3rem;">
                    <div style="font-size: 40px; margin-bottom: 12px;">⚖️</div>
                    <p style="color: #64748b;">No cases available yet.</p>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="case-list">
                ${cases.map((caseItem, index) => `
                    <div class="case-item">
                        <h4>${index + 1}. ${escapeHtml(caseItem.title || caseItem.name)}</h4>
                        ${caseItem.year ? `<div class="case-meta"><span class="meta-tag">Year: ${caseItem.year}</span></div>` : ''}
                        <p>${escapeHtml(caseItem.summary || caseItem.description || '')}</p>
                    </div>
                `).join('')}
            </div>
        `;
    }

    function renderPracticeContent(container, data) {
        const questions = data?.questions || data || [];
        if (!questions.length) {
            container.innerHTML = `
                <div style="text-align: center; padding: 3rem;">
                    <div style="font-size: 40px; margin-bottom: 12px;">✏️</div>
                    <p style="color: #64748b;">No practice questions available yet.</p>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="question-list">
                ${questions.map((q, index) => `
                    <div class="question-item">
                        <h4>Q${index + 1}. ${escapeHtml(q.title || q.question)}</h4>
                        ${q.marks ? `<div class="question-meta"><span class="meta-tag">${q.marks} Marks</span></div>` : ''}
                    </div>
                `).join('')}
            </div>
        `;
    }

    function renderNotesEditor(container, subject) {
        const savedNotes = localStorage.getItem(`notes_${subject.id}`) || '';

        container.innerHTML = `
            <div class="notes-editor">
                <h3>Your Notes for ${escapeHtml(subject.title)}</h3>
                <p style="color: #64748b; margin-bottom: 1rem;">Write your personal notes, summaries, and key points here.</p>
                <textarea id="notesTextarea" placeholder="Start typing your notes...">${escapeHtml(savedNotes)}</textarea>
                <button class="btn-save" onclick="window.studyApp.saveNotes()">Save Notes</button>
            </div>
        `;
    }

    function saveNotes() {
        const textarea = document.getElementById('notesTextarea');
        const subject = state.currentSubject;

        if (!textarea || !subject) return;

        localStorage.setItem(`notes_${subject.id}`, textarea.value);

        const btn = document.querySelector('.btn-save');
        if (btn) {
            const originalText = btn.textContent;
            btn.textContent = 'Saved!';
            btn.style.background = '#10b981';

            setTimeout(() => {
                btn.textContent = originalText;
                btn.style.background = '';
            }, 2000);
        }
    }

    async function init() {
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
                selectSubject(Number(subjectId));
            }

        } catch (err) {
            console.error('Failed to load curriculum:', err);
            state.isLoading = false;
            state.error = err.message;

            if (err.message.includes('Not authenticated') || err.message.includes('401')) {
                showError('Please log in to view your subjects.');
            } else {
                showError(err.message || 'Failed to load subjects. Please try again.');
            }
        }
    }

    window.studyApp = {
        selectSubject,
        backToSubjects,
        goBackToDashboard,
        openMode,
        backToModes,
        saveNotes,
        openModuleContent
    };

    window.selectSubject = selectSubject;
    window.backToSubjects = backToSubjects;
    window.goBackToDashboard = goBackToDashboard;
    window.openMode = openMode;
    window.backToModes = backToModes;
    window.saveNotes = saveNotes;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
