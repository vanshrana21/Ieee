/**
 * Notes - Phase 3.4
 * Smart Notes System for Law Students
 */

const API_BASE_URL = 'http://127.0.0.1:8000';

let state = {
    notes: [],
    filteredNotes: [],
    subjects: [],
    modules: [],
    cases: [],
    currentNote: null,
    isNewNote: false,
    searchQuery: ''
};

document.addEventListener('DOMContentLoaded', function() {
    initializePage();
});

async function initializePage() {
    setupEventListeners();
    setupSidebarToggle();
    await loadUserInfo();
    await Promise.all([
        loadSubjects(),
        loadCases(),
        loadNotes()
    ]);
    checkURLParams();
}

function setupEventListeners() {
    document.getElementById('newNoteBtn').addEventListener('click', createNewNote);
    document.getElementById('emptyNewNoteBtn').addEventListener('click', createNewNote);
    document.getElementById('saveNoteBtn').addEventListener('click', saveNote);
    document.getElementById('cancelNoteBtn').addEventListener('click', cancelEdit);
    document.getElementById('deleteNoteBtn').addEventListener('click', showDeleteModal);
    document.getElementById('confirmDeleteBtn').addEventListener('click', deleteNote);
    document.getElementById('cancelDeleteBtn').addEventListener('click', hideDeleteModal);
    document.getElementById('clearFiltersBtn').addEventListener('click', clearFilters);
    document.getElementById('logoutBtn').addEventListener('click', logout);

    document.getElementById('filterSubject').addEventListener('change', handleFilterSubjectChange);
    document.getElementById('filterModule').addEventListener('change', applyFilters);
    document.getElementById('filterCase').addEventListener('change', applyFilters);
    document.getElementById('searchNotes').addEventListener('input', handleSearch);

    document.getElementById('noteSubject').addEventListener('change', handleNoteSubjectChange);

    document.querySelector('.modal-overlay')?.addEventListener('click', hideDeleteModal);
}

function setupSidebarToggle() {
    const menuToggle = document.getElementById('menuToggle');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');

    if (menuToggle && sidebar) {
        menuToggle.addEventListener('click', () => {
            sidebar.classList.toggle('open');
            overlay.classList.toggle('show');
        });
    }

    if (overlay) {
        overlay.addEventListener('click', () => {
            sidebar.classList.remove('open');
            overlay.classList.remove('show');
        });
    }
}

async function loadUserInfo() {
    try {
        const response = await apiRequest('/api/users/me');
        if (response && response.email) {
            document.getElementById('userName').textContent = response.full_name || response.email.split('@')[0];
        }
    } catch (err) {
        console.error('Failed to load user info:', err);
    }
}

async function loadSubjects() {
    try {
        const response = await apiRequest('/api/curriculum/my-subjects');
        state.subjects = response.subjects || [];

        const filterSelect = document.getElementById('filterSubject');
        const noteSelect = document.getElementById('noteSubject');

        filterSelect.innerHTML = '<option value="">All Subjects</option>';
        noteSelect.innerHTML = '<option value="">-- Select Subject --</option>';

        state.subjects.forEach(subject => {
            const filterOpt = document.createElement('option');
            filterOpt.value = subject.id;
            filterOpt.textContent = subject.title;
            filterSelect.appendChild(filterOpt);

            const noteOpt = document.createElement('option');
            noteOpt.value = subject.id;
            noteOpt.textContent = subject.title;
            noteSelect.appendChild(noteOpt);
        });
    } catch (err) {
        console.error('Failed to load subjects:', err);
    }
}

async function loadModulesForSubject(subjectId, targetSelect) {
    if (!subjectId) {
        targetSelect.innerHTML = '<option value="">All Modules</option>';
        targetSelect.disabled = true;
        return;
    }

    try {
        const response = await apiRequest(`/api/content/subjects/${subjectId}/modules`);
        const modules = response.modules || [];

        state.modules = modules;
        targetSelect.innerHTML = '<option value="">All Modules</option>';

        modules.forEach(module => {
            const option = document.createElement('option');
            option.value = module.id;
            option.textContent = module.title;
            targetSelect.appendChild(option);
        });

        targetSelect.disabled = false;
    } catch (err) {
        console.error('Failed to load modules:', err);
        targetSelect.disabled = true;
    }
}

async function loadCases() {
    try {
        const response = await apiRequest('/api/case-detail/recent?limit=50');
        state.cases = response.cases || [];

        const filterSelect = document.getElementById('filterCase');
        const noteSelect = document.getElementById('noteCase');

        filterSelect.innerHTML = '<option value="">All Cases</option>';
        noteSelect.innerHTML = '<option value="">-- Select Case --</option>';

        state.cases.forEach(caseItem => {
            const filterOpt = document.createElement('option');
            filterOpt.value = caseItem.id;
            filterOpt.textContent = caseItem.title;
            filterSelect.appendChild(filterOpt);

            const noteOpt = document.createElement('option');
            noteOpt.value = caseItem.id;
            noteOpt.textContent = caseItem.title;
            noteSelect.appendChild(noteOpt);
        });
    } catch (err) {
        console.error('Failed to load cases:', err);
    }
}

async function loadNotes() {
    try {
        const response = await apiRequest('/api/notes');
        state.notes = response.notes || [];
        state.filteredNotes = [...state.notes];
        renderNotesList();
        updateUI();
    } catch (err) {
        console.error('Failed to load notes:', err);
        showToast('Failed to load notes');
    }
}

function renderNotesList() {
    const listEl = document.getElementById('notesList');
    const countEl = document.getElementById('notesCount');

    if (state.filteredNotes.length === 0) {
        listEl.innerHTML = `
            <div class="empty-list-msg" style="padding: 1.5rem; text-align: center; color: #666;">
                No notes found
            </div>
        `;
        countEl.textContent = '0 notes';
        return;
    }

    countEl.textContent = `${state.filteredNotes.length} note${state.filteredNotes.length !== 1 ? 's' : ''}`;

    listEl.innerHTML = state.filteredNotes.map(note => {
        const subjectName = getSubjectName(note.entity_type === 'subject' ? note.entity_id : note.subject_id);
        const moduleName = note.entity_type === 'module' ? getModuleName(note.entity_id) : '';
        const caseName = note.entity_type === 'case' ? getCaseName(note.entity_id) : '';

        return `
            <div class="note-item ${state.currentNote?.id === note.id ? 'active' : ''}" 
                 data-note-id="${note.id}" onclick="selectNote(${note.id})">
                <div class="note-item-title">${escapeHtml(note.title)}</div>
                <div class="note-item-preview">${escapeHtml(note.content?.substring(0, 100) || '')}</div>
                <div class="note-item-meta">
                    ${subjectName ? `<span class="note-item-badge subject">${escapeHtml(subjectName)}</span>` : ''}
                    ${moduleName ? `<span class="note-item-badge module">${escapeHtml(moduleName)}</span>` : ''}
                    ${caseName ? `<span class="note-item-badge case">${escapeHtml(caseName)}</span>` : ''}
                </div>
            </div>
        `;
    }).join('');
}

function updateUI() {
    const hasNotes = state.notes.length > 0;
    const hasCurrentNote = state.currentNote !== null || state.isNewNote;

    document.getElementById('emptyState').classList.toggle('hidden', hasNotes || hasCurrentNote);
    document.getElementById('noteEditor').classList.toggle('hidden', !hasCurrentNote);

    if (!hasCurrentNote && hasNotes) {
        document.getElementById('emptyState').classList.add('hidden');
        document.getElementById('noteEditor').classList.add('hidden');
    }
}

function selectNote(noteId) {
    const note = state.notes.find(n => n.id === noteId);
    if (!note) return;

    state.currentNote = note;
    state.isNewNote = false;

    document.getElementById('noteTitle').value = note.title || '';
    document.getElementById('noteContent').value = note.content || '';

    const subjectId = note.entity_type === 'subject' ? note.entity_id : note.subject_id;
    document.getElementById('noteSubject').value = subjectId || '';

    if (subjectId) {
        loadModulesForSubject(subjectId, document.getElementById('noteModule')).then(() => {
            if (note.entity_type === 'module') {
                document.getElementById('noteModule').value = note.entity_id || '';
            }
        });
    }

    if (note.entity_type === 'case') {
        document.getElementById('noteCase').value = note.entity_id || '';
    } else {
        document.getElementById('noteCase').value = '';
    }

    updateMetadataBadges();
    renderNotesList();
    updateUI();

    document.getElementById('deleteNoteBtn').style.display = 'block';
    document.getElementById('saveStatus').textContent = '';
}

function createNewNote() {
    state.currentNote = null;
    state.isNewNote = true;

    document.getElementById('noteTitle').value = '';
    document.getElementById('noteContent').value = '';
    document.getElementById('noteSubject').value = '';
    document.getElementById('noteModule').value = '';
    document.getElementById('noteModule').disabled = true;
    document.getElementById('noteCase').value = '';

    document.getElementById('metadataBadges').innerHTML = '';
    document.getElementById('deleteNoteBtn').style.display = 'none';
    document.getElementById('saveStatus').textContent = '';

    renderNotesList();
    updateUI();

    document.getElementById('noteTitle').focus();
}

async function saveNote() {
    const title = document.getElementById('noteTitle').value.trim();
    const content = document.getElementById('noteContent').value.trim();
    const subjectId = document.getElementById('noteSubject').value;
    const moduleId = document.getElementById('noteModule').value;
    const caseId = document.getElementById('noteCase').value;

    if (!title) {
        showToast('Please enter a title');
        return;
    }

    if (!subjectId) {
        showToast('Please select a subject');
        return;
    }

    let entityType = 'subject';
    let entityId = parseInt(subjectId);

    if (caseId) {
        entityType = 'case';
        entityId = parseInt(caseId);
    } else if (moduleId) {
        entityType = 'module';
        entityId = parseInt(moduleId);
    }

    const payload = {
        title,
        content,
        entity_type: entityType,
        entity_id: entityId,
        subject_id: parseInt(subjectId)
    };

    try {
        document.getElementById('saveStatus').textContent = 'Saving...';

        let response;
        if (state.isNewNote) {
            response = await apiRequest('/api/notes', 'POST', payload);
            showToast('Note created successfully');
        } else {
            response = await apiRequest(`/api/notes/${state.currentNote.id}`, 'PUT', payload);
            showToast('Note saved successfully');
        }

        document.getElementById('saveStatus').textContent = 'Saved';
        document.getElementById('saveStatus').classList.add('saved');

        await loadNotes();

        if (response.note) {
            selectNote(response.note.id);
        }

    } catch (err) {
        console.error('Failed to save note:', err);
        showToast('Failed to save note');
        document.getElementById('saveStatus').textContent = 'Error saving';
    }
}

function cancelEdit() {
    if (state.isNewNote) {
        state.isNewNote = false;
        state.currentNote = null;
        updateUI();
    } else if (state.currentNote) {
        selectNote(state.currentNote.id);
    }
}

function showDeleteModal() {
    document.getElementById('deleteModal').classList.remove('hidden');
}

function hideDeleteModal() {
    document.getElementById('deleteModal').classList.add('hidden');
}

async function deleteNote() {
    if (!state.currentNote) return;

    try {
        await apiRequest(`/api/notes/${state.currentNote.id}`, 'DELETE');
        showToast('Note deleted');

        state.currentNote = null;
        state.isNewNote = false;

        hideDeleteModal();
        await loadNotes();
        updateUI();

    } catch (err) {
        console.error('Failed to delete note:', err);
        showToast('Failed to delete note');
    }
}

function handleFilterSubjectChange(e) {
    const subjectId = e.target.value;
    loadModulesForSubject(subjectId, document.getElementById('filterModule'));
    applyFilters();
}

function handleNoteSubjectChange(e) {
    const subjectId = e.target.value;
    loadModulesForSubject(subjectId, document.getElementById('noteModule'));
    updateMetadataBadges();
}

function handleSearch(e) {
    state.searchQuery = e.target.value.toLowerCase();
    applyFilters();
}

function applyFilters() {
    const subjectId = document.getElementById('filterSubject').value;
    const moduleId = document.getElementById('filterModule').value;
    const caseId = document.getElementById('filterCase').value;

    state.filteredNotes = state.notes.filter(note => {
        if (subjectId) {
            const noteSubjectId = note.entity_type === 'subject' ? note.entity_id : note.subject_id;
            if (noteSubjectId != subjectId) return false;
        }

        if (moduleId && note.entity_type === 'module' && note.entity_id != moduleId) {
            return false;
        }

        if (caseId && note.entity_type === 'case' && note.entity_id != caseId) {
            return false;
        }

        if (state.searchQuery) {
            const searchIn = `${note.title} ${note.content}`.toLowerCase();
            if (!searchIn.includes(state.searchQuery)) return false;
        }

        return true;
    });

    renderNotesList();
}

function clearFilters() {
    document.getElementById('filterSubject').value = '';
    document.getElementById('filterModule').value = '';
    document.getElementById('filterModule').disabled = true;
    document.getElementById('filterCase').value = '';
    document.getElementById('searchNotes').value = '';
    state.searchQuery = '';
    state.filteredNotes = [...state.notes];
    renderNotesList();
}

function updateMetadataBadges() {
    const subjectId = document.getElementById('noteSubject').value;
    const moduleId = document.getElementById('noteModule').value;
    const caseId = document.getElementById('noteCase').value;

    const badges = [];

    if (subjectId) {
        const subjectName = getSubjectName(subjectId);
        if (subjectName) {
            badges.push(`<span class="metadata-badge subject">${escapeHtml(subjectName)}</span>`);
        }
    }

    if (moduleId) {
        const moduleName = getModuleName(moduleId);
        if (moduleName) {
            badges.push(`<span class="metadata-badge module">${escapeHtml(moduleName)}</span>`);
        }
    }

    if (caseId) {
        const caseName = getCaseName(caseId);
        if (caseName) {
            badges.push(`<span class="metadata-badge case">${escapeHtml(caseName)}</span>`);
        }
    }

    document.getElementById('metadataBadges').innerHTML = badges.join('');
}

function getSubjectName(id) {
    const subject = state.subjects.find(s => s.id == id);
    return subject?.title || '';
}

function getModuleName(id) {
    const module = state.modules.find(m => m.id == id);
    return module?.title || '';
}

function getCaseName(id) {
    const caseItem = state.cases.find(c => c.id == id);
    return caseItem?.title || '';
}

function checkURLParams() {
    const params = new URLSearchParams(window.location.search);
    const subjectId = params.get('subject_id');
    const moduleId = params.get('module_id');
    const caseId = params.get('case_id');
    const action = params.get('action');

    if (action === 'new') {
        createNewNote();

        if (subjectId) {
            document.getElementById('noteSubject').value = subjectId;
            loadModulesForSubject(subjectId, document.getElementById('noteModule')).then(() => {
                if (moduleId) {
                    document.getElementById('noteModule').value = moduleId;
                }
                updateMetadataBadges();
            });
        }

        if (caseId) {
            document.getElementById('noteCase').value = caseId;
            updateMetadataBadges();
        }
    } else if (subjectId || caseId) {
        if (subjectId) {
            document.getElementById('filterSubject').value = subjectId;
            loadModulesForSubject(subjectId, document.getElementById('filterModule'));
        }
        if (caseId) {
            document.getElementById('filterCase').value = caseId;
        }
        applyFilters();
    }
}

async function apiRequest(endpoint, method = 'GET', body = null) {
    const token = localStorage.getItem('access_token');
    const headers = {
        'Content-Type': 'application/json'
    };

    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const config = {
        method,
        headers
    };

    if (body) {
        config.body = JSON.stringify(body);
    }

    const response = await fetch(`${API_BASE_URL}${endpoint}`, config);
    
    if (method === 'DELETE' && response.status === 204) {
        return {};
    }

    const data = await response.json();

    if (!response.ok) {
        if (response.status === 401) {
            localStorage.removeItem('access_token');
            window.location.href = '/html/login.html';
        }
        throw new Error(data.detail || 'API request failed');
    }

    return data;
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showToast(message) {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 3000);
}

function logout() {
    localStorage.removeItem('access_token');
    window.location.href = '/html/login.html';
}

window.selectNote = selectNote;
