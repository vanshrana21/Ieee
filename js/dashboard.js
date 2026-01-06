/**
 * dashboard.js
 * Dashboard page logic
 * Handles user data loading and display
 */

document.addEventListener('DOMContentLoaded', () => {
    requireAuth();
    loadDashboardData();
    initializeSearch();
});

function initializeSearch() {
    const searchButton = document.querySelector('.search-submit');
    const searchInput = document.getElementById('searchInput');
    
    if (searchButton) {
        searchButton.addEventListener('click', handleSearch);
    }
    
    if (searchInput) {
        searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                handleSearch();
            }
        });
    }
}

async function handleSearch() {
    const searchInput = document.getElementById('searchInput');
    const query = searchInput ? searchInput.value.trim() : '';
    
    if (!query) {
        return;
    }
    
    const jurisdictionFilter = document.getElementById('jurisdictionFilter');
    const courtFilter = document.getElementById('courtFilter');
    const yearFilter = document.getElementById('yearFilter');
    
    const filters = {
        jurisdiction: (jurisdictionFilter && jurisdictionFilter.value) ? jurisdictionFilter.value : null,
        court: (courtFilter && courtFilter.value) ? courtFilter.value : null,
        year: (yearFilter && yearFilter.value) ? yearFilter.value : null
    };
    
    await executeSearch(query, filters);
}

async function executeSearch(query, filters) {
    try {
        showSearchLoading();
        
        const token = localStorage.getItem('access_token');
        
        if (!token) {
            throw new Error('Not authenticated. Please login again.');
        }
        
        console.log('=== SEARCH REQUEST ===');
        console.log('Token:', token ? 'Present (length: ' + token.length + ')' : 'Missing');
        console.log('Query:', query);
        console.log('URL:', 'http://127.0.0.1:8000/api/search');
        
        const response = await fetch('http://127.0.0.1:8000/api/search', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + token
            },
            body: JSON.stringify({
                query: query,
                filters: filters
            })
        });
        
        console.log('Response status:', response.status);
        console.log('Response ok:', response.ok);
        
        if (response.status === 401) {
            localStorage.removeItem('access_token');
            throw new Error('Session expired. Redirecting to login...');
        }
        
        if (response.status === 402) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Insufficient credits');
        }
        
        if (response.status === 403) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Access forbidden');
        }
        
        if (response.status === 500) {
            throw new Error('Server error. Please try again later.');
        }
        
        if (response.status === 503) {
            throw new Error('Search service temporarily unavailable');
        }
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Search failed: ' + response.status);
        }
        
        const data = await response.json();
        displaySearchResults(data, query);
        
    } catch (error) {
        console.error('Search error:', error);
        showSearchError(error.message);
        
        if (error.message.includes('Session expired') || error.message.includes('Not authenticated')) {
            setTimeout(() => {
                window.location.href = '/html/login.html';
            }, 2000);
        }
    }
}

function displaySearchResults(data, query) {
    const resultsListContainer = document.querySelector('.results-list');
    const resultsTitle = document.querySelector('.results-title');
    const resultsCount = document.querySelector('.results-count');
    
    if (!resultsListContainer) {
        return;
    }
    
    if (resultsTitle) {
        resultsTitle.textContent = 'Search Results for "' + query + '"';
    }
    
    const resultCount = data.results ? data.results.length : 0;
    if (resultsCount) {
        resultsCount.textContent = resultCount + ' result' + (resultCount !== 1 ? 's' : '') + ' found';
    }
    
    resultsListContainer.innerHTML = '';
    
    if (!data.results || data.results.length === 0) {
        resultsListContainer.innerHTML = '<div style="text-align: center; padding: 48px 24px; color: #64748b;"><svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-bottom: 16px;"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg><h3 style="font-size: 18px; margin-bottom: 8px;">No results found</h3><p style="font-size: 14px;">Try adjusting your search query or filters</p></div>';
        return;
    }
    
    data.results.forEach(result => {
        const resultCard = createResultCard(result);
        resultsListContainer.appendChild(resultCard);
    });
}

/**
 * Updated createResultCard function with click handler
 * Replace the existing createResultCard function in dashboard.js
 */
function createResultCard(result) {
    const card = document.createElement('div');
    card.className = 'case-card';
    
    // Make card clickable
    card.style.cursor = 'pointer';
    card.addEventListener('click', () => {
        openCaseDetail(result.id);
    });
    
    const caseNumber = result.id || 'N/A';
    const title = result.title || 'Untitled Case';
    const court = result.court || 'Unknown Court';
    const year = result.year || 'N/A';
    const summary = result.summary || 'No summary available.';
    const relevanceScore = result.relevance_score || 0;
    
    card.innerHTML = `
        <div class="case-header">
            <div class="case-number">${escapeHtml(String(caseNumber))}</div>
            <button class="case-bookmark" onclick="event.stopPropagation(); bookmarkCase('${escapeHtml(String(caseNumber))}')">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/>
                </svg>
            </button>
        </div>
        <h3 class="case-title">${escapeHtml(title)}</h3>
        <div class="case-meta">
            <div class="case-meta-item">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
                    <line x1="16" y1="2" x2="16" y2="6"/>
                    <line x1="8" y1="2" x2="8" y2="6"/>
                    <line x1="3" y1="10" x2="21" y2="10"/>
                </svg>
                <span>${escapeHtml(String(year))}</span>
            </div>
            <div class="case-meta-item">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>
                    <polyline points="9 22 9 12 15 12 15 22"/>
                </svg>
                <span>${escapeHtml(court)}</span>
            </div>
            <div class="case-meta-item">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                </svg>
                <span>Relevance: ${Math.round(relevanceScore * 10)}%</span>
            </div>
        </div>
        <p class="case-excerpt">${escapeHtml(summary)}</p>
        <div class="case-actions">
            <button class="case-action-btn" onclick="event.stopPropagation(); openCaseDetail('${escapeHtml(String(caseNumber))}')">
                View Details
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="5" y1="12" x2="19" y2="12"/>
                    <polyline points="12 5 19 12 12 19"/>
                </svg>
            </button>
        </div>
    `;
    
    return card;
}

/**
 * Bookmark case function
 */
function bookmarkCase(caseId) {
    console.log('Bookmarking case:', caseId);
    alert('Bookmark functionality coming soon!');
}

function showSearchLoading() {
    const resultsListContainer = document.querySelector('.results-list');
    const resultsTitle = document.querySelector('.results-title');
    
    if (resultsTitle) {
        resultsTitle.textContent = 'Searching...';
    }
    
    if (resultsListContainer) {
        resultsListContainer.innerHTML = '<div style="text-align: center; padding: 48px 24px;"><div style="width: 48px; height: 48px; border: 4px solid #e2e8f0; border-top-color: #1e3a5f; border-radius: 50%; margin: 0 auto 16px; animation: spin 0.8s linear infinite;"></div><p style="color: #64748b; font-size: 16px;">Searching legal database...</p></div>';
    }
}

function showSearchError(errorMessage) {
    const resultsListContainer = document.querySelector('.results-list');
    const resultsTitle = document.querySelector('.results-title');
    
    if (resultsTitle) {
        resultsTitle.textContent = 'Search Error';
    }
    
    if (resultsListContainer) {
        resultsListContainer.innerHTML = '<div style="text-align: center; padding: 48px 24px;"><svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color: #ef4444; margin-bottom: 16px;"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg><h3 style="color: #dc2626; font-size: 18px; margin-bottom: 8px;">Search Failed</h3><p style="color: #64748b; font-size: 14px; margin-bottom: 16px;">' + escapeHtml(errorMessage) + '</p><button class="btn btn-primary" onclick="handleSearch()">Try Again</button></div>';
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function loadDashboardData() {
    try {
        showLoadingState();
        
        const userResult = await getCurrentUser();
        const creditsResult = await getUserCredits();
        
        if (!userResult.success) {
            throw new Error(userResult.error || 'Failed to load user data');
        }
        
        if (!creditsResult.success) {
            throw new Error(creditsResult.error || 'Failed to load credits');
        }
        
        updateDashboardUI(userResult.data, creditsResult.data.credits);
        
        hideLoadingState();
        showMainContent();
        
    } catch (error) {
        console.error('Dashboard loading error:', error);
        showErrorState(error.message);
    }
}

function updateDashboardUI(user, credits) {
    updateUserInfo(user);
    updateCreditsDisplay(credits);
    updateWelcomeMessage(user);
}

function updateUserInfo(user) {
    const userName = document.getElementById('userName');
    const userEmail = document.getElementById('userEmail');
    const userAvatar = document.getElementById('userAvatar');
    
    if (user.full_name && userName) {
        userName.textContent = user.full_name;
    }
    
    if (user.email && userEmail) {
        userEmail.textContent = user.email;
    }
    
    if (user.full_name && userAvatar) {
        userAvatar.textContent = user.full_name.charAt(0).toUpperCase();
    }
}

function updateCreditsDisplay(credits) {
    const creditsValue = document.getElementById('creditsValue');
    
    if (creditsValue) {
        creditsValue.textContent = credits;
    }
}

function updateWelcomeMessage(user) {
    const welcomeName = document.getElementById('welcomeName');
    
    if (user.full_name && welcomeName) {
        const firstName = user.full_name.split(' ')[0];
        welcomeName.textContent = firstName;
    }
}

function showLoadingState() {
    const loadingState = document.getElementById('loadingState');
    if (loadingState) {
        loadingState.style.display = 'block';
    }
}

function hideLoadingState() {
    const loadingState = document.getElementById('loadingState');
    if (loadingState) {
        loadingState.style.display = 'none';
    }
}

function showMainContent() {
    const mainContent = document.getElementById('mainContent');
    if (mainContent) {
        mainContent.style.display = 'block';
    }
}

function showErrorState(errorMessage) {
    const loadingState = document.getElementById('loadingState');
    const errorState = document.getElementById('errorState');
    const errorMessageDiv = document.getElementById('errorMessage');
    
    if (loadingState) {
        loadingState.style.display = 'none';
    }
    
    if (errorState) {
        errorState.style.display = 'block';
    }
    
    if (errorMessageDiv) {
        errorMessageDiv.textContent = errorMessage || 'An unexpected error occurred';
    }
}

function retryLoadDashboard() {
    const errorState = document.getElementById('errorState');
    if (errorState) {
        errorState.style.display = 'none';
    }
    
    loadDashboardData();
}

function handleLogout() {
    if (confirm('Are you sure you want to logout?')) {
        logout();
    }
}
/**
 * Open case detail page - navigates to case-detail.html
 */
function openCaseDetail(opinionId) {
    console.log('Opening case detail for opinion ID:', opinionId);
    window.location.href = `/html/case-detail.html?opinion_id=${opinionId}`;
}

/**
 * Updated createResultCard function with click handler
 * Replace the existing createResultCard function in dashboard.js
 */
function createResultCard(result) {
    const card = document.createElement('div');
    card.className = 'case-card';
    
    // Make card clickable
    card.style.cursor = 'pointer';
    card.addEventListener('click', () => {
        openCaseDetail(result.id);
    });
    
    const caseNumber = result.id || 'N/A';
    const title = result.title || 'Untitled Case';
    const court = result.court || 'Unknown Court';
    const year = result.year || 'N/A';
    const summary = result.summary || 'No summary available.';
    const relevanceScore = result.relevance_score || 0;
    
    card.innerHTML = `
        <div class="case-header">
            <div class="case-number">${escapeHtml(String(caseNumber))}</div>
            <button class="case-bookmark" onclick="event.stopPropagation(); bookmarkCase('${escapeHtml(String(caseNumber))}')">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/>
                </svg>
            </button>
        </div>
        <h3 class="case-title">${escapeHtml(title)}</h3>
        <div class="case-meta">
            <div class="case-meta-item">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
                    <line x1="16" y1="2" x2="16" y2="6"/>
                    <line x1="8" y1="2" x2="8" y2="6"/>
                    <line x1="3" y1="10" x2="21" y2="10"/>
                </svg>
                <span>${escapeHtml(String(year))}</span>
            </div>
            <div class="case-meta-item">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>
                    <polyline points="9 22 9 12 15 12 15 22"/>
                </svg>
                <span>${escapeHtml(court)}</span>
            </div>
            <div class="case-meta-item">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                </svg>
                <span>Relevance: ${Math.round(relevanceScore * 10)}%</span>
            </div>
        </div>
        <p class="case-excerpt">${escapeHtml(summary)}</p>
        <div class="case-actions">
            <button class="case-action-btn" onclick="event.stopPropagation(); openCaseDetail('${escapeHtml(String(caseNumber))}')">
                View Details
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="5" y1="12" x2="19" y2="12"/>
                    <polyline points="12 5 19 12 12 19"/>
                </svg>
            </button>
        </div>
    `;
    
    return card;
}

/**
 * Bookmark case function
 */
function bookmarkCase(caseId) {
    console.log('Bookmarking case:', caseId);
    alert('Bookmark functionality coming soon!');
}

const style = document.createElement('style');
style.textContent = '@keyframes spin { to { transform: rotate(360deg); } }';
document.head.appendChild(style);
/**
 * Open case detail page - navigates to case-detail.html
 * Only works if case has valid opinion_id or cluster_id
 */
function openCaseDetail(result) {
    // Extract IDs - handle both object and string input
    const caseId = typeof result === 'object' ? result.id : result;
    const clusterId = typeof result === 'object' ? result.cluster_id : null;
    
    console.log('Opening case detail - ID:', caseId, 'Cluster:', clusterId);
    
    // Validate we have a usable ID
    if (!caseId || caseId === 'N/A' || caseId === '' || caseId === null) {
        if (clusterId && clusterId !== 'N/A' && clusterId !== '' && clusterId !== null) {
            // Use cluster ID instead
            window.location.href = `/html/case-detail.html?case_id=${clusterId}&id_type=cluster`;
            return;
        }
        alert('Case details not available for this result');
        return;
    }
    
    // Navigate with opinion ID
    window.location.href = `/html/case-detail.html?case_id=${caseId}&id_type=opinion`;
}

/**
 * Updated createResultCard function with click handler
 * Replace the existing createResultCard function in dashboard.js
 */
function createResultCard(result) {
    const card = document.createElement('div');
    card.className = 'case-card';
    
    const caseId = result.id || 'N/A';
    const clusterId = result.cluster_id;
    const title = result.title || 'Untitled Case';
    const court = result.court || 'Unknown Court';
    const year = result.year || 'N/A';
    const summary = result.summary || 'No summary available.';
    const relevanceScore = result.relevance_score || 0;
    
    // Determine if case has valid ID
    const hasValidId = (caseId && caseId !== 'N/A') || (clusterId && clusterId !== 'N/A');
    
    // Make card clickable only if valid ID exists
    if (hasValidId) {
        card.style.cursor = 'pointer';
        card.addEventListener('click', () => {
            openCaseDetail(result);
        });
    } else {
        card.style.opacity = '0.7';
    }
    
    card.innerHTML = `
        <div class="case-header">
            <div class="case-number">${escapeHtml(String(caseId))}</div>
            <button class="case-bookmark" onclick="event.stopPropagation(); bookmarkCase('${escapeHtml(String(caseId))}')">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/>
                </svg>
            </button>
        </div>
        <h3 class="case-title">${escapeHtml(title)}</h3>
        <div class="case-meta">
            <div class="case-meta-item">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
                    <line x1="16" y1="2" x2="16" y2="6"/>
                    <line x1="8" y1="2" x2="8" y2="6"/>
                    <line x1="3" y1="10" x2="21" y2="10"/>
                </svg>
                <span>${escapeHtml(String(year))}</span>
            </div>
            <div class="case-meta-item">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>
                    <polyline points="9 22 9 12 15 12 15 22"/>
                </svg>
                <span>${escapeHtml(court)}</span>
            </div>
            <div class="case-meta-item">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                </svg>
                <span>Relevance: ${Math.round(relevanceScore * 10)}%</span>
            </div>
        </div>
        <p class="case-excerpt">${escapeHtml(summary)}</p>
        <div class="case-actions">
            ${hasValidId ? `
                <button class="case-action-btn" onclick="event.stopPropagation(); openCaseDetail(${JSON.stringify(result).replace(/"/g, '&quot;')})">
                    View Details
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="5" y1="12" x2="19" y2="12"/>
                        <polyline points="12 5 19 12 12 19"/>
                    </svg>
                </button>
            ` : `
                <button class="case-action-btn" disabled style="opacity: 0.5; cursor: not-allowed;">
                    Details Unavailable
                </button>
            `}
        </div>
    `;
    
    return card;
}

/**
 * Bookmark case function
 */
function bookmarkCase(caseId) {
    console.log('Bookmarking case:', caseId);
    alert('Bookmark functionality coming soon!');
}