(function() {
    'use strict';

    const API_BASE = window.__API_BASE__ || (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' ? `${window.location.protocol}//${window.location.hostname}:8000` : '');

    const state = {
        subjects: [],
        courseName: null,
        currentSemester: null,
        currentSubject: null,
        activeSubjectId: null,
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

    function getMicroHint(subject) {
        const hints = [
            "Recommended based on your curriculum",
            "Good subject to start today",
            "A foundational subject for your law career",
            "Great time to dive into legal principles",
            "Perfect for a focused study session"
        ];
        return hints[subject.id % hints.length];
    }

    function createSubjectCard(subject, index) {
        const icon = getCategoryIcon(subject.category);
        const moduleCount = subject.modules_count || 0;
        const hint = getMicroHint(subject);
        const isFirst = index === 0;

        return `
            <div class="subject-card ${isFirst ? 'active' : ''}" data-subject-id="${subject.id}" data-index="${index}">
                <div class="subject-card-header">
                    <div class="subject-icon">${icon}</div>
                    <div class="subject-info">
                        <h3>${escapeHtml(subject.title)}</h3>
                        <span class="semester-text">Semester ${subject.semester || state.currentSemester || 'N/A'}</span>
                    </div>
                </div>
                
                <div class="reveal-panel">
                    <p class="reveal-hint">${hint}</p>
                    <div class="reveal-actions">
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
            return;
        }

        strip.innerHTML = state.subjects.map((s, i) => createSubjectCard(s, i)).join('');
        
        if (state.subjects.length > 0) {
            state.activeSubjectId = state.subjects[0].id;
        }

        setupScrollObserver();
        setupClickHandlers();
    }

    function setupScrollObserver() {
        const cards = document.querySelectorAll('.subject-card');
        if (!cards.length) return;

        const observerOptions = {
            root: null,
            rootMargin: '-30% 0px -30% 0px',
            threshold: 0.5
        };

        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    setActiveCard(entry.target);
                }
            });
        }, observerOptions);

        cards.forEach(card => observer.observe(card));
    }

    function setupClickHandlers() {
        const cards = document.querySelectorAll('.subject-card');
        cards.forEach(card => {
            card.addEventListener('click', () => {
                setActiveCard(card);
            });
        });
    }

    function setActiveCard(cardElement) {
        const id = parseInt(cardElement.dataset.subjectId);
        if (state.activeSubjectId === id) return;
        
        state.activeSubjectId = id;

        document.querySelectorAll('.subject-card').forEach(c => c.classList.remove('active'));
        cardElement.classList.add('active');
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
            // Keep defaults
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
    }

    async function init() {
        try {
            try {
                const profile = await fetchJson(`${API_BASE}/api/student/academic-profile`);
                state.courseName = profile.course_name;
                state.currentSemester = profile.current_semester;
            } catch (e) {
                // Non-blocking
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
