/**
 * search.js
 * Phase 6.1: Search, Filtering & Discovery
 * Provides unified search across all content types
 */

// ============================================================================
// SEARCH API
// ============================================================================

/**
 * Perform search query
 * @param {string} query - Search query string
 * @param {Object} filters - Optional filters
 * @returns {Promise} Search results
 */
async function performSearch(query, filters = {}) {
    if (!query || query.trim().length < 2) {
        return {
            success: false,
            error: 'Search query must be at least 2 characters'
        };
    }

    try {
        const token = window.auth.getToken();
        if (!token) {
            throw new Error('Not authenticated');
        }

        // Build query parameters
        const params = new URLSearchParams({
            q: query.trim(),
            page: filters.page || 1,
            page_size: filters.page_size || 20
        });

        // Add optional filters
        if (filters.content_types && filters.content_types.length > 0) {
            params.append('content_types', filters.content_types.join(','));
        }
        if (filters.subject_id) {
            params.append('subject_id', filters.subject_id);
        }
        if (filters.semester) {
            params.append('semester', filters.semester);
        }

        const response = await fetch(
            `http://127.0.0.1:8000/api/search?${params.toString()}`,
            {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                }
            }
        );

        const data = await response.json();

        if (!response.ok) {
            return {
                success: false,
                error: data.detail || 'Search failed',
                status: response.status
            };
        }

        return {
            success: true,
            data: data
        };

    } catch (error) {
        console.error('Search error:', error);
        return {
            success: false,
            error: error.message || 'Network error'
        };
    }
}

// ============================================================================
// SEARCH UI RENDERING
// ============================================================================

/**
 * Render search results in container
 * @param {HTMLElement} container - Container element
 * @param {Array} results - Search results array
 * @param {Object} metadata - Pagination metadata
 */
function renderSearchResults(container, results, metadata) {
    if (!container) {
        console.error('Search container not found');
        return;
    }

    // Clear existing content
    container.innerHTML = '';

    if (!results || results.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">🔍</div>
                <h3>No results found</h3>
                <p>Try different keywords or adjust your filters</p>
            </div>
        `;
        return;
    }

    // Create results header
    const header = document.createElement('div');
    header.className = 'search-results-header';
    header.innerHTML = `
        <p>Found <strong>${metadata.total_count}</strong> result${metadata.total_count !== 1 ? 's' : ''}</p>
    `;
    container.appendChild(header);

    // Render each result
    const resultsContainer = document.createElement('div');
    resultsContainer.className = 'search-results-list';

    results.forEach(result => {
        const resultCard = createSearchResultCard(result);
        resultsContainer.appendChild(resultCard);
    });

    container.appendChild(resultsContainer);

    // Add pagination if needed
    if (metadata.has_more || metadata.page > 1) {
        const pagination = createPagination(metadata);
        container.appendChild(pagination);
    }
}

/**
 * Create search result card based on content type
 */
function createSearchResultCard(result) {
    const card = document.createElement('div');
    card.className = 'search-result-card';
    card.onclick = () => navigateToContent(result);

    const icon = getContentIcon(result.content_type);
    const typeLabel = getContentTypeLabel(result.content_type);

    card.innerHTML = `
        <div class="result-icon">${icon}</div>
        <div class="result-content">
            <div class="result-header">
                <h3 class="result-title">${escapeHtml(result.title)}</h3>
                <span class="result-type-badge">${typeLabel}</span>
            </div>
            ${result.description ? 
                `<p class="result-description">${escapeHtml(result.description.substring(0, 150))}${result.description.length > 150 ? '...' : ''}</p>` 
                : ''}
            <div class="result-meta">
                ${result.subject_code ? 
                    `<span class="meta-item">📚 ${result.subject_code} - ${result.subject_name}</span>` 
                    : ''}
                ${result.semester ? 
                    `<span class="meta-item">📅 Semester ${result.semester}</span>` 
                    : ''}
                ${result.module_title ? 
                    `<span class="meta-item">📂 ${result.module_title}</span>` 
                    : ''}
                ${result.exam_importance ? 
                    `<span class="meta-item importance-${result.exam_importance}">⭐ ${result.exam_importance.toUpperCase()} Importance</span>` 
                    : ''}
                ${result.difficulty ? 
                    `<span class="meta-item difficulty-${result.difficulty}">📊 ${result.difficulty}</span>` 
                    : ''}
                ${result.marks ? 
                    `<span class="meta-item">✍️ ${result.marks} marks</span>` 
                    : ''}
            </div>
            ${result.tags && result.tags.length > 0 ? 
                `<div class="result-tags">
                    ${result.tags.slice(0, 5).map(tag => `<span class="tag">${escapeHtml(tag)}</span>`).join('')}
                </div>` 
                : ''}
        </div>
    `;

    return card;
}

/**
 * Get icon for content type
 */
function getContentIcon(contentType) {
    const icons = {
        'subject': '📚',
        'learn': '📖',
        'case': '⚖️',
        'practice': '✏️'
    };
    return icons[contentType] || '📄';
}

/**
 * Get label for content type
 */
function getContentTypeLabel(contentType) {
    const labels = {
        'subject': 'Subject',
        'learn': 'Learn',
        'case': 'Case',
        'practice': 'Practice'
    };
    return labels[contentType] || contentType;
}

/**
 * Navigate to content based on type
 */
function navigateToContent(result) {
    const routes = {
        'subject': (r) => `/html/subject-modules.html?subjectId=${r.id}`,
        'learn': (r) => `/html/learn-content.html?id=${r.id}`,
        'case': (r) => `/html/case-content.html?id=${r.id}`,
        'practice': (r) => `/html/practice-content.html?id=${r.id}`
    };

    const route = routes[result.content_type];
    if (route) {
        window.location.href = route(result);
    } else {
        console.error('Unknown content type:', result.content_type);
    }
}

/**
 * Create pagination controls
 */
function createPagination(metadata) {
    const pagination = document.createElement('div');
    pagination.className = 'search-pagination';

    const prevDisabled = metadata.page <= 1;
    const nextDisabled = !metadata.has_more;

    pagination.innerHTML = `
        <button 
            class="pagination-btn" 
            id="prevPageBtn" 
            ${prevDisabled ? 'disabled' : ''}
        >
            ← Previous
        </button>
        <span class="pagination-info">Page ${metadata.page}</span>
        <button 
            class="pagination-btn" 
            id="nextPageBtn" 
            ${nextDisabled ? 'disabled' : ''}
        >
            Next →
        </button>
    `;

    return pagination;
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============================================================================
// SEARCH INITIALIZATION
// ============================================================================

let currentSearchQuery = '';
let currentFilters = {};

/**
 * Initialize search functionality
 */
function initializeSearch() {
    const searchInput = document.getElementById('searchInput');
    const searchButton = document.getElementById('searchButton');
    const searchResults = document.getElementById('searchResults');

    if (!searchInput || !searchButton || !searchResults) {
        console.warn('Search elements not found on this page');
        return;
    }

    // Search button click
    searchButton.addEventListener('click', async () => {
        await executeSearch();
    });

    // Enter key in search input
    searchInput.addEventListener('keypress', async (e) => {
        if (e.key === 'Enter') {
            await executeSearch();
        }
    });

    // Initialize filter checkboxes if present
    initializeFilters();
}

/**
 * Execute search with current query and filters
 */
async function executeSearch(page = 1) {
    const searchInput = document.getElementById('searchInput');
    const searchResults = document.getElementById('searchResults');
    const query = searchInput.value.trim();

    if (query.length < 2) {
        searchResults.innerHTML = `
            <div class="search-hint">
                <p>⌨️ Enter at least 2 characters to search</p>
            </div>
        `;
        return;
    }

    // Show loading state
    searchResults.innerHTML = `
        <div class="loading-state">
            <div class="spinner"></div>
            <p>Searching...</p>
        </div>
    `;

    currentSearchQuery = query;
    currentFilters.page = page;

    const result = await performSearch(query, currentFilters);

    if (!result.success) {
        searchResults.innerHTML = `
            <div class="error-state">
                <p>❌ ${result.error}</p>
            </div>
        `;
        return;
    }

    renderSearchResults(searchResults, result.data.results, {
        total_count: result.data.total_count,
        page: result.data.page,
        page_size: result.data.page_size,
        has_more: result.data.has_more
    });

    // Setup pagination handlers
    setupPaginationHandlers();
}

/**
 * Setup pagination button handlers
 */
function setupPaginationHandlers() {
    const prevBtn = document.getElementById('prevPageBtn');
    const nextBtn = document.getElementById('nextPageBtn');

    if (prevBtn) {
        prevBtn.onclick = () => {
            executeSearch((currentFilters.page || 1) - 1);
        };
    }

    if (nextBtn) {
        nextBtn.onclick = () => {
            executeSearch((currentFilters.page || 1) + 1);
        };
    }
}

/**
 * Initialize filter controls
 */
function initializeFilters() {
    const filterCheckboxes = document.querySelectorAll('.filter-checkbox');
    
    filterCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', () => {
            updateFilters();
        });
    });
}

/**
 * Update filters from UI controls
 */
function updateFilters() {
    const contentTypeCheckboxes = document.querySelectorAll('.content-type-filter:checked');
    currentFilters.content_types = Array.from(contentTypeCheckboxes).map(cb => cb.value);

    const subjectFilter = document.getElementById('subjectFilter');
    if (subjectFilter && subjectFilter.value) {
        currentFilters.subject_id = parseInt(subjectFilter.value);
    } else {
        delete currentFilters.subject_id;
    }

    const semesterFilter = document.getElementById('semesterFilter');
    if (semesterFilter && semesterFilter.value) {
        currentFilters.semester = parseInt(semesterFilter.value);
    } else {
        delete currentFilters.semester;
    }

    // Re-run search with new filters
    if (currentSearchQuery) {
        executeSearch(1);
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initializeSearch);

// ============================================================================
// GLOBAL EXPORTS
// ============================================================================

window.search = {
    performSearch,
    renderSearchResults,
    executeSearch,
    initializeSearch
};

window.Storage = window.Storage || {
  getSavedCases: () => [],
  getSearchHistory: () => []
};

const SearchManager = {
    state: {
        searchTerm: '',
        filters: {
            jurisdiction: '',
            court: '',
            year: ''
        },
        sortBy: 'relevance',
        results: [],
        debounceTimer: null
    },

    init() {
        this.cacheElements();
        this.bindEvents();
        this.loadInitialResults();
        this.updateSavedCasesCount();
    },

    cacheElements() {
        this.elements = {
            searchBar: document.querySelector('.search-bar'),
            searchSubmit: document.querySelector('.search-submit'),
            jurisdictionFilter: document.querySelector('.filter-select[name="jurisdiction"]'),
            courtFilter: document.querySelector('.filter-select[name="court"]'),
            yearFilter: document.querySelector('.filter-select[name="year"]'),
            filterReset: document.querySelector('.filter-reset'),
            sortSelect: document.querySelector('.results-sort select'),
            resultsList: document.querySelector('.results-list'),
            resultsCount: document.querySelector('.results-count'),
            savedCasesBadge: document.querySelector('.sidebar-link[href="#saved"] .sidebar-badge')
        };

        // Inside cacheElements() function, replace the dropdown population section:

const jurisdictionSelect = document.querySelector('.filter-group:nth-child(1) .filter-select');
if (jurisdictionSelect) {
    jurisdictionSelect.innerHTML = `
        <option value="">All Jurisdictions</option>
        <option value="central">Central (Union of India)</option>
        <option value="state">State Governments</option>
        <option value="ut">Union Territories</option>
        <option value="local">Local / District Administration</option>
    `;
}

const courtSelect = document.querySelector('.filter-group:nth-child(2) .filter-select');
if (courtSelect) {
    courtSelect.innerHTML = `
        <option value="">All Courts</option>
        <optgroup label="Supreme Court">
            <option value="sci">Supreme Court of India</option>
        </optgroup>
        <optgroup label="High Courts">
            <option value="allahabad">Allahabad High Court</option>
            <option value="andhra">Andhra Pradesh High Court</option>
            <option value="bombay">Bombay High Court</option>
            <option value="calcutta">Calcutta High Court</option>
            <option value="chhattisgarh">Chhattisgarh High Court</option>
            <option value="delhi">Delhi High Court</option>
            <option value="gauhati">Gauhati High Court</option>
            <option value="gujarat">Gujarat High Court</option>
            <option value="himachal">Himachal Pradesh High Court</option>
            <option value="jk">Jammu & Kashmir and Ladakh High Court</option>
            <option value="jharkhand">Jharkhand High Court</option>
            <option value="karnataka">Karnataka High Court</option>
            <option value="kerala">Kerala High Court</option>
            <option value="mp">Madhya Pradesh High Court</option>
            <option value="madras">Madras High Court</option>
            <option value="manipur">Manipur High Court</option>
            <option value="meghalaya">Meghalaya High Court</option>
            <option value="orissa">Orissa High Court</option>
            <option value="patna">Patna High Court</option>
            <option value="punjab">Punjab & Haryana High Court</option>
            <option value="rajasthan">Rajasthan High Court</option>
            <option value="sikkim">Sikkim High Court</option>
            <option value="telangana">Telangana High Court</option>
            <option value="tripura">Tripura High Court</option>
            <option value="uttarakhand">Uttarakhand High Court</option>
        </optgroup>
        <optgroup label="District & Subordinate Courts">
            <option value="district">District Court</option>
            <option value="sessions">Sessions Court</option>
            <option value="family">Family Court</option>
            <option value="magistrate">Magistrate Court</option>
            <option value="civil">Civil Judge Court</option>
            <option value="smallcauses">Small Causes Court</option>
        </optgroup>
        <optgroup label="Special & Tribunal Courts">
            <option value="nclt">National Company Law Tribunal (NCLT)</option>
            <option value="nclat">National Company Law Appellate Tribunal (NCLAT)</option>
            <option value="itat">Income Tax Appellate Tribunal (ITAT)</option>
            <option value="cat">Central Administrative Tribunal (CAT)</option>
            <option value="aft">Armed Forces Tribunal (AFT)</option>
            <option value="ngt">National Green Tribunal (NGT)</option>
            <option value="dcdrc">Consumer Disputes Redressal Commission (District)</option>
            <option value="scdrc">State Consumer Disputes Redressal Commission</option>
            <option value="ncdrc">National Consumer Disputes Redressal Commission (NCDRC)</option>
            <option value="drt">Debt Recovery Tribunal (DRT)</option>
            <option value="drat">Debt Recovery Appellate Tribunal (DRAT)</option>
            <option value="ipab">Intellectual Property Appellate Board (IPAB)</option>
            <option value="rct">Railway Claims Tribunal</option>
            <option value="mact">Motor Accident Claims Tribunal (MACT)</option>
            <option value="eat">Electricity Appellate Tribunal</option>
            <option value="sat">Securities Appellate Tribunal (SAT)</option>
        </optgroup>
    `;
}

const yearSelect = document.querySelector('.filter-group:nth-child(3) .filter-select');
if (yearSelect) {
    yearSelect.innerHTML = `
        <option value="">All Years</option>
        <option value="last1">Last 1 Year</option>
        <option value="last3">Last 3 Years</option>
        <option value="last5">Last 5 Years</option>
        <option value="last10">Last 10 Years</option>
        <option value="2000-2010">2000 – 2010</option>
        <option value="before2000">Before 2000</option>
    `;
}

// Update element references
this.elements.jurisdictionFilter = jurisdictionSelect;
this.elements.courtFilter = courtSelect;
this.elements.yearFilter = yearSelect;
    },

    bindEvents() {
        if (this.elements.searchBar) {
            this.elements.searchBar.addEventListener('input', (e) => {
                this.handleSearchInput(e.target.value);
            });
        }

        if (this.elements.searchSubmit) {
            this.elements.searchSubmit.addEventListener('click', () => {
                this.performSearch();
            });
        }

        if (this.elements.jurisdictionFilter) {
            this.elements.jurisdictionFilter.addEventListener('change', (e) => {
                this.state.filters.jurisdiction = e.target.value;
                this.performSearch();
            });
        }

        if (this.elements.courtFilter) {
            this.elements.courtFilter.addEventListener('change', (e) => {
                this.state.filters.court = e.target.value;
                this.performSearch();
            });
        }

        if (this.elements.yearFilter) {
            this.elements.yearFilter.addEventListener('change', (e) => {
                this.state.filters.year = e.target.value;
                this.performSearch();
            });
        }

        if (this.elements.filterReset) {
            this.elements.filterReset.addEventListener('click', () => {
                this.resetFilters();
            });
        }

        if (this.elements.sortSelect) {
            this.elements.sortSelect.addEventListener('change', (e) => {
                this.state.sortBy = e.target.value;
                this.sortResults();
            });
        }

        document.addEventListener('click', (e) => {
            if (e.target.closest('.case-bookmark')) {
                const button = e.target.closest('.case-bookmark');
                const caseId = button.getAttribute('data-case-id');
                this.toggleBookmark(caseId, button);
            }

            if (e.target.closest('.case-actions .btn-primary')) {
                const button = e.target.closest('.case-actions .btn-primary');
                const caseCard = button.closest('.case-card');
                const caseId = caseCard.getAttribute('data-case-id');
                this.showCaseDetail(caseId);
            }
        });
    },

    handleSearchInput(value) {
        this.state.searchTerm = value;
        
        if (this.state.debounceTimer) {
            clearTimeout(this.state.debounceTimer);
        }

        this.state.debounceTimer = setTimeout(() => {
            this.performSearch();
        }, 300);
    },

    performSearch() {
        const searchTerm = this.state.searchTerm.toLowerCase();
        const { jurisdiction, court, year } = this.state.filters;

        let results = window.CASES_DATABASE || [];

        if (searchTerm) {
            results = results.filter(caseItem => {
                const titleMatch = caseItem.title.toLowerCase().includes(searchTerm);
                const summaryMatch = caseItem.summary.toLowerCase().includes(searchTerm);
                const tagsMatch = caseItem.tags.some(tag => tag.toLowerCase().includes(searchTerm));
                return titleMatch || summaryMatch || tagsMatch;
            });
        }

        if (jurisdiction) {
            results = results.filter(caseItem => {
                const courtLower = caseItem.court.toLowerCase();
                if (jurisdiction === 'federal') {
                    return courtLower.includes('u.s.') || courtLower.includes('federal') || courtLower.includes('circuit');
                } else if (jurisdiction === 'supreme') {
                    return courtLower.includes('supreme court') && courtLower.includes('u.s.');
                } else if (jurisdiction === 'appeals') {
                    return courtLower.includes('circuit');
                } else if (jurisdiction === 'state') {
                    return !courtLower.includes('u.s.') && !courtLower.includes('federal');
                }
                return true;
            });
        }

        if (court) {
            results = results.filter(caseItem => {
                const courtLower = caseItem.court.toLowerCase();
                if (court === 'scotus') {
                    return courtLower.includes('u.s. supreme court');
                } else if (court === 'ca9') {
                    return courtLower.includes('9th circuit');
                } else if (court === 'ca2') {
                    return courtLower.includes('2nd circuit');
                } else if (court === 'ca7') {
                    return courtLower.includes('7th circuit');
                } else if (court === 'dcca') {
                    return courtLower.includes('d.c. circuit');
                } else if (court === 'calsc') {
                    return courtLower.includes('california supreme court');
                } else if (court === 'taxcourt') {
                    return courtLower.includes('tax court');
                } else if (court === 'statesc') {
                    return courtLower.includes('state supreme court');
                }
                return true;
            });
        }

        if (year) {
            results = results.filter(caseItem => {
                if (year === 'older') {
                    return parseInt(caseItem.year) < 2020;
                }
                return caseItem.year.toString() === year;
            });
        }

        this.state.results = results;
        this.sortResults();
    },

    sortResults() {
        const { sortBy } = this.state;
        let sorted = [...this.state.results];

        if (sortBy === 'date') {
            sorted.sort((a, b) => parseInt(b.year) - parseInt(a.year));
        } else if (sortBy === 'citations') {
            sorted.sort((a, b) => b.citations - a.citations);
        } else {
            sorted.sort((a, b) => {
                const searchTerm = this.state.searchTerm.toLowerCase();
                if (!searchTerm) return 0;
                
                const aRelevance = this.calculateRelevance(a, searchTerm);
                const bRelevance = this.calculateRelevance(b, searchTerm);
                return bRelevance - aRelevance;
            });
        }

        this.state.results = sorted;
        this.renderResults();
    },

    calculateRelevance(caseItem, searchTerm) {
        let score = 0;
        const titleLower = caseItem.title.toLowerCase();
        const summaryLower = caseItem.summary.toLowerCase();

        if (titleLower.includes(searchTerm)) score += 10;
        if (summaryLower.includes(searchTerm)) score += 5;
        
        caseItem.tags.forEach(tag => {
            if (tag.toLowerCase().includes(searchTerm)) score += 3;
        });

        return score;
    },

    resetFilters() {
        this.state.searchTerm = '';
        this.state.filters = {
            jurisdiction: '',
            court: '',
            year: ''
        };
        this.state.sortBy = 'relevance';

        if (this.elements.searchBar) this.elements.searchBar.value = '';
        if (this.elements.jurisdictionFilter) this.elements.jurisdictionFilter.value = '';
        if (this.elements.courtFilter) this.elements.courtFilter.value = '';
        if (this.elements.yearFilter) this.elements.yearFilter.value = '';
        if (this.elements.sortSelect) this.elements.sortSelect.value = 'relevance';

        this.loadInitialResults();
    },

    loadInitialResults() {
        this.state.results = window.CASES_DATABASE || [];
        this.renderResults();
    },

    renderResults() {
        if (!this.elements.resultsList) return;

        const savedCases = Storage.getSavedCases();
        
        if (this.state.results.length === 0) {
            this.elements.resultsList.innerHTML = `
                <div style="padding: 3rem; text-align: center; color: #6c757d;">
                    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin: 0 auto 1rem;">
                        <circle cx="11" cy="11" r="8"/>
                        <path d="M21 21l-4.35-4.35"/>
                    </svg>
                    <h3 style="font-size: 1.25rem; color: #1e3a5f; margin-bottom: 0.5rem;">No cases found</h3>
                    <p style="margin: 0;">Try adjusting your search terms or filters</p>
                </div>
            `;
            if (this.elements.resultsCount) {
                this.elements.resultsCount.textContent = 'No results';
            }
            return;
        }

        const html = this.state.results.map(caseItem => {
            const isBookmarked = savedCases.some(c => c.id === caseItem.id);
            const bookmarkClass = isBookmarked ? 'case-bookmark active' : 'case-bookmark';
            const bookmarkIcon = isBookmarked 
                ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2">
                     <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/>
                   </svg>`
                : `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                     <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/>
                   </svg>`;

            return `
                <article class="case-card" data-case-id="${caseItem.id}">
                    <div class="case-header">
                        <h3 class="case-title">${this.escapeHtml(caseItem.title)}</h3>
                        <button class="${bookmarkClass}" data-case-id="${caseItem.id}" aria-label="${isBookmarked ? 'Unbookmark' : 'Bookmark'} case">
                            ${bookmarkIcon}
                        </button>
                    </div>
                    
                    <div class="case-meta">
                        <span class="case-court">${this.escapeHtml(caseItem.court)}</span>
                        <span class="case-separator">•</span>
                        <span class="case-year">${caseItem.year}</span>
                        <span class="case-separator">•</span>
                        <span class="case-citations">${caseItem.citations} citations</span>
                    </div>
                    
                    <p class="case-summary">${this.escapeHtml(caseItem.summary)}</p>
                    
                    <div class="case-tags">
                        ${caseItem.tags.map(tag => `<span class="case-tag">${this.escapeHtml(tag)}</span>`).join('')}
                    </div>
                    
                    <div class="case-actions">
                        <button class="btn btn-primary btn-small">View Details</button>
                        <button class="btn btn-outline btn-small">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                                <polyline points="7 10 12 15 17 10"/>
                                <line x1="12" y1="15" x2="12" y2="3"/>
                            </svg>
                            Export
                        </button>
                    </div>
                </article>
            `;
        }).join('');

        this.elements.resultsList.innerHTML = html;

        if (this.elements.resultsCount) {
            const count = this.state.results.length;
            this.elements.resultsCount.textContent = `Showing ${count} result${count !== 1 ? 's' : ''}`;
        }
    },

    toggleBookmark(caseId, button) {
        const savedCases = Storage.getSavedCases();
        const caseItem = this.state.results.find(c => c.id === caseId);
        
        if (!caseItem) return;

        const isCurrentlySaved = savedCases.some(c => c.id === caseId);

        if (isCurrentlySaved) {
            Storage.removeSavedCase(caseId);
            button.classList.remove('active');
            button.innerHTML = `
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/>
                </svg>
            `;
            button.setAttribute('aria-label', 'Bookmark case');
        } else {
            Storage.addSavedCase(caseItem);
            button.classList.add('active');
            button.innerHTML = `
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2">
                    <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/>
                </svg>
            `;
            button.setAttribute('aria-label', 'Unbookmark case');
        }

        this.updateSavedCasesCount();

        const detailPanel = document.querySelector('.detail-panel.active');
        if (detailPanel) {
            const detailCaseId = detailPanel.getAttribute('data-case-id');
            if (detailCaseId === caseId) {
                const detailBookmarkBtn = detailPanel.querySelector('.detail-actions .btn-outline');
                if (detailBookmarkBtn) {
                    if (isCurrentlySaved) {
                        detailBookmarkBtn.innerHTML = `
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/>
                            </svg>
                            Save Case
                        `;
                    } else {
                        detailBookmarkBtn.innerHTML = `
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2">
                                <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/>
                            </svg>
                            Unsave Case
                        `;
                    }
                }
            }
        }
    },

    updateSavedCasesCount() {
        if (!this.elements.savedCasesBadge) return;
        const count = Storage.getSavedCases().length;
        this.elements.savedCasesBadge.textContent = count;
    },

    showCaseDetail(caseId) {
        const caseItem = (window.CASES_DATABASE || []).find(c => c.id === caseId);
        if (!caseItem) return;

        let detailPanel = document.querySelector('.detail-panel');
        
        if (!detailPanel) {
            detailPanel = document.createElement('div');
            detailPanel.className = 'detail-panel';
            document.body.appendChild(detailPanel);
        }

        detailPanel.setAttribute('data-case-id', caseId);
        detailPanel.innerHTML = this.renderCaseDetailHTML(caseItem);

        requestAnimationFrame(() => {
            detailPanel.classList.add('active');
            document.body.style.overflow = 'hidden';
        });

        this.setupPanelCloseHandlers(detailPanel, caseId);
    },

    renderCaseDetailHTML(caseItem) {
        const savedCases = Storage.getSavedCases();
        const isSaved = savedCases.some(c => c.id === caseItem.id);
        const saveButtonText = isSaved ? 'Unsave Case' : 'Save Case';
        const saveButtonIcon = isSaved
            ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2">
                 <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/>
               </svg>`
            : `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                 <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/>
               </svg>`;

        return `
            <div class="detail-header">
                <h2 class="detail-title">Case Overview</h2>
                <button class="detail-close" aria-label="Close detail panel">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" y1="6" x2="6" y2="18"/>
                        <line x1="6" y1="6" x2="18" y2="18"/>
                    </svg>
                </button>
            </div>
            
            <div class="detail-content">
                <div class="detail-section">
                    <h3 class="detail-section-title">${this.escapeHtml(caseItem.title)}</h3>
                    <div class="detail-meta">
                        <div class="detail-meta-item">
                            <span class="detail-meta-label">Court:</span>
                            <span class="detail-meta-value">${this.escapeHtml(caseItem.court)}</span>
                        </div>
                        <div class="detail-meta-item">
                            <span class="detail-meta-label">Year:</span>
                            <span class="detail-meta-value">${caseItem.year}</span>
                        </div>
                        <div class="detail-meta-item">
                            <span class="detail-meta-label">Docket No.:</span>
                            <span class="detail-meta-value">${caseItem.docketNumber || 'N/A'}</span>
                        </div>
                        <div class="detail-meta-item">
                            <span class="detail-meta-label">Citations:</span>
                            <span class="detail-meta-value">${caseItem.citations} citations</span>
                        </div>
                    </div>
                </div>
                
                <div class="detail-section">
                    <h3 class="detail-section-title">Summary</h3>
                    <p class="detail-text">${this.escapeHtml(caseItem.summary)}</p>
                </div>
                
                <div class="detail-section">
                    <h3 class="detail-section-title">Tags</h3>
                    <div class="case-tags">
                        ${caseItem.tags.map(tag => `<span class="case-tag">${this.escapeHtml(tag)}</span>`).join('')}
                    </div>
                </div>
                
                ${caseItem.holdings ? `
                    <div class="detail-section">
                        <h3 class="detail-section-title">Holdings</h3>
                        <p class="detail-text">${this.escapeHtml(caseItem.holdings)}</p>
                    </div>
                ` : ''}
                
                ${caseItem.keyPoints && caseItem.keyPoints.length > 0 ? `
                    <div class="detail-section">
                        <h3 class="detail-section-title">Key Points</h3>
                        <ul class="detail-list">
                            ${caseItem.keyPoints.map(point => `
                                <li class="detail-list-item">${this.escapeHtml(point)}</li>
                            `).join('')}
                        </ul>
                    </div>
                ` : ''}
            </div>
            
            <div class="detail-actions">
                <button class="btn btn-primary" data-action="export">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                        <polyline points="7 10 12 15 17 10"/>
                        <line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                    Export Case
                </button>
                <button class="btn btn-outline" data-action="save">
                    ${saveButtonIcon}
                    ${saveButtonText}
                </button>
            </div>
        `;
    },

    setupPanelCloseHandlers(panel, caseId) {
        const closeBtn = panel.querySelector('.detail-close');
        const saveBtn = panel.querySelector('[data-action="save"]');
        const exportBtn = panel.querySelector('[data-action="export"]');

        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                this.closeCaseDetail(panel);
            });
        }

        if (saveBtn) {
            saveBtn.addEventListener('click', () => {
                const bookmarkBtn = document.querySelector(`.case-bookmark[data-case-id="${caseId}"]`);
                if (bookmarkBtn) {
                    this.toggleBookmark(caseId, bookmarkBtn);
                }
            });
        }

        if (exportBtn) {
            exportBtn.addEventListener('click', () => {
                this.exportCase(caseId);
            });
        }

        const overlay = document.createElement('div');
        overlay.className = 'detail-overlay';
        overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.5);
            z-index: 1019;
            opacity: 0;
            transition: opacity 250ms ease;
        `;
        document.body.appendChild(overlay);

        requestAnimationFrame(() => {
            overlay.style.opacity = '1';
        });

        overlay.addEventListener('click', () => {
            this.closeCaseDetail(panel);
        });

        const escHandler = (e) => {
            if (e.key === 'Escape') {
                this.closeCaseDetail(panel);
            }
        };
        document.addEventListener('keydown', escHandler);
        panel.setAttribute('data-esc-handler', 'true');
    },

    closeCaseDetail(panel) {
        if (!panel) return;

        panel.classList.remove('active');
        document.body.style.overflow = '';

        const overlay = document.querySelector('.detail-overlay');
        if (overlay) {
            overlay.style.opacity = '0';
            setTimeout(() => {
                overlay.remove();
            }, 250);
        }

        setTimeout(() => {
            if (panel.parentNode) {
                panel.parentNode.removeChild(panel);
            }
        }, 250);

        document.removeEventListener('keydown', this.escHandler);
    },

    exportCase(caseId) {
        const caseItem = (window.CASES_DATABASE || []).find(c => c.id === caseId);
        if (!caseItem) return;

        const content = `
Case Title: ${caseItem.title}
Court: ${caseItem.court}
Year: ${caseItem.year}
Citations: ${caseItem.citations}
Docket Number: ${caseItem.docketNumber || 'N/A'}

Summary:
${caseItem.summary}

Tags:
${caseItem.tags.join(', ')}

${caseItem.holdings ? `Holdings:\n${caseItem.holdings}\n\n` : ''}
${caseItem.keyPoints && caseItem.keyPoints.length > 0 ? `Key Points:\n${caseItem.keyPoints.map((p, i) => `${i + 1}. ${p}`).join('\n')}` : ''}
        `.trim();

        const blob = new Blob([content], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${caseItem.title.replace(/[^a-z0-9]/gi, '_')}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    },

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
};

if (typeof window !== 'undefined') {
    window.SearchManager = SearchManager;
}