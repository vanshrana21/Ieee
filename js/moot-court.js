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
