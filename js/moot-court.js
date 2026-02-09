(function() {
    'use strict';

    // ============================================
    // STORAGE LAYER (localStorage)
    // ============================================
    const STORAGE_KEY = 'juris_moot_projects';

    function loadProjects() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            return raw ? JSON.parse(raw) : [];
        } catch (e) {
            console.error('Failed to load moot projects:', e);
            return [];
        }
    }

    function saveProjects(projects) {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(projects));
        } catch (e) {
            console.error('Failed to save moot projects:', e);
        }
    }

    function getProject(id) {
        return loadProjects().find(p => p.id === id) || null;
    }

    function updateProject(id, updates) {
        const projects = loadProjects();
        const idx = projects.findIndex(p => p.id === id);
        if (idx === -1) return null;
        projects[idx] = { ...projects[idx], ...updates, updatedAt: Date.now() };
        saveProjects(projects);
        return projects[idx];
    }

    function deleteProject(id) {
        const projects = loadProjects().filter(p => p.id !== id);
        saveProjects(projects);
    }

    function generateId() {
        return 'moot_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6);
    }

    // ============================================
    // STATE
    // ============================================
    const state = {
        currentView: 'list',       // list | create | workspace
        currentProjectId: null,
        currentIssueIndex: null,
        editingIssueIndex: null,
        saveTimeout: null,
        dragSourceIndex: null
    };

    // ============================================
    // DOM HELPERS
    // ============================================
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    function show(el) { if (el) el.classList.remove('hidden'); }
    function hide(el) { if (el) el.classList.add('hidden'); }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // ============================================
    // VIEW MANAGEMENT
    // ============================================
    function showView(view) {
        state.currentView = view;
        hide($('#projectListView'));
        hide($('#createProjectView'));
        hide($('#workspaceView'));

        if (view === 'list') {
            show($('#projectListView'));
            renderProjectList();
        } else if (view === 'create') {
            show($('#createProjectView'));
            resetCreateForm();
        } else if (view === 'workspace') {
            show($('#workspaceView'));
            renderWorkspace();
        }
    }

    // ============================================
    // PROJECT LIST
    // ============================================
    function renderProjectList() {
        const projects = loadProjects();
        const grid = $('#projectsGrid');
        const emptyState = $('#emptyState');

        if (projects.length === 0) {
            hide(grid);
            show(emptyState);
            return;
        }

        hide(emptyState);
        show(grid);

        // Sort by last updated
        const sorted = [...projects].sort((a, b) => (b.updatedAt || b.createdAt) - (a.updatedAt || a.createdAt));

        grid.innerHTML = sorted.map(project => {
            const progress = computeProjectProgress(project);
            const issueCount = (project.issues || []).length;
            const dateStr = formatDate(project.updatedAt || project.createdAt);

            return `
                <div class="project-card" data-id="${project.id}">
                    <div class="project-card-title">${escapeHtml(project.title)}</div>
                    <div class="project-card-meta">
                        <span class="project-card-badge ${project.side}">${escapeHtml(project.side)}</span>
                        ${project.domain ? `<span class="project-card-badge domain">${escapeHtml(project.domain)}</span>` : ''}
                    </div>
                    <div class="project-card-progress">
                        <span>${issueCount} issue${issueCount !== 1 ? 's' : ''}</span>
                        <div class="project-card-progress-bar">
                            <div class="project-card-progress-fill" style="width: ${progress}%"></div>
                        </div>
                        <span>${progress}%</span>
                    </div>
                    <div class="project-card-date">Last updated ${dateStr}</div>
                </div>
            `;
        }).join('');

        // Bind click events
        grid.querySelectorAll('.project-card').forEach(card => {
            card.addEventListener('click', () => {
                state.currentProjectId = card.dataset.id;
                state.currentIssueIndex = null;
                showView('workspace');
            });
        });
    }

    function computeProjectProgress(project) {
        const issues = project.issues || [];
        if (issues.length === 0) return 0;

        let filledFields = 0;
        let totalFields = 0;

        issues.forEach(issue => {
            const irac = issue.irac || {};
            const fields = ['issue', 'rule', 'application', 'conclusion'];
            fields.forEach(f => {
                totalFields++;
                if (irac[f] && irac[f].trim().length > 0) filledFields++;
            });
        });

        return totalFields === 0 ? 0 : Math.round((filledFields / totalFields) * 100);
    }

    function formatDate(ts) {
        if (!ts) return '';
        const d = new Date(ts);
        const now = new Date();
        const diffMs = now - d;
        const diffMins = Math.floor(diffMs / 60000);
        if (diffMins < 1) return 'just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        const diffHrs = Math.floor(diffMins / 60);
        if (diffHrs < 24) return `${diffHrs}h ago`;
        const diffDays = Math.floor(diffHrs / 24);
        if (diffDays < 7) return `${diffDays}d ago`;
        return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
    }

    // ============================================
    // CREATE PROJECT
    // ============================================
    let selectedSide = null;

    function resetCreateForm() {
        $('#mootTitle').value = '';
        $('#mootProposition').value = '';
        $('#mootCourt').value = '';
        $('#mootDomain').value = '';
        selectedSide = null;
        $$('.side-btn').forEach(b => b.classList.remove('active'));
    }

    function handleCreateProject() {
        const title = $('#mootTitle').value.trim();
        const proposition = $('#mootProposition').value.trim();
        const court = $('#mootCourt').value.trim();
        const domain = $('#mootDomain').value.trim();

        if (!title) {
            $('#mootTitle').focus();
            return;
        }
        if (!proposition) {
            $('#mootProposition').focus();
            return;
        }
        if (!selectedSide) {
            // Flash the side selector briefly
            $$('.side-btn').forEach(b => {
                b.style.borderColor = '#DC2626';
                setTimeout(() => { b.style.borderColor = ''; }, 1000);
            });
            return;
        }

        const project = {
            id: generateId(),
            title,
            proposition,
            side: selectedSide,
            court: court || '',
            domain: domain || '',
            issues: [],
            createdAt: Date.now(),
            updatedAt: Date.now()
        };

        const projects = loadProjects();
        projects.push(project);
        saveProjects(projects);

        state.currentProjectId = project.id;
        state.currentIssueIndex = null;
        showView('workspace');
    }

    // ============================================
    // WORKSPACE
    // ============================================
    function renderWorkspace() {
        const project = getProject(state.currentProjectId);
        if (!project) {
            showView('list');
            return;
        }

        // Header
        $('#workspaceTitle').textContent = project.title;

        const sideBadge = $('#workspaceSide');
        sideBadge.textContent = project.side;
        sideBadge.className = `badge badge-side ${project.side}`;

        const courtBadge = $('#workspaceCourt');
        if (project.court) {
            courtBadge.textContent = project.court;
            show(courtBadge);
        } else {
            hide(courtBadge);
        }

        const domainBadge = $('#workspaceDomain');
        if (project.domain) {
            domainBadge.textContent = project.domain;
            show(domainBadge);
        } else {
            hide(domainBadge);
        }

        // Proposition body
        $('#propositionBody').textContent = project.proposition;

        // Render issues
        renderIssues();
        renderIRAC();
    }

    // ============================================
    // ISSUES
    // ============================================
    function renderIssues() {
        const project = getProject(state.currentProjectId);
        if (!project) return;

        const list = $('#issuesList');
        const emptyEl = $('#issuesEmpty');

        if (project.issues.length === 0) {
            list.innerHTML = '';
            show(emptyEl);
            return;
        }

        hide(emptyEl);

        list.innerHTML = project.issues.map((issue, i) => {
            const irac = issue.irac || {};
            const filled = ['issue', 'rule', 'application', 'conclusion'].filter(f => irac[f] && irac[f].trim()).length;
            let statusClass = 'incomplete';
            let statusLabel = 'Not started';
            if (filled === 4) { statusClass = 'complete'; statusLabel = 'Complete'; }
            else if (filled > 0) { statusClass = 'partial'; statusLabel = `${filled}/4 fields`; }

            const isActive = state.currentIssueIndex === i;

            return `
                <div class="issue-item ${isActive ? 'active' : ''}" data-index="${i}" draggable="true">
                    <span class="issue-drag-handle" title="Drag to reorder">&#x2630;</span>
                    <span class="issue-number">${i + 1}</span>
                    <div class="issue-content">
                        <div class="issue-text">${escapeHtml(issue.text)}</div>
                        <div class="issue-status">
                            <span class="issue-status-dot ${statusClass}"></span>
                            <span class="issue-status-label">${statusLabel}</span>
                        </div>
                    </div>
                    <div class="issue-actions">
                        <button class="issue-action-btn edit" data-index="${i}" title="Edit issue">&#9998;</button>
                        <button class="issue-action-btn delete" data-index="${i}" title="Delete issue">&#10005;</button>
                    </div>
                </div>
            `;
        }).join('');

        // Bind events
        list.querySelectorAll('.issue-item').forEach(item => {
            item.addEventListener('click', (e) => {
                if (e.target.closest('.issue-action-btn') || e.target.closest('.issue-drag-handle')) return;
                const idx = parseInt(item.dataset.index);
                state.currentIssueIndex = idx;
                renderIssues();
                renderIRAC();
            });

            // Drag and drop
            item.addEventListener('dragstart', handleDragStart);
            item.addEventListener('dragover', handleDragOver);
            item.addEventListener('drop', handleDrop);
            item.addEventListener('dragend', handleDragEnd);
        });

        // Edit / Delete buttons
        list.querySelectorAll('.issue-action-btn.edit').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                openEditIssueModal(parseInt(btn.dataset.index));
            });
        });

        list.querySelectorAll('.issue-action-btn.delete').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                deleteIssue(parseInt(btn.dataset.index));
            });
        });
    }

    // Drag and Drop
    function handleDragStart(e) {
        state.dragSourceIndex = parseInt(e.currentTarget.dataset.index);
        e.currentTarget.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
    }

    function handleDragOver(e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
    }

    function handleDrop(e) {
        e.preventDefault();
        const targetIndex = parseInt(e.currentTarget.dataset.index);
        if (state.dragSourceIndex === null || state.dragSourceIndex === targetIndex) return;

        const project = getProject(state.currentProjectId);
        if (!project) return;

        const issues = [...project.issues];
        const [moved] = issues.splice(state.dragSourceIndex, 1);
        issues.splice(targetIndex, 0, moved);

        // Adjust current issue index to follow the selected issue
        if (state.currentIssueIndex === state.dragSourceIndex) {
            state.currentIssueIndex = targetIndex;
        } else if (
            state.currentIssueIndex !== null &&
            state.currentIssueIndex > state.dragSourceIndex &&
            state.currentIssueIndex <= targetIndex
        ) {
            state.currentIssueIndex--;
        } else if (
            state.currentIssueIndex !== null &&
            state.currentIssueIndex < state.dragSourceIndex &&
            state.currentIssueIndex >= targetIndex
        ) {
            state.currentIssueIndex++;
        }

        updateProject(state.currentProjectId, { issues });
        renderIssues();
    }

    function handleDragEnd(e) {
        state.dragSourceIndex = null;
        $$('.issue-item').forEach(item => item.classList.remove('dragging'));
    }

    function deleteIssue(index) {
        const project = getProject(state.currentProjectId);
        if (!project) return;

        const issues = [...project.issues];
        issues.splice(index, 1);

        // Adjust current issue index
        if (state.currentIssueIndex !== null) {
            if (state.currentIssueIndex === index) {
                state.currentIssueIndex = issues.length > 0 ? Math.min(index, issues.length - 1) : null;
            } else if (state.currentIssueIndex > index) {
                state.currentIssueIndex--;
            }
        }

        updateProject(state.currentProjectId, { issues });
        renderIssues();
        renderIRAC();
    }

    // ============================================
    // ISSUE MODAL
    // ============================================
    function openAddIssueModal() {
        state.editingIssueIndex = null;
        $('#issueModalTitle').textContent = 'Add Legal Issue';
        $('#issueText').value = '';
        show($('#issueModal'));
        setTimeout(() => $('#issueText').focus(), 100);
    }

    function openEditIssueModal(index) {
        const project = getProject(state.currentProjectId);
        if (!project || !project.issues[index]) return;

        state.editingIssueIndex = index;
        $('#issueModalTitle').textContent = 'Edit Legal Issue';
        $('#issueText').value = project.issues[index].text;
        show($('#issueModal'));
        setTimeout(() => $('#issueText').focus(), 100);
    }

    function handleSaveIssue() {
        const text = $('#issueText').value.trim();
        if (!text) {
            $('#issueText').focus();
            return;
        }

        const project = getProject(state.currentProjectId);
        if (!project) return;

        const issues = [...project.issues];

        if (state.editingIssueIndex !== null) {
            // Edit existing
            issues[state.editingIssueIndex] = {
                ...issues[state.editingIssueIndex],
                text
            };
        } else {
            // Add new
            issues.push({
                id: generateId(),
                text,
                irac: { issue: '', rule: '', application: '', conclusion: '' }
            });
            // Auto-select the new issue
            state.currentIssueIndex = issues.length - 1;
        }

        updateProject(state.currentProjectId, { issues });
        hide($('#issueModal'));
        renderIssues();
        renderIRAC();
    }

    // ============================================
    // IRAC BUILDER
    // ============================================
    function renderIRAC() {
        const project = getProject(state.currentProjectId);
        if (!project) return;

        const emptyEl = $('#iracEmpty');
        const workspaceEl = $('#iracWorkspace');

        if (state.currentIssueIndex === null || !project.issues[state.currentIssueIndex]) {
            show(emptyEl);
            hide(workspaceEl);
            return;
        }

        hide(emptyEl);
        show(workspaceEl);

        const issue = project.issues[state.currentIssueIndex];
        const irac = issue.irac || {};

        // Counter
        $('#iracIssueCounter').textContent = `Issue ${state.currentIssueIndex + 1} of ${project.issues.length}`;

        // Nav buttons
        $('#prevIssueBtn').disabled = state.currentIssueIndex === 0;
        $('#nextIssueBtn').disabled = state.currentIssueIndex === project.issues.length - 1;

        // Fill fields
        $('#iracIssue').value = irac.issue || '';
        $('#iracRule').value = irac.rule || '';
        $('#iracApplication').value = irac.application || '';
        $('#iracConclusion').value = irac.conclusion || '';

        // Status
        updateIRACStatus();

        // Save indicator
        $('#iracSaveIndicator').textContent = 'All changes saved';
        $('#iracSaveIndicator').classList.remove('saving');
    }

    function updateIRACStatus() {
        const project = getProject(state.currentProjectId);
        if (!project || state.currentIssueIndex === null) return;

        const issue = project.issues[state.currentIssueIndex];
        const irac = issue.irac || {};
        const filled = ['issue', 'rule', 'application', 'conclusion'].filter(f => irac[f] && irac[f].trim()).length;

        const statusEl = $('#iracStatus');
        if (filled === 4) {
            statusEl.textContent = 'Complete';
            statusEl.className = 'irac-status complete';
        } else if (filled > 0) {
            statusEl.textContent = `${filled}/4 fields`;
            statusEl.className = 'irac-status partial';
        } else {
            statusEl.textContent = 'Not started';
            statusEl.className = 'irac-status incomplete';
        }
    }

    function handleIRACInput(field) {
        if (state.currentProjectId === null || state.currentIssueIndex === null) return;

        const value = $(`#irac${capitalize(field)}`).value;

        // Debounced save
        $('#iracSaveIndicator').textContent = 'Saving...';
        $('#iracSaveIndicator').classList.add('saving');

        if (state.saveTimeout) clearTimeout(state.saveTimeout);
        state.saveTimeout = setTimeout(() => {
            const project = getProject(state.currentProjectId);
            if (!project || !project.issues[state.currentIssueIndex]) return;

            const issues = [...project.issues];
            issues[state.currentIssueIndex] = {
                ...issues[state.currentIssueIndex],
                irac: {
                    ...(issues[state.currentIssueIndex].irac || {}),
                    [field]: value
                }
            };

            updateProject(state.currentProjectId, { issues });
            updateIRACStatus();
            renderIssues(); // Update status dots in issue list

            $('#iracSaveIndicator').textContent = 'All changes saved';
            $('#iracSaveIndicator').classList.remove('saving');
        }, 400);
    }

    function capitalize(str) {
        return str.charAt(0).toUpperCase() + str.slice(1);
    }

    // ============================================
    // DELETE PROJECT
    // ============================================
    let deleteTarget = null;

    function openDeleteProjectModal() {
        deleteTarget = 'project';
        $('#deleteModalText').textContent = 'Are you sure you want to delete this moot project and all its issues? This action cannot be undone.';
        show($('#deleteModal'));
    }

    function handleConfirmDelete() {
        if (deleteTarget === 'project' && state.currentProjectId) {
            deleteProject(state.currentProjectId);
            state.currentProjectId = null;
            state.currentIssueIndex = null;
            hide($('#deleteModal'));
            showView('list');
        }
        deleteTarget = null;
    }

    // ============================================
    // PHASE 2: AI FEATURES
    // ============================================

    const AI_API_BASE = '/api/moot-court';
    let currentJudgeMode = 'summarize';

    // ---------- AI Coach ----------
    function initAICoach() {
        $('#toggleCoachBtn').addEventListener('click', () => {
            const panel = $('#aiCoachPanel');
            if (panel.classList.contains('hidden')) {
                show(panel);
            } else {
                hide(panel);
            }
        });

        $('#closeCoachBtn').addEventListener('click', () => hide($('#aiCoachPanel')));

        $('#aiCoachSendBtn').addEventListener('click', handleCoachQuestion);
        $('#aiCoachInput').addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleCoachQuestion();
            }
        });
    }

    async function handleCoachQuestion() {
        const input = $('#aiCoachInput');
        const question = input.value.trim();
        if (!question) return;

        const project = getProject(state.currentProjectId);
        if (!project) return;

        // Add user message
        addCoachMessage('user', question);
        input.value = '';

        // Show loading
        const loadingId = addCoachLoading();

        try {
            const currentIssue = state.currentIssueIndex !== null ? project.issues[state.currentIssueIndex] : null;
            const irac = currentIssue?.irac || {};

            const response = await fetch(`${AI_API_BASE}/ai-coach`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    question,
                    proposition: project.proposition,
                    side: project.side,
                    current_issue: currentIssue?.text || '',
                    irac
                })
            });

            removeCoachLoading(loadingId);

            if (!response.ok) throw new Error('AI Coach request failed');
            const data = await response.json();
            addCoachMessage('ai', data.response);
        } catch (err) {
            removeCoachLoading(loadingId);
            addCoachMessage('ai', 'Sorry, the AI Coach is temporarily unavailable. Please try again later.');
            console.error('AI Coach error:', err);
        }
    }

    function addCoachMessage(role, text) {
        const container = $('#aiCoachMessages');
        const msg = document.createElement('div');
        msg.className = `ai-coach-msg ${role}`;
        msg.innerHTML = formatCoachText(text);
        container.appendChild(msg);
        container.scrollTop = container.scrollHeight;
    }

    function formatCoachText(text) {
        // Convert markdown-like formatting to HTML
        return text
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\n/g, '<br>')
            .replace(/- (.*?)(?=<br>|$)/g, '• $1');
    }

    function addCoachLoading() {
        const container = $('#aiCoachMessages');
        const id = 'loading_' + Date.now();
        const loading = document.createElement('div');
        loading.id = id;
        loading.className = 'ai-coach-msg ai ai-loading';
        loading.innerHTML = '<span class="ai-loading-dot"></span><span class="ai-loading-dot"></span><span class="ai-loading-dot"></span> Thinking...';
        container.appendChild(loading);
        container.scrollTop = container.scrollHeight;
        return id;
    }

    function removeCoachLoading(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    // ---------- AI Review ----------
    function initAIReview() {
        $('#aiReviewBtn').addEventListener('click', handleAIReview);
        $('#closeAiReview').addEventListener('click', () => hide($('#aiReviewOutput')));
    }

    async function handleAIReview() {
        const project = getProject(state.currentProjectId);
        if (!project || state.currentIssueIndex === null) return;

        const issue = project.issues[state.currentIssueIndex];
        const output = $('#aiReviewOutput');
        const body = $('#aiReviewBody');

        show(output);
        body.innerHTML = '<div class="ai-loading"><span class="ai-loading-dot"></span><span class="ai-loading-dot"></span><span class="ai-loading-dot"></span> Analyzing IRAC...</div>';

        try {
            const response = await fetch(`${AI_API_BASE}/ai-review`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    proposition: project.proposition,
                    side: project.side,
                    issue_text: issue.text,
                    irac: issue.irac || {}
                })
            });

            if (!response.ok) throw new Error('AI Review request failed');
            const data = await response.json();
            body.innerHTML = formatAIOutput(data.review);
        } catch (err) {
            body.innerHTML = '<p style="color: var(--danger);">Unable to generate AI review. Please try again later.</p>';
            console.error('AI Review error:', err);
        }
    }

    // ---------- Counter-Argument Simulator ----------
    function initCounterArgument() {
        $('#aiCounterBtn').addEventListener('click', handleCounterArgument);
        $('#closeAiCounter').addEventListener('click', () => hide($('#aiCounterOutput')));
    }

    async function handleCounterArgument() {
        const project = getProject(state.currentProjectId);
        if (!project || state.currentIssueIndex === null) return;

        const issue = project.issues[state.currentIssueIndex];
        const output = $('#aiCounterOutput');
        const body = $('#aiCounterBody');

        show(output);
        body.innerHTML = '<div class="ai-loading"><span class="ai-loading-dot"></span><span class="ai-loading-dot"></span><span class="ai-loading-dot"></span> Simulating opposing view...</div>';

        try {
            const response = await fetch(`${AI_API_BASE}/counter-argument`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    proposition: project.proposition,
                    side: project.side,
                    issue_text: issue.text,
                    irac: issue.irac || {}
                })
            });

            if (!response.ok) throw new Error('Counter-argument request failed');
            const data = await response.json();
            body.innerHTML = formatAIOutput(data.counter_arguments);
        } catch (err) {
            body.innerHTML = '<p style="color: var(--danger);">Unable to simulate counter-arguments. Please try again later.</p>';
            console.error('Counter-argument error:', err);
        }
    }

    function formatAIOutput(text) {
        return text
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\n/g, '<br>')
            .replace(/- (.*?)(?=<br>|$)/g, '• $1');
    }

    // ---------- Judge Assist ----------
    function initJudgeAssist() {
        $('#toggleJudgeAssistBtn').addEventListener('click', () => {
            const overlay = $('#judgeAssistOverlay');
            if (overlay.classList.contains('hidden')) {
                show(overlay);
            } else {
                hide(overlay);
            }
        });

        $('#closeJudgeAssist').addEventListener('click', () => hide($('#judgeAssistOverlay')));

        // Mode buttons
        $$('.judge-mode-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                $$('.judge-mode-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                currentJudgeMode = btn.dataset.mode;
                $('#judgeAssistBody').innerHTML = '<p class="judge-assist-placeholder">Click "Run Analysis" to generate ' + currentJudgeMode.replace('_', ' ') + ' analysis.</p>';
            });
        });

        $('#judgeAssistRunBtn').addEventListener('click', handleJudgeAssist);
    }

    async function handleJudgeAssist() {
        const project = getProject(state.currentProjectId);
        if (!project) return;

        const body = $('#judgeAssistBody');
        body.innerHTML = '<div class="ai-loading"><span class="ai-loading-dot"></span><span class="ai-loading-dot"></span><span class="ai-loading-dot"></span> Analyzing submissions...</div>';

        // Build submissions from current project (only one side available in this view)
        const submissions = project.issues.map(issue => ({
            issue_text: issue.text,
            irac: issue.irac || {}
        }));

        const isPetitioner = project.side === 'petitioner';
        const petitionerSubmissions = isPetitioner ? submissions : [];
        const respondentSubmissions = isPetitioner ? [] : submissions;

        try {
            const response = await fetch(`${AI_API_BASE}/judge-assist`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    proposition: project.proposition,
                    petitioner_submissions: petitionerSubmissions,
                    respondent_submissions: respondentSubmissions,
                    mode: currentJudgeMode
                })
            });

            if (!response.ok) throw new Error('Judge Assist request failed');
            const data = await response.json();
            body.innerHTML = formatAIOutput(data.analysis);
        } catch (err) {
            body.innerHTML = '<p style="color: var(--danger);">Unable to generate analysis. Note: Judge Assist works best when both sides have submissions.</p>';
            console.error('Judge Assist error:', err);
        }
    }

    // ============================================
    // PHASE 3: ORAL ROUNDS
    // ============================================

    const ORAL_STAGES = ['petitioner', 'respondent', 'rebuttal'];

    const oralState = {
        isActive: false,
        currentStage: 0, // 0: petitioner, 1: respondent, 2: rebuttal
        role: 'judge', // 'judge' or 'speaker'
        timeRemaining: 0,
        timerInterval: null,
        isPaused: false,
        durations: { petitioner: 600, respondent: 600, rebuttal: 180 }, // in seconds
        responses: [], // { stage, issueIndex, text, timestamp, type: 'response' | 'rebuttal' }
        questions: [], // { text, timestamp, stage, answered: boolean }
        activeQuestion: null,
        judgeNotes: '',
        currentIssueIndex: 0
    };

    function initOralRound() {
        $('#enterOralRoundBtn').addEventListener('click', enterOralRoundMode);
        $('#backToWorkspaceBtn').addEventListener('click', exitOralRoundMode);
        $('#endOralRoundBtn').addEventListener('click', endOralRound);
        $('#startOralRoundBtn').addEventListener('click', startOralRound);
        $('#pauseTimerBtn').addEventListener('click', togglePause);
        $('#nextStageBtn').addEventListener('click', skipToNextStage);
        $('#askQuestionBtn').addEventListener('click', submitBenchQuestion);
        $('#clearQuestionBtn').addEventListener('click', clearActiveQuestion);
        $('#oralViewTranscriptBtn').addEventListener('click', showTranscript);
        $('#closeTranscriptBtn').addEventListener('click', () => hide($('#oralTranscriptOverlay')));
        $('#downloadTranscriptBtn').addEventListener('click', downloadTranscript);
        $('#generateAiQuestionsBtn').addEventListener('click', generateAiBenchQuestions);

        // Role switching
        $$('.oral-role-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                $$('.oral-role-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                oralState.role = btn.dataset.role;
                updateRoleBasedUI();
            });
        });

        // Enter to submit response
        $('#oralResponseInput').addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey && !oralState.isPaused && oralState.isActive) {
                e.preventDefault();
                submitOralResponse();
            }
        });

        // Judge notes auto-save
        $('#judgeNotesInput').addEventListener('input', (e) => {
            oralState.judgeNotes = e.target.value;
        });

        // Issue selector
        $('#oralIssueSelect').addEventListener('change', (e) => {
            oralState.currentIssueIndex = parseInt(e.target.value) || 0;
        });
    }

    function enterOralRoundMode() {
        const project = getProject(state.currentProjectId);
        if (!project || project.issues.length === 0) {
            alert('Please create at least one legal issue before starting an oral round.');
            return;
        }

        // Reset oral state
        resetOralState();

        // Populate issue selector
        const select = $('#oralIssueSelect');
        select.innerHTML = '<option value="">Select an issue to address...</option>' +
            project.issues.map((issue, i) => `<option value="${i}">${i + 1}. ${escapeHtml(issue.text.substring(0, 60))}${issue.text.length > 60 ? '...' : ''}</option>`).join('');

        // Show oral round view
        hide($('#workspaceView'));
        show($('#oralRoundView'));

        // Reset UI
        show($('#oralSetupPanel'));
        hide($('#oralRoundPanel'));
        updateStageIndicator();
        updateTimerDisplay();
    }

    function resetOralState() {
        oralState.isActive = false;
        oralState.currentStage = 0;
        oralState.role = 'judge';
        oralState.timeRemaining = 0;
        oralState.isPaused = false;
        oralState.responses = [];
        oralState.questions = [];
        oralState.activeQuestion = null;
        oralState.judgeNotes = '';
        oralState.currentIssueIndex = 0;

        // Reset role buttons
        $$('.oral-role-btn').forEach(b => b.classList.remove('active'));
        $('#roleJudgeBtn').classList.add('active');

        // Clear timer
        if (oralState.timerInterval) {
            clearInterval(oralState.timerInterval);
            oralState.timerInterval = null;
        }

        // Clear UI
        $('#oralResponseInput').value = '';
        $('#oralResponseInput').disabled = false;
        $('#benchQuestionInput').value = '';
        $('#judgeNotesInput').value = '';
        $('#oralResponsesList').innerHTML = '';
        $('#oralHistoryList').innerHTML = '';
        hide($('#oralActiveQuestion'));
    }

    function exitOralRoundMode() {
        if (oralState.isActive && !confirm('Exit oral round mode? Current round progress will be lost.')) {
            return;
        }

        // Stop timer
        if (oralState.timerInterval) {
            clearInterval(oralState.timerInterval);
            oralState.timerInterval = null;
        }

        hide($('#oralRoundView'));
        show($('#workspaceView'));
    }

    function endOralRound() {
        if (!confirm('End this oral round? The transcript will be preserved.')) {
            return;
        }

        // Save round to project
        saveOralRoundToProject();

        // Stop timer
        if (oralState.timerInterval) {
            clearInterval(oralState.timerInterval);
            oralState.timerInterval = null;
        }

        oralState.isActive = false;
        showTranscript();
    }

    function startOralRound() {
        // Get durations from inputs
        oralState.durations.petitioner = parseInt($('#petitionerTime').value) * 60 || 600;
        oralState.durations.respondent = parseInt($('#respondentTime').value) * 60 || 600;
        oralState.durations.rebuttal = parseInt($('#rebuttalTime').value) * 60 || 180;

        oralState.isActive = true;
        oralState.currentStage = 0;
        oralState.timeRemaining = oralState.durations[ORAL_STAGES[0]];

        hide($('#oralSetupPanel'));
        show($('#oralRoundPanel'));

        updateStageIndicator();
        updateTimerDisplay();
        updateSpeakerLabel();
        startTimer();
    }

    function startTimer() {
        if (oralState.timerInterval) clearInterval(oralState.timerInterval);

        oralState.timerInterval = setInterval(() => {
            if (!oralState.isPaused && oralState.timeRemaining > 0) {
                oralState.timeRemaining--;
                updateTimerDisplay();

                if (oralState.timeRemaining <= 0) {
                    handleTimeUp();
                }
            }
        }, 1000);
    }

    function updateTimerDisplay() {
        const minutes = Math.floor(oralState.timeRemaining / 60);
        const seconds = oralState.timeRemaining % 60;
        const display = `${minutes}:${seconds.toString().padStart(2, '0')}`;

        const timerEl = $('#oralTimerDisplay');
        timerEl.textContent = display;

        // Visual warnings
        timerEl.classList.remove('warning', 'critical');
        if (oralState.timeRemaining <= 30) {
            timerEl.classList.add('critical');
        } else if (oralState.timeRemaining <= 120) {
            timerEl.classList.add('warning');
        }
    }

    function updateTimerStatus() {
        const statusEl = $('#oralTimerStatus');
        if (oralState.isPaused) {
            statusEl.textContent = 'Paused - Bench Question';
            statusEl.classList.add('paused');
        } else if (oralState.isActive) {
            statusEl.textContent = ORAL_STAGES[oralState.currentStage].replace(/^./, c => c.toUpperCase()) + ' Speaking';
            statusEl.classList.remove('paused');
        } else {
            statusEl.textContent = 'Ready';
        }

        // Update bench status
        const benchStatus = $('#benchStatus');
        if (oralState.isPaused) {
            benchStatus.textContent = 'Paused';
            benchStatus.classList.add('paused');
        } else {
            benchStatus.textContent = 'Active';
            benchStatus.classList.remove('paused');
        }
    }

    function togglePause() {
        oralState.isPaused = !oralState.isPaused;
        $('#pauseTimerBtn').innerHTML = oralState.isPaused
            ? '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg> Resume'
            : '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>';
        updateTimerStatus();
    }

    function handleTimeUp() {
        clearInterval(oralState.timerInterval);
        oralState.timerInterval = null;

        // Lock input
        $('#oralResponseInput').disabled = true;

        // Auto advance after delay
        setTimeout(() => {
            advanceToNextStage();
        }, 2000);
    }

    function advanceToNextStage() {
        if (oralState.currentStage < ORAL_STAGES.length - 1) {
            oralState.currentStage++;
            oralState.timeRemaining = oralState.durations[ORAL_STAGES[oralState.currentStage]];
            $('#oralResponseInput').disabled = false;
            $('#oralResponseInput').value = '';
            updateStageIndicator();
            updateTimerDisplay();
            updateSpeakerLabel();
            startTimer();
        } else {
            // Round complete
            endOralRound();
        }
    }

    function skipToNextStage() {
        if (oralState.currentStage < ORAL_STAGES.length - 1) {
            advanceToNextStage();
        }
    }

    function updateStageIndicator() {
        ORAL_STAGES.forEach((stage, i) => {
            const el = $(`#stage${stage.replace(/^./, c => c.toUpperCase())}`);
            el.classList.remove('active', 'completed');
            if (i < oralState.currentStage) {
                el.classList.add('completed');
            } else if (i === oralState.currentStage) {
                el.classList.add('active');
            }
        });

        $('#oralStageBadge').textContent = ORAL_STAGES[oralState.currentStage].replace(/^./, c => c.toUpperCase());
    }

    function updateSpeakerLabel() {
        const stage = ORAL_STAGES[oralState.currentStage];
        const label = stage === 'rebuttal' ? 'Petitioner Rebuttal' : stage.replace(/^./, c => c.toUpperCase());
        $('#oralSpeakerLabel').textContent = label + ' Speaking';
    }

    function updateRoleBasedUI() {
        $('#oralRoleBadge').textContent = oralState.role === 'judge' ? 'Judge View' : 'Speaker View';

        if (oralState.role === 'speaker') {
            hide($('#oralBenchPanel'));
            hide($('#oralResponsesLog'));
            $('#oralSpeakerPanel').style.gridColumn = '1 / -1';
        } else {
            show($('#oralBenchPanel'));
            show($('#oralResponsesLog'));
            $('#oralSpeakerPanel').style.gridColumn = '';
        }
    }

    function submitOralResponse() {
        const input = $('#oralResponseInput');
        const text = input.value.trim();
        if (!text) return;

        const response = {
            type: ORAL_STAGES[oralState.currentStage] === 'rebuttal' ? 'rebuttal' : 'response',
            stage: ORAL_STAGES[oralState.currentStage],
            stageIndex: oralState.currentStage,
            issueIndex: oralState.currentIssueIndex,
            text: text,
            timestamp: Date.now()
        };

        oralState.responses.push(response);

        // Add to UI
        const entry = document.createElement('div');
        entry.className = 'oral-response-item';
        entry.innerHTML = `
            <div class="oral-response-meta">
                <span>${formatTime(response.timestamp)} - ${response.stage.replace(/^./, c => c.toUpperCase())}</span>
                <span>Issue ${response.issueIndex + 1}</span>
            </div>
            <div class="oral-response-text">${escapeHtml(text)}</div>
        `;
        $('#oralResponsesList').appendChild(entry);
        $('#oralResponsesList').scrollTop = $('#oralResponsesList').scrollHeight;

        // Clear input
        input.value = '';
    }

    function submitBenchQuestion() {
        const input = $('#benchQuestionInput');
        const text = input.value.trim();
        if (!text) return;

        // Create question
        const question = {
            text: text,
            timestamp: Date.now(),
            stage: ORAL_STAGES[oralState.currentStage],
            stageIndex: oralState.currentStage,
            answered: false
        };

        oralState.questions.push(question);
        oralState.activeQuestion = question;

        // Pause timer
        if (!oralState.isPaused) {
            togglePause();
        }

        // Show active question
        $('#oralQuestionText').textContent = text;
        show($('#oralActiveQuestion'));

        // Add to history
        const historyItem = document.createElement('div');
        historyItem.className = 'oral-history-item';
        historyItem.innerHTML = `
            <div class="oral-history-meta">${formatTime(question.timestamp)} - ${question.stage}</div>
            <div>${escapeHtml(text)}</div>
        `;
        $('#oralHistoryList').appendChild(historyItem);

        // Clear input
        input.value = '';
    }

    function clearActiveQuestion() {
        oralState.activeQuestion = null;
        hide($('#oralActiveQuestion'));

        // Resume if paused
        if (oralState.isPaused) {
            togglePause();
        }
    }

    async function generateAiBenchQuestions() {
        const project = getProject(state.currentProjectId);
        if (!project) return;

        const container = $('#oralAiList');
        container.innerHTML = '<div class="ai-loading"><span class="ai-loading-dot"></span><span class="ai-loading-dot"></span><span class="ai-loading-dot"></span> Generating suggestions...</div>';

        try {
            const currentIssue = project.issues[oralState.currentIssueIndex];
            const response = await fetch(`${AI_API_BASE}/bench-questions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    proposition: project.proposition,
                    side: ORAL_STAGES[oralState.currentStage] === 'respondent' ? 'respondent' : 'petitioner',
                    current_stage: ORAL_STAGES[oralState.currentStage],
                    issue_text: currentIssue?.text || '',
                    issue_index: oralState.currentIssueIndex
                })
            });

            if (!response.ok) throw new Error('Failed to generate suggestions');
            const data = await response.json();

            // Display suggestions
            container.innerHTML = '';
            data.questions.forEach((q, i) => {
                const item = document.createElement('div');
                item.className = 'oral-ai-item';
                item.textContent = q;
                item.addEventListener('click', () => {
                    $('#benchQuestionInput').value = q;
                });
                container.appendChild(item);
            });
        } catch (err) {
            container.innerHTML = '<p class="oral-ai-placeholder">Unable to generate suggestions. Please try again.</p>';
            console.error('AI bench questions error:', err);
        }
    }

    function showTranscript() {
        const body = $('#oralTranscriptBody');

        let html = '';

        // Stages
        ORAL_STAGES.forEach((stage, stageIdx) => {
            const stageResponses = oralState.responses.filter(r => r.stageIndex === stageIdx);
            const stageQuestions = oralState.questions.filter(q => q.stageIndex === stageIdx);

            if (stageResponses.length === 0 && stageQuestions.length === 0) return;

            html += `<div class="transcript-section">`;
            html += `<div class="transcript-section-title">${stage.replace(/^./, c => c.toUpperCase())} Stage</div>`;

            // Interleave responses and questions by timestamp
            const allEntries = [
                ...stageResponses.map(r => ({ ...r, entryType: 'response' })),
                ...stageQuestions.map(q => ({ ...q, entryType: 'question' }))
            ].sort((a, b) => a.timestamp - b.timestamp);

            allEntries.forEach(entry => {
                const role = entry.entryType === 'question' ? 'Bench' : (entry.stage === 'respondent' ? 'Respondent' : 'Petitioner');
                const typeClass = entry.entryType;

                html += `
                    <div class="transcript-entry ${typeClass}">
                        <div class="transcript-entry-meta">
                            <span class="transcript-entry-role">${role}</span>
                            <span>${formatTime(entry.timestamp)}</span>
                        </div>
                        <div class="transcript-entry-text">${escapeHtml(entry.text)}</div>
                    </div>
                `;
            });

            html += `</div>`;
        });

        // Judge notes (only if any)
        if (oralState.judgeNotes.trim()) {
            html += `<div class="transcript-section">`;
            html += `<div class="transcript-section-title">Judge Private Notes</div>`;
            html += `<div class="transcript-entry">`;
            html += `<div class="transcript-entry-text" style="font-style: italic; color: var(--text-muted);">${escapeHtml(oralState.judgeNotes)}</div>`;
            html += `</div></div>`;
        }

        if (html === '') {
            html = '<p style="color: var(--text-muted); text-align: center;">No transcript entries yet.</p>';
        }

        body.innerHTML = html;
        show($('#oralTranscriptOverlay'));
    }

    function downloadTranscript() {
        const project = getProject(state.currentProjectId);
        if (!project) return;

        let text = `ORAL ROUND TRANSCRIPT\n`;
        text += `Project: ${project.title}\n`;
        text += `Date: ${new Date().toLocaleString()}\n`;
        text += `\n${'='.repeat(60)}\n\n`;

        ORAL_STAGES.forEach((stage, stageIdx) => {
            const stageResponses = oralState.responses.filter(r => r.stageIndex === stageIdx);
            const stageQuestions = oralState.questions.filter(q => q.stageIndex === stageIdx);

            if (stageResponses.length === 0 && stageQuestions.length === 0) return;

            text += `${stage.toUpperCase()} STAGE\n`;
            text += `${'-'.repeat(40)}\n\n`;

            const allEntries = [
                ...stageResponses.map(r => ({ ...r, entryType: 'response' })),
                ...stageQuestions.map(q => ({ ...q, entryType: 'question' }))
            ].sort((a, b) => a.timestamp - b.timestamp);

            allEntries.forEach(entry => {
                const role = entry.entryType === 'question' ? 'BENCH' : (entry.stage === 'respondent' ? 'RESPONDENT' : 'PETITIONER');
                text += `[${formatTime(entry.timestamp)}] ${role}:\n${entry.text}\n\n`;
            });

            text += `\n`;
        });

        if (oralState.judgeNotes.trim()) {
            text += `${'='.repeat(60)}\n`;
            text += `JUDGE PRIVATE NOTES (Not visible to speakers)\n`;
            text += `${'-'.repeat(40)}\n\n`;
            text += oralState.judgeNotes + '\n\n';
        }

        const blob = new Blob([text], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `oral-round-${project.title.replace(/[^a-z0-9]/gi, '-').toLowerCase()}-${Date.now()}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    function saveOralRoundToProject() {
        const project = getProject(state.currentProjectId);
        if (!project) return;

        const oralRound = {
            id: generateId(),
            startedAt: Date.now() - (oralState.durations.petitioner + oralState.durations.respondent + oralState.durations.rebuttal - oralState.timeRemaining) * 1000,
            endedAt: Date.now(),
            responses: oralState.responses,
            questions: oralState.questions,
            judgeNotes: oralState.judgeNotes,
            durations: oralState.durations
        };

        const oralRounds = project.oralRounds || [];
        oralRounds.push(oralRound);

        updateProject(state.currentProjectId, { oralRounds });
    }

    function formatTime(timestamp) {
        const d = new Date(timestamp);
        return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
    }

    // ============================================
    // PHASE 4: EVALUATION SYSTEM
    // ============================================

    // Default Scoring Rubric
    const DEFAULT_RUBRIC = [
        { id: 'issue_framing', name: 'Issue Identification & Framing', maxScore: 10, description: 'Clarity and precision in identifying legal issues' },
        { id: 'legal_reasoning', name: 'Legal Reasoning & Application', maxScore: 10, description: 'Quality of argumentation and application of law to facts' },
        { id: 'use_of_authority', name: 'Use of Authority', maxScore: 10, description: 'Effective use of precedents, statutes, and legal principles' },
        { id: 'structure_clarity', name: 'Structure & Clarity', maxScore: 10, description: 'Organization, coherence, and presentation of arguments' },
        { id: 'oral_advocacy', name: 'Oral Advocacy', maxScore: 10, description: 'Performance in oral rounds (if applicable)' },
        { id: 'responsiveness', name: 'Responsiveness to Bench', maxScore: 10, description: 'Ability to handle judicial questions and interruptions' }
    ];

    let evalState = {
        evaluationId: null,
        judgeId: '',
        scores: {},
        comments: {},
        overallComments: '',
        isDraft: true,
        isFinalized: false,
        submittedAt: null
    };

    let currentRubric = [...DEFAULT_RUBRIC];

    function initEvaluation() {
        $('#openEvaluationBtn').addEventListener('click', openEvaluationPanel);
        $('#closeEvalBtn').addEventListener('click', closeEvaluationPanel);
        $('#saveDraftEvalBtn').addEventListener('click', saveDraftEvaluation);
        $('#finalizeEvalBtn').addEventListener('click', finalizeEvaluation);
        $('#suggestFeedbackBtn').addEventListener('click', suggestFeedbackAssist);
        $('#closeFeedbackBtn').addEventListener('click', () => hide($('#feedbackReportOverlay')));
        $('#downloadFeedbackBtn').addEventListener('click', downloadFeedbackReport);

        // Tab switching
        $$('.eval-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                $$('.eval-tab').forEach(t => t.classList.remove('active'));
                $$('.eval-tab-content').forEach(c => c.classList.remove('active'));
                tab.classList.add('active');
                $(`#${tab.dataset.tab}Tab`).classList.add('active');
            });
        });

        // Close on overlay click
        $('#evaluationOverlay').addEventListener('click', (e) => {
            if (e.target === $('#evaluationOverlay')) {
                if (evalState.isDraft && !evalState.isFinalized) {
                    if (confirm('Close without saving? Your draft evaluation will be lost.')) {
                        closeEvaluationPanel();
                    }
                } else {
                    closeEvaluationPanel();
                }
            }
        });

        $('#feedbackReportOverlay').addEventListener('click', (e) => {
            if (e.target === $('#feedbackReportOverlay')) hide($('#feedbackReportOverlay'));
        });
    }

    function openEvaluationPanel() {
        const project = getProject(state.currentProjectId);
        if (!project) return;

        // Reset or load existing evaluation
        resetEvalState();
        loadExistingEvaluation();

        // Populate review panels
        populateWrittenSubmissions(project);
        populateOralSummary(project);
        populateTranscript(project);

        // Build scoring rubric
        buildScoringRubric();

        // Check for multi-judge evaluations
        updateMultiJudgeDisplay(project);

        show($('#evaluationOverlay'));
        updateEvalUI();
    }

    function resetEvalState() {
        evalState = {
            evaluationId: generateId(),
            judgeId: '',
            scores: {},
            comments: {},
            overallComments: '',
            isDraft: true,
            isFinalized: false,
            submittedAt: null
        };

        // Initialize scores to 0
        currentRubric.forEach(cat => {
            evalState.scores[cat.id] = 0;
            evalState.comments[cat.id] = '';
        });

        $('#judgeIdInput').value = '';
        $('#overallComments').value = '';
        $('#evalAiContent').innerHTML = '<p class="eval-ai-placeholder">Click "Suggest Feedback" for AI assistance with phrasing.</p>';
    }

    function loadExistingEvaluation() {
        const project = getProject(state.currentProjectId);
        if (!project || !project.evaluations) return;

        // For now, check if current judge has an existing draft
        const judgeId = $('#judgeIdInput').value.trim();
        if (!judgeId) return;

        const existing = project.evaluations.find(e => e.judgeId === judgeId && !e.isFinalized);
        if (existing) {
            evalState = { ...existing };
            $('#judgeIdInput').value = evalState.judgeId;
            $('#overallComments').value = evalState.overallComments;
        }
    }

    function populateWrittenSubmissions(project) {
        const container = $('#evalIssuesList');
        
        if (!project.issues || project.issues.length === 0) {
            container.innerHTML = '<p class="eval-placeholder">No written submissions available.</p>';
            return;
        }

        container.innerHTML = project.issues.map((issue, i) => {
            const irac = issue.irac || {};
            return `
                <div class="eval-issue-card">
                    <div class="eval-issue-header">Issue ${i + 1}</div>
                    <div class="eval-issue-text">${escapeHtml(issue.text)}</div>
                    
                    <div class="eval-irac-section">
                        <div class="eval-irac-label">Issue Statement</div>
                        <div class="eval-irac-content ${!irac.issue ? 'empty' : ''}">${irac.issue ? escapeHtml(irac.issue) : 'Not provided'}</div>
                    </div>
                    
                    <div class="eval-irac-section">
                        <div class="eval-irac-label">Rule</div>
                        <div class="eval-irac-content ${!irac.rule ? 'empty' : ''}">${irac.rule ? escapeHtml(irac.rule) : 'Not provided'}</div>
                    </div>
                    
                    <div class="eval-irac-section">
                        <div class="eval-irac-label">Application</div>
                        <div class="eval-irac-content ${!irac.application ? 'empty' : ''}">${irac.application ? escapeHtml(irac.application) : 'Not provided'}</div>
                    </div>
                    
                    <div class="eval-irac-section">
                        <div class="eval-irac-label">Conclusion</div>
                        <div class="eval-irac-content ${!irac.conclusion ? 'empty' : ''}">${irac.conclusion ? escapeHtml(irac.conclusion) : 'Not provided'}</div>
                    </div>
                </div>
            `;
        }).join('');
    }

    function populateOralSummary(project) {
        const container = $('#evalOralSummary');
        
        if (!project.oralRounds || project.oralRounds.length === 0) {
            container.innerHTML = '<p class="eval-placeholder">No oral round recorded for this moot.</p>';
            $('#oralTabBtn').disabled = true;
            return;
        }

        $('#oralTabBtn').disabled = false;
        const lastRound = project.oralRounds[project.oralRounds.length - 1];
        
        const stats = {
            responses: lastRound.responses ? lastRound.responses.length : 0,
            questions: lastRound.questions ? lastRound.questions.length : 0,
            duration: lastRound.durations ? 
                Math.floor((lastRound.durations.petitioner + lastRound.durations.respondent + lastRound.durations.rebuttal) / 60) : 0
        };

        container.innerHTML = `
            <div class="eval-oral-stats">
                <div class="eval-stat-box">
                    <div class="eval-stat-value">${stats.responses}</div>
                    <div class="eval-stat-label">Responses</div>
                </div>
                <div class="eval-stat-box">
                    <div class="eval-stat-value">${stats.questions}</div>
                    <div class="eval-stat-label">Bench Questions</div>
                </div>
                <div class="eval-stat-box">
                    <div class="eval-stat-value">${stats.duration}</div>
                    <div class="eval-stat-label">Minutes Total</div>
                </div>
            </div>
            <div class="eval-round-details">
                <p style="font-size: 0.8rem; color: var(--text-secondary);">
                    Last oral round completed: ${new Date(lastRound.endedAt).toLocaleString()}
                </p>
            </div>
        `;
    }

    function populateTranscript(project) {
        const container = $('#evalTranscript');
        
        if (!project.oralRounds || project.oralRounds.length === 0) {
            container.innerHTML = '<p class="eval-placeholder">No transcript available.</p>';
            return;
        }

        const lastRound = project.oralRounds[project.oralRounds.length - 1];
        let html = '';

        ['petitioner', 'respondent', 'rebuttal'].forEach((stage, idx) => {
            const stageResponses = lastRound.responses ? lastRound.responses.filter(r => r.stageIndex === idx) : [];
            const stageQuestions = lastRound.questions ? lastRound.questions.filter(q => q.stageIndex === idx) : [];

            if (stageResponses.length === 0 && stageQuestions.length === 0) return;

            html += `<div style="margin-bottom: 1.5rem;"><h5 style="font-size: 0.8rem; font-weight: 700; color: var(--accent-teal); text-transform: uppercase; margin-bottom: 0.5rem;">${stage}</h5>`;

            const allEntries = [
                ...stageResponses.map(r => ({ ...r, type: 'response' })),
                ...stageQuestions.map(q => ({ ...q, type: 'question' }))
            ].sort((a, b) => a.timestamp - b.timestamp);

            allEntries.forEach(entry => {
                const role = entry.type === 'question' ? 'Bench' : (entry.stage === 'respondent' ? 'Respondent' : 'Petitioner');
                const color = entry.type === 'question' ? '#F59E0B' : 'var(--accent-teal)';
                html += `
                    <div style="margin-bottom: 0.75rem; padding-left: 0.75rem; border-left: 2px solid ${color};">
                        <div style="font-size: 0.65rem; color: var(--text-muted); margin-bottom: 0.125rem;">${role} • ${new Date(entry.timestamp).toLocaleTimeString()}</div>
                        <div style="font-size: 0.8rem; color: var(--text-primary);">${escapeHtml(entry.text)}</div>
                    </div>
                `;
            });

            html += '</div>';
        });

        container.innerHTML = html || '<p class="eval-placeholder">No transcript entries available.</p>';
    }

    function buildScoringRubric() {
        const container = $('#evalCategories');
        
        container.innerHTML = currentRubric.map(cat => `
            <div class="eval-category" data-category="${cat.id}">
                <div class="eval-category-header">
                    <span class="eval-category-name">${cat.name}</span>
                    <div class="eval-category-score">
                        <input type="number" 
                               class="eval-score-input" 
                               data-category="${cat.id}"
                               min="0" 
                               max="${cat.maxScore}" 
                               value="0"
                               ${evalState.isFinalized ? 'disabled' : ''}>
                        <span class="eval-max-label">/ ${cat.maxScore}</span>
                    </div>
                </div>
                <div class="eval-category-comment">
                    <textarea placeholder="Add comments for this category..." 
                              data-category="${cat.id}"
                              rows="2"
                              ${evalState.isFinalized ? 'disabled' : ''}>${evalState.comments[cat.id] || ''}</textarea>
                </div>
            </div>
        `).join('');

        // Bind score input events
        $$('.eval-score-input').forEach(input => {
            input.addEventListener('change', (e) => {
                const catId = e.target.dataset.category;
                let val = parseInt(e.target.value) || 0;
                const max = currentRubric.find(c => c.id === catId).maxScore;
                val = Math.max(0, Math.min(val, max));
                e.target.value = val;
                evalState.scores[catId] = val;
                updateScoreSummary();
            });
        });

        $$('.eval-category-comment textarea').forEach(textarea => {
            textarea.addEventListener('input', (e) => {
                evalState.comments[e.target.dataset.category] = e.target.value;
            });
        });

        updateScoreSummary();
    }

    function updateScoreSummary() {
        const total = Object.values(evalState.scores).reduce((sum, score) => sum + score, 0);
        const max = currentRubric.reduce((sum, cat) => sum + cat.maxScore, 0);
        const percentage = max > 0 ? Math.round((total / max) * 100) : 0;

        $('#totalScore').textContent = total;
        $('#maxScore').textContent = `/ ${max}`;
        $('#scorePercentage').textContent = `${percentage}%`;
    }

    function updateEvalUI() {
        $('#evalStatusBadge').textContent = evalState.isFinalized ? 'Finalized' : 'Draft';
        $('#evalStatusBadge').className = `badge ${evalState.isFinalized ? 'badge-complete' : 'badge-role'}`;
        
        $('#saveDraftEvalBtn').disabled = evalState.isFinalized;
        $('#finalizeEvalBtn').disabled = evalState.isFinalized;
        
        if (evalState.isFinalized) {
            $('#saveDraftEvalBtn').style.display = 'none';
            $('#finalizeEvalBtn').style.display = 'none';
        }
    }

    function closeEvaluationPanel() {
        hide($('#evaluationOverlay'));
    }

    function saveDraftEvaluation() {
        const project = getProject(state.currentProjectId);
        if (!project) return;

        evalState.judgeId = $('#judgeIdInput').value.trim() || 'Anonymous';
        evalState.overallComments = $('#overallComments').value;
        evalState.isDraft = true;
        evalState.isFinalized = false;

        // Save to project
        const evaluations = project.evaluations || [];
        const existingIdx = evaluations.findIndex(e => e.evaluationId === evalState.evaluationId);
        
        if (existingIdx >= 0) {
            evaluations[existingIdx] = { ...evalState };
        } else {
            evaluations.push({ ...evalState });
        }

        updateProject(state.currentProjectId, { evaluations });
        
        // Show confirmation
        alert('Draft evaluation saved.');
        updateMultiJudgeDisplay({ ...project, evaluations });
    }

    function finalizeEvaluation() {
        if (!confirm('Finalize this evaluation? Once finalized, it cannot be edited.')) {
            return;
        }

        const project = getProject(state.currentProjectId);
        if (!project) return;

        // Check if scores are entered
        const totalScore = Object.values(evalState.scores).reduce((sum, s) => sum + s, 0);
        if (totalScore === 0) {
            if (!confirm('You have not entered any scores. Finalize anyway?')) {
                return;
            }
        }

        evalState.judgeId = $('#judgeIdInput').value.trim() || 'Anonymous';
        evalState.overallComments = $('#overallComments').value;
        evalState.isDraft = false;
        evalState.isFinalized = true;
        evalState.submittedAt = Date.now();

        // Save to project
        const evaluations = project.evaluations || [];
        const existingIdx = evaluations.findIndex(e => e.evaluationId === evalState.evaluationId);
        
        if (existingIdx >= 0) {
            evaluations[existingIdx] = { ...evalState };
        } else {
            evaluations.push({ ...evalState });
        }

        updateProject(state.currentProjectId, { evaluations });

        // Disable inputs
        $$('.eval-score-input').forEach(i => i.disabled = true);
        $$('.eval-category-comment textarea').forEach(t => t.disabled = true);
        $('#overallComments').disabled = true;
        $('#judgeIdInput').disabled = true;

        updateEvalUI();
        updateMultiJudgeDisplay({ ...project, evaluations });

        // Show feedback report
        generateFeedbackReport(evalState);
    }

    function updateMultiJudgeDisplay(project) {
        const panel = $('#multiJudgePanel');
        const evaluations = project.evaluations || [];
        const finalized = evaluations.filter(e => e.isFinalized);

        if (finalized.length === 0) {
            hide(panel);
            return;
        }

        show(panel);

        // Show judge chips
        $('#judgesList').innerHTML = finalized.map(e => `
            <span class="eval-judge-chip final">${escapeHtml(e.judgeId)} ✓</span>
        `).join('');

        // Calculate aggregates
        const agg = {};
        currentRubric.forEach(cat => {
            const scores = finalized.map(e => e.scores[cat.id] || 0);
            agg[cat.id] = scores.reduce((sum, s) => sum + s, 0) / scores.length;
        });

        const totalAvg = Object.values(agg).reduce((sum, s) => sum + s, 0) / currentRubric.length;

        $('#aggregateScores').innerHTML = `
            <div class="eval-aggregate-item">
                <div class="eval-aggregate-label">Average Total Score</div>
                <div class="eval-aggregate-value">${totalAvg.toFixed(1)}</div>
            </div>
            <div class="eval-aggregate-item">
                <div class="eval-aggregate-label">Judges</div>
                <div class="eval-aggregate-value">${finalized.length}</div>
            </div>
        `;
    }

    async function suggestFeedbackAssist() {
        const project = getProject(state.currentProjectId);
        if (!project) return;

        const container = $('#evalAiContent');
        container.innerHTML = '<div class="ai-loading"><span class="ai-loading-dot"></span><span class="ai-loading-dot"></span><span class="ai-loading-dot"></span> Generating suggestions...</div>';

        // Build prompt from current scores
        const scoreSummary = currentRubric.map(cat => {
            const score = evalState.scores[cat.id] || 0;
            return `${cat.name}: ${score}/${cat.maxScore}`;
        }).join(', ');

        try {
            const response = await fetch(`${AI_API_BASE}/feedback-suggest`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    scores: evalState.scores,
                    rubric: currentRubric,
                    overall_comments: $('#overallComments').value,
                    submission_summary: project.issues.map(i => i.text).join('; ')
                })
            });

            if (!response.ok) throw new Error('Failed to generate suggestions');
            const data = await response.json();

            container.innerHTML = `
                <div style="margin-bottom: 0.75rem;"><strong>Strengths:</strong><br>${data.strengths}</div>
                <div><strong>Areas for Improvement:</strong><br>${data.improvements}</div>
                <p style="font-size: 0.7rem; color: var(--text-muted); margin-top: 0.5rem; font-style: italic;">These are suggestions only. Use your professional judgment.</p>
            `;
        } catch (err) {
            container.innerHTML = '<p class="eval-ai-placeholder">Unable to generate suggestions. Please try again.</p>';
            console.error('AI feedback assist error:', err);
        }
    }

    function generateFeedbackReport(evaluation) {
        const project = getProject(state.currentProjectId);
        if (!project) return;

        const body = $('#feedbackBody');

        // Calculate totals
        const totalScore = Object.values(evaluation.scores).reduce((sum, s) => sum + s, 0);
        const maxScore = currentRubric.reduce((sum, cat) => sum + cat.maxScore, 0);
        const percentage = Math.round((totalScore / maxScore) * 100);

        // Generate strengths/improvements from comments
        const strengths = [];
        const improvements = [];
        
        currentRubric.forEach(cat => {
            const score = evaluation.scores[cat.id] || 0;
            const comment = evaluation.comments[cat.id];
            if (score >= cat.maxScore * 0.8 && comment) strengths.push(comment);
            else if (score <= cat.maxScore * 0.5 && comment) improvements.push(comment);
        });

        body.innerHTML = `
            <div class="feedback-section">
                <div class="feedback-section-title">Score Summary</div>
                <div class="feedback-score-grid">
                    ${currentRubric.map(cat => `
                        <div class="feedback-score-item">
                            <span class="feedback-score-name">${cat.name}</span>
                            <span class="feedback-score-value">${evaluation.scores[cat.id] || 0}/${cat.maxScore}</span>
                        </div>
                    `).join('')}
                </div>
                <div style="margin-top: 1rem; text-align: center; padding: 1rem; background: #FAFBFC; border-radius: 8px;">
                    <div style="font-size: 2rem; font-weight: 800; color: var(--accent-teal);">${totalScore}/${maxScore}</div>
                    <div style="font-size: 1rem; color: var(--text-secondary);">${percentage}%</div>
                </div>
            </div>

            ${strengths.length > 0 ? `
            <div class="feedback-section">
                <div class="feedback-section-title">Strengths</div>
                <div class="feedback-strengths">
                    <h5>Highlighted Strengths</h5>
                    <ul>${strengths.map(s => `<li>${escapeHtml(s)}</li>`).join('')}</ul>
                </div>
            </div>
            ` : ''}

            ${improvements.length > 0 ? `
            <div class="feedback-section">
                <div class="feedback-section-title">Areas for Improvement</div>
                <div class="feedback-improvements">
                    <h5>Suggested Improvements</h5>
                    <ul>${improvements.map(i => `<li>${escapeHtml(i)}</li>`).join('')}</ul>
                </div>
            </div>
            ` : ''}

            ${evaluation.overallComments ? `
            <div class="feedback-section">
                <div class="feedback-section-title">Judge's Overall Comments</div>
                <div class="feedback-comment">${escapeHtml(evaluation.overallComments)}</div>
            </div>
            ` : ''}

            <div class="feedback-meta">
                Evaluation by ${escapeHtml(evaluation.judgeId)} • ${new Date(evaluation.submittedAt || Date.now()).toLocaleString()}
            </div>
        `;

        show($('#feedbackReportOverlay'));
    }

    function downloadFeedbackReport() {
        const project = getProject(state.currentProjectId);
        if (!project) return;

        const content = $('#feedbackBody').innerText;
        const text = `FEEDBACK REPORT\n${'='.repeat(50)}\n\nProject: ${project.title}\nDate: ${new Date().toLocaleString()}\n\n${content}`;

        const blob = new Blob([text], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `feedback-report-${project.title.replace(/[^a-z0-9]/gi, '-').toLowerCase()}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    // ============================================
    // EVENT BINDINGS
    // ============================================
    function init() {
        // Project list
        $('#newProjectBtn').addEventListener('click', () => showView('create'));
        $('#emptyNewProjectBtn').addEventListener('click', () => showView('create'));

        // Create form
        $('#backToListBtn').addEventListener('click', () => showView('list'));
        $('#cancelCreateBtn').addEventListener('click', () => showView('list'));
        $('#createProjectBtn').addEventListener('click', handleCreateProject);

        // Side selector
        $$('.side-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                $$('.side-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                selectedSide = btn.dataset.side;
            });
        });

        // Workspace nav
        $('#backToProjectsBtn').addEventListener('click', () => {
            state.currentProjectId = null;
            state.currentIssueIndex = null;
            showView('list');
        });

        // Proposition toggle
        $('#viewPropositionBtn').addEventListener('click', () => {
            const panel = $('#propositionPanel');
            if (panel.classList.contains('hidden')) {
                show(panel);
            } else {
                hide(panel);
            }
        });
        $('#closePropositionBtn').addEventListener('click', () => hide($('#propositionPanel')));

        // Delete project
        $('#deleteProjectBtn').addEventListener('click', openDeleteProjectModal);
        $('#cancelDeleteBtn').addEventListener('click', () => hide($('#deleteModal')));
        $('#confirmDeleteBtn').addEventListener('click', handleConfirmDelete);

        // Issues
        $('#addIssueBtn').addEventListener('click', openAddIssueModal);
        $('#cancelIssueBtn').addEventListener('click', () => hide($('#issueModal')));
        $('#saveIssueBtn').addEventListener('click', handleSaveIssue);

        // IRAC inputs
        $('#iracIssue').addEventListener('input', () => handleIRACInput('issue'));
        $('#iracRule').addEventListener('input', () => handleIRACInput('rule'));
        $('#iracApplication').addEventListener('input', () => handleIRACInput('application'));
        $('#iracConclusion').addEventListener('input', () => handleIRACInput('conclusion'));

        // IRAC nav
        $('#prevIssueBtn').addEventListener('click', () => {
            if (state.currentIssueIndex > 0) {
                state.currentIssueIndex--;
                renderIssues();
                renderIRAC();
            }
        });

        $('#nextIssueBtn').addEventListener('click', () => {
            const project = getProject(state.currentProjectId);
            if (project && state.currentIssueIndex < project.issues.length - 1) {
                state.currentIssueIndex++;
                renderIssues();
                renderIRAC();
            }
        });

        // Keyboard shortcuts for issue modal
        $('#issueText').addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSaveIssue();
            }
        });

        // Keyboard shortcut for create form
        $('#mootTitle').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                $('#mootProposition').focus();
            }
        });

        // Close modals on overlay click
        $$('.modal-overlay').forEach(overlay => {
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) hide(overlay);
            });
        });

        // Phase 2: AI Features
        initAICoach();
        initAIReview();
        initCounterArgument();
        initJudgeAssist();

        // Phase 3: Oral Rounds
        initOralRound();

        // Phase 4: Evaluation System
        initEvaluation();

        // Initial render
        showView('list');
    }

    // Start when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
