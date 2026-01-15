/**
 * notes.js
 * Phase 7: Smart Notes Management
 */

const API_BASE_URL = 'http://127.0.0.1:8000';

// ============================================================================
// NOTES API
// ============================================================================

async function createNote(noteData) {
    try {
        const token = window.auth.getToken();
        if (!token) throw new Error('Not authenticated');

        const response = await fetch(`${API_BASE_URL}/api/notes`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(noteData)
        });

        const data = await response.json();
        return response.ok ? { success: true, data } : { success: false, error: data.detail };

    } catch (error) {
        return { success: false, error: error.message };
    }
}

async function listNotes(filters = {}) {
    try {
        const token = window.auth.getToken();
        if (!token) throw new Error('Not authenticated');

        const params = new URLSearchParams();
        if (filters.entity_type) params.append('entity_type', filters.entity_type);
        if (filters.entity_id) params.append('entity_id', filters.entity_id);
        if (filters.tags) params.append('tags', filters.tags);
        if (filters.search) params.append('search', filters.search);
        if (filters.importance) params.append('importance', filters.importance);
        if (filters.pinned_only) params.append('pinned_only', 'true');
        params.append('page', filters.page || 1);
        params.append('page_size', filters.page_size || 20);

        const response = await fetch(
            `${API_BASE_URL}/api/notes?${params.toString()}`,
            {
                headers: { 'Authorization': `Bearer ${token}` }
            }
        );

        const data = await response.json();
        return response.ok ? { success: true, data } : { success: false, error: data.detail };

    } catch (error) {
        return { success: false, error: error.message };
    }
}

async function getNote(noteId) {
    try {
        const token = window.auth.getToken();
        if (!token) throw new Error('Not authenticated');

        const response = await fetch(`${API_BASE_URL}/api/notes/${noteId}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        const data = await response.json();
        return response.ok ? { success: true, data } : { success: false, error: data.detail };

    } catch (error) {
        return { success: false, error: error.message };
    }
}

async function updateNote(noteId, updates) {
    try {
        const token = window.auth.getToken();
        if (!token) throw new Error('Not authenticated');

        const response = await fetch(`${API_BASE_URL}/api/notes/${noteId}`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(updates)
        });

        const data = await response.json();
        return response.ok ? { success: true, data } : { success: false, error: data.detail };

    } catch (error) {
        return { success: false, error: error.message };
    }
}

async function deleteNote(noteId) {
    try {
        const token = window.auth.getToken();
        if (!token) throw new Error('Not authenticated');

        const response = await fetch(`${API_BASE_URL}/api/notes/${noteId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });

        return response.ok || response.status === 204 
            ? { success: true } 
            : { success: false, error: 'Failed to delete' };

    } catch (error) {
        return { success: false, error: error.message };
    }
}

async function getAIAssist(noteId, action) {
    try {
        const token = window.auth.getToken();
        if (!token) throw new Error('Not authenticated');

        const response = await fetch(`${API_BASE_URL}/api/notes/ai-assist`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ note_id: noteId, action })
        });

        const data = await response.json();
        return response.ok ? { success: true, data } : { success: false, error: data.detail };

    } catch (error) {
        return { success: false, error: error.message };
    }
}

// ============================================================================
// UI FUNCTIONS
// ============================================================================

let noteDraft = null; // Autosave draft storage

function openNoteModal(entityType = null, entityId = null, entityTitle = null) {
    const modal = document.getElementById('noteModal');
    if (!modal) {
        console.error('Note modal not found');
        return;
    }

    // Reset form
    document.getElementById('noteTitle').value = '';
    document.getElementById('noteContent').value = '';
    document.getElementById('noteTags').value = '';
    document.getElementById('noteImportance').value = 'medium';
    document.getElementById('noteIsPinned').checked = false;
    document.getElementById('noteId').value = '';

    // Set entity link if provided
    if (entityType && entityId) {
        document.getElementById('linkedEntityType').value = entityType;
        document.getElementById('linkedEntityId').value = entityId;
        
        const linkInfo = document.getElementById('entityLinkInfo');
        if (linkInfo) {
            const icon = {
                'subject': '📚',
                'case': '⚖️',
                'learn': '📖',
                'practice': '✏️'
            }[entityType] || '📄';
            
            linkInfo.innerHTML = `${icon} Linked to: ${entityTitle || 'Unknown'}`;
            linkInfo.style.display = 'block';
        }
    } else {
        document.getElementById('linkedEntityType').value = '';
        document.getElementById('linkedEntityId').value = '';
        const linkInfo = document.getElementById('entityLinkInfo');
        if (linkInfo) linkInfo.style.display = 'none';
    }

    // Load draft if exists
    if (noteDraft) {
        if (confirm('Restore unsaved draft?')) {
            document.getElementById('noteTitle').value = noteDraft.title || '';
            document.getElementById('noteContent').value = noteDraft.content || '';
        } else {
            noteDraft = null;
        }
    }

    modal.style.display = 'block';
    
    // Start autosave
    startAutosave();
}

function closeNoteModal() {
    const modal = document.getElementById('noteModal');
    if (modal) modal.style.display = 'none';
    stopAutosave();
    noteDraft = null;
}

let autosaveInterval;

function startAutosave() {
    stopAutosave();
    autosaveInterval = setInterval(() => {
        const title = document.getElementById('noteTitle').value;
        const content = document.getElementById('noteContent').value;
        
        if (title || content) {
            noteDraft = { title, content };
            console.log('Draft autosaved');
        }
    }, 5000); // Every 5 seconds
}

function stopAutosave() {
    if (autosaveInterval) {
        clearInterval(autosaveInterval);
        autosaveInterval = null;
    }
}

async function saveNote() {
    const noteId = document.getElementById('noteId').value;
    const title = document.getElementById('noteTitle').value.trim();
    const content = document.getElementById('noteContent').value.trim();
    const tags = document.getElementById('noteTags').value
        .split(',')
        .map(t => t.trim())
        .filter(t => t);
    const importance = document.getElementById('noteImportance').value;
    const isPinned = document.getElementById('noteIsPinned').checked;
    const linkedEntityType = document.getElementById('linkedEntityType').value || null;
    const linkedEntityId = document.getElementById('linkedEntityId').value || null;

    if (!title || !content) {
        alert('Please provide both title and content');
        return;
    }

    const saveBtn = document.getElementById('saveNoteBtn');
    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.textContent = 'Saving...';
    }

    try {
        let result;

        if (noteId) {
            // Update existing note
            result = await updateNote(noteId, {
                title,
                content,
                tags,
                importance,
                is_pinned: isPinned
            });
        } else {
            // Create new note
            result = await createNote({
                title,
                content,
                linked_entity_type: linkedEntityType,
                linked_entity_id: linkedEntityId ? parseInt(linkedEntityId) : null,
                tags,
                importance,
                is_pinned: isPinned
            });
        }

        if (result.success) {
            noteDraft = null;
            closeNoteModal();
            
            // Refresh notes list if exists
            if (typeof refreshNotesList === 'function') {
                refreshNotesList();
            }
            
            alert(noteId ? 'Note updated!' : 'Note created!');
        } else {
            alert(result.error || 'Failed to save note');
        }

    } catch (error) {
        alert('An error occurred: ' + error.message);
    } finally {
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save Note';
        }
    }
}

async function renderNotesList(containerId, filters = {}) {
    const container = document.getElementById(containerId);
    if (!container) return;

    container.innerHTML = '<div class="loading">Loading notes...</div>';

    const result = await listNotes(filters);

    if (!result.success) {
        container.innerHTML = `<div class="error">${result.error}</div>`;
        return;
    }

    const notes = result.data.notes;

    if (notes.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <p>📝 No notes yet</p>
                <p>Start taking notes to organize your learning!</p>
                <button onclick="openNoteModal()" class="btn-primary">Create First Note</button>
            </div>
        `;
        return;
    }

    container.innerHTML = '';
    notes.forEach(note => {
        const card = createNoteCard(note);
        container.appendChild(card);
    });
}

function createNoteCard(note) {
    const card = document.createElement('div');
    card.className = 'note-card';
    if (note.is_pinned) card.classList.add('pinned');
    
    const importanceColors = {
        'high': '🔴',
        'medium': '🟡',
        'low': '🟢'
    };
    
    const entityIcon = note.linked_entity_type ? {
        'subject': '📚',
        'case': '⚖️',
        'learn': '📖',
        'practice': '✏️'
    }[note.linked_entity_type] || '📄' : '';

    card.innerHTML = `
        <div class="note-header">
            <div class="note-title">
                ${note.is_pinned ? '📌 ' : ''}
                ${importanceColors[note.importance]} 
                ${escapeHtml(note.title)}
            </div>
            <div class="note-actions">
                <button onclick="editNote(${note.id})" class="btn-sm">Edit</button>
                <button onclick="confirmDeleteNote(${note.id})" class="btn-sm btn-danger">Delete</button>
            </div>
        </div>
        
        ${note.entity_title ? `
            <div class="note-link">
                ${entityIcon} ${escapeHtml(note.entity_title)}
                ${note.entity_subtitle ? `<span class="subtitle">${escapeHtml(note.entity_subtitle)}</span>` : ''}
            </div>
        ` : ''}
        
        <div class="note-content">
            ${escapeHtml(note.content.substring(0, 200))}${note.content.length > 200 ? '...' : ''}
        </div>
        
        ${note.tags && note.tags.length > 0 ? `
            <div class="note-tags">
                ${note.tags.map(tag => `<span class="tag">#${escapeHtml(tag)}</span>`).join(' ')}
            </div>
        ` : ''}
        
        <div class="note-meta">
            <span>${formatDate(note.created_at)}</span>
            ${note.updated_at !== note.created_at ? `<span>• Updated ${formatDate(note.updated_at)}</span>` : ''}
        </div>
        
        <div class="ai-assist-btns" style="margin-top: 0.5rem;">
            <button onclick="requestAIAssist(${note.id}, 'summarize')" class="btn-sm">✨ Summarize</button>
            <button onclick="requestAIAssist(${note.id}, 'exam_format')" class="btn-sm">📝 Exam Format</button>
            <button onclick="requestAIAssist(${note.id}, 'revision_bullets')" class="btn-sm">📋 Revision Points</button>
        </div>
    `;

    return card;
}

async function editNote(noteId) {
    const result = await getNote(noteId);
    
    if (!result.success) {
        alert('Failed to load note');
        return;
    }

    const note = result.data;
    
    document.getElementById('noteId').value = note.id;
    document.getElementById('noteTitle').value = note.title;
    document.getElementById('noteContent').value = note.content;
    document.getElementById('noteTags').value = note.tags.join(', ');
    document.getElementById('noteImportance').value = note.importance;
    document.getElementById('noteIsPinned').checked = note.is_pinned;
    
    const modal = document.getElementById('noteModal');
    if (modal) modal.style.display = 'block';
    
    startAutosave();
}

async function confirmDeleteNote(noteId) {
    if (!confirm('Delete this note permanently?')) return;

    const result = await deleteNote(noteId);
    
    if (result.success) {
        if (typeof refreshNotesList === 'function') {
            refreshNotesList();
        }
    } else {
        alert(result.error || 'Failed to delete note');
    }
}

async function requestAIAssist(noteId, action) {
    const result = await getAIAssist(noteId, action);
    
    if (!result.success) {
        alert(result.error || 'AI assist failed');
        return;
    }

    // Show AI result in modal
    showAIResultModal(result.data.result, action);
}

function showAIResultModal(content, action) {
    const actionTitles = {
        'summarize': 'AI Summary',
        'exam_format': 'Exam Format',
        'revision_bullets': 'Revision Points'
    };

    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h3>${actionTitles[action]}</h3>
                <button onclick="this.closest('.modal').remove()" class="close-btn">×</button>
            </div>
            <div class="modal-body">
                <div class="ai-result">${escapeHtml(content).replace(/\n/g, '<br>')}</div>
                <p class="note">💡 Your original note is preserved. Copy this if you want to use it.</p>
            </div>
            <div class="modal-footer">
                <button onclick="copyToClipboard(\`${content.replace(/`/g, '\\`')}\`)" class="btn-secondary">Copy</button>
                <button onclick="this.closest('.modal').remove()" class="btn-primary">Close</button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);
    modal.style.display = 'block';
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        alert('Copied to clipboard!');
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(isoString) {
    const date = new Date(isoString);
    const now = new Date();
    const diff = now - date;
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));

    if (days === 0) return 'today';
    if (days === 1) return 'yesterday';
    if (days < 7) return `${days} days ago`;
    return date.toLocaleDateString();
}

// ============================================================================
// GLOBAL EXPORTS
// ============================================================================

window.notes = {
    createNote,
    listNotes,
    getNote,
    updateNote,
    deleteNote,
    getAIAssist,
    openNoteModal,
    closeNoteModal,
    saveNote,
    renderNotesList,
    editNote,
    confirmDeleteNote,
    requestAIAssist
};
