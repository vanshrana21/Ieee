(function () {
    'use strict';

    const API_BASE = window.__API_BASE__ || 'http://127.0.0.1:8000';

    const state = {
        user: null,
        curriculum: null,
        subjects: [],
        archiveSubjects: [],
        analytics: null,
        recentActivity: [],
        lastActivity: null,
        dashboardStats: null,
        isLoading: true
    };

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
            setTimeout(() => {
                if (container.contains(toast)) container.removeChild(toast);
            }, 300);
        }, duration);
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

    function updateStats(curriculum, analytics, dashboardStats) {
        const progressEl = q('#overallProgress');
        const progressFillEl = q('#overallProgressFill');
        const accuracyEl = q('#practiceAccuracy');
        const timeEl = q('#timeStudied');
        const streakEl = q('#streakCount');
        const courseEl = q('#currentCourse');

        if (courseEl && curriculum?.course) {
            courseEl.textContent = curriculum.course.name || 'Your Course';
        }

        if (dashboardStats) {
            const overallProgress = Math.round(dashboardStats.overall_progress || 0);
            if (progressEl && progressFillEl) {
                progressEl.textContent = `${overallProgress}% Complete`;
                progressFillEl.style.width = `${overallProgress}%`;
            }

            if (accuracyEl) {
                accuracyEl.textContent = `${Math.round(dashboardStats.practice_accuracy || 0)}%`;
            }

            if (streakEl) {
                streakEl.textContent = dashboardStats.study_streak || 0;
            }

            if (timeEl) {
                const seconds = dashboardStats.total_time_spent_seconds || 0;
                const hours = Math.floor(seconds / 3600);
                const mins = Math.floor((seconds % 3600) / 60);
                timeEl.textContent = hours > 0 ? `${hours}h ${mins}m` : `${mins}m`;
            }
        } else if (analytics?.data) {
            const data = analytics.data;
            
            const overallProgress = Math.round(data.overall_mastery_percent || 0);
            if (progressEl && progressFillEl) {
                progressEl.textContent = `${overallProgress}% Complete`;
                progressFillEl.style.width = `${overallProgress}%`;
            }

            if (accuracyEl) {
                accuracyEl.textContent = `${overallProgress}%`;
            }

            if (streakEl) {
                streakEl.textContent = data.study_streak || 0;
            }

            if (timeEl) {
                const subjectsCount = (data.subjects_by_mastery || []).length;
                timeEl.textContent = subjectsCount > 0 ? `${subjectsCount} subjects` : '0m';
            }

            const strengthLabel = data.overall_strength_label || 'Weak';
            const strengthEl = q('#strengthLabel');
            if (strengthEl) {
                strengthEl.textContent = strengthLabel;
                strengthEl.className = `strength-badge strength-${strengthLabel.toLowerCase()}`;
            }
        } else {
            const allSubjects = [...(state.subjects || []), ...(state.archiveSubjects || [])];
            let overallProgress = 0;
            if (allSubjects.length > 0) {
                const totalCompletion = allSubjects.reduce((sum, s) => sum + (s.completion_percentage || s.progress || 0), 0);
                overallProgress = Math.round(totalCompletion / allSubjects.length);
            }

            if (progressEl && progressFillEl) {
                progressEl.textContent = `${overallProgress}% Complete`;
                progressFillEl.style.width = `${overallProgress}%`;
            }

            if (accuracyEl) accuracyEl.textContent = '—';
            if (timeEl) timeEl.textContent = '0m';
            if (streakEl) streakEl.textContent = '0';
        }
    }

    function renderSubjectsEmpty() {
        const grid = q('#subjectsGrid');
        if (!grid) return;

        grid.innerHTML = `
            <div class="empty-state" style="grid-column: 1 / -1; text-align: center; padding: 3rem;">
                <div style="font-size: 48px; margin-bottom: 12px;">📚</div>
                <h3 style="color: #0F172A; margin-bottom: 8px; font-size: 16px;">No Subjects Yet</h3>
                <p style="color: #64748B; font-size: 14px;">Your curriculum will appear here once it's set up.</p>
            </div>
        `;
    }

    function renderSubjects(subjects, analyticsData = null) {
        const grid = q('#subjectsGrid');
        if (!grid) return;

        if (!subjects || subjects.length === 0) {
            renderSubjectsEmpty();
            return;
        }

        const colors = ['blue', 'green', 'orange', 'purple'];
        
        const masteryMap = {};
        if (analyticsData?.data?.subjects_by_mastery) {
            analyticsData.data.subjects_by_mastery.forEach(s => {
                masteryMap[s.subject_id] = s;
            });
        }

        grid.innerHTML = subjects.slice(0, 6).map((subject, idx) => {
            const masteryInfo = masteryMap[subject.id];
            const progress = masteryInfo 
                ? Math.round(masteryInfo.mastery_percent || 0)
                : Math.round(subject.completion_percentage || 0);
            const strengthLabel = masteryInfo?.strength_label || 'Weak';
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
                        <span>${progress}% mastery</span>
                        <span class="strength-label strength-${strengthLabel.toLowerCase()}">${strengthLabel}</span>
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
        
        if (subjects.length === 0) {
            section.style.display = 'none';
            return;
        }

        const inProgress = subjects.find(s => s.completion_percentage > 0 && s.completion_percentage < 100) || subjects[0];

        if (inProgress) {
            const resumeSubject = q('#resumeSubject');
            const resumeTopic = q('#resumeTopic');
            const resumeProgressLabel = q('#resumeProgressLabel');
            const resumeProgressFill = q('#resumeProgressFill');

            if (resumeSubject) resumeSubject.textContent = inProgress.title || 'Continue Learning';
            if (resumeTopic) resumeTopic.textContent = inProgress.description || 'Pick up where you left off';
            
            const progress = Math.round(inProgress.completion_percentage || 0);
            if (resumeProgressLabel) resumeProgressLabel.textContent = `${progress}% complete`;
            if (resumeProgressFill) resumeProgressFill.style.width = `${progress}%`;
            
            section.style.display = 'block';
            state.lastActivity = inProgress;
        } else {
            section.style.display = 'none';
        }
    }

    function renderRecentActivity(activities) {
        const list = q('#activityList');
        if (!list) return;

        if (!activities || activities.length === 0) {
            list.innerHTML = `
                <div class="empty-state" style="text-align: center; padding: 2rem;">
                    <div style="font-size: 32px; margin-bottom: 8px;">📋</div>
                    <p style="color: #64748B; font-size: 13px;">No recent activity yet.<br>Start learning to see your history here.</p>
                </div>
            `;
            return;
        }

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
            </svg>`,
            learn: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
            </svg>`
        };

        list.innerHTML = activities.slice(0, 5).map(act => {
            const type = act.type || act.activity_type || 'learn';
            const icon = iconMap[type] || iconMap.learn;
            const title = act.title || act.subject_title || 'Activity';
            const meta = act.meta || act.timestamp || '';

            return `
                <div class="activity-item" onclick="window.jurisDashboard.openActivity('${type}', ${act.id || 0})">
                    <div class="activity-icon activity-icon-${type === 'case' ? 'case' : type === 'note' ? 'note' : 'practice'}">
                        ${icon}
                    </div>
                    <div class="activity-details">
                        <span class="activity-title">${escapeHtml(title)}</span>
                        <span class="activity-meta">${escapeHtml(meta)}</span>
                    </div>
                </div>
            `;
        }).join('');
    }

    function renderFocus(focusData) {
        const grid = q('#focusGrid');
        if (!grid) return;

        if (!focusData?.data?.has_focus || !focusData?.data?.topics?.length) {
            grid.innerHTML = `
                <div class="focus-empty">
                    <div class="focus-empty-icon">
                        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="12" cy="12" r="10"/>
                            <circle cx="12" cy="12" r="6"/>
                            <circle cx="12" cy="12" r="2"/>
                        </svg>
                    </div>
                    <h3>No Focus Topics Yet</h3>
                    <p>${focusData?.data?.message || 'Start practicing to get personalized recommendations!'}</p>
                </div>
            `;
            return;
        }

        const topics = focusData.data.topics;

        grid.innerHTML = topics.map(topic => {
            const topicName = (topic.topic_tag || '').replace(/-/g, ' ').replace(/_/g, ' ');
            const mastery = Math.round(topic.mastery_percent || 0);
            const priority = (topic.priority || 'medium').toLowerCase();
            
            let masteryClass = 'weak';
            if (mastery >= 70) masteryClass = 'strong';
            else if (mastery >= 40) masteryClass = 'average';

            const actions = topic.actions || [];

            return `
                <div class="focus-card priority-${priority}">
                    <div class="focus-card-header">
                        <div class="focus-rank">${topic.rank || '?'}</div>
                        <span class="focus-priority-badge ${priority}">${topic.priority || 'Medium'}</span>
                    </div>
                    <h3 class="focus-topic">${escapeHtml(topicName)}</h3>
                    <div class="focus-mastery">
                        <div class="focus-mastery-bar">
                            <div class="focus-mastery-fill ${masteryClass}" style="width: ${mastery}%"></div>
                        </div>
                        <span class="focus-mastery-percent">${mastery}%</span>
                    </div>
                    <div class="focus-explanation">${escapeHtml(topic.explanation || 'Focus on this topic to improve your understanding.')}</div>
                    <div class="focus-why">${escapeHtml(topic.why_now || '')}</div>
                    ${actions.length ? `
                        <div class="focus-actions">
                            ${actions.slice(0, 3).map(action => `
                                <span class="focus-action-tag">${escapeHtml(action)}</span>
                            `).join('')}
                        </div>
                    ` : ''}
                    <button class="focus-btn" onclick="window.jurisDashboard.openSubject(${topic.subject_id}, 'practice')">
                        Start Practicing
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M5 12h14M12 5l7 7-7 7"/>
                        </svg>
                    </button>
                </div>
            `;
        }).join('');
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

        openActivity(type, id) {
            if (id) {
                const routes = {
                    case: `case-detail.html?id=${id}`,
                    note: `my-notes.html?id=${id}`,
                    practice: `practice-content.html?id=${id}`,
                    learn: `start-studying.html?subject=${id}`
                };
                window.location.href = routes[type] || 'start-studying.html';
            } else {
                const routes = {
                    case: 'case-simplifier.html',
                    note: 'my-notes.html',
                    practice: 'practice-content.html'
                };
                window.location.href = routes[type] || 'start-studying.html';
            }
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

        renderRecentActivity([]);

        try {
            const dashboardStatsRes = await fetchJson(`${API_BASE}/api/dashboard/stats`).catch(err => {
                console.warn('Dashboard stats fetch failed:', err.message);
                return null;
            });

            if (dashboardStatsRes) {
                state.dashboardStats = dashboardStatsRes;
            }

            const subjectsRes = await fetchJson(`${API_BASE}/api/subjects`).catch(err => {
                console.warn('Subjects fetch failed:', err.message);
                return null;
            });

            if (subjectsRes && Array.isArray(subjectsRes)) {
                state.subjects = subjectsRes.map(s => ({
                    ...s,
                    completion_percentage: s.progress || 0
                }));
                renderSubjects(state.subjects, null);
                updateResumeSection();
            } else {
                const curriculumRes = await fetchJson(`${API_BASE}/api/curriculum/dashboard`).catch(err => {
                    console.warn('Curriculum fetch failed:', err.message);
                    return null;
                });

                if (curriculumRes) {
                    state.curriculum = curriculumRes;
                    state.subjects = curriculumRes.active_subjects || [];
                    state.archiveSubjects = curriculumRes.archive_subjects || [];
                    renderSubjects(state.subjects, null);
                    updateResumeSection();
                } else {
                    renderSubjectsEmpty();
                }
            }

            const lastActivityRes = await fetchJson(`${API_BASE}/api/dashboard/last-activity`).catch(err => {
                console.warn('Last activity fetch failed:', err.message);
                return null;
            });

            if (lastActivityRes && lastActivityRes.content_title) {
                state.lastActivity = lastActivityRes;
                updateResumeSectionWithActivity(lastActivityRes);
            }

            const analyticsRes = await fetchJson(`${API_BASE}/api/analytics/dashboard`).catch(err => {
                console.warn('Analytics fetch failed:', err.message);
                return null;
            });

            state.analytics = analyticsRes;
            updateStats(state.curriculum, analyticsRes, state.dashboardStats);

            const focusRes = await fetchJson(`${API_BASE}/api/study/focus`).catch(err => {
                console.warn('Focus fetch failed:', err.message);
                return null;
            });
            renderFocus(focusRes);

            const progressRes = await fetchJson(`${API_BASE}/api/progress/recent?limit=5`).catch(() => null);
            if (progressRes?.activities) {
                state.recentActivity = progressRes.activities;
                renderRecentActivity(progressRes.activities);
            }

        } catch (err) {
            console.error('Dashboard init error:', err);
            renderSubjectsEmpty();
            renderRecentActivity([]);
            updateStats(null, null, null);
        }

        state.isLoading = false;
    }

    function updateResumeSectionWithActivity(activity) {
        const section = q('#resumeSection');
        if (!section) return;

        if (!activity || !activity.content_title) {
            return;
        }

        const resumeSubject = q('#resumeSubject');
        const resumeTopic = q('#resumeTopic');
        const resumeProgressLabel = q('#resumeProgressLabel');
        const resumeProgressFill = q('#resumeProgressFill');

        if (resumeSubject) resumeSubject.textContent = activity.subject_title || 'Continue Learning';
        if (resumeTopic) resumeTopic.textContent = activity.content_title || 'Pick up where you left off';
        
        if (state.dashboardStats) {
            const progress = Math.round(state.dashboardStats.overall_progress || 0);
            if (resumeProgressLabel) resumeProgressLabel.textContent = `${progress}% overall progress`;
            if (resumeProgressFill) resumeProgressFill.style.width = `${progress}%`;
        }
        
        section.style.display = 'block';
        
        const resumeBtn = q('#resumeBtn');
        if (resumeBtn) {
            resumeBtn.onclick = () => {
                if (activity.content_type === 'learn') {
                    window.location.href = `learn-content.html?id=${activity.content_id}`;
                } else if (activity.content_type === 'case') {
                    window.location.href = `case-detail.html?id=${activity.content_id}`;
                } else if (activity.content_type === 'practice') {
                    window.location.href = `practice-content.html?id=${activity.content_id}`;
                } else if (activity.subject_id) {
                    window.location.href = `start-studying.html?subject=${activity.subject_id}`;
                }
            };
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
