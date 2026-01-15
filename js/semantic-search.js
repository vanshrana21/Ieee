/**
 * semantic-search.js
 * Phase 8: Semantic Search UI
 */

const API_BASE_URL = 'http://127.0.0.1:8000';

async function semanticSearch(query, filters = {}) {
    try {
        const token = window.auth.getToken();
        if (!token) throw new Error('Not authenticated');

        const params = new URLSearchParams({ q: query });
        if (filters.entity_types) params.append('entity_types', filters.entity_types);
        if (filters.subject_id) params.append('subject_id', filters.subject_id);
        if (filters.top_k) params.append('top_k', filters.top_k);
        if (filters.min_similarity) params.append('min_similarity', filters.min_similarity);

        const response = await fetch(
            `${API_BASE_URL}/api/search/semantic?${params.toString()}`,
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

async function renderSemanticResults(containerId, query, filters = {}) {
    const container = document.getElementById(containerId);
    if (!container) return;

    container.innerHTML = '<div class="loading">🔍 Searching semantically...</div>';

    const result = await semanticSearch(query, filters);

    if (!result.success) {
        container.innerHTML = `<div class="error">${result.error}</div>`;
        return;
    }

    const results = result.data.results;

    if (results.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <p>No semantic matches found for "${escapeHtml(query)}"</p>
                <p>Try different keywords or broaden your search.</p>
            </div>
        `;
        return;
    }

    container.innerHTML = `
        <div class="search-summary">
            Found ${results.length} semantic matches for "<strong>${escapeHtml(query)}</strong>"
        </div>
    `;

    results.forEach(item => {
        const card = createSemanticResultCard(item);
        container.appendChild(card);
    });
}

function createSemanticResultCard(result) {
    const card = document.createElement('div');
    card.className = 'semantic-result-card';
    
    const icon = {
        'note': '📝',
        'case': '⚖️',
        'learn': '📖',
        'practice': '✏️'
    }[result.entity_type] || '📄';

    const similarityPercent = Math.round(result.similarity_score * 100);
    const similarityColor = similarityPercent >= 70 ? '#28a745' : similarityPercent >= 50 ? '#ffc107' : '#6c757d';

    card.innerHTML = `
        <div class="result-header">
            <span class="result-icon">${icon}</span>
            <span class="result-type">${result.entity_type}</span>
            <span class="similarity-badge" style="background: ${similarityColor}">
                ${similarityPercent}% match
            </span>
        </div>
        <h4 class="result-title">${escapeHtml(result.title)}</h4>
        <p class="result-snippet">${escapeHtml(result.snippet)}</p>
        <div class="result-metadata">
            ${result.metadata.subject_code ? `<span class="meta-tag">${result.metadata.subject_code}</span>` : ''}
            ${result.metadata.tags ? result.metadata.tags.map(tag => `<span class="meta-tag">#${tag}</span>`).join('') : ''}
        </div>
    `;

    card.onclick = () => navigateToEntity(result.entity_type, result.entity_id);

    return card;
}

function navigateToEntity(entityType, entityId) {
    const routes = {
        'note': () => `/html/my-notes.html?id=${entityId}`,
        'case': () => `/html/case-content.html?id=${entityId}`,
        'learn': () => `/html/learn-content.html?id=${entityId}`,
        'practice': () => `/html/practice-content.html?id=${entityId}`
    };

    const route = routes[entityType];
    if (route) {
        window.location.href = route();
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Global export
window.semanticSearch = {
    search: semanticSearch,
    renderResults: renderSemanticResults
};
