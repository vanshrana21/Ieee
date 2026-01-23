(function() {
    'use strict';

    const API_BASE = window.__API_BASE__ || (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' ? `${window.location.protocol}//${window.location.hostname}:8000` : '');

    const state = {
        subjects: [],
        courseName: null,
        currentSemester: null,
        currentSubject: null,
        activeIndex: 0,
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
            return 'Begin your journey with this subject. Learn foundational concepts and build understanding step by step.';
        }
        if (status === 'Completed') {
            return 'You have completed this subject. Review materials or practice to reinforce your knowledge.';
        }
        return 'Continue where you left off. Keep building on what you have learned.';
    }

    function renderSpotlightTrack() {
        const track = document.getElementById('spotlightTrack');
        if (!track) return;

        if (state.subjects.length === 0) {
            track.innerHTML = `
                <div class="spotlight-card active">
                    <div class="spotlight-inner">
                        <h2 class="spotlight-title">No subjects found</h2>
                        <p class="spotlight-semester">Please check your enrollment</p>
                    </div>
                </div>
            `;
            return;
        }

        track.innerHTML = state.subjects.map((subject, index) => {
            const progress = subject.progress || 0;
            const status = getStatusText(subject);
            const ctaText = status === 'Not started' ? 'Start Studying' : 'Continue';

            return `
                <div class="spotlight-card" data-index="${index}" data-id="${subject.id}">
                    <div class="spotlight-inner">
                        <h2 class="spotlight-title">${subject.title}</h2>
                        <p class="spotlight-semester">Semester ${subject.semester || state.currentSemester || 1}</p>
                        <p class="spotlight-description">${getDescription(subject)}</p>
                        <div class="spotlight-progress">
                            <div class="spotlight-progress-bar">
                                <div class="spotlight-progress-fill" style="width: ${progress}%"></div>
                            </div>
                            <span class="spotlight-progress-text">${progress}% complete</span>
                        </div>
                        <button class="spotlight-cta" onclick="window.studyApp.selectSubject('${subject.id}')">
                            ${ctaText}
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                        </button>
                    </div>
                </div>
            `;
        }).join('');

        setupSpotlightObserver();
        setupCardClicks();
        updateMetrics();

        if (state.subjects.length > 0) {
            const firstCard = track.querySelector('.spotlight-card');
            if (firstCard) firstCard.classList.add('active');
        }
    }

    function setupSpotlightObserver() {
        const cards = document.querySelectorAll('.spotlight-card');
        if (cards.length === 0) return;

        const observer = new IntersectionObserver((entries) => {
            let mostVisible = null;
            let maxRatio = 0;

            entries.forEach(entry => {
                if (entry.intersectionRatio > maxRatio) {
                    maxRatio = entry.intersectionRatio;
                    mostVisible = entry.target;
                }
            });

            if (mostVisible && maxRatio > 0.5) {
                cards.forEach(card => card.classList.remove('active'));
                mostVisible.classList.add('active');
                state.activeIndex = parseInt(mostVisible.dataset.index, 10);
            }
        }, {
            root: null,
            rootMargin: '-40% 0px -40% 0px',
            threshold: [0, 0.25, 0.5, 0.75, 1]
        });

        cards.forEach(card => observer.observe(card));
    }

    function setupCardClicks() {
        const cards = document.querySelectorAll('.spotlight-card');
        cards.forEach(card => {
            card.addEventListener('click', (e) => {
                if (e.target.closest('.spotlight-cta')) return;
                
                const index = parseInt(card.dataset.index, 10);
                if (index !== state.activeIndex) {
                    card.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            });
        });
    }

    function updateMetrics() {
        const totalEl = document.getElementById('totalSubjects');
        if (totalEl) totalEl.textContent = state.subjects.length;
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

        window.scrollTo(0, 0);

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

    function backToSubjects() {
        document.getElementById('studyHub').classList.add('hidden');
        document.getElementById('subjectSelection').classList.remove('hidden');
        state.currentSubject = null;

        requestAnimationFrame(() => {
            const activeCard = document.querySelector(`.spotlight-card[data-index="${state.activeIndex}"]`);
            if (activeCard) {
                activeCard.scrollIntoView({ behavior: 'instant', block: 'center' });
            }
        });
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
                state.activeIndex = lastStudiedIndex >= 0 ? lastStudiedIndex : 0;
            }

            renderSpotlightTrack();

            if (state.activeIndex > 0) {
                requestAnimationFrame(() => {
                    const card = document.querySelector(`.spotlight-card[data-index="${state.activeIndex}"]`);
                    if (card) {
                        card.scrollIntoView({ behavior: 'instant', block: 'center' });
                        document.querySelectorAll('.spotlight-card').forEach(c => c.classList.remove('active'));
                        card.classList.add('active');
                    }
                });
            }
        } catch (err) {
            console.warn("Start Studying: subjects API unavailable");
            const track = document.getElementById('spotlightTrack');
            if (track) {
                track.innerHTML = `
                    <div class="spotlight-card active">
                        <div class="spotlight-inner">
                            <h2 class="spotlight-title">Unable to load</h2>
                            <p class="spotlight-semester">Please ensure the server is running</p>
                        </div>
                    </div>
                `;
            }
        }
    }

    window.studyApp = {
        selectSubject,
        openMode,
        showStudyPlan,
        closeModal,
        generatePlan,
        quickPractice,
        backToSubjects
    };

    window.backToSubjects = backToSubjects;
    window.goBackToDashboard = () => window.location.href = 'dashboard-student.html';
    window.backToModes = () => document.getElementById('contentArea').classList.add('hidden');
    window.openMode = openMode;

    init();
})();
