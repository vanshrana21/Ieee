(function () {
    const API_BASE = window.__API_BASE__ || 'http://127.0.0.1:8000';

    const state = {
        user: null,
        curriculum: null,
        subjects: [],
        analytics: null,
        lastActivity: null,
        isLoading: true
    };

    const DOM = {};

    function q(sel, parent = document) {
        return parent.querySelector(sel);
    }

    function qa(sel, parent = document) {
        return Array.from(parent.querySelectorAll(sel));
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function showToast(message, type = 'info', duration = 3000) {
        let container = document.getElementById('toastContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toastContainer';
            Object.assign(container.style, {
                position: 'fixed',
                bottom: '24px',
                right: '24px',
                zIndex: '9999',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px'
            });
            document.body.appendChild(container);
        }

        const toast = document.createElement('div');
        Object.assign(toast.style, {
            background: type === 'error' ? '#FEE2E2' : '#0F172A',
            color: type === 'error' ? '#991B1B' : '#FFFFFF',
            padding: '14px 20px',
            borderRadius: '12px',
            fontSize: '14px',
            fontWeight: '500',
            boxShadow: '0 4px 20px rgba(0,0,0,0.15)',
            animation: 'slideIn 0.3s ease'
        });
        toast.textContent = message;
        container.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(20px)';
            toast.style.transition = 'all 0.3s ease';
            setTimeout(() => container.removeChild(toast), 300);
        }, duration);
    }

    async function fetchJson(url, opts = {}) {
        const token = window.auth?.getToken?.() || localStorage.getItem('token');
        const headers = { ...opts.headers };
        if (token) headers['Authorization'] = `Bearer ${token}`;
        headers['Content-Type'] = headers['Content-Type'] || 'application/json';

        try {
            const resp = await fetch(url, { ...opts, headers });
            const text = await resp.text();
            let json;
            try { json = text ? JSON.parse(text) : null; } catch { json = null; }
            if (!resp.ok) throw new Error(json?.detail || json?.error || resp.statusText);
            return json;
        } catch (err) {
            throw err;
        }
    }

    function getGreeting() {
        const hour = new Date().getHours();
        if (hour < 12) return 'Good morning';
        if (hour < 17) return 'Good afternoon';
        return 'Good evening';
    }

    function updateGreeting() {
        const greetingEl = q('#greeting');
        const heroNameEl = q('#heroName');
        const avatarEl = q('#avatarInitial');

        if (greetingEl) greetingEl.textContent = getGreeting();

        const firstName = window.auth?.getUserFirstName?.() || 
                         state.user?.first_name || 
                         localStorage.getItem('userName')?.split(' ')[0] || 
                         '';

        if (heroNameEl) {
            heroNameEl.textContent = firstName ? `Welcome back, ${firstName}!` : 'Welcome back!';
        }

        if (avatarEl && firstName) {
            avatarEl.textContent = firstName.charAt(0).toUpperCase();
        }
    }

    function updateStats(analytics) {
        if (!analytics) return;

        const progressEl = q('#overallProgress');
        const progressFillEl = q('#overallProgressFill');
        const accuracyEl = q('#practiceAccuracy');
        const timeEl = q('#timeStudied');
        const streakEl = q('#streakCount');
        const courseEl = q('#currentCourse');

        const snapshot = analytics.snapshot || {};
        const consistency = analytics.consistency || {};

        if (progressEl && progressFillEl) {
            const completion = Math.round(snapshot.overall_completion || 0);
            progressEl.textContent = `${completion}% Complete`;
            progressFillEl.style.width = `${completion}%`;
        }

        if (accuracyEl) {
            const accuracy = Math.round(snapshot.overall_accuracy || 0);
            accuracyEl.textContent = `${accuracy}%`;
        }

        if (timeEl) {
            const hours = Math.floor((consistency.total_time_spent_hours || 0));
            const minutes = Math.round(((consistency.total_time_spent_hours || 0) % 1) * 60);
            timeEl.textContent = hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
        }

        if (streakEl) {
            streakEl.textContent = consistency.current_streak || 0;
        }

        if (courseEl && state.curriculum?.course) {
            courseEl.textContent = state.curriculum.course.name || 'BA LLB';
        }
    }

    function renderSubjects(subjects) {
        const grid = q('#subjectsGrid');
        if (!grid || !subjects?.length) return;

        const colors = ['blue', 'green', 'orange', 'purple'];

        grid.innerHTML = subjects.slice(0, 6).map((subject, idx) => {
            const progress = Math.round(subject.completion_percentage || 0);
            const color = colors[idx % colors.length];
            const semester = subject.semester ? `Sem ${subject.semester}` : '';

            return `
                <div class="subject-card" data-subject-id="${subject.id}">
                    <div class="subject-card-header">
                        <div class="subject-icon subject-icon-${color}">
                            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                            </svg>
                        </div>
                        <span class="subject-semester">${escapeHtml(semester)}</span>
                    </div>
                    <h3 class="subject-name">${escapeHtml(subject.title)}</h3>
                    <div class="subject-progress">
                        <div class="subject-progress-fill" style="width: ${progress}%"></div>
                    </div>
                    <div class="subject-meta">
                        <span>${progress}% complete</span>
                    </div>
                    <div class="subject-actions">
                        <button class="subject-btn subject-btn-primary" onclick="window.jurisDashboard.openSubject(${subject.id}, 'learn')">Learn</button>
                        <button class="subject-btn subject-btn-secondary" onclick="window.jurisDashboard.openSubject(${subject.id}, 'practice')">Practice</button>
                    </div>
                </div>
            `;
        }).join('');
    }

    function updateResumeSection() {
        const section = q('#resumeSection');
        if (!section) return;

        const subjects = state.subjects || [];
        const inProgress = subjects.find(s => s.completion_percentage > 0 && s.completion_percentage < 100) || subjects[0];

        if (inProgress) {
            q('#resumeSubject').textContent = inProgress.title || 'Constitutional Law';
            q('#resumeTopic').textContent = inProgress.last_topic || 'Continue your learning journey';
            const progress = Math.round(inProgress.completion_percentage || 0);
            q('#resumeProgressLabel').textContent = `${progress}% complete`;
            q('#resumeProgressFill').style.width = `${progress}%`;
            section.style.display = 'block';
            state.lastActivity = inProgress;
        }
    }

    function renderRecentActivity() {
        const list = q('#activityList');
        if (!list) return;

        const activities = [
            { type: 'case', title: 'Kesavananda Bharati v. State of Kerala', meta: 'Constitutional Law • 2h ago' },
            { type: 'note', title: 'Article 21 - Right to Life Notes', meta: 'My Notes • Yesterday' },
            { type: 'practice', title: 'Basic Structure Doctrine - 5 Mark', meta: 'Practice • 3 days ago' },
            { type: 'case', title: 'Maneka Gandhi v. Union of India', meta: 'Constitutional Law • 5 days ago' }
        ];

        const iconMap = {
            case: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
            </svg>`,
            note: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
                <polyline points="14 2 14 8 20 8"/>
            </svg>`,
            practice: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
            </svg>`
        };

        list.innerHTML = activities.map(act => `
            <div class="activity-item" onclick="window.jurisDashboard.openActivity('${act.type}')">
                <div class="activity-icon activity-icon-${act.type}">
                    ${iconMap[act.type]}
                </div>
                <div class="activity-details">
                    <span class="activity-title">${escapeHtml(act.title)}</span>
                    <span class="activity-meta">${escapeHtml(act.meta)}</span>
                </div>
            </div>
        `).join('');
    }

    function setupSidebar() {
        const menuToggle = q('#menuToggle');
        const sidebar = q('#sidebar');
        const overlay = q('#sidebarOverlay');

        if (menuToggle && sidebar) {
            menuToggle.addEventListener('click', () => {
                sidebar.classList.toggle('open');
                overlay?.classList.toggle('active');
            });
        }

        if (overlay) {
            overlay.addEventListener('click', () => {
                sidebar?.classList.remove('open');
                overlay.classList.remove('active');
            });
        }
    }

    function setupSearch() {
        const input = q('#searchInput');
        const results = q('#searchResults');

        if (!input || !results) return;

        let debounceTimer;

        input.addEventListener('input', () => {
            clearTimeout(debounceTimer);
            const query = input.value.trim();

            if (query.length < 2) {
                results.classList.remove('active');
                return;
            }

            debounceTimer = setTimeout(async () => {
                try {
                    const res = await fetchJson(`${API_BASE}/api/search?q=${encodeURIComponent(query)}&limit=10`);
                    if (res?.results?.length) {
                        results.innerHTML = res.results.map(r => `
                            <div class="search-result-item" onclick="window.jurisDashboard.openSearchResult('${r.content_type}', ${r.id})">
                                <div class="search-result-title">${escapeHtml(r.title)}</div>
                                <div class="search-result-meta">${escapeHtml(r.content_type)} • ${escapeHtml(r.subject_name || '')}</div>
                            </div>
                        `).join('');
                        results.classList.add('active');
                    } else {
                        results.innerHTML = '<div class="search-empty">No results found</div>';
                        results.classList.add('active');
                    }
                } catch (err) {
                    console.error('Search error:', err);
                }
            }, 300);
        });

        document.addEventListener('click', (e) => {
            if (!e.target.closest('.search-wrapper')) {
                results.classList.remove('active');
            }
        });
    }

    function setupAIModal() {
        const fab = q('#fabAI');
        const modal = q('#aiModal');
        const overlay = q('#aiModalOverlay');
        const closeBtn = q('#aiModalClose');
        const input = q('#aiModalInput');
        const sendBtn = q('#aiModalSend');
        const body = q('#aiModalBody');

        const inlineInput = q('#aiInput');
        const inlineSend = q('#aiSendBtn');
        const chips = qa('.ai-chip');

        function openModal(query = '') {
            modal?.classList.add('active');
            if (input && query) {
                input.value = query;
                sendAIQuery(query);
            }
        }

        function closeModal() {
            modal?.classList.remove('active');
        }

        async function sendAIQuery(query) {
            if (!query || query.length < 2) return;

            body.innerHTML = `
                <div style="text-align:center;padding:40px;">
                    <div style="width:32px;height:32px;border:3px solid #E2E8F0;border-top-color:#0066FF;border-radius:50%;animation:spin 1s linear infinite;margin:0 auto 16px;"></div>
                    <p style="color:#64748B;">Thinking...</p>
                </div>
                <style>@keyframes spin{to{transform:rotate(360deg)}}</style>
            `;

            try {
                const res = await fetchJson(`${API_BASE}/api/tutor/chat`, {
                    method: 'POST',
                    body: JSON.stringify({
                        session_id: null,
                        input: query,
                        context: { previous_turns: 2 }
                    })
                });

                if (res?.content) {
                    body.innerHTML = `
                        <div style="white-space:pre-wrap;line-height:1.7;color:#0F172A;">
                            ${escapeHtml(res.content)}
                        </div>
                        ${res.provenance?.length ? `
                            <div style="margin-top:20px;padding-top:16px;border-top:1px solid #E2E8F0;font-size:13px;color:#64748B;">
                                <strong>Sources:</strong> ${res.provenance.map(p => escapeHtml(p.title || p.doc_type)).join(', ')}
                            </div>
                        ` : ''}
                    `;
                } else {
                    body.innerHTML = '<div class="ai-response-placeholder">No response available. Try a different question.</div>';
                }
            } catch (err) {
                body.innerHTML = `<div style="color:#EF4444;text-align:center;padding:40px;">Failed to get response. Please try again.</div>`;
            }
        }

        fab?.addEventListener('click', () => openModal());
        overlay?.addEventListener('click', closeModal);
        closeBtn?.addEventListener('click', closeModal);

        sendBtn?.addEventListener('click', () => {
            const query = input?.value.trim();
            if (query) sendAIQuery(query);
        });

        input?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const query = input.value.trim();
                if (query) sendAIQuery(query);
            }
        });

        inlineSend?.addEventListener('click', () => {
            const query = inlineInput?.value.trim();
            if (query) openModal(query);
        });

        inlineInput?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const query = inlineInput.value.trim();
                if (query) openModal(query);
            }
        });

        chips.forEach(chip => {
            chip.addEventListener('click', () => {
                const query = chip.dataset.query;
                if (query) openModal(query);
            });
        });
    }

    function setupLogout() {
        const logoutBtn = q('#logoutBtn');
        logoutBtn?.addEventListener('click', (e) => {
            e.preventDefault();
            if (window.auth?.logout) {
                window.auth.logout();
            }
            localStorage.removeItem('token');
            showToast('Logged out successfully');
            setTimeout(() => {
                window.location.href = 'login.html';
            }, 500);
        });
    }

    function setupContinueLearning() {
        const btn = q('#continueLearningBtn');
        const resumeBtn = q('#resumeBtn');

        const navigate = () => {
            if (state.lastActivity?.id) {
                window.location.href = `start-studying.html?subject=${state.lastActivity.id}`;
            } else if (state.subjects?.[0]?.id) {
                window.location.href = `start-studying.html?subject=${state.subjects[0].id}`;
            } else {
                window.location.href = 'start-studying.html';
            }
        };

        btn?.addEventListener('click', navigate);
        resumeBtn?.addEventListener('click', navigate);
    }

    window.jurisDashboard = {
        openSubject(id, mode = 'learn') {
            const url = mode === 'practice' 
                ? `practice-content.html?subject=${id}` 
                : `start-studying.html?subject=${id}`;
            window.location.href = url;
        },

        openActivity(type) {
            const routes = {
                case: 'case-detail.html',
                note: 'my-notes.html',
                practice: 'practice-content.html'
            };
            window.location.href = routes[type] || 'start-studying.html';
        },

        openSearchResult(type, id) {
            const routes = {
                subject: `start-studying.html?subject=${id}`,
                learn: `learn-content.html?id=${id}`,
                case: `case-detail.html?id=${id}`,
                practice: `practice-content.html?id=${id}`
            };
            window.location.href = routes[type] || `start-studying.html`;
        }
    };

    async function init() {
        updateGreeting();
        setupSidebar();
        setupSearch();
        setupAIModal();
        setupLogout();
        setupContinueLearning();
        renderRecentActivity();

        try {
            const [curriculumRes, analyticsRes] = await Promise.all([
                fetchJson(`${API_BASE}/api/curriculum/dashboard`).catch(() => null),
                fetchJson(`${API_BASE}/api/analytics/comprehensive`).catch(() => null)
            ]);

            if (curriculumRes) {
                state.curriculum = curriculumRes;
                state.subjects = curriculumRes.active_subjects || [];
                renderSubjects(state.subjects);
                updateResumeSection();
            }

            if (analyticsRes?.data) {
                state.analytics = analyticsRes.data;
                updateStats(analyticsRes.data);
            }

        } catch (err) {
            console.error('Dashboard init error:', err);
        }

        state.isLoading = false;
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
