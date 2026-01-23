(function() {
    'use strict';

    const API_BASE = window.__API_BASE__ || (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' ? `${window.location.protocol}//${window.location.hostname}:8000` : '');

    const state = {
        subjects: [],
        courseName: null,
        currentSemester: null,
        currentSubject: null,
        activeSubjectIndex: 0,
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

    function getContextualHint(subject, index) {
        const hints = [
            "A foundational subject for your law career",
            "Great for building legal reasoning skills",
            "Essential for understanding Indian jurisprudence",
            "Perfect for a focused study session",
            "You studied this last session",
            "Recommended based on your curriculum",
            "Good subject to start today"
        ];
        return hints[index % hints.length];
    }

    function createSubjectCard(subject, index) {
        const icon = getCategoryIcon(subject.category);
        const hint = getContextualHint(subject, index);
        const isFirst = index === 0;

        return `
            <div class="subject-card ${isFirst ? 'active' : ''}" data-subject-id="${subject.id}" data-index="${index}">
                <div class="card-inner">
                    <span class="subject-icon">${icon}</span>
                    <h3>${escapeHtml(subject.title)}</h3>
                    <span class="semester-text">Semester ${subject.semester || state.currentSemester || 'N/A'}</span>
                    <p class="contextual-hint">${hint}</p>
                    <div class="card-actions">
                        <button class="btn-primary" onclick="event.stopPropagation(); window.studyApp.selectSubject(${subject.id})">Start Studying</button>
                        <button class="btn-secondary" onclick="event.stopPropagation(); window.studyApp.openMode('practice', ${subject.id})">Practice</button>
                    </div>
                </div>
            </div>
        `;
    }

    function renderSubjects() {
        const strip = document.getElementById('subjectFocusStrip');
        if (!strip) return;

        if (state.subjects.length === 0) {
            strip.innerHTML = '<div class="fallback-state"><p>No subjects found.</p><p>Please check your enrollment.</p></div>';
            hideScrollUI();
            return;
        }

        strip.innerHTML = state.subjects.map((s, i) => createSubjectCard(s, i)).join('');
        
        state.activeSubjectIndex = 0;
        updateStickyCta();
        renderScrollDots();
        setupScrollSnap();
        
        setTimeout(() => {
            document.getElementById('stickyCta')?.classList.add('visible');
        }, 500);
    }

    function renderScrollDots() {
        const dotsContainer = document.getElementById('scrollDots');
        if (!dotsContainer || state.subjects.length <= 1) {
            document.getElementById('scrollIndicator')?.classList.add('hidden');
            return;
        }

        dotsContainer.innerHTML = state.subjects.map((_, i) => 
            `<div class="scroll-dot ${i === 0 ? 'active' : ''}" data-index="${i}"></div>`
        ).join('');
    }

    function updateScrollDots(activeIndex) {
        const dots = document.querySelectorAll('.scroll-dot');
        dots.forEach((dot, i) => {
            dot.classList.toggle('active', i === activeIndex);
        });
    }

    function hideScrollUI() {
        document.getElementById('scrollIndicator')?.classList.add('hidden');
        document.getElementById('stickyCta')?.classList.remove('visible');
    }

    function setupScrollSnap() {
        const wrapper = document.getElementById('focusStripWrapper');
        const cards = document.querySelectorAll('.subject-card');
        if (!wrapper || !cards.length) return;

        let scrollTimeout;
        
        wrapper.addEventListener('scroll', () => {
            clearTimeout(scrollTimeout);
            scrollTimeout = setTimeout(() => {
                detectActiveCard();
            }, 50);
        }, { passive: true });

        const observerOptions = {
            root: wrapper,
            rootMargin: '-45% 0px -45% 0px',
            threshold: 0
        };

        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const index = parseInt(entry.target.dataset.index);
                    setActiveCard(index);
                }
            });
        }, observerOptions);

        cards.forEach(card => observer.observe(card));
    }

    function detectActiveCard() {
        const wrapper = document.getElementById('focusStripWrapper');
        const cards = document.querySelectorAll('.subject-card');
        if (!wrapper || !cards.length) return;

        const wrapperRect = wrapper.getBoundingClientRect();
        const wrapperCenter = wrapperRect.top + wrapperRect.height / 2;

        let closestIndex = 0;
        let closestDistance = Infinity;

        cards.forEach((card, index) => {
            const cardRect = card.getBoundingClientRect();
            const cardCenter = cardRect.top + cardRect.height / 2;
            const distance = Math.abs(cardCenter - wrapperCenter);

            if (distance < closestDistance) {
                closestDistance = distance;
                closestIndex = index;
            }
        });

        setActiveCard(closestIndex);
    }

    function setActiveCard(index) {
        if (state.activeSubjectIndex === index) return;
        
        state.activeSubjectIndex = index;

        document.querySelectorAll('.subject-card').forEach((c, i) => {
            c.classList.toggle('active', i === index);
        });

        updateScrollDots(index);
        updateStickyCta();
    }

    function updateStickyCta() {
        const subject = state.subjects[state.activeSubjectIndex];
        if (!subject) return;

        const btn = document.getElementById('stickyCtaBtn');
        if (btn) {
            btn.textContent = `Continue with ${subject.title} →`;
            btn.onclick = () => selectSubject(subject.id);
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
        const strip = document.getElementById('subjectFocusStrip');
        if (!strip) return;

        strip.innerHTML = `
            <div class="fallback-state">
                <p>Subjects are loading. Please ensure the server is running.</p>
                <p>If this persists, return to dashboard and try again.</p>
            </div>
        `;
        hideScrollUI();
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
                modules_count: s.module_count || 0
            }));

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
        backToSubjects: () => {
            document.getElementById('studyHub').classList.add('hidden');
            document.getElementById('subjectSelection').classList.remove('hidden');
            state.currentSubject = null;
        }
    };

    window.backToSubjects = window.studyApp.backToSubjects;
    window.goBackToDashboard = () => window.location.href = 'dashboard-student.html';
    window.backToModes = () => document.getElementById('contentArea').classList.add('hidden');

    init();
})();
