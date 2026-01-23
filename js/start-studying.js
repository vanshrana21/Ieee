(function() {
    'use strict';

    const API_BASE = window.__API_BASE__ || (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' ? `${window.location.protocol}//${window.location.hostname}:8000` : '');

    const STUDY_MODES = [
        { id: 'learn', label: 'Learn', emoji: '📖' },
        { id: 'practice', label: 'Practice', emoji: '🎯' },
        { id: 'revision', label: 'Revision', emoji: '📝' },
        { id: 'exam-prep', label: 'Exam Prep', emoji: '🔥' }
    ];

    const AI_HINTS = [
        "Recommended based on your recent activity",
        "You haven't studied this in 3 days",
        "Important for upcoming assessments",
        "Great match for your learning goals",
        "Suggested by your study pattern"
    ];

    const state = {
        subjects: [],
        courseName: null,
        currentSemester: null,
        currentSubject: null,
        expandedSubjectId: null,
        selectedModes: {},
        isLoading: true,
        error: null,
        contentAvailability: {
            has_learning_content: false,
            has_modules: false,
            has_cases: false,
            has_practice: false,
            has_notes: true,
            modules_count: 0,
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
            window.location.href = 'login.html';
            throw new Error('Not authenticated');
        }
        
        const headers = { ...opts.headers };
        headers['Authorization'] = `Bearer ${token}`;
        headers['Content-Type'] = headers['Content-Type'] || 'application/json';

        const resp = await fetch(url, { ...opts, headers });
        
        if (resp.status === 401) {
            localStorage.removeItem('access_token');
            window.location.href = 'login.html';
            throw new Error('Session expired');
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

    function getAIHint(index) {
        return AI_HINTS[index % AI_HINTS.length];
    }

    function getSelectedMode(subjectId) {
        return state.selectedModes[subjectId] || 'learn';
    }

    function setSelectedMode(subjectId, modeId) {
        state.selectedModes[subjectId] = modeId;
    }

    function createModeSelector(subjectId) {
        const selectedMode = getSelectedMode(subjectId);
        const pills = STUDY_MODES.map(mode => `
            <button class="mode-pill ${mode.id === selectedMode ? 'selected' : ''}" 
                    data-mode="${mode.id}" 
                    data-subject="${subjectId}"
                    onclick="event.stopPropagation(); window.studyApp.selectMode(${subjectId}, '${mode.id}')">
                <span class="mode-emoji">${mode.emoji}</span>
                <span>${mode.label}</span>
            </button>
        `).join('');

        return `
            <div class="inline-mode-selector">
                <div class="mode-label">Study Mode</div>
                <div class="mode-pills">${pills}</div>
            </div>
        `;
    }

    function createSubjectCard(subject, index) {
        const icon = getCategoryIcon(subject.category);
        const isExpanded = state.expandedSubjectId === subject.id;
        const aiHint = getAIHint(index);
        const progress = subject.progress || Math.floor(Math.random() * 100);
        const circumference = 2 * Math.PI * 18;
        const dashOffset = circumference - (progress / 100) * circumference;

        return `
            <div class="subject-card ${isExpanded ? 'expanded' : ''}" 
                 data-subject-id="${subject.id}" 
                 data-index="${index}"
                 onclick="window.studyApp.toggleExpand(${subject.id})">
                <div class="subject-card-header">
                    <div class="subject-icon-wrap">
                        <svg class="progress-ring" viewBox="0 0 44 44">
                            <circle class="progress-ring-bg" cx="22" cy="22" r="18"/>
                            <circle class="progress-ring-fill" cx="22" cy="22" r="18" 
                                    stroke-dasharray="${circumference}" 
                                    stroke-dashoffset="${dashOffset}"/>
                        </svg>
                        <span class="subject-icon">${icon}</span>
                    </div>
                    <div class="subject-info">
                        <h3>${escapeHtml(subject.title)}</h3>
                        <div class="subject-meta-row">
                            <span class="semester-badge">Sem ${subject.semester || state.currentSemester || 1}</span>
                            <span class="difficulty-badge ${(subject.difficulty || 'medium').toLowerCase()}">${subject.difficulty || 'Medium'}</span>
                        </div>
                    </div>
                </div>
                <div class="subject-stats">
                    <span>📚 ${subject.modules_count || 0} modules</span>
                    <span>📊 ${progress}% complete</span>
                </div>
                <div class="last-studied">Last studied: ${subject.last_studied || '2 days ago'}</div>
                ${createModeSelector(subject.id)}
                <p class="ai-hint">${aiHint}</p>
                <button class="card-start-btn" onclick="event.stopPropagation(); window.studyApp.startStudying(${subject.id})">
                    Start Studying
                </button>
            </div>
        `;
    }

    function renderSubjects() {
        const grid = document.getElementById('subjectsGrid');
        if (!grid) return;

        if (state.subjects.length === 0) {
            grid.innerHTML = '<div class="fallback-state"><p>No subjects found.</p><p>Please check your enrollment.</p></div>';
            return;
        }

        grid.innerHTML = state.subjects.map((s, i) => createSubjectCard(s, i)).join('');
        
        const totalEl = document.getElementById('totalSubjects');
        if (totalEl) totalEl.textContent = state.subjects.length;
    }

    function toggleExpand(subjectId) {
        if (state.expandedSubjectId === subjectId) {
            state.expandedSubjectId = null;
        } else {
            state.expandedSubjectId = subjectId;
        }
        renderSubjects();
    }

    function selectMode(subjectId, modeId) {
        setSelectedMode(subjectId, modeId);
        
        const card = document.querySelector(`[data-subject-id="${subjectId}"]`);
        if (!card) return;
        
        card.querySelectorAll('.mode-pill').forEach(pill => {
            pill.classList.toggle('selected', pill.dataset.mode === modeId);
        });
    }

    function startStudying(subjectId) {
        const subject = state.subjects.find(s => s.id === subjectId);
        if (!subject) return;

        const selectedMode = getSelectedMode(subjectId);
        
        console.log(`Starting study session: Subject=${subject.title}, Mode=${selectedMode}`);
        
        selectSubject(subjectId);
    }

    async function selectSubject(subjectId) {
        const subject = state.subjects.find(s => s.id === subjectId);
        if (!subject) return;

        state.currentSubject = subject;
        document.getElementById('subjectSelection').classList.add('hidden');
        document.getElementById('studyHub').classList.remove('hidden');
        document.getElementById('currentSubject').textContent = subject.title;
        document.getElementById('subjectTitle').textContent = subject.title;

        try {
            const avail = await fetchJson(`${API_BASE}/api/student/subject/${subjectId}/availability`);
            state.contentAvailability = avail;
        } catch (e) {
        }
        updateStudyModeCards();
    }

    function updateStudyModeCards() {
        const modes = ['concepts', 'cases', 'practice', 'notes'];
        const cards = document.querySelectorAll('.mode-card');
        
        cards.forEach((card, i) => {
            const mode = modes[i];
            const isAvail = mode === 'notes' || 
                           (mode === 'concepts' && state.contentAvailability.has_modules) ||
                           (mode === 'cases' && state.contentAvailability.has_cases) ||
                           (mode === 'practice' && state.contentAvailability.has_practice);

            card.classList.toggle('mode-card-disabled', !isAvail);
            
            const existingBadge = card.querySelector('.mode-availability-badge');
            if (existingBadge) existingBadge.remove();

            const badge = document.createElement('div');
            badge.className = `mode-availability-badge ${isAvail ? 'mode-available' : 'mode-unavailable'}`;
            
            if (mode === 'concepts') {
                badge.textContent = isAvail ? `${state.contentAvailability.modules_count} modules available` : 'Coming soon';
            } else if (mode === 'cases') {
                badge.textContent = isAvail ? `${state.contentAvailability.cases_count} cases available` : 'Coming soon';
            } else if (mode === 'practice') {
                badge.textContent = isAvail ? `${state.contentAvailability.practice_count} questions available` : 'Coming soon';
            } else {
                badge.textContent = 'Ready to use';
            }
            card.appendChild(badge);
        });
    }

    function openMode(mode, subjectId = null) {
        const id = subjectId || (state.currentSubject ? state.currentSubject.id : null);
        if (!id) return;

        if (mode === 'concepts') window.location.href = `modules.html?subject_id=${id}`;
        else if (mode === 'cases') window.location.href = `cases.html?subject_id=${id}`;
        else if (mode === 'practice') window.location.href = `practice.html?subject_id=${id}`;
        else if (mode === 'notes') window.location.href = `notes.html?subject_id=${id}`;
    }

    function renderFallbackUI() {
        const grid = document.getElementById('subjectsGrid');
        if (!grid) return;

        grid.innerHTML = `
            <div class="fallback-state">
                <p>Subjects are loading. Please ensure the server is running.</p>
                <p>If this persists, return to dashboard and try again.</p>
            </div>
        `;
    }

    function showStudyPlan() {
        const modal = document.getElementById('studyPlanModal');
        if (modal) modal.classList.remove('hidden');
    }

    function closeModal() {
        const modal = document.getElementById('studyPlanModal');
        if (modal) modal.classList.add('hidden');
    }

    function generatePlan() {
        alert('AI Study Plan generation coming soon!');
        closeModal();
    }

    function quickPractice() {
        if (state.subjects.length > 0) {
            const randomSubject = state.subjects[Math.floor(Math.random() * state.subjects.length)];
            window.location.href = `practice.html?subject_id=${randomSubject.id}`;
        }
    }

    async function init() {
        try {
            try {
                const profile = await fetchJson(`${API_BASE}/api/student/academic-profile`);
                state.courseName = profile.course_name;
                state.currentSemester = profile.current_semester;
            } catch (e) {
            }

            const data = await fetchJson(`${API_BASE}/api/student/subjects`);
            state.subjects = (data.subjects || []).map(s => ({
                id: s.id,
                title: s.title,
                semester: s.semester,
                category: s.category || 'core',
                modules_count: s.module_count || 0,
                difficulty: s.difficulty || 'Medium',
                progress: s.progress || 0,
                last_studied: s.last_studied || null
            }));

            state.subjects.forEach(s => {
                state.selectedModes[s.id] = 'learn';
            });

            if (state.subjects.length > 0) {
                renderSubjects();
            } else {
                renderFallbackUI();
            }
        } catch (err) {
            console.warn("Start Studying: subjects API unavailable");
            renderFallbackUI();
        }
    }

    window.studyApp = {
        selectSubject,
        openMode,
        toggleExpand,
        selectMode,
        startStudying,
        showStudyPlan,
        closeModal,
        generatePlan,
        quickPractice,
        backToSubjects: () => {
            document.getElementById('studyHub').classList.add('hidden');
            document.getElementById('subjectSelection').classList.remove('hidden');
            state.currentSubject = null;
        }
    };

    window.backToSubjects = window.studyApp.backToSubjects;
    window.goBackToDashboard = () => window.location.href = 'dashboard-student.html';
    window.backToModes = () => document.getElementById('contentArea').classList.add('hidden');
    window.openMode = openMode;

    init();
})();
