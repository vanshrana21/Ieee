/**
 * case-detail.js
 * Handles case detail view - fetching and displaying comprehensive case information
 */

/**
 * Initialize case detail page if case_id is in URL
 */
document.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const caseId = urlParams.get('case_id') || urlParams.get('opinion_id'); // Support both params
    const idType = urlParams.get('id_type');
    
    console.log('Case Detail Page Loaded');
    console.log('Case ID from URL:', caseId);
    console.log('ID Type:', idType);
    
    if (caseId && document.getElementById('caseDetailContainer')) {
        loadCaseDetail(caseId, idType);
    } else if (!caseId) {
        showCaseDetailError('No case ID provided in URL');
    } else if (!document.getElementById('caseDetailContainer')) {
        console.error('caseDetailContainer element not found');
    }
});

/**
 * Open case detail - called when user clicks on a case card
 */
function openCaseDetail(caseId, idType = 'opinion') {
    console.log('Opening case detail for case ID:', caseId, 'type:', idType);
    window.location.href = `/html/case-detail.html?case_id=${caseId}&id_type=${idType}`;
}

/**
 * Fetch and display case details
 */
async function loadCaseDetail(caseId, idType) {
    try {
        showCaseDetailLoading();
        
        console.log('Fetching case details from API...');
        
        // Build URL with optional id_type parameter
        let url = `http://127.0.0.1:8000/api/cases/${caseId}`;
        if (idType) {
            url += `?id_type=${idType}`;
        }
        
        const response = await fetch(url, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        console.log('API Response Status:', response.status);
        
        if (!response.ok) {
            if (response.status === 404) {
                throw new Error('Case not found');
            }
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `Failed to load case: ${response.status}`);
        }
        
        const caseData = await response.json();
        console.log('Case data received:', caseData);
        displayCaseDetail(caseData);
        
    } catch (error) {
        console.error('Error loading case detail:', error);
        showCaseDetailError(error.message);
    }
}

/**
 * Display case detail in the UI
 */
function displayCaseDetail(caseData) {
    const container = document.getElementById('caseDetailContainer');
    if (!container) {
        console.error('caseDetailContainer not found');
        return;
    }
    
    console.log('Rendering case detail...');
    
    const metadata = caseData.metadata;
    const aiBrief = caseData.ai_brief;
    const fullJudgment = caseData.full_judgment;
    
    container.innerHTML = `
        <div class="case-detail-page">
            <!-- Header Section -->
            <div class="case-detail-header">
                <button class="btn-back" onclick="window.history.back()">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="19" y1="12" x2="5" y2="12"/>
                        <polyline points="12 19 5 12 12 5"/>
                    </svg>
                    Back to Search
                </button>
                
                <h1 class="case-title">${escapeHtml(metadata.case_name)}</h1>
                
                <div class="case-actions">
                    <button class="btn btn-outline" onclick="saveCaseForLater('${caseData.case_id}')">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/>
                        </svg>
                        Save
                    </button>
                    <button class="btn btn-outline" onclick="printCase()">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="6 9 6 2 18 2 18 9"/>
                            <path d="M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2"/>
                            <rect x="6" y="14" width="12" height="8"/>
                        </svg>
                        Print
                    </button>
                    ${fullJudgment.download_url ? `
                    <a href="${escapeHtml(fullJudgment.download_url)}" target="_blank" rel="noopener noreferrer" class="btn btn-primary" style="text-decoration: none;">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                            <polyline points="7 10 12 15 17 10"/>
                            <line x1="12" y1="15" x2="12" y2="3"/>
                        </svg>
                        Download PDF
                    </a>
                    ` : `
                    <button class="btn btn-outline" disabled style="opacity: 0.5; cursor: not-allowed;">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                            <polyline points="7 10 12 15 17 10"/>
                            <line x1="12" y1="15" x2="12" y2="3"/>
                        </svg>
                        PDF Unavailable
                    </button>
                    `}
                </div>
            </div>
            
            <!-- Metadata Section -->
            <div class="case-section case-metadata">
                <h2 class="section-title">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                        <polyline points="14 2 14 8 20 8"/>
                        <line x1="16" y1="13" x2="8" y2="13"/>
                        <line x1="16" y1="17" x2="8" y2="17"/>
                        <polyline points="10 9 9 9 8 9"/>
                    </svg>
                    Case Information
                </h2>
                <div class="metadata-grid">
                    <div class="metadata-item">
                        <span class="metadata-label">Court:</span>
                        <span class="metadata-value">${escapeHtml(metadata.court_full_name || metadata.court)}</span>
                    </div>
                    <div class="metadata-item">
                        <span class="metadata-label">Date Filed:</span>
                        <span class="metadata-value">${formatDate(metadata.date_filed)}</span>
                    </div>
                    <div class="metadata-item">
                        <span class="metadata-label">Jurisdiction:</span>
                        <span class="metadata-value">${escapeHtml(metadata.jurisdiction)}</span>
                    </div>
                    <div class="metadata-item">
                        <span class="metadata-label">Docket Number:</span>
                        <span class="metadata-value">${escapeHtml(metadata.docket_number || 'N/A')}</span>
                    </div>
                    ${metadata.judges ? `
                    <div class="metadata-item metadata-full-width">
                        <span class="metadata-label">Judges:</span>
                        <span class="metadata-value">${escapeHtml(metadata.judges)}</span>
                    </div>
                    ` : ''}
                    ${metadata.author ? `
                    <div class="metadata-item">
                        <span class="metadata-label">Author:</span>
                        <span class="metadata-value">${escapeHtml(metadata.author)}</span>
                    </div>
                    ` : ''}
                    ${metadata.opinion_type ? `
                    <div class="metadata-item">
                        <span class="metadata-label">Opinion Type:</span>
                        <span class="metadata-value">${escapeHtml(metadata.opinion_type)}</span>
                    </div>
                    ` : ''}
                </div>
            </div>
            
            <!-- AI Brief Section -->
            <div class="case-section case-ai-brief">
                <h2 class="section-title">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                        <path d="M2 17l10 5 10-5"/>
                        <path d="M2 12l10 5 10-5"/>
                    </svg>
                    AI-Generated Case Brief
                    <span class="ai-badge">AI</span>
                </h2>
                ${caseData.ai_brief_available ? renderAIBrief(aiBrief) : renderNoAIBrief()}
            </div>
            
            <!-- Full Judgment Section -->
            <div class="case-section case-full-judgment">
                <h2 class="section-title">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                        <polyline points="14 2 14 8 20 8"/>
                    </svg>
                    Full Judgment Text
                </h2>
                ${renderFullJudgment(fullJudgment)}
            </div>
        </div>
    `;
    
    console.log('Case detail rendered successfully');
}

/**
 * Render AI brief sections
 */
function renderAIBrief(aiBrief) {
    return `
        <div class="ai-brief-content">
            <div class="brief-section">
                <h3 class="brief-section-title">Case Summary</h3>
                <p class="brief-text">${formatBriefText(aiBrief.case_summary)}</p>
            </div>
            
            <div class="brief-section">
                <h3 class="brief-section-title">Legal Issues</h3>
                <div class="brief-text">${formatBriefText(aiBrief.legal_issues)}</div>
            </div>
            
            <div class="brief-section">
                <h3 class="brief-section-title">Court's Holding</h3>
                <div class="brief-text">${formatBriefText(aiBrief.holding)}</div>
            </div>
            
            <div class="brief-section">
                <h3 class="brief-section-title">Reasoning</h3>
                <div class="brief-text">${formatBriefText(aiBrief.reasoning)}</div>
            </div>
            
            <div class="brief-section">
                <h3 class="brief-section-title">Final Outcome</h3>
                <div class="brief-text">${formatBriefText(aiBrief.outcome)}</div>
            </div>
        </div>
    `;
}

/**
 * Render message when AI brief is not available
 */
function renderNoAIBrief() {
    return `
        <div class="no-ai-brief">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="8" x2="12" y2="12"/>
                <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <h3>AI Summary Unavailable</h3>
            <p>The full opinion text for this case is not available in the database, so an AI-generated brief could not be created. Please refer to the case metadata and source link below.</p>
        </div>
    `;
}

/**
 * Render full judgment text
 */
function renderFullJudgment(fullJudgment) {
    // Check if any text is available
    if (!fullJudgment.has_text) {
        return `
            <div class="no-judgment-text">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color: #94a3b8; margin-bottom: 16px;">
                    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                </svg>
                <h3 style="font-size: 18px; color: #475569; margin: 0 0 8px 0;">Full Opinion Text Unavailable</h3>
                <p>The complete opinion text is not available in the CourtListener database for this case. This is common for older cases or cases from certain courts.</p>
                <a href="${escapeHtml(fullJudgment.source_url)}" target="_blank" rel="noopener noreferrer" class="btn btn-primary">
                    View Case on CourtListener
                </a>
            </div>
        `;
    }
    
    if (fullJudgment.plain_text) {
        return `
            <div class="judgment-text">
                <pre class="judgment-pre">${escapeHtml(fullJudgment.plain_text)}</pre>
            </div>
            <div class="judgment-footer">
                <a href="${escapeHtml(fullJudgment.source_url)}" target="_blank" rel="noopener noreferrer" class="btn btn-outline">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/>
                        <polyline points="15 3 21 3 21 9"/>
                        <line x1="10" y1="14" x2="21" y2="3"/>
                    </svg>
                    View on CourtListener
                </a>
                ${fullJudgment.download_url ? `
                <a href="${escapeHtml(fullJudgment.download_url)}" target="_blank" rel="noopener noreferrer" class="btn btn-primary" style="margin-left: 12px;">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                        <polyline points="7 10 12 15 17 10"/>
                        <line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                    Download PDF
                </a>
                ` : ''}
            </div>
        `;
    } else if (fullJudgment.html) {
        return `
            <div class="judgment-text">
                <div class="judgment-html">${fullJudgment.html}</div>
            </div>
            <div class="judgment-footer">
                <a href="${escapeHtml(fullJudgment.source_url)}" target="_blank" rel="noopener noreferrer" class="btn btn-outline">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/>
                        <polyline points="15 3 21 3 21 9"/>
                        <line x1="10" y1="14" x2="21" y2="3"/>
                    </svg>
                    View on CourtListener
                </a>
                ${fullJudgment.download_url ? `
                <a href="${escapeHtml(fullJudgment.download_url)}" target="_blank" rel="noopener noreferrer" class="btn btn-primary" style="margin-left: 12px;">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                        <polyline points="7 10 12 15 17 10"/>
                        <line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                    Download PDF
                </a>
                ` : ''}
            </div>
        `;
    }
    
    return `
        <div class="no-judgment-text">
            <p>Full judgment text is not available.</p>
            <a href="${escapeHtml(fullJudgment.source_url)}" target="_blank" rel="noopener noreferrer" class="btn btn-primary">
                View Case on CourtListener
            </a>
        </div>
    `;
}

/**
 * Show loading state
 */
function showCaseDetailLoading() {
    const container = document.getElementById('caseDetailContainer');
    if (!container) return;
    
    container.innerHTML = `
        <div class="loading-container">
            <div class="spinner"></div>
            <p>Loading case details...</p>
        </div>
    `;
}

/**
 * Show error state
 */
function showCaseDetailError(message) {
    const container = document.getElementById('caseDetailContainer');
    if (!container) return;
    
    container.innerHTML = `
        <div class="error-container">
            <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="8" x2="12" y2="12"/>
                <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <h2>Error Loading Case</h2>
            <p>${escapeHtml(message)}</p>
            <button class="btn btn-primary" onclick="window.history.back()">Go Back</button>
        </div>
    `;
}

/**
 * Format brief text with proper line breaks
 */
function formatBriefText(text) {
    if (!text) return '';
    return escapeHtml(text).replace(/\n/g, '<br>');
}

/**
 * Format date
 */
function formatDate(dateStr) {
    if (!dateStr) return 'N/A';
    try {
        const date = new Date(dateStr);
        return date.toLocaleDateString('en-US', { 
            year: 'numeric', 
            month: 'long', 
            day: 'numeric' 
        });
    } catch (e) {
        return dateStr;
    }
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Placeholder functions for action buttons
 */
function saveCaseForLater(caseId) {
    alert(`Save functionality coming soon for case ${caseId}`);
}

function printCase() {
    window.print();
}

function exportCasePDF(caseId) {
    alert(`PDF export functionality coming soon for case ${caseId}`);
}