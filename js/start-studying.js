(function() {
    'use strict';

    const API_BASE = window.__API_BASE__ || (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' ? `${window.location.protocol}//${window.location.hostname}:8000` : '');

    const state = {
        subjects: [],
        courseName: null,
        currentSemester: null,
        currentSubject: null,
        focusedIndex: 0,
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

    function createSubjectItem(subject, index) {
        const progress = subject.progress || 0;
        const status = getStatusText(subject);
        const isFocused = index === state.focusedIndex;
        const description = getDescription(subject);

        return `
            <div class="subject-item ${isFocused ? 'focused' : 'collapsed'}" 
                 data-subject-id="${subject.id}" 
                 data-index="${index}"
                 onclick="window.studyApp.handleItemClick(${index})">
                <div class="subject-item-row">
                    <div class="subject-item-info">
                        <div class="subject-item-name">${escapeHtml(subject.title)}</div>
                        <div class="subject-item-meta">Semester ${subject.semester || state.currentSemester || 1}</div>
                    </div>
                    <div class="subject-item-status">${status}</div>
                </div>
                <div class="subject-item-expanded">
                    <p class="subject-item-description">${description}</p>
                    <div class="subject-item-progress">
                        <div class="subject-progress-row">
                            <span class="subject-progress-label">Progress</span>
                            <span class="subject-progress-value">${progress}%</span>
                        </div>
                        <div class="subject-progress-bar">
                            <div class="subject-progress-fill" style="width: ${progress}%"></div>
                        </div>
                    </div>
                    <button class="subject-item-cta" onclick="event.stopPropagation(); window.studyApp.selectSubject(${subject.id})">
                        ${status === 'Not started' ? 'Start Studying' : 'Continue Studying'}
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                    </button>
                </div>
            </div>
        `;
    }

    function renderFocusStack() {
        const stack = document.getElementById('focusStack');
        if (!stack) return;

        if (state.subjects.length === 0) {
            stack.innerHTML = '<div class="fallback-state"><p>No subjects found.</p><p>Please check your enrollment.</p></div>';
            return;
        }

        stack.innerHTML = state.subjects.map((s, i) => createSubjectItem(s, i)).join('');
        
        const totalEl = document.getElementById('totalSubjects');
        if (totalEl) totalEl.textContent = state.subjects.length;
    }

    function updateFocusState(newIndex) {
        if (newIndex < 0 || newIndex >= state.subjects.length) return;
        
        state.focusedIndex = newIndex;
        
        const items = document.querySelectorAll('.subject-item');
        items.forEach((item, i) => {
            if (i === newIndex) {
                item.classList.remove('collapsed');
                item.classList.add('focused');
            } else {
                item.classList.remove('focused');
                item.classList.add('collapsed');
            }
        });
    }

    function handleItemClick(index) {
        if (index !== state.focusedIndex) {
            updateFocusState(index);
        }
    }

    function setupScrollFocus() {
        const stack = document.getElementById('focusStack');
        if (!stack) return;

        let ticking = false;
        
        window.addEventListener('scroll', () => {
            if (!ticking) {
                requestAnimationFrame(() => {
                    const items = document.querySelectorAll('.subject-item');
                    if (items.length === 0) { ticking = false; return; }
                    
                    const viewportCenter = window.innerHeight / 2;
                    let closestIndex = state.focusedIndex;
                    let closestDistance = Infinity;
                    
                    items.forEach((item, index) => {
                        const rect = item.getBoundingClientRect();
                        const itemCenter = rect.top + rect.height / 2;
                        const distance = Math.abs(itemCenter - viewportCenter);
                        
                        if (distance < closestDistance) {
                            closestDistance = distance;
                            closestIndex = index;
                        }
                    });
                    
                    if (closestIndex !== state.focusedIndex) {
                        updateFocusState(closestIndex);
                    }
                    
                    ticking = false;
                });
                ticking = true;
            }
        }, { passive: true });
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
        const stack = document.getElementById('focusStack');
        if (!stack) return;

        stack.innerHTML = `
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
                const lastStudiedIndex = state.subjects.findIndex(s => s.last_studied);
                state.focusedIndex = lastStudiedIndex >= 0 ? lastStudiedIndex : 0;
                renderFocusStack();
                setupScrollFocus();
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
        handleItemClick,
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
