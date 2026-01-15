/**
 * bookmarks.js
 * Phase 6.2: Bookmark Management
 */

const API_BASE_URL = 'http://127.0.0.1:8000';

// ============================================================================
// BOOKMARK API CALLS
// ============================================================================

/**
 * Create or update a bookmark
 */
async function createBookmark(contentType, contentId, note = null) {
    try {
        const token = window.auth.getToken();
        if (!token) {
            throw new Error('Not authenticated');
        }

        const response = await fetch(`${API_BASE_URL}/api/bookmarks`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                content_type: contentType,
                content_id: contentId,
                note: note
            })
        });

        const data = await response.json();

        if (!response.ok) {
            return {
                success: false,
                error: data.detail || 'Failed to create bookmark'
            };
        }

        return {
            success: true,
            data: data
        };

    } catch (error) {
        console.error('Bookmark creation error:', error);
        return {
            success: false,
            error: error.message || 'Network error'
        };
    }
}

/**
 * Delete a bookmark by content reference
 */
async function deleteBookmark(contentType, contentId) {
    try {
        const token = window.auth.getToken();
        if (!token) {
            throw new Error('Not authenticated');
        }

        const params = new URLSearchParams({
            content_type: contentType,
            content_id: contentId
        });

        const response = await fetch(
            `${API_BASE_URL}/api/bookmarks?${params.toString()}`,
            {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            }
        );

        if (!response.ok && response.status !== 204) {
            const data = await response.json();
            return {
                success: false,
                error: data.detail || 'Failed to delete bookmark'
            };
        }

        return {
            success: true
        };

    } catch (error) {
        console.error('Bookmark deletion error:', error);
        return {
            success: false,
            error: error.message || 'Network error'
        };
    }
}

/**
 * Check if content is bookmarked
 */
async function checkBookmark(contentType, contentId) {
    try {
        const token = window.auth.getToken();
        if (!token) {
            throw new Error('Not authenticated');
        }

        const params = new URLSearchParams({
            content_type: contentType,
            content_id: contentId
        });

        const response = await fetch(
            `${API_BASE_URL}/api/bookmarks/check?${params.toString()}`,
            {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            }
        );

        const data = await response.json();

        if (!response.ok) {
            return {
                success: false,
                error: data.detail || 'Failed to check bookmark'
            };
        }

        return {
            success: true,
            data: data
        };

    } catch (error) {
        console.error('Bookmark check error:', error);
        return {
            success: false,
            error: error.message || 'Network error'
        };
    }
}

/**
 * List user's bookmarks
 */
async function listBookmarks(contentType = null, page = 1, pageSize = 20) {
    try {
        const token = window.auth.getToken();
        if (!token) {
            throw new Error('Not authenticated');
        }

        const params = new URLSearchParams({
            page: page,
            page_size: pageSize
        });

        if (contentType) {
            params.append('content_type', contentType);
        }

        const response = await fetch(
            `${API_BASE_URL}/api/bookmarks?${params.toString()}`,
            {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            }
        );

        const data = await response.json();

        if (!response.ok) {
            return {
                success: false,
                error: data.detail || 'Failed to fetch bookmarks'
            };
        }

        return {
            success: true,
            data: data
        };

    } catch (error) {
        console.error('Bookmark list error:', error);
        return {
            success: false,
            error: error.message || 'Network error'
        };
    }
}

// ============================================================================
// BOOKMARK UI FUNCTIONS
// ============================================================================

/**
 * Toggle bookmark for content
 */
async function toggleBookmark(button, contentType, contentId) {
    const isBookmarked = button.classList.contains('bookmarked');

    // Optimistic UI update
    button.disabled = true;
    button.classList.toggle('bookmarked');
    button.innerHTML = isBookmarked ? '🔖 Bookmark' : '✓ Bookmarked';

    try {
        const result = isBookmarked 
            ? await deleteBookmark(contentType, contentId)
            : await createBookmark(contentType, contentId);

        if (!result.success) {
            // Revert on failure
            button.classList.toggle('bookmarked');
            button.innerHTML = isBookmarked ? '✓ Bookmarked' : '🔖 Bookmark';
            alert(result.error || 'Failed to update bookmark');
        }

    } catch (error) {
        // Revert on error
        button.classList.toggle('bookmarked');
        button.innerHTML = isBookmarked ? '✓ Bookmarked' : '🔖 Bookmark';
        alert('An error occurred');
    } finally {
        button.disabled = false;
    }
}

/**
 * Initialize bookmark button for a content item
 */
async function initializeBookmarkButton(button, contentType, contentId) {
    // Check current bookmark status
    const result = await checkBookmark(contentType, contentId);

    if (result.success && result.data.is_bookmarked) {
        button.classList.add('bookmarked');
        button.innerHTML = '✓ Bookmarked';
    } else {
        button.classList.remove('bookmarked');
        button.innerHTML = '🔖 Bookmark';
    }

    // Add click handler
    button.onclick = () => toggleBookmark(button, contentType, contentId);
}

/**
 * Render bookmarks list in a container
 */
async function renderBookmarksList(containerId, contentType = null) {
    const container = document.getElementById(containerId);
    if (!container) {
        console.error('Bookmarks container not found');
        return;
    }

    container.innerHTML = '<div class="loading">Loading bookmarks...</div>';

    const result = await listBookmarks(contentType);

    if (!result.success) {
        container.innerHTML = `<div class="error">${result.error}</div>`;
        return;
    }

    const bookmarks = result.data.bookmarks;

    if (bookmarks.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <p>📚 No bookmarks yet</p>
                <p>Start bookmarking content to find it easily later!</p>
            </div>
        `;
        return;
    }

    // Render bookmarks
    container.innerHTML = '';
    bookmarks.forEach(bookmark => {
        const card = createBookmarkCard(bookmark);
        container.appendChild(card);
    });
}

/**
 * Create bookmark card element
 */
function createBookmarkCard(bookmark) {
    const card = document.createElement('div');
    card.className = 'bookmark-card';
    
    const icon = {
        'subject': '📚',
        'learn': '📖',
        'case': '⚖️',
        'practice': '✏️'
    }[bookmark.content_type] || '📄';

    card.innerHTML = `
        <div class="bookmark-icon">${icon}</div>
        <div class="bookmark-content">
            <h4>${escapeHtml(bookmark.title)}</h4>
            ${bookmark.subject_code ? `<p class="meta">${bookmark.subject_code} - ${bookmark.subject_name}</p>` : ''}
            ${bookmark.note ? `<p class="note">${escapeHtml(bookmark.note)}</p>` : ''}
            <p class="timestamp">Saved ${formatDate(bookmark.created_at)}</p>
        </div>
        <button class="remove-bookmark-btn" data-type="${bookmark.content_type}" data-id="${bookmark.content_id}">
            Remove
        </button>
    `;

    // Add click to navigate
    card.querySelector('.bookmark-content').onclick = () => navigateToBookmark(bookmark);

    // Add remove handler
    card.querySelector('.remove-bookmark-btn').onclick = async (e) => {
        e.stopPropagation();
        if (confirm('Remove this bookmark?')) {
            const result = await deleteBookmark(bookmark.content_type, bookmark.content_id);
            if (result.success) {
                card.remove();
            }
        }
    };

    return card;
}

/**
 * Navigate to bookmarked content
 */
function navigateToBookmark(bookmark) {
    const routes = {
        'subject': (b) => `/html/subject-modules.html?subjectId=${b.content_id}`,
        'learn': (b) => `/html/learn-content.html?id=${b.content_id}`,
        'case': (b) => `/html/case-content.html?id=${b.content_id}`,
        'practice': (b) => `/html/practice-content.html?id=${b.content_id}`
    };

    const route = routes[bookmark.content_type];
    if (route) {
        window.location.href = route(bookmark);
    }
}

// ============================================================================
// HELPERS
// ============================================================================

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

window.bookmarks = {
    createBookmark,
    deleteBookmark,
    checkBookmark,
    listBookmarks,
    toggleBookmark,
    initializeBookmarkButton,
    renderBookmarksList
};
