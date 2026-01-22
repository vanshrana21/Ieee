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
            "Mid-semester exams approaching soon",
            "A foundational subject for your law career",
            "Great time to dive into legal principles",
            "Perfect for a deep focus session today",
            "You haven't studied this in 5 days",
            "Recommended based on last session"
        ];
        // Semi-random but consistent hint for the subject
        return hints[subject.id % hints.length];
    }

    function createSubjectCard(subject) {
        const icon = getCategoryIcon(subject.category);
        const moduleCount = subject.modules_count || 0;

        return `
            <div class="subject-card" data-subject-id="${subject.id}" id="card-${subject.id}">
                <div class="subject-icon">${icon}</div>
                <h3>${escapeHtml(subject.title)}</h3>
                <span class="semester-text">Semester ${subject.semester || state.currentSemester || 'N/A'}</span>
                
                <div class="reveal-panel">
                    <p class="reveal-hint">${moduleCount} modules left for mid-sem</p>
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
            strip.innerHTML = '<div style="padding: 2rem; color: #64748b;">No subjects found.</div>';
            return;
        }

        strip.innerHTML = state.subjects.map(s => createSubjectCard(s)).join('');
        
        // Add scroll event listener for focus detection
        strip.addEventListener('scroll', handleScroll, { passive: true });
        
        // Initial update
        setTimeout(() => {
            handleScroll();
            document.getElementById('focusGuidance').classList.remove('hidden');
        }, 100);
    }

    function handleScroll() {
        const strip = document.getElementById('subjectFocusStrip');
        const cards = strip.querySelectorAll('.subject-card');
        const stripCenter = strip.scrollLeft + (strip.offsetWidth / 2);
        
        let closestCard = null;
        let minDistance = Infinity;

        cards.forEach(card => {
            const cardCenter = card.offsetLeft + (card.offsetWidth / 2);
            const distance = Math.abs(stripCenter - cardCenter);

            if (distance < minDistance) {
                minDistance = distance;
                closestCard = card;
            }
        });

        if (closestCard && state.activeSubjectId !== parseInt(closestCard.dataset.subjectId)) {
            setActiveCard(closestCard);
        }
    }

    function setActiveCard(cardElement) {
        const id = parseInt(cardElement.dataset.subjectId);
        state.activeSubjectId = id;

        // Update UI states
        document.querySelectorAll('.subject-card').forEach(c => c.classList.remove('active'));
        cardElement.classList.add('active');

        // Update guidance content
        const subject = state.subjects.find(s => s.id === id);
        if (subject) {
            const hintEl = document.getElementById('whyMicroHint');
            const ctaEl = document.getElementById('smartCTA');
            
            hintEl.textContent = getMicroHint(subject);
            ctaEl.textContent = `Continue with ${subject.title} →`;
            ctaEl.onclick = () => selectSubject(id);
            
            // Subtle entrance animation for guidance
            hintEl.style.opacity = '0';
            ctaEl.style.opacity = '0';
            setTimeout(() => {
                hintEl.style.transition = 'opacity 0.4s ease';
                ctaEl.style.transition = 'opacity 0.4s ease';
                hintEl.style.opacity = '1';
                ctaEl.style.opacity = '1';
            }, 50);
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

        // Fetch availability for mode enablement
        const avail = await fetchJson(`${API_BASE}/api/student/subject/${subjectId}/availability`);
        state.contentAvailability = avail;
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

    async function init() {
        try {
            const profile = await fetchJson(`${API_BASE}/api/student/academic-profile`);
            state.courseName = profile.course_name;
            state.currentSemester = profile.current_semester;

            const data = await fetchJson(`${API_BASE}/api/student/subjects`);
            state.subjects = (data.subjects || []).map(s => ({
                id: s.id,
                title: s.title,
                semester: s.semester,
                category: s.category || 'core',
                modules_count: s.module_count || 0
            }));

            renderSubjects();
        } catch (err) {
            console.error('Init failed:', err);
            const strip = document.getElementById('subjectFocusStrip');
            if (strip) strip.innerHTML = `<p style="color: #64748b; padding: 2rem;">Error: ${escapeHtml(err.message)}</p>`;
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
