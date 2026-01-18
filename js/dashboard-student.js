/**
 * dashboard-student.js
 * Enhanced dashboard with improved UI/UX
 */

(function () {
  const API_BASE = window.__API_BASE__ || 'http://127.0.0.1:8000';
  const MIN_SEARCH_LENGTH = 2;

  let state = {
    sessionInitialized: false,
    curriculum: null,
    subjects: [],
    studyPlan: null,
    isEnrolled: true,
    userFirstName: '',
    dashboardStats: null,
    lastActivity: null,
    isLoading: true
  };

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

  function showToast(message, type = 'info', ms = 3500) {
    let container = document.getElementById('toastContainer');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toastContainer';
      container.style.position = 'fixed';
      container.style.right = '20px';
      container.style.bottom = '20px';
      container.style.zIndex = 9999;
      document.body.appendChild(container);
    }
    const el = document.createElement('div');
    el.textContent = message;
    el.style.background = type === 'error' ? '#fee2e2' : '#0F172A';
    el.style.color = type === 'error' ? '#991b1b' : '#fff';
    el.style.padding = '12px 20px';
    el.style.marginTop = '10px';
    el.style.borderRadius = '10px';
    el.style.boxShadow = '0 4px 16px rgba(0,0,0,0.15)';
    el.style.fontSize = '14px';
    el.style.fontWeight = '500';
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

  // UI Rendering
  function renderSubjectProgress(subjects = []) {
    const container = q('#subjectProgressContainer');
    if (!container) return;
    container.innerHTML = '';

    if (!subjects || subjects.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <p style="font-size:48px;margin-bottom:12px;">📚</p>
          <p style="font-weight:600;margin-bottom:6px;">No subjects available</p>
          <p class="text-muted">Subjects will appear once you're enrolled.</p>
        </div>
      `;
      return;
    }

    const frag = document.createDocumentFragment();
    subjects.forEach((subject) => {
    const card = document.createElement('div');
    card.className = 'subject-card';
    if (String(StorageService.getItem(STORAGE_KEYS.CURRENT_SUBJECT_ID)) === String(subject.id)) {
      card.classList.add('active-context');
      card.style.border = '2px solid #3b82f6';
      card.style.boxShadow = '0 0 10px rgba(59, 130, 246, 0.3)';
    }
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
      card.addEventListener('click', async () => {
        try {
          // Phase 9.1: Select subject (validate on backend)
          await window.api.selectSubject(subject.id);
          StorageService.setItem(STORAGE_KEYS.CURRENT_SUBJECT_ID, subject.id);
          
          // Phase 9.2: Resume logic
          const resume = await window.api.getResumeContext(subject.id);
          handleResumeNavigation(resume);
        } catch (err) {
          console.error('Subject selection error', err);
          showToast(err.message || 'Failed to select subject', 'error');
        }
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
          <h4 style="font-size:48px;margin-bottom:12px;">📅</h4>
          <h4>No Active Study Plan</h4>
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
      container.innerHTML = `<div class="search-empty">No results found</div>`;
      container.style.display = 'none';
      return;
    }
    container.style.display = 'block';
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
        if (r.type === 'subject' || r.doc_type === 'subject') {
          window.location.href = `start-studying.html?subject=${r.id}`;
        } else if (r.doc_type === 'case') {
          window.location.href = `case-detail.html?id=${r.id}`;
        } else if (r.doc_type === 'learn') {
          window.location.href = `learn-content.html?id=${r.id}`;
        } else if (r.doc_type === 'practice') {
          window.location.href = `practice-content.html?id=${r.id}`;
        } else {
          showToast('Opening item', 'info');
          window.location.href = `/html/item.html?id=${r.id}`;
        }
      });
      frag.appendChild(item);
    });
    container.appendChild(frag);
  }

  function handleResumeNavigation(resume) {
    if (!resume) return;
    const { type, content_id, subject_id, module_id } = resume;
    
    if (type === 'learn') {
      window.location.href = `learn-content.html?id=${content_id}&subject=${subject_id}&module=${module_id}`;
    } else if (type === 'case') {
      window.location.href = `case-detail.html?id=${content_id}&subject=${subject_id}&module=${module_id}`;
    } else if (type === 'practice') {
      // If content_id is missing, it goes to the practice entry for the subject
      const url = content_id 
        ? `practice-content.html?id=${content_id}&subject=${subject_id}&module=${module_id}`
        : `practice-content.html?subject=${subject_id}`;
      window.location.href = url;
    } else if (type === 'revision') {
      window.location.href = `start-studying.html?subject=${subject_id}&view=revision`;
    }
  }

  // Actions
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

  window.dashboardStudent = dashboardStudent;

  function ensureAuthOrRedirect() {
    if (!window.auth || !window.auth.isAuthenticated || !window.auth.isAuthenticated()) {
      const loginUrls = ['/html/login.html', '/login.html', '/index.html'];
      const candidate = loginUrls.find(u => !!u);
      showToast('You are not authenticated. Redirecting...', 'error', 2000);
      setTimeout(() => {
        window.location.href = candidate;
      }, 900);
      return false;
    }
    return true;
  }

  async function startStudying() {
    if (!ensureAuthOrRedirect()) return;
    
    // Phase 9.1 & 9.2: Use active context or first subject
    const activeSubjectId = StorageService.getItem(STORAGE_KEYS.CURRENT_SUBJECT_ID);
    const firstSubject = state.subjects && state.subjects[0];
    const targetId = activeSubjectId || (firstSubject ? firstSubject.id : null);
    
    if (targetId) {
      try {
        const resume = await window.api.getResumeContext(targetId);
        handleResumeNavigation(resume);
      } catch (err) {
        console.error('Resume error', err);
        // Fallback to start-studying page
        window.location.href = `start-studying.html?subject=${targetId}`;
      }
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

    const btn = DOM.aiSubmit;
    if (btn) btn.disabled = true;
    try {
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
        showModalAnswer(json.content, json.provenance || [], json.confidence_score || null);
      } else {
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
      DOM.aiQuery.value = text.replace(/^[""]|[""]$/g, '');
      DOM.aiQuery.focus();
    }
  }

  function toggleCheck(el) {
    if (!el) return;
    const checkbox = el.querySelector('.task-checkbox');
    if (!checkbox) return;
    checkbox.classList.toggle('checked');
    el.classList.toggle('completed');
  }

  function openItem(id) {
    const mapping = {
      case1: 'case-detail.html?id=kesavananda',
      case2: 'case-detail.html?id=maneka',
      note1: 'my-notes.html',
      practice1: 'practice-content.html'
    };
    const path = mapping[id] || `item.html?id=${id}`;
    window.location.href = path;
  }

  async function handleSearch() {
    const qText = DOM.searchInput.value.trim();
    if (!qText || qText.length < MIN_SEARCH_LENGTH) {
      DOM.searchResults.style.display = 'none';
      return;
    }
    try {
      const url = `${API_BASE}/api/search?q=${encodeURIComponent(qText)}&limit=20`;
      const res = await fetchJson(url, { method: 'GET' }).catch(() => null);
      if (res && Array.isArray(res.results)) {
        renderSearchResults(res.results);
      } else {
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

  function showModalAnswer(content, provenance = [], confidence = null) {
    let modal = document.getElementById('aiAnswerModal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'aiAnswerModal';
      modal.style.position = 'fixed';
      modal.style.left = '0';
      modal.style.top = '0';
      modal.style.right = '0';
      modal.style.bottom = '0';
      modal.style.background = 'rgba(0,0,0,0.5)';
      modal.style.display = 'flex';
      modal.style.alignItems = 'center';
      modal.style.justifyContent = 'center';
      modal.style.zIndex = 99999;
      modal.innerHTML = `
        <div id="aiAnswerBox" style="max-width:800px;width:90%;background:#fff;border-radius:16px;padding:32px;box-shadow:0 20px 60px rgba(0,0,0,0.3);">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;">
            <h3 style="margin:0;font-size:20px;font-weight:700;">AI Assistant</h3>
            <button id="closeAiAnswerBtn" style="border:none;background:#f8fafc;padding:8px 12px;border-radius:8px;cursor:pointer;font-weight:600;">Close</button>
          </div>
          <div id="aiAnswerContent" style="max-height:60vh;overflow:auto;padding-bottom:16px;line-height:1.7;"></div>
          <div id="aiAnswerProvenance" style="margin-top:16px;color:#64748b;font-size:13px;"></div>
        </div>
      `;
      document.body.appendChild(modal);
      q('#closeAiAnswerBtn', modal).addEventListener('click', () => modal.remove());
    }
    const contentBox = q('#aiAnswerContent', modal);
    contentBox.innerHTML = (typeof content === 'string') ? `<div style="white-space:pre-wrap;">${escapeHtml(content)}</div>` : `<pre>${escapeHtml(JSON.stringify(content, null, 2))}</pre>`;
    const provBox = q('#aiAnswerProvenance', modal);
    if (provenance && provenance.length) {
      provBox.innerHTML = `<strong>Sources:</strong> ${provenance.map(p => escapeHtml(p.title || `${p.doc_type}:${p.doc_id}`)).join(', ')}`;
    } else {
      provBox.innerHTML = '';
    }
    modal.style.display = 'flex';
  }

  async function init() {
    if (state.sessionInitialized) return;
    state.sessionInitialized = true;

    DOM.searchInput = q('#searchInput');
    DOM.searchButton = q('#searchButton');
    DOM.searchResults = q('#searchResults');
    DOM.subjectProgress = q('#subjectProgressContainer');
    DOM.studyPlanContainer = q('#studyPlanContainer');
    DOM.aiQuery = q('#aiQuery');
    DOM.aiSubmit = q('#sendAIBtn');

    if (DOM.searchInput) {
      DOM.searchInput.addEventListener('input', () => {
        if (DOM.searchInput.value.trim().length >= MIN_SEARCH_LENGTH) {
          handleSearch();
        } else {
          DOM.searchResults.style.display = 'none';
        }
      });
      DOM.searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          handleSearch();
        }
      });
    }

    if (DOM.aiSubmit) {
      DOM.aiSubmit.addEventListener('click', (e) => {
        e.preventDefault();
        askAI();
      });
    }

    if (DOM.aiQuery) {
      DOM.aiQuery.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          askAI();
        }
      });
    }

    const logoutBtn = q('.logout-btn') || q('.nav-logout');
    if (logoutBtn) {
      logoutBtn.addEventListener('click', (e) => {
        e.preventDefault();
        handleLogout();
      });
    }

    const hamburger = q('#hamburgerBtn');
    const sidebar = q('#sidebar');
    const overlay = q('#sidebarOverlay');
    if (hamburger && sidebar) {
      hamburger.addEventListener('click', () => {
        sidebar.classList.toggle('open');
        if (overlay) overlay.classList.toggle('active');
      });
      if (overlay) overlay.addEventListener('click', () => {
        sidebar.classList.remove('open');
        overlay.classList.remove('active');
      });
    }

    qa('.suggestion-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const text = chip.textContent || chip.innerText || '';
        if (DOM.aiQuery) {
          DOM.aiQuery.value = text.replace(/^[""]|[""]$/g, '');
          DOM.aiQuery.focus();
        }
      });
    });

    try {
      if (!window.auth || !window.auth.isAuthenticated || !window.auth.getUserCurriculum) {
        state.userFirstName = (window.auth && window.auth.getUserFirstName && window.auth.getUserFirstName()) || '';
        const nameEl = q('#studentNameFull');
        if (nameEl && state.userFirstName) {
          nameEl.textContent = `, ${state.userFirstName}`;
        }
        const avatarEl = q('#studentName');
        if (avatarEl && state.userFirstName) {
          avatarEl.textContent = state.userFirstName.charAt(0).toUpperCase();
        }
      } else {
          const subjectsResult = await window.api.getSubjects();
          if (subjectsResult) {
            state.subjects = subjectsResult.map(s => ({
              ...s,
              name: s.title // Map title to name for existing render logic
            }));
            state.userFirstName = window.auth.getUserFirstName ? window.auth.getUserFirstName() : '';
            const nameEl = q('#studentNameFull');
            if (nameEl && state.userFirstName) {
              nameEl.textContent = `, ${state.userFirstName}`;
            }
            const avatarEl = q('#studentName');
            if (avatarEl && state.userFirstName) {
              avatarEl.textContent = state.userFirstName.charAt(0).toUpperCase();
            }
            renderSubjectProgress(state.subjects);
          } else {
            const res = await fetchJson(`${API_BASE}/api/user/curriculum`, { method: 'GET' }).catch(()=>null);
            if (res && res.data) {
              state.curriculum = res.data;
              state.subjects = res.data.subjects || [];
              renderSubjectProgress(state.subjects);
            }
          }
      }

      const plan = await fetchJson(`${API_BASE}/api/study-plan/active`, { method: 'GET' }).catch(()=>null);
      if (plan && plan.has_active_plan && plan.plan) {
        state.studyPlan = plan.plan;
        renderStudyPlan(plan.plan);
      } else {
        renderStudyPlan(null);
      }
    } catch (err) {
      console.warn('Initialization fetch failed', err);
      renderStudyPlan(null);
    }
  }

  function handleLogout() {
    if (window.auth && window.auth.logout) {
      try {
        window.auth.logout();
      } catch (e) {
        console.error('auth.logout failed', e);
      }
    }
    try {
      localStorage.removeItem('token');
    } catch (e) {}
    showToast('Logged out', 'info', 900);
    setTimeout(() => {
      window.location.href = '/html/login.html';
    }, 700);
  }

  document.addEventListener('DOMContentLoaded', () => {
    setTimeout(init, 80);
  });

  window.__JURIS_DASH__ = {
    state,
    init,
    renderSubjectProgress,
    renderStudyPlan,
    renderSearchResults,
    fetchJson,
  };
})();