(function() {
    'use strict';

    const API_BASE = window.__API_BASE__ || (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' ? `${window.location.protocol}//${window.location.hostname}:8000` : '');

    const state = {
        subjects: [],
        courseName: null,
        currentSemester: null,
        currentSubject: null,
        focusSubjectId: null,
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

    function getFocusSubject() {
        if (state.subjects.length === 0) return null;
        const lastStudied = state.subjects.find(s => s.last_studied);
        if (lastStudied) return lastStudied;
        return state.subjects[0];
    }

    function getFocusReason(subject) {
        if (!subject) return 'Select a subject to begin';
        if (subject.last_studied) return 'Continue where you left off';
        if (subject.progress === 0) return 'Start your first lesson';
        return 'Based on your study pattern';
    }

    function getStatusText(subject) {
        if (!subject.progress || subject.progress === 0) return 'Not started';
        if (subject.progress >= 100) return 'Completed';
        return 'In progress';
    }

    function createSubjectCard(subject) {
        const progress = subject.progress || 0;
        const status = getStatusText(subject);
        const showProgressBar = progress > 0 && progress < 100;

        return `
            <div class="subject-card" data-subject-id="${subject.id}" onclick="window.studyApp.selectSubject(${subject.id})">
                <div class="subject-name">${escapeHtml(subject.title)}</div>
                <div class="subject-semester">Semester ${subject.semester || state.currentSemester || 1}</div>
                ${showProgressBar ? `
                    <div class="subject-progress-bar">
                        <div class="subject-progress-fill" style="width: ${progress}%"></div>
                    </div>
                ` : `
                    <div class="subject-status">${status}</div>
                `}
                <button class="card-cta" onclick="event.stopPropagation(); window.studyApp.selectSubject(${subject.id})">
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

        grid.innerHTML = state.subjects.map(s => createSubjectCard(s)).join('');
        
        const totalEl = document.getElementById('totalSubjects');
        if (totalEl) totalEl.textContent = state.subjects.length;
    }

    function renderFocusCard() {
        const focusSubject = getFocusSubject();
        state.focusSubjectId = focusSubject?.id || null;

        const titleEl = document.getElementById('focusTitle');
        const reasonEl = document.getElementById('focusReason');
        const ctaEl = document.getElementById('focusCta');
        const cardEl = document.getElementById('focusCard');

        if (!focusSubject) {
            if (cardEl) cardEl.style.display = 'none';
            return;
        }

        if (titleEl) titleEl.textContent = focusSubject.title;
        if (reasonEl) reasonEl.textContent = getFocusReason(focusSubject);
        if (ctaEl) ctaEl.textContent = focusSubject.last_studied ? 'Continue Studying' : 'Start Studying';
    }

    function startFocusSubject() {
        if (state.focusSubjectId) {
            selectSubject(state.focusSubjectId);
        }
    }

    async function selectSubject(subjectId) {
        const subject = state.subjects.find(s => s.id === subjectId);
        if (!subject) return;

        state.currentSubject = subject;
        document.getElementById('subjectSelection').classList.add('hidden');
        document.getElementById('studyHub').classList.remove('hidden');
        document.getElementById('currentSubject').textContent = subject.title;
        document.getElementById('subjectTitle').textContent = subject.title;
        document.getElementById('subjectSemester').textContent = `Semester ${subject.semester || state.currentSemester || 1}`;
        document.getElementById('subjectProgress').textContent = `${subject.progress || 0}% complete`;

        try {
            const avail = await fetchJson(`${API_BASE}/api/student/subject/${subjectId}/availability`);
            state.contentAvailability = avail;
        } catch (e) {
            console.warn('Could not fetch content availability');
        }
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
                console.warn('Could not fetch academic profile');
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

            if (state.subjects.length > 0) {
                renderFocusCard();
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
        startFocusSubject,
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
