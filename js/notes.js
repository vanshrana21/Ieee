/**
 * My Notes - Demo Safe Frontend Version
 * Semester 1 ONLY - localStorage based
 */

if (!window.API_BASE_URL) {
    window.API_BASE_URL = 'http://127.0.0.1:8000';
}

// 📘 SEMESTER 1 SCOPE (HARD-CODED)
const SEM1_DATA = {
    subjects: [
        {
            id: 'eng_1',
            title: 'General and Legal English',
            modules: ['Vocabulary & Legal Terminology', 'Grammar & Sentence Correction', 'Legal Writing']
        },
        {
            id: 'pol_1',
            title: 'Fundamental Principles of Political Science',
            modules: ['Political Theory Concepts', 'Thinkers-Based Questions', 'Sovereignty']
        },
        {
            id: 'soc_1',
            title: 'Sociology–I (Legal Sociology)',
            modules: ['Law and Society', 'Social Institutions & Law', 'Law as Instrument of Social Change']
        },
        {
            id: 'his_1',
            title: 'Indian History – Part I',
            modules: ['Ancient Indian History', 'Medieval Indian History', 'Society & Culture']
        }
    ],
    cases: [
        { id: 'maneka_1978', title: 'Maneka Gandhi v. Union of India (1978)' }
    ]
};

let state = {
    notes: [],
    filteredNotes: [],
    currentNote: null,
    isNewNote: false,
    searchQuery: '',
    filters: {
        subject: '',
        module: '',
        case: ''
    }
};

document.addEventListener('DOMContentLoaded', function() {
    initializePage();
});

function initializePage() {
    setupEventListeners();
    setupSidebarToggle();
    loadUserInfo();
    populateStaticSelectors();
    loadNotesFromStorage();
    checkURLParams();
    console.log("Subject select bound");
    console.log("Subject changed");
}

function setupEventListeners() {
    // Buttons
    document.getElementById('newNoteBtn')?.addEventListener('click', createNewNote);
    document.getElementById('emptyNewNoteBtn')?.addEventListener('click', createNewNote);
    document.getElementById('saveNoteBtn')?.addEventListener('click', saveNote);
    document.getElementById('cancelNoteBtn')?.addEventListener('click', cancelEdit);
    document.getElementById('deleteNoteBtn')?.addEventListener('click', showDeleteModal);
    document.getElementById('confirmDeleteBtn')?.addEventListener('click', deleteNote);
    document.getElementById('cancelDeleteBtn')?.addEventListener('click', hideDeleteModal);
    document.getElementById('clearFiltersBtn')?.addEventListener('click', clearFilters);
    document.getElementById('logoutBtn')?.addEventListener('click', logout);

    // Filters
    document.getElementById('filterSubject')?.addEventListener('change', handleFilterSubjectChange);
    document.getElementById('filterModule')?.addEventListener('change', (e) => {
        state.filters.module = e.target.value;
        applyFilters();
    });
    document.getElementById('filterCase')?.addEventListener('change', (e) => {
        state.filters.case = e.target.value;
        applyFilters();
    });
    document.getElementById('searchNotes')?.addEventListener('input', (e) => {
        state.searchQuery = e.target.value.toLowerCase();
        applyFilters();
    });

    // Editor fields
    document.getElementById('noteSubject')?.addEventListener('change', handleNoteSubjectChange);
    
    // Modal overlay
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

function loadUserInfo() {
    const userName = localStorage.getItem('legalai_user_name') || 'Student';
    const userNameEl = document.getElementById('userName');
    if (userNameEl) userNameEl.textContent = userName;
}

function populateStaticSelectors() {
    const filterSubject = document.getElementById('filterSubject');
    const noteSubject = document.getElementById('noteSubject');
    const filterCase = document.getElementById('filterCase');
    const noteCase = document.getElementById('noteCase');

    if (filterSubject && noteSubject) {
        SEM1_DATA.subjects.forEach(s => {
            const opt1 = new Option(s.title, s.id);
            const opt2 = new Option(s.title, s.id);
            filterSubject.add(opt1);
            noteSubject.add(opt2);
        });
    }

    if (filterCase && noteCase) {
        SEM1_DATA.cases.forEach(c => {
            const opt1 = new Option(c.title, c.id);
            const opt2 = new Option(c.title, c.id);
            filterCase.add(opt1);
            noteCase.add(opt2);
        });
    }
}

function loadNotesFromStorage() {
    const storedNotes = localStorage.getItem('juris_ai_notes');
    state.notes = storedNotes ? JSON.parse(storedNotes) : [];
    state.filteredNotes = [...state.notes];
    renderNotesList();
    updateUI();
}

function saveNotesToStorage() {
    localStorage.setItem('juris_ai_notes', JSON.stringify(state.notes));
    if (state.notes.length > 0) {
        localStorage.setItem('juris_ai_has_notes', 'true');
    }
}

function renderNotesList() {
    const listEl = document.getElementById('notesList');
    const countEl = document.getElementById('notesCount');
    if (!listEl || !countEl) return;

    countEl.textContent = `${state.filteredNotes.length} note${state.filteredNotes.length !== 1 ? 's' : ''}`;

    if (state.filteredNotes.length === 0) {
        listEl.innerHTML = '<div class="empty-list-msg">No notes found</div>';
        return;
    }

    listEl.innerHTML = state.filteredNotes.map(note => {
        const subject = SEM1_DATA.subjects.find(s => s.id === note.subjectId);
        const caseObj = SEM1_DATA.cases.find(c => c.id === note.caseId);
        
        return `
            <div class="note-item ${state.currentNote?.id === note.id ? 'active' : ''}" 
                 onclick="window.selectNote('${note.id}')">
                <div class="note-item-title">${escapeHtml(note.title || 'Untitled Note')}</div>
                <div class="note-item-preview">${escapeHtml(note.content?.substring(0, 60) || '')}...</div>
                <div class="note-item-meta">
                    ${subject ? `<span class="note-item-badge subject">${escapeHtml(subject.title)}</span>` : ''}
                    ${note.moduleName ? `<span class="note-item-badge module">${escapeHtml(note.moduleName)}</span>` : ''}
                    ${caseObj ? `<span class="note-item-badge case">${escapeHtml(caseObj.title)}</span>` : ''}
                </div>
            </div>
        `;
    }).join('');
}

function updateUI() {
    const hasEverHadNotes = localStorage.getItem('juris_ai_has_notes') === 'true' || state.notes.length > 0;
    const hasCurrentNote = state.currentNote !== null || state.isNewNote;

    const emptyState = document.getElementById('emptyState');
    const noteEditor = document.getElementById('noteEditor');

    if (emptyState) emptyState.classList.toggle('hidden', hasEverHadNotes || hasCurrentNote);
    if (noteEditor) noteEditor.classList.toggle('hidden', !hasCurrentNote);
}

function selectNote(noteId) {
    const note = state.notes.find(n => n.id === noteId);
    if (!note) return;

    state.currentNote = note;
    state.isNewNote = false;

    document.getElementById('noteTitle').value = note.title || '';
    document.getElementById('noteContent').value = note.content || '';
    document.getElementById('noteSubject').value = note.subjectId || '';
    document.getElementById('noteCase').value = note.caseId || '';

    handleNoteSubjectChange({ target: { value: note.subjectId } });
    document.getElementById('noteModule').value = note.moduleName || '';

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
    document.getElementById('noteModule').innerHTML = '<option value="">-- Select Module --</option>';
    document.getElementById('noteModule').disabled = true;
    document.getElementById('noteCase').value = '';

    document.getElementById('metadataBadges').innerHTML = '';
    document.getElementById('deleteNoteBtn').style.display = 'none';
    document.getElementById('saveStatus').textContent = '';

    updateUI();
    document.getElementById('noteTitle').focus();
}

function saveNote() {
    const title = document.getElementById('noteTitle').value.trim();
    const content = document.getElementById('noteContent').value.trim();
    const subjectId = document.getElementById('noteSubject').value;
    const moduleName = document.getElementById('noteModule').value;
    const caseId = document.getElementById('noteCase').value;

    if (!title) {
        showToast('Please enter a title');
        return;
    }

    const noteData = {
        id: state.isNewNote ? Date.now().toString() : state.currentNote.id,
        title,
        content,
        subjectId,
        moduleName,
        caseId,
        updatedAt: new Date().toISOString()
    };

    if (state.isNewNote) {
        state.notes.unshift(noteData);
    } else {
        const index = state.notes.findIndex(n => n.id === state.currentNote.id);
        if (index !== -1) state.notes[index] = noteData;
    }

    saveNotesToStorage();
    state.currentNote = noteData;
    state.isNewNote = false;
    
    applyFilters();
    showToast('Note saved successfully');
    document.getElementById('saveStatus').textContent = 'Saved';
    updateUI();
}

function deleteNote() {
    if (!state.currentNote) return;

    state.notes = state.notes.filter(n => n.id !== state.currentNote.id);
    saveNotesToStorage();
    
    state.currentNote = null;
    state.isNewNote = false;

    hideDeleteModal();
    applyFilters();
    updateUI();
    showToast('Note deleted');
}

function handleFilterSubjectChange(e) {
    const subjectId = e.target.value;
    state.filters.subject = subjectId;
    state.filters.module = '';
    
    const moduleSelect = document.getElementById('filterModule');
    moduleSelect.innerHTML = '<option value="">All Modules</option>';
    
    if (subjectId) {
        const subject = SEM1_DATA.subjects.find(s => s.id === subjectId);
        if (subject) {
            subject.modules.forEach(m => {
                moduleSelect.add(new Option(m, m));
            });
            moduleSelect.disabled = false;
        }
    } else {
        moduleSelect.disabled = true;
    }
    
    applyFilters();
}

function handleNoteSubjectChange(e) {
    const subjectId = e.target.value;
    const moduleSelect = document.getElementById('noteModule');
    if (!moduleSelect) return;

    moduleSelect.innerHTML = '<option value="">-- Select Module --</option>';
    
    if (subjectId) {
        const subject = SEM1_DATA.subjects.find(s => s.id === subjectId);
        if (subject) {
            subject.modules.forEach(m => {
                moduleSelect.add(new Option(m, m));
            });
            moduleSelect.disabled = false;
        }
    } else {
        moduleSelect.disabled = true;
    }
    updateMetadataBadges();
}

function applyFilters() {
    state.filteredNotes = state.notes.filter(note => {
        if (state.filters.subject && note.subjectId !== state.filters.subject) return false;
        if (state.filters.module && note.moduleName !== state.filters.module) return false;
        if (state.filters.case && note.caseId !== state.filters.case) return false;
        
        if (state.searchQuery) {
            const searchStr = `${note.title} ${note.content}`.toLowerCase();
            if (!searchStr.includes(state.searchQuery)) return false;
        }
        
        return true;
    });
    
    renderNotesList();
}

function clearFilters() {
    state.filters = { subject: '', module: '', case: '' };
    state.searchQuery = '';
    
    document.getElementById('filterSubject').value = '';
    document.getElementById('filterModule').value = '';
    document.getElementById('filterModule').disabled = true;
    document.getElementById('filterCase').value = '';
    document.getElementById('searchNotes').value = '';
    
    applyFilters();
}

function updateMetadataBadges() {
    const subjectId = document.getElementById('noteSubject').value;
    const moduleName = document.getElementById('noteModule').value;
    const caseId = document.getElementById('noteCase').value;

    const badges = [];
    if (subjectId) {
        const s = SEM1_DATA.subjects.find(sub => sub.id === subjectId);
        if (s) badges.push(`<span class="metadata-badge subject">${escapeHtml(s.title)}</span>`);
    }
    if (moduleName) {
        badges.push(`<span class="metadata-badge module">${escapeHtml(moduleName)}</span>`);
    }
    if (caseId) {
        const c = SEM1_DATA.cases.find(cs => cs.id === caseId);
        if (c) badges.push(`<span class="metadata-badge case">${escapeHtml(c.title)}</span>`);
    }

    const badgeContainer = document.getElementById('metadataBadges');
    if (badgeContainer) badgeContainer.innerHTML = badges.join('');
}

function cancelEdit() {
    state.currentNote = null;
    state.isNewNote = false;
    updateUI();
}

function showDeleteModal() {
    document.getElementById('deleteModal').classList.remove('hidden');
}

function hideDeleteModal() {
    document.getElementById('deleteModal').classList.add('hidden');
}

function checkURLParams() {
    const params = new URLSearchParams(window.location.search);
    const subjectId = params.get('subject_id');
    const caseId = params.get('case_id');
    const action = params.get('action');

    if (action === 'new') {
        createNewNote();
        if (subjectId) {
            document.getElementById('noteSubject').value = subjectId;
            handleNoteSubjectChange({ target: { value: subjectId } });
        }
        if (caseId) {
            document.getElementById('noteCase').value = caseId;
        }
    }
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

// Global exposure
window.selectNote = selectNote;
window.createNewNote = createNewNote;
