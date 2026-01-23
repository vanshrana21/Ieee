(function() {
    'use strict';

    const API_BASE = window.__API_BASE__ || (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' ? `${window.location.protocol}//${window.location.hostname}:8000` : '');

    const state = {
        subjects: [],
        courseName: null,
        currentSemester: null,
        currentSubject: null,
        focusedIndex: 0,
        isTransitioning: false,
        scrollAccumulator: 0,
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

    function getStatusText(subject) {
        if (!subject.progress || subject.progress === 0) return 'Not started';
        if (subject.progress >= 100) return 'Completed';
        return 'In progress';
    }

    function getDescription(subject) {
        const status = getStatusText(subject);
        if (status === 'Not started') {
            return 'Begin your journey with this subject. Learn foundational concepts and build your understanding step by step.';
        }
        if (status === 'Completed') {
            return 'You have completed this subject. Review materials or practice to reinforce your knowledge.';
        }
        return 'Continue where you left off. Keep building on what you have learned so far.';
    }

    function renderFocusCard() {
        if (state.subjects.length === 0) {
            document.getElementById('focusSubjectName').textContent = 'No subjects found';
            document.getElementById('focusSemester').textContent = '';
            document.getElementById('focusDescription').textContent = 'Please check your enrollment.';
            document.getElementById('focusProgressFill').style.width = '0%';
            document.getElementById('focusProgressText').textContent = '';
            document.getElementById('focusCta').style.display = 'none';
            document.getElementById('scrollHint').style.display = 'none';
            return;
        }

        const subject = state.subjects[state.focusedIndex];
        const progress = subject.progress || 0;
        const status = getStatusText(subject);

        document.getElementById('focusSubjectName').textContent = subject.title;
        document.getElementById('focusSemester').textContent = `Semester ${subject.semester || state.currentSemester || 1}`;
        document.getElementById('focusDescription').textContent = getDescription(subject);
        document.getElementById('focusProgressFill').style.width = `${progress}%`;
        document.getElementById('focusProgressText').textContent = `${progress}% complete`;
        
        const ctaBtn = document.getElementById('focusCta');
        ctaBtn.innerHTML = `${status === 'Not started' ? 'Start Studying' : 'Continue Studying'} <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>`;
        ctaBtn.style.display = 'inline-flex';

        renderScrollDots();
        updateMetrics();
    }

    function renderScrollDots() {
        const dotsContainer = document.getElementById('scrollDots');
        if (!dotsContainer || state.subjects.length <= 1) {
            if (dotsContainer) dotsContainer.innerHTML = '';
            const hint = document.getElementById('scrollHint');
            if (hint) hint.style.display = state.subjects.length <= 1 ? 'none' : 'flex';
            return;
        }

        dotsContainer.innerHTML = state.subjects.map((_, i) => 
            `<div class="scroll-dot ${i === state.focusedIndex ? 'active' : ''}"></div>`
        ).join('');
    }

    function updateMetrics() {
        const totalEl = document.getElementById('totalSubjects');
        if (totalEl) totalEl.textContent = state.subjects.length;
    }

    function transitionToSubject(newIndex) {
        if (newIndex < 0 || newIndex >= state.subjects.length) return;
        if (newIndex === state.focusedIndex) return;
        if (state.isTransitioning) return;

        state.isTransitioning = true;
        const card = document.getElementById('focusCard');
        
        card.classList.add('transitioning');
        
        setTimeout(() => {
            state.focusedIndex = newIndex;
            renderFocusCard();
            
            setTimeout(() => {
                card.classList.remove('transitioning');
                state.isTransitioning = false;
            }, 50);
        }, 200);
    }

    function setupScrollNavigation() {
        const SCROLL_THRESHOLD = 80;
        let lastScrollTime = 0;
        const SCROLL_COOLDOWN = 400;

        window.addEventListener('wheel', (e) => {
            if (state.subjects.length <= 1) return;
            
            const now = Date.now();
            if (now - lastScrollTime < SCROLL_COOLDOWN) return;
            
            state.scrollAccumulator += e.deltaY;
            
            if (Math.abs(state.scrollAccumulator) >= SCROLL_THRESHOLD) {
                const direction = state.scrollAccumulator > 0 ? 1 : -1;
                const newIndex = state.focusedIndex + direction;
                
                if (newIndex >= 0 && newIndex < state.subjects.length) {
                    transitionToSubject(newIndex);
                    lastScrollTime = now;
                }
                
                state.scrollAccumulator = 0;
            }
        }, { passive: true });

        let touchStartY = 0;
        window.addEventListener('touchstart', (e) => {
            touchStartY = e.touches[0].clientY;
        }, { passive: true });

        window.addEventListener('touchend', (e) => {
            if (state.subjects.length <= 1) return;
            
            const touchEndY = e.changedTouches[0].clientY;
            const deltaY = touchStartY - touchEndY;
            
            if (Math.abs(deltaY) > 50) {
                const direction = deltaY > 0 ? 1 : -1;
                const newIndex = state.focusedIndex + direction;
                
                if (newIndex >= 0 && newIndex < state.subjects.length) {
                    transitionToSubject(newIndex);
                }
            }
        }, { passive: true });

        window.addEventListener('keydown', (e) => {
            if (state.subjects.length <= 1) return;
            if (document.getElementById('studyHub') && !document.getElementById('studyHub').classList.contains('hidden')) return;
            
            if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
                e.preventDefault();
                const newIndex = state.focusedIndex + 1;
                if (newIndex < state.subjects.length) transitionToSubject(newIndex);
            } else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
                e.preventDefault();
                const newIndex = state.focusedIndex - 1;
                if (newIndex >= 0) transitionToSubject(newIndex);
            } else if (e.key === 'Enter') {
                e.preventDefault();
                startFocusedSubject();
            }
        });
    }

    function startFocusedSubject() {
        if (state.subjects.length === 0) return;
        const subject = state.subjects[state.focusedIndex];
        selectSubject(subject.id);
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
                const lastStudiedIndex = state.subjects.findIndex(s => s.last_studied);
                state.focusedIndex = lastStudiedIndex >= 0 ? lastStudiedIndex : 0;
            }

            renderFocusCard();
            setupScrollNavigation();
        } catch (err) {
            console.warn("Start Studying: subjects API unavailable");
            document.getElementById('focusSubjectName').textContent = 'Unable to load';
            document.getElementById('focusSemester').textContent = '';
            document.getElementById('focusDescription').textContent = 'Please ensure the server is running and try again.';
            document.getElementById('focusCta').style.display = 'none';
            document.getElementById('scrollHint').style.display = 'none';
        }
    }

    window.studyApp = {
        selectSubject,
        openMode,
        startFocusedSubject,
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
