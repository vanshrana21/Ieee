/**
 * dashboard-student.js
 * Full, connected dashboard client for JurisAI
 *
 * - Exposes window.dashboardStudent with all methods referenced by HTML:
 *    startStudying(), openCaseSimplifier(), practiceAnswers(), openNotes(),
 *    askAI(), setQuery(el), toggleCheck(el), openItem(id), generateStudyPlan()
 * - Handles search box, filters, quick-action cards, study plan, subject progress,
 *   AI assistant, navigation/hamburger, logout, and basic graceful fallbacks.
 *
 * IMPORTANT:
 * - This assumes an existing `window.auth` helper (auth.js) that provides:
 *     - isAuthenticated() -> boolean
 *     - getToken() -> string (JWT)
 *     - logout() -> void
 *     - getUserCurriculum() -> { success, data } OR fallback
 *     - getUserFirstName() -> string
 * - Adjust API_BASE to your backend if different.
 *
 * Copy-paste this file into ../js/dashboard-student.js and ensure auth.js is loaded first.
 */

/* eslint-disable no-console */
(function () {
  // Configuration
  const API_BASE = window.__API_BASE__ || 'http://127.0.0.1:8000';
  const MIN_SEARCH_LENGTH = 2;

  // Internal state
  let state = {
    sessionInitialized: false,
    curriculum: null,
    subjects: [],
    studyPlan: null,
    isEnrolled: true,
    userFirstName: '',
  };

  // DOM shortcuts (populated at init)
  const DOM = {};

  // Utilities
  function q(selector, parent = document) {
    return parent.querySelector(selector);
  }
  function qa(selector, parent = document) {
    return Array.from(parent.querySelectorAll(selector));
  }

  function escapeHtml(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function formatDateRelative(dateString) {
    if (!dateString) return '';
    const d = new Date(dateString);
    const now = new Date();
    const diff = Math.floor((now - d) / 1000);
    if (diff < 60) return 'Just now';
    if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} hours ago`;
    if (diff < 604800) return `${Math.floor(diff / 86400)} days ago`;
    return d.toLocaleDateString();
  }

  function showToast(message, type = 'info', ms = 3500) {
    // Minimal toast UI if not present
    let container = document.getElementById('toastContainer');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toastContainer';
      container.style.position = 'fixed';
      container.style.right = '16px';
      container.style.bottom = '16px';
      container.style.zIndex = 9999;
      document.body.appendChild(container);
    }
    const el = document.createElement('div');
    el.textContent = message;
    el.style.background = type === 'error' ? '#fee2e2' : '#111827';
    el.style.color = type === 'error' ? '#991b1b' : '#fff';
    el.style.padding = '10px 14px';
    el.style.marginTop = '8px';
    el.style.borderRadius = '8px';
    el.style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)';
    container.appendChild(el);
    setTimeout(() => {
      el.style.transition = 'opacity 300ms';
      el.style.opacity = '0';
      setTimeout(() => container.removeChild(el), 300);
    }, ms);
  }

  async function fetchJson(url, opts = {}) {
    const token = window.auth && window.auth.getToken ? window.auth.getToken() : null;
    const headers = Object.assign({}, opts.headers || {});
    if (token) headers['Authorization'] = `Bearer ${token}`;
    headers['Content-Type'] = headers['Content-Type'] || 'application/json';
    try {
      const resp = await fetch(url, Object.assign({}, opts, { headers }));
      const text = await resp.text();
      let json;
      try {
        json = text ? JSON.parse(text) : null;
      } catch (e) {
        json = null;
      }
      if (!resp.ok) {
        const err = (json && (json.detail || json.error)) || resp.statusText || 'Request failed';
        throw new Error(err);
      }
      return json;
    } catch (err) {
      throw err;
    }
  }

  // ---------------------------
  // UI Rendering helpers
  // ---------------------------

  function renderSubjectProgress(subjects = []) {
    const container = DOM.subjectProgress;
    if (!container) return;
    container.innerHTML = '';

    if (!subjects || subjects.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <p>📚 No subjects available</p>
          <p class="text-muted">Subjects will appear here once you're enrolled.</p>
        </div>
      `;
      return;
    }

    const frag = document.createDocumentFragment();
    subjects.forEach((subject) => {
      const card = document.createElement('div');
      card.className = 'subject-card';
      const progressPercent = Math.round(subject.progress || 0);
      const semester = subject.semester ? `Sem ${subject.semester}` : '';
      card.innerHTML = `
        <div class="subject-header">
            <h3>${escapeHtml(subject.name)}</h3>
            <span class="subject-code">${escapeHtml(subject.code || '')}</span>
        </div>
        <div class="progress-bar">
            <div class="progress-fill" style="width: ${progressPercent}%"></div>
        </div>
        <div class="subject-stats">
            <span>${progressPercent}% complete</span>
            <span>${escapeHtml(semester)}</span>
        </div>
      `;
      card.addEventListener('click', () => {
        // Navigate to start-studying with subject id
        window.location.href = `start-studying.html?subject=${subject.id}`;
      });
      frag.appendChild(card);
    });

    container.appendChild(frag);
  }

  function renderStudyPlan(plan) {
    const container = DOM.studyPlanContainer;
    if (!container) return;
    if (!plan || !plan.weeks || plan.weeks.length === 0) {
      container.innerHTML = `
        <div class="study-plan-widget empty">
          <h4>📅 No Active Study Plan</h4>
          <p>Generate a personalized study plan based on your mastery scores and practice history.</p>
          <button class="generate-plan-btn" id="generatePlanBtn">Generate Study Plan</button>
        </div>
      `;
      const btn = q('#generatePlanBtn');
      if (btn) btn.addEventListener('click', () => generateStudyPlan());
      return;
    }

    const currentWeek = plan.weeks[0];
    const summary = escapeHtml(plan.summary || 'Focus on weak topics this week.');
    const tasksHTML = currentWeek.topics.map((topic) => {
      const subjectName = escapeHtml(topic.subject_name || 'Subject');
      const tag = escapeHtml(topic.topic_tag || '');
      const actions = (topic.recommended_actions || []).slice(0, 3).map(a => `<div class="action-item">• ${escapeHtml(a)}</div>`).join('');
      const hours = topic.estimated_hours || 1;
      const priority = topic.priority || 'medium';
      const rationale = escapeHtml(topic.rationale || '');
      return `
        <div class="task-item" data-priority="${priority}">
            <div class="task-header">
                <strong>${subjectName}</strong>
                <span class="priority-badge priority-${priority}">${priority}</span>
            </div>
            <div class="task-topic">${tag}</div>
            <div class="task-actions">${actions}</div>
            <div class="task-meta">
                <span>⏱ ${hours}h</span>
                <span class="task-rationale">${rationale}</span>
            </div>
        </div>
      `;
    }).join('');

    container.innerHTML = `
      <div class="study-plan-widget">
        <h4>✨ Today's Suggested Tasks (Week ${currentWeek.week_number})</h4>
        <p class="plan-summary">${summary}</p>
        ${tasksHTML}
        <button class="view-full-plan-btn" id="viewFullPlanBtn">View Full ${plan.duration_weeks}-Week Plan →</button>
      </div>
    `;

    const btn = q('#viewFullPlanBtn');
    if (btn) btn.addEventListener('click', () => window.location.href = 'study-plan.html');
  }

  function renderSearchResults(results = []) {
    const container = DOM.searchResults;
    if (!container) return;
    container.innerHTML = '';
    if (!results || results.length === 0) {
      container.innerHTML = `<div class="search-empty">No results</div>`;
      return;
    }
    const frag = document.createDocumentFragment();
    results.forEach((r) => {
      const item = document.createElement('div');
      item.className = 'search-result-item';
      const title = escapeHtml(r.title || (r.name || 'Untitled'));
      const meta = escapeHtml((r.type || r.doc_type || '') + (r.subject ? ` • ${r.subject}` : ''));
      item.innerHTML = `
        <div class="search-result-title">${title}</div>
        <div class="search-result-meta">${meta}</div>
      `;
      item.addEventListener('click', () => {
        // route depending on type
        if (r.type === 'subject' || r.doc_type === 'subject') {
          window.location.href = `start-studying.html?subject=${r.id}`;
        } else if (r.doc_type === 'case') {
          window.location.href = `case-detail.html?id=${r.id}`;
        } else if (r.doc_type === 'learn') {
          window.location.href = `learn-content.html?id=${r.id}`;
        } else if (r.doc_type === 'practice') {
          window.location.href = `practice-content.html?id=${r.id}`;
        } else {
          // default fallback
          showToast('Opening item', 'info');
          window.location.href = `/html/item.html?id=${r.id}`;
        }
      });
      frag.appendChild(item);
    });
    container.appendChild(frag);
  }

  // ---------------------------
  // Actions called by HTML (exposed)
  // ---------------------------

  const dashboardStudent = {
    startStudying,
    openCaseSimplifier,
    practiceAnswers,
    openNotes,
    askAI,
    setQuery,
    toggleCheck,
    openItem,
    generateStudyPlan,
  };

  window.dashboardStudent = dashboardStudent; // expose

  // ---------------------------
  // Action Implementations
  // ---------------------------

  function ensureAuthOrRedirect() {
    if (!window.auth || !window.auth.isAuthenticated || !window.auth.isAuthenticated()) {
      // Redirect to login (use html login if present)
      const loginUrls = ['/html/login.html', '/login.html', '/index.html'];
      const candidate = loginUrls.find(u => !!u);
      showToast('You are not authenticated. Redirecting to login...', 'error', 2000);
      setTimeout(() => {
        window.location.href = candidate;
      }, 900);
      return false;
    }
    return true;
  }

  function startStudying() {
    if (!ensureAuthOrRedirect()) return;
    // If subjects available, go to start-studying; else go to onboarding
    const firstSubject = state.subjects && state.subjects[0];
    if (firstSubject) {
      window.location.href = `start-studying.html?subject=${firstSubject.id}`;
    } else {
      window.location.href = 'onboarding.html';
    }
  }

  function openCaseSimplifier() {
    if (!ensureAuthOrRedirect()) return;
    window.location.href = 'case-simplifier.html';
  }

  function practiceAnswers() {
    if (!ensureAuthOrRedirect()) return;
    window.location.href = 'practice-content.html';
  }

  function openNotes() {
    if (!ensureAuthOrRedirect()) return;
    window.location.href = 'my-notes.html';
  }

  async function askAI() {
    if (!ensureAuthOrRedirect()) return;
    const inputEl = DOM.aiQuery;
    const qText = inputEl ? inputEl.value.trim() : '';
    if (!qText || qText.length < 2) {
      showToast('Please type a question for the AI assistant', 'error', 2000);
      return;
    }

    // Basic UI disabled while fetching
    const btn = DOM.aiSubmit;
    if (btn) btn.disabled = true;
    try {
      // Use tutor/chat endpoint if available, else fallback to simple search
      const payload = {
        session_id: null,
        input: qText,
        context: { previous_turns: 2 }
      };
      const json = await fetchJson(`${API_BASE}/api/tutor/chat`, {
        method: 'POST',
        body: JSON.stringify(payload),
      }).catch(() => null);

      if (json && json.content) {
        // Show result in a simple modal or new page; for now use alert / toast + console
        showModalAnswer(json.content, json.provenance || [], json.confidence_score || null);
      } else {
        // fallback: call search endpoint and show top result snippet
        const searchRes = await fetchJson(`${API_BASE}/api/search?q=${encodeURIComponent(qText)}&limit=3`, { method: 'GET' }).catch(() => null);
        if (searchRes && Array.isArray(searchRes.results) && searchRes.results.length > 0) {
          const top = searchRes.results[0];
          showModalAnswer(top.snippet || top.title || 'No snippet available', [top], 0.5);
        } else {
          showToast('No AI or search response available', 'error');
        }
      }
    } catch (err) {
      console.error('askAI error', err);
      showToast(String(err.message || err), 'error');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function setQuery(el) {
    const text = el && (el.textContent || el.innerText) ? el.textContent.trim() : '';
    if (DOM.aiQuery) {
      DOM.aiQuery.value = text.replace(/^["“”']|["“”']$/g, '');
      DOM.aiQuery.focus();
    }
  }

  function toggleCheck(el) {
    if (!el) return;
    const checkbox = el.querySelector('.checkbox');
    if (!checkbox) return;
    checkbox.classList.toggle('checked');
    el.classList.toggle('completed');
  }

  function openItem(id) {
    // Map quick demo ids to pages
    const mapping = {
      case1: 'case-detail.html?id=kesavananda',
      case2: 'case-detail.html?id=maneka',
      note1: 'my-notes.html',
      practice1: 'practice-content.html'
    };
    const path = mapping[id] || `item.html?id=${id}`;
    window.location.href = path;
  }

  // ---------------------------
  // Search handling
  // ---------------------------

  function collectSearchFilters() {
    const checked = qa('.content-type-filter.filter-checkbox').filter(i => i.checked).map(i => i.value);
    return checked;
  }

  async function handleSearch() {
    const qText = DOM.searchInput.value.trim();
    if (!qText || qText.length < MIN_SEARCH_LENGTH) {
      showToast('Type at least 2 characters to search', 'error', 1200);
      return;
    }
    const filters = collectSearchFilters();
    try {
      // Prefer backend search route
      const url = `${API_BASE}/api/search?q=${encodeURIComponent(qText)}&types=${encodeURIComponent(filters.join(','))}&limit=20`;
      const res = await fetchJson(url, { method: 'GET' }).catch(() => null);
      if (res && Array.isArray(res.results)) {
        renderSearchResults(res.results);
      } else {
        // fallback: client-side fuzzy search of loaded curriculum
        const local = (state.curriculum && (state.curriculum.learn || [])).concat(state.subjects || []);
        const lower = qText.toLowerCase();
        const matches = (local || []).filter(item => {
          const title = (item.title || item.name || '').toLowerCase();
          const body = (item.content || item.snippet || '').toLowerCase();
          return title.includes(lower) || body.includes(lower);
        }).slice(0, 20).map(item => ({
          id: item.id, title: item.title || item.name, doc_type: item.doc_type || item.type, subject: item.subject_name, snippet: item.snippet
        }));
        renderSearchResults(matches);
      }
    } catch (err) {
      console.error('Search error', err);
      showToast('Search failed', 'error');
    }
  }

  // ---------------------------
  // Study Plan generation (client -> API)
  // ---------------------------

  async function generateStudyPlan() {
    if (!ensureAuthOrRedirect()) return;
    const weeksStr = prompt('How many weeks do you want to study? (1-12)', '4');
    const weeks = parseInt(weeksStr, 10);
    if (!weeks || weeks < 1 || weeks > 52) {
      showToast('Invalid number of weeks', 'error');
      return;
    }
    try {
      const payload = { duration_weeks: weeks };
      const plan = await fetchJson(`${API_BASE}/api/tutor/suggest_plan`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      state.studyPlan = plan;
      renderStudyPlan(plan);
      showToast('Study plan generated', 'info');
    } catch (err) {
      console.error('generateStudyPlan err', err);
      showToast('Failed to generate study plan', 'error');
    }
  }

  // ---------------------------
  // Modal for AI answers
  // ---------------------------

  function showModalAnswer(content, provenance = [], confidence = null) {
    // Create simple modal
    let modal = document.getElementById('aiAnswerModal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'aiAnswerModal';
      modal.style.position = 'fixed';
      modal.style.left = '0';
      modal.style.top = '0';
      modal.style.right = '0';
      modal.style.bottom = '0';
      modal.style.background = 'rgba(0,0,0,0.4)';
      modal.style.display = 'flex';
      modal.style.alignItems = 'center';
      modal.style.justifyContent = 'center';
      modal.style.zIndex = 99999;
      modal.innerHTML = `
        <div id="aiAnswerBox" style="max-width:900px;width:90%;background:#fff;border-radius:12px;padding:20px;box-shadow:0 12px 40px rgba(0,0,0,0.15);">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
            <h3 style="margin:0">AI Assistant</h3>
            <button id="closeAiAnswerBtn" style="border:none;background:#eee;padding:8px 10px;border-radius:8px;cursor:pointer">Close</button>
          </div>
          <div id="aiAnswerContent" style="max-height:60vh;overflow:auto;padding-bottom:10px;"></div>
          <div id="aiAnswerProvenance" style="margin-top:12px;color:#374151;font-size:13px;"></div>
        </div>
      `;
      document.body.appendChild(modal);
      q('#closeAiAnswerBtn', modal).addEventListener('click', () => modal.remove());
    }
    const contentBox = q('#aiAnswerContent', modal);
    contentBox.innerHTML = (typeof content === 'string') ? `<div style="white-space:pre-wrap;line-height:1.5">${escapeHtml(content)}</div>` : `<pre>${escapeHtml(JSON.stringify(content, null, 2))}</pre>`;
    const provBox = q('#aiAnswerProvenance', modal);
    if (provenance && provenance.length) {
      provBox.innerHTML = `<strong>Sources:</strong> ${provenance.map(p => escapeHtml(p.title || `${p.doc_type}:${p.doc_id}`)).join(', ')}`;
    } else {
      provBox.innerHTML = '';
    }
    modal.style.display = 'flex';
  }

  // ---------------------------
  // Initialization
  // ---------------------------

  async function init() {
    if (state.sessionInitialized) return;
    state.sessionInitialized = true;

    // Query DOM elements referenced in HTML
    DOM.searchInput = q('#searchInput');
    DOM.searchButton = q('#searchButton');
    DOM.searchResults = q('#searchResults');
    DOM.subjectProgress = q('.subject-progress');
    DOM.studyPlanContainer = q('#studyPlanContainer');
    DOM.aiQuery = q('#aiQuery') || q('#aiInput');
    DOM.aiSubmit = q('#sendAIBtn') || q.querySelector && q('#sendAIBtn');
    DOM.generatePlanBtn = q('#generatePlanBtn');

    // Wire search
    if (DOM.searchButton && DOM.searchInput) {
      DOM.searchButton.addEventListener('click', (e) => {
        e.preventDefault();
        handleSearch();
      });
      DOM.searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          handleSearch();
        }
      });
    }

    // Wire ai submit
    if (DOM.aiSubmit) {
      DOM.aiSubmit.addEventListener('click', (e) => {
        e.preventDefault();
        askAI();
      });
    }

    // Quick action cards (IDs from HTML)
    const quickMap = [
      ['#startStudyingCard', startStudying],
      ['#caseSimplifierCard', openCaseSimplifier],
      ['#practiceModeCard', practiceAnswers],
      ['#myNotesCard', openNotes],
      ['#aiTutorCard', () => window.location.href = 'tutor.html'],
    ];
    quickMap.forEach(([sel, fn]) => {
      const el = q(sel);
      if (el) el.addEventListener('click', (ev) => {
        ev.preventDefault();
        fn();
      });
    });

    // Top nav / logout
    const logoutBtn = q('.logout-btn') || q('.nav-logout');
    if (logoutBtn) {
      logoutBtn.addEventListener('click', (e) => {
        e.preventDefault();
        handleLogout();
      });
    }

    // Hamburger toggle
    const hamburger = q('#hamburgerBtn');
    const sidebar = q('#sidebar');
    const overlay = q('#sidebarOverlay');
    if (hamburger && sidebar) {
      hamburger.addEventListener('click', () => {
        sidebar.classList.toggle('open');
        if (overlay) overlay.style.display = sidebar.classList.contains('open') ? 'block' : 'none';
      });
      if (overlay) overlay.addEventListener('click', () => {
        sidebar.classList.remove('open');
        overlay.style.display = 'none';
      });
    }

    // Suggestion chips (if present)
    qa('.chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const text = chip.textContent || chip.innerText || '';
        if (DOM.aiQuery) {
          DOM.aiQuery.value = text.replace(/^["“”']|["“”']$/g, '');
          DOM.aiQuery.focus();
        }
      });
    });

    // Example queries clickable
    qa('.example-query').forEach(el => {
      el.addEventListener('click', () => {
        setQuery(el);
        if (DOM.aiQuery) DOM.aiQuery.focus();
      });
    });

    // Initialize user and curriculum data
    try {
      if (!window.auth || !window.auth.isAuthenticated || !window.auth.getUserCurriculum) {
        // Minimal fallback: populate only UI name
        state.userFirstName = (window.auth && window.auth.getUserFirstName && window.auth.getUserFirstName()) || '';
        q('#studentName') && (q('#studentName').textContent = state.userFirstName ? ` ${state.userFirstName}` : '');
        // don't fail initialization
      } else {
        // call auth helper to get curriculum
        const curriculumResult = await window.auth.getUserCurriculum();
        if (curriculumResult && curriculumResult.success && curriculumResult.data) {
          state.curriculum = curriculumResult.data;
          state.subjects = curriculumResult.data.subjects || [];
          state.userFirstName = window.auth.getUserFirstName ? window.auth.getUserFirstName() : '';
          q('#studentName') && (q('#studentName').textContent = state.userFirstName ? ` ${state.userFirstName}` : '');
          renderSubjectProgress(state.subjects);
        } else {
          // fallback: attempt to fetch from backend
          const res = await fetchJson(`${API_BASE}/api/user/curriculum`, { method: 'GET' }).catch(()=>null);
          if (res && res.data) {
            state.curriculum = res.data;
            state.subjects = res.data.subjects || [];
            renderSubjectProgress(state.subjects);
          }
        }
      }

      // Load active study plan from backend if any
      const plan = await fetchJson(`${API_BASE}/api/study-plan/active`, { method: 'GET' }).catch(()=>null);
      if (plan && plan.has_active_plan && plan.plan) {
        state.studyPlan = plan.plan;
        renderStudyPlan(plan.plan);
      } else {
        // render empty placeholder
        renderStudyPlan(null);
      }
    } catch (err) {
      console.warn('Initialization fetch failed', err);
      renderStudyPlan(null);
    }
  }

  // ---------------------------
  // Logout handler
  // ---------------------------
  function handleLogout() {
    if (window.auth && window.auth.logout) {
      try {
        window.auth.logout();
      } catch (e) {
        console.error('auth.logout failed', e);
      }
    }
    // try to clear token storage and redirect to login
    try {
      localStorage.removeItem('token');
    } catch (e) {}
    showToast('Logged out', 'info', 900);
    setTimeout(() => {
      window.location.href = '/html/login.html';
    }, 700);
  }

  // ---------------------------
  // Wire DOMContentLoaded
  // ---------------------------
  document.addEventListener('DOMContentLoaded', () => {
    // basic element mapping
    DOM.searchInput = q('#searchInput');
    DOM.searchButton = q('#searchButton');
    DOM.searchResults = q('#searchResults');
    DOM.subjectProgress = q('.subject-progress');
    DOM.studyPlanContainer = q('#studyPlanContainer');
    DOM.aiQuery = q('#aiQuery') || q('#aiInput');
    DOM.aiSubmit = q('#sendAIBtn') || q('#sendAIBtn') || q('#sendAIBtn');
    DOM.generatePlanBtn = q('#generatePlanBtn');

    // Initialize after slight delay to ensure auth.js loaded
    setTimeout(init, 80);
  });

  // ---------------------------
  // Defensive exports for testing or console usage
  // ---------------------------
  window.__JURIS_DASH__ = {
    state,
    init,
    renderSubjectProgress,
    renderStudyPlan,
    renderSearchResults,
    fetchJson,
  };
})();
