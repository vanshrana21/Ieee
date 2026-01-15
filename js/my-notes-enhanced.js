/**
 * my-notes-enhanced.js
 * Phase 10: Full backend integration for Smart Notes
 */

const API_BASE = 'http://127.0.0.1:8000';

// Application State
let notes = [];
let currentFilter = {
    subject: null,
    importance: null,
    search: '',
    sort: 'recent'
};
let editingNoteId = null;
let noteToDelete = null;

// DOM Elements
const notesList = document.getElementById('notesList');
const editorPanel = document.getElementById('editorPanel');
const editorTitle = document.getElementById('editorTitle');
const noteTitle = document.getElementById('noteTitle');
const noteSubject = document.getElementById('noteSubject');
const noteImportance = document.getElementById('noteImportance');
const noteTags = document.getElementById('noteTags');
const noteContent = document.getElementById('noteContent');
const saveBtn = document.getElementById('saveBtn');
const deleteModal = document.getElementById('deleteModal');

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', async () => {
    // Check authentication
    if (!window.auth.isAuthenticated()) {
        window.location.href = '/html/login.html';
        return;
    }
    
    await init();
});

async function init() {
    setupEventListeners();
    await loadNotes();
    renderNotes();
}

// ============================================================================
// API CALLS
// ============================================================================

async function loadNotes() {
    try {
        const token = window.auth.getToken();
        
        const response = await fetch(`${API_BASE}/api/notes`, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        const data = await response.json();
        
        if (response.ok) {
            notes = data.notes || [];
        } else {
            console.error('Failed to load notes:', data.detail);
            notes = [];
        }
        
    } catch (error) {
        console.error('Load notes error:', error);
        notes = [];
    }
}

async function createNote(noteData) {
    try {
        const token = window.auth.getToken();
        
        const response = await fetch(`${API_BASE}/api/notes`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(noteData)
        });
        
        const data = await response.json();
        
        if (response.ok) {
            return { success: true, note: data };
        } else {
            return { success: false, error: data.detail };
        }
        
    } catch (error) {
        return { success: false, error: error.message };
    }
}

async function updateNote(noteId, noteData) {
    try {
        const token = window.auth.getToken();
        
        const response = await fetch(`${API_BASE}/api/notes/${noteId}`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(noteData)
        });
        
        const data = await response.json();
        
        if (response.ok) {
            return { success: true, note: data };
        } else {
            return { success: false, error: data.detail };
        }
        
    } catch (error) {
        return { success: false, error: error.message };
    }
}

async function deleteNoteAPI(noteId) {
    try {
        const token = window.auth.getToken();
        
        const response = await fetch(`${API_BASE}/api/notes/${noteId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (response.ok) {
            return { success: true };
        } else {
            const data = await response.json();
            return { success: false, error: data.detail };
        }
        
    } catch (error) {
        return { success: false, error: error.message };
    }
}

// ============================================================================
// EVENT LISTENERS
// ============================================================================

function setupEventListeners() {
    // New Note button
    const newNoteBtn = document.getElementById('newNoteBtn');
    if (newNoteBtn) {
        newNoteBtn.addEventListener('click', openNewNote);
    }
    
    // Close editor
    const closeEditor = document.getElementById('closeEditor');
    if (closeEditor) {
        closeEditor.addEventListener('click', closeEditorPanel);
    }
    
    // Cancel button
    const cancelBtn = document.getElementById('cancelBtn');
    if (cancelBtn) {
        cancelBtn.addEventListener('click', closeEditorPanel);
    }
    
    // Save button
    if (saveBtn) {
        saveBtn.addEventListener('click', saveNote);
    }
    
    // Search
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            currentFilter.search = e.target.value.toLowerCase();
            renderNotes();
        });
    }
    
    // Sort
    const sortSelect = document.getElementById('sortSelect');
    if (sortSelect) {
        sortSelect.addEventListener('change', (e) => {
            currentFilter.sort = e.target.value;
            renderNotes();
        });
    }
    
    // Delete modal
    const cancelDelete = document.getElementById('cancelDelete');
    const confirmDelete = document.getElementById('confirmDelete');
    
    if (cancelDelete) {
        cancelDelete.addEventListener('click', closeDeleteModal);
    }
    
    if (confirmDelete) {
        confirmDelete.addEventListener('click', executeDelete);
    }
    
    // Logout
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', (e) => {
            e.preventDefault();
            window.auth.logout();
        });
    }
}

// ============================================================================
// EDITOR FUNCTIONS
// ============================================================================

function openNewNote() {
    editingNoteId = null;
    editorTitle.textContent = 'Create New Note';
    clearEditorForm();
    editorPanel.classList.add('active');
    noteTitle.focus();
}

function openEditNote(noteId) {
    const note = notes.find(n => n.id === noteId);
    
    if (!note) {
        return;
    }
    
    editingNoteId = noteId;
    editorTitle.textContent = 'Edit Note';
    
    noteTitle.value = note.title;
    noteContent.value = note.content;
    
    if (noteSubject) {
        noteSubject.value = note.subject_id || '';
    }
    
    if (noteImportance) {
        noteImportance.value = note.importance || 'medium';
    }
    
    if (noteTags) {
        noteTags.value = note.tags ? note.tags.join(', ') : '';
    }
    
    editorPanel.classList.add('active');
    noteTitle.focus();
}

function closeEditorPanel() {
    editorPanel.classList.remove('active');
    clearEditorForm();
    editingNoteId = null;
}

function clearEditorForm() {
    noteTitle.value = '';
    noteContent.value = '';
    
    if (noteSubject) {
        noteSubject.value = '';
    }
    
    if (noteImportance) {
        noteImportance.value = 'medium';
    }
    
    if (noteTags) {
        noteTags.value = '';
    }
}

async function saveNote() {
    const title = noteTitle.value.trim();
    const content = noteContent.value.trim();
    
    if (!title) {
        alert('Please enter a note title');
        noteTitle.focus();
        return;
    }
    
    if (!content) {
        alert('Please enter note content');
        noteContent.focus();
        return;
    }
    
    const tags = noteTags && noteTags.value 
        ? noteTags.value.split(',').map(t => t.trim()).filter(t => t)
        : [];
    
    const noteData = {
        title,
        content,
        tags,
        importance: noteImportance ? noteImportance.value : 'medium',
        subject_id: noteSubject && noteSubject.value ? parseInt(noteSubject.value) : null
    };
    
    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving...';
    
    try {
        let result;
        
        if (editingNoteId) {
            result = await updateNote(editingNoteId, noteData);
        } else {
            result = await createNote(noteData);
        }
        
        if (result.success) {
            await loadNotes();
            renderNotes();
            closeEditorPanel();
        } else {
            alert(`Error: ${result.error}`);
        }
        
    } catch (error) {
        alert('Failed to save note');
    } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save Note';
    }
}

// ============================================================================
// DELETE FUNCTIONS
// ============================================================================

function deleteNote(noteId) {
    noteToDelete = noteId;
    deleteModal.classList.add('active');
}

async function executeDelete() {
    if (!noteToDelete) {
        return;
    }
    
    const result = await deleteNoteAPI(noteToDelete);
    
    if (result.success) {
        await loadNotes();
        renderNotes();
    } else {
        alert(`Error deleting note: ${result.error}`);
    }
    
    closeDeleteModal();
}

function closeDeleteModal() {
    deleteModal.classList.remove('active');
    noteToDelete = null;
}

// ============================================================================
// RENDER FUNCTIONS
// ============================================================================

function renderNotes() {
    if (!notesList) {
        return;
    }
    
    let filteredNotes = [...notes];
    
    // Apply filters
    if (currentFilter.search) {
        filteredNotes = filteredNotes.filter(note => 
            note.title.toLowerCase().includes(currentFilter.search) ||
            note.content.toLowerCase().includes(currentFilter.search) ||
            (note.tags && note.tags.some(tag => tag.toLowerCase().includes(currentFilter.search)))
        );
    }
    
    if (currentFilter.importance) {
        filteredNotes = filteredNotes.filter(note => note.importance === currentFilter.importance);
    }
    
    if (currentFilter.subject) {
        filteredNotes = filteredNotes.filter(note => note.subject_id === currentFilter.subject);
    }
    
    // Apply sorting
    switch (currentFilter.sort) {
        case 'recent':
            filteredNotes.sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));
            break;
        case 'alphabetical':
            filteredNotes.sort((a, b) => a.title.localeCompare(b.title));
            break;
        case 'oldest':
            filteredNotes.sort((a, b) => new Date(a.updated_at) - new Date(b.updated_at));
            break;
    }
    
    // Render
    if (filteredNotes.length === 0) {
        notesList.innerHTML = `
            <div class="empty-state">
                <p>📝 No notes found</p>
                <p class="text-muted">Create your first note to get started</p>
            </div>
        `;
        return;
    }
    
    notesList.innerHTML = filteredNotes.map(note => `
        <div class="note-card" data-importance="${note.importance || 'medium'}">
            <div class="note-header">
                <h3>${escapeHtml(note.title)}</h3>
                ${note.is_pinned ? '<span class="pin-badge">📌</span>' : ''}
            </div>
            <div class="note-preview">${escapeHtml(note.content.substring(0, 150))}${note.content.length > 150 ? '...' : ''}</div>
            ${note.tags && note.tags.length > 0 ? `
                <div class="note-tags">
                    ${note.tags.map(tag => `<span class="tag">${escapeHtml(tag)}</span>`).join('')}
                </div>
            ` : ''}
            <div class="note-meta">
                <span>${formatDate(note.updated_at)}</span>
                <span class="importance-badge importance-${note.importance || 'medium'}">${note.importance || 'medium'}</span>
            </div>
            <div class="note-actions">
                <button onclick="openEditNote(${note.id})" class="btn-secondary">Edit</button>
                <button onclick="deleteNote(${note.id})" class="btn-danger">Delete</button>
            </div>
        </div>
    `).join('');
}

// ============================================================================
// UTILITIES
// ============================================================================

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diff = Math.floor((now - date) / 1000);
    
    if (diff < 60) return 'Just now';
    if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} hours ago`;
    if (diff < 604800) return `${Math.floor(diff / 86400)} days ago`;
    
    return date.toLocaleDateString();
}
