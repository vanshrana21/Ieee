// Notes Application - JavaScript
// Storage key for localStorage
const STORAGE_KEY = 'legalai_notes';

// Application State
let notes = [];
let currentFilter = {
    subject: null,
    caseLinked: false,
    search: '',
    sort: 'recent'
};
let editingNoteId = null;
let examMode = false;
let noteToDelete = null;

// DOM Elements
const backBtn = document.getElementById('backBtn');
const examToggle = document.getElementById('examToggle');
const newNoteBtn = document.getElementById('newNoteBtn');
const subjectCards = document.querySelectorAll('.subject-card');
const filterCaseLinked = document.getElementById('filterCaseLinked');
const sortSelect = document.getElementById('sortSelect');
const searchInput = document.getElementById('searchInput');
const notesList = document.getElementById('notesList');
const editorPanel = document.getElementById('editorPanel');
const editorTitle = document.getElementById('editorTitle');
const closeEditor = document.getElementById('closeEditor');
const noteTitle = document.getElementById('noteTitle');
const noteSubject = document.getElementById('noteSubject');
const linkedCase = document.getElementById('linkedCase');
const noteTags = document.getElementById('noteTags');
const noteContent = document.getElementById('noteContent');
const saveBtn = document.getElementById('saveBtn');
const cancelBtn = document.getElementById('cancelBtn');
const deleteModal = document.getElementById('deleteModal');
const confirmDelete = document.getElementById('confirmDelete');
const cancelDelete = document.getElementById('cancelDelete');
const toolbarBtns = document.querySelectorAll('.toolbar-btn');
const panelTitle = document.getElementById('panelTitle');

// Initialize Application
function init() {
    loadNotes();
    setupEventListeners();
    updateSubjectCards();
    renderNotes();
}

// Load notes from localStorage
function loadNotes() {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
        try {
            notes = JSON.parse(stored);
        } catch (e) {
            console.error('Error loading notes:', e);
            notes = [];
        }
    }
}

// Save notes to localStorage
function saveNotes() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(notes));
    updateSubjectCards();
}

// Setup Event Listeners
function setupEventListeners() {
    // Navigation
    backBtn.addEventListener('click', () => {
        window.location.href = 'dashboard-student.html';
    });

    // Exam Mode Toggle
    examToggle.addEventListener('click', toggleExamMode);

    // New Note Button
    newNoteBtn.addEventListener('click', openNewNote);

    // Subject Cards
    subjectCards.forEach(card => {
        card.addEventListener('click', () => {
            const subject = card.dataset.subject;
            selectSubject(subject);
        });
    });

    // Filters
    filterCaseLinked.addEventListener('change', (e) => {
        currentFilter.caseLinked = e.target.checked;
        renderNotes();
    });

    sortSelect.addEventListener('change', (e) => {
        currentFilter.sort = e.target.value;
        renderNotes();
    });

    searchInput.addEventListener('input', (e) => {
        currentFilter.search = e.target.value.toLowerCase();
        renderNotes();
    });

    // Editor
    closeEditor.addEventListener('click', closeEditorPanel);
    cancelBtn.addEventListener('click', closeEditorPanel);
    saveBtn.addEventListener('click', saveNote);

    // Toolbar
    toolbarBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const command = btn.dataset.command;
            document.execCommand(command, false, null);
            noteContent.focus();
        });
    });

    // Modal
    cancelDelete.addEventListener('click', closeDeleteModal);
    confirmDelete.addEventListener('click', executeDelete);

    // Close modal on overlay click
    deleteModal.addEventListener('click', (e) => {
        if (e.target === deleteModal) {
            closeDeleteModal();
        }
    });
}

// Toggle Exam Mode
function toggleExamMode() {
    examMode = !examMode;
    examToggle.classList.toggle('active', examMode);
    renderNotes();
}

// Select Subject
function selectSubject(subject) {
    // Update active state
    subjectCards.forEach(card => {
        card.classList.toggle('active', card.dataset.subject === subject);
    });

    // Update filter
    if (currentFilter.subject === subject) {
        currentFilter.subject = null;
        panelTitle.textContent = 'All Notes';
    } else {
        currentFilter.subject = subject;
        const subjectNames = {
            constitutional: 'Constitutional Law',
            criminal: 'Criminal Law',
            contract: 'Contract Law'
        };
        panelTitle.textContent = subjectNames[subject];
    }

    renderNotes();
}

// Update Subject Cards
function updateSubjectCards() {
    subjectCards.forEach(card => {
        const subject = card.dataset.subject;
        const subjectNotes = notes.filter(note => note.subject === subject);
        const count = subjectNotes.length;
        
        const countElem = card.querySelector('.note-count');
        const updatedElem = card.querySelector('.last-updated');
        
        countElem.textContent = `${count} note${count !== 1 ? 's' : ''}`;
        
        if (subjectNotes.length > 0) {
            const lastNote = subjectNotes.reduce((latest, note) => {
                return new Date(note.lastEdited) > new Date(latest.lastEdited) ? note : latest;
            });
            updatedElem.textContent = formatDate(lastNote.lastEdited);
        } else {
            updatedElem.textContent = 'Never updated';
        }
    });
}

// Open New Note
function openNewNote() {
    editingNoteId = null;
    editorTitle.textContent = 'Create New Note';
    clearEditorForm();
    editorPanel.classList.add('active');
}

// Open Edit Note
function openEditNote(noteId) {
    const note = notes.find(n => n.id === noteId);
    if (!note) return;

    editingNoteId = noteId;
    editorTitle.textContent = 'Edit Note';
    
    noteTitle.value = note.title;
    noteSubject.value = note.subject;
    linkedCase.value = note.linkedCase || '';
    noteTags.value = note.tags.join(', ');
    noteContent.innerHTML = note.content;
    
    editorPanel.classList.add('active');
}

// Close Editor Panel
function closeEditorPanel() {
    editorPanel.classList.remove('active');
    clearEditorForm();
    editingNoteId = null;
}

// Clear Editor Form
function clearEditorForm() {
    noteTitle.value = '';
    noteSubject.value = 'constitutional';
    linkedCase.value = '';
    noteTags.value = '';
    noteContent.innerHTML = '';
}

// Save Note
function saveNote() {
    const title = noteTitle.value.trim();
    const content = noteContent.innerHTML.trim();
    
    if (!title) {
        noteTitle.focus();
        return;
    }
    
    if (!content || content === '<br>') {
        noteContent.focus();
        return;
    }
    
    const tags = noteTags.value
        .split(',')
        .map(tag => tag.trim())
        .filter(tag => tag.length > 0);
    
    const noteData = {
        title,
        subject: noteSubject.value,
        linkedCase: linkedCase.value.trim() || null,
        tags,
        content,
        lastEdited: new Date().toISOString()
    };
    
    if (editingNoteId) {
        // Update existing note
        const index = notes.findIndex(n => n.id === editingNoteId);
        if (index !== -1) {
            notes[index] = { ...notes[index], ...noteData };
        }
    } else {
        // Create new note
        const newNote = {
            id: generateId(),
            ...noteData,
            createdAt: new Date().toISOString()
        };
        notes.unshift(newNote);
    }
    
    saveNotes();
    renderNotes();
    closeEditorPanel();
}

// Delete Note
function deleteNote(noteId) {
    noteToDelete = noteId;
    deleteModal.classList.add('active');
}

// Execute Delete
function executeDelete() {
    if (noteToDelete) {
        notes = notes.filter(note => note.id !== noteToDelete);
        saveNotes();
        renderNotes();
        noteToDelete = null;
    }
    closeDeleteModal();
}

// Close Delete Modal
function closeDeleteModal() {
    deleteModal.classList.remove('active');
    noteToDelete = null;
}

// Copy Note Content
function copyNote(noteId) {
    const note = notes.find(n => n.id === noteId);
    if (!note) return;
    
    const textContent = noteContent.textContent || noteContent.innerText;
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = note.content;
    const text = tempDiv.textContent || tempDiv.innerText;
    
    navigator.clipboard.writeText(text).then(() => {
        // Visual feedback could be added here
        console.log('Note copied to clipboard');
    }).catch(err => {
        console.error('Failed to copy:', err);
    });
}

// Export as PDF (placeholder)
function exportPDF(noteId) {
    const note = notes.find(n => n.id === noteId);
    if (!note) return;
    
    // This is a UI placeholder - actual PDF generation would require a library
    console.log('Export PDF functionality - would export:', note.title);
}

// Render Notes
function renderNotes() {
    let filteredNotes = [...notes];
    
    // Apply subject filter
    if (currentFilter.subject) {
        filteredNotes = filteredNotes.filter(note => note.subject === currentFilter.subject);
    }
    
    // Apply case-linked filter
    if (currentFilter.caseLinked) {
        filteredNotes = filteredNotes.filter(note => note.linkedCase);
    }
    
    // Apply search filter
    if (currentFilter.search) {
        filteredNotes = filteredNotes.filter(note => {
            const searchLower = currentFilter.search;
            return note.title.toLowerCase().includes(searchLower) ||
                   (note.linkedCase && note.linkedCase.toLowerCase().includes(searchLower)) ||
                   note.tags.some(tag => tag.toLowerCase().includes(searchLower)) ||
                   note.content.toLowerCase().includes(searchLower);
        });
    }
    
    // Apply sorting
    switch (currentFilter.sort) {
        case 'recent':
            filteredNotes.sort((a, b) => new Date(b.lastEdited) - new Date(a.lastEdited));
            break;
        case 'alphabetical':
            filteredNotes.sort((a, b) => a.title.localeCompare(b.title));
            break;
        case 'oldest':
            filteredNotes.sort((a, b) => new Date(a.lastEdited) - new Date(b.lastEdited));
            break;
    }
    
    // Render
    if (filteredNotes.length === 0) {
        notesList.innerHTML = `
            <div class="empty-state">
                <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
                    <rect x="12" y="8" width="40" height="48" rx="2" stroke="currentColor" stroke-width="2"/>
                    <line x1="20" y1="20" x2="44" y2="20" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    <line x1="20" y1="28" x2="38" y2="28" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    <line x1="20" y1="36" x2="42" y2="36" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                </svg>
                <h3>No notes found</h3>
                <p>${currentFilter.subject || currentFilter.caseLinked || currentFilter.search ? 
                    'Try adjusting your filters or search query.' : 
                    'Create your first note to get started with your legal research.'}</p>
            </div>
        `;
        return;
    }
    
    notesList.innerHTML = filteredNotes.map((note, index) => {
        const preview = extractTextPreview(note.content);
        return `
            <div class="note-item ${examMode ? 'exam-mode' : ''}" style="animation-delay: ${index * 0.05}s">
                <div class="note-header">
                    <div class="note-title-group">
                        <h3>${escapeHtml(note.title)}</h3>
                        ${note.linkedCase ? `<div class="note-case">${escapeHtml(note.linkedCase)}</div>` : ''}
                    </div>
                    <div class="note-actions-inline">
                        <button class="note-action-btn" onclick="app.openEditNote('${note.id}')" title="Edit">
                            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                                <path d="M11.5 2L14 4.5L5 13.5H2.5V11L11.5 2Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                            </svg>
                        </button>
                        <button class="note-action-btn" onclick="app.copyNote('${note.id}')" title="Copy">
                            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                                <rect x="5" y="5" width="9" height="9" rx="1" stroke="currentColor" stroke-width="1.5"/>
                                <path d="M3 11V3C3 2.44772 3.44772 2 4 2H10" stroke="currentColor" stroke-width="1.5"/>
                            </svg>
                        </button>
                        <button class="note-action-btn" onclick="app.deleteNote('${note.id}')" title="Delete">
                            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                                <path d="M3 4H13M5 4V3C5 2.44772 5.44772 2 6 2H10C10.5523 2 11 2.44772 11 3V4M6 7V11M10 7V11M4 4L5 13C5 13.5523 5.44772 14 6 14H10C10.5523 14 11 13.5523 11 13L12 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                            </svg>
                        </button>
                    </div>
                </div>
                <div class="note-preview ${examMode ? 'exam-mode' : ''}">${preview}</div>
                <div class="note-footer">
                    <div class="note-tags">
                        ${note.tags.map(tag => `<span class="note-tag">${escapeHtml(tag)}</span>`).join('')}
                    </div>
                    <div class="note-date">${formatDate(note.lastEdited)}</div>
                </div>
            </div>
        `;
    }).join('');
}

// Extract Text Preview
function extractTextPreview(html) {
    const temp = document.createElement('div');
    temp.innerHTML = html;
    
    // Get text content
    let text = temp.textContent || temp.innerText || '';
    
    // In exam mode, extract bullet points
    if (examMode) {
        const listItems = temp.querySelectorAll('li');
        if (listItems.length > 0) {
            text = Array.from(listItems)
                .slice(0, 3)
                .map(li => '• ' + (li.textContent || li.innerText))
                .join(' ');
        }
    }
    
    return escapeHtml(text.substring(0, 200) + (text.length > 200 ? '...' : ''));
}

// Utility: Generate ID
function generateId() {
    return Date.now().toString(36) + Math.random().toString(36).substr(2);
}

// Utility: Format Date
function formatDate(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins} minute${diffMins !== 1 ? 's' : ''} ago`;
    if (diffHours < 24) return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
    if (diffDays < 7) return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
    
    const options = { year: 'numeric', month: 'short', day: 'numeric' };
    return date.toLocaleDateString('en-US', options);
}

// Utility: Escape HTML
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}

// Create global app object for inline event handlers
window.app = {
    openEditNote,
    deleteNote,
    copyNote,
    exportPDF
};

// Initialize on DOM load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}