/**
 * Case Simplifier - Frontend Logic
 * Connects to JurisAI Backend for real Indian legal data analysis
 */

// Global state
let currentCase = null;

/**
 * Initialize page
 */
document.addEventListener('DOMContentLoaded', function() {
    loadSavedCases();
    
    // Allow Enter key to submit
    const caseNameInput = document.getElementById('caseName');
    if (caseNameInput) {
        caseNameInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                simplifyCase();
            }
        });
    }
});

/**
 * Navigation
 */
function goBackToDashboard() {
    window.location.href = "./dashboard-student.html";
}

/**
 * Reset form to search for a new case
 */
function resetForm() {
    document.getElementById('caseName').value = '';
    document.getElementById('subjectSelect').value = '';
    document.getElementById('outputSection').classList.add('hidden');
    document.getElementById('inputSection').classList.remove('hidden');
    document.getElementById('searchHeader').classList.remove('hidden');
    currentCase = null;
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

/**
 * Normalizes case identifier for backend resolution
 * 1. Lowercase
 * 2. vs -> v
 * 3. Remove (year)
 * 4. Strip punctuation
 * 5. Spaces -> hyphens
 */
function normalizeCaseIdentifier(input) {
    if (!input) return '';
    return input
        .toLowerCase()
        .replace(/\bvs\.?\b/g, 'v')
        .replace(/\(\d{4}\)/g, '')
        .replace(/[^\w\s]/g, '')
        .trim()
        .replace(/\s+/g, '-');
}

/**
 * Main Simplify Case function
 * Directly calls the unified Case Simplifier API
 */
async function simplifyCase() {
    const caseNameInput = document.getElementById('caseName');
    const caseName = caseNameInput.value.trim();
    if (!caseName) {
        showToast('⚠️ Please enter a case name');
        return;
    }

    const normalizedIdentifier = normalizeCaseIdentifier(caseName);
    console.log('Normalized identifier:', normalizedIdentifier);

    // Show loading state
    setLoadingState(true);

    try {
        // Direct call to the unified Case Simplifier API
        const data = await api.get(`/api/case-simplifier/${encodeURIComponent(normalizedIdentifier)}`);
        
        if (!data || !data.raw_case) {
            throw new Error('Case data not available');
        }

        currentCase = data;
        displayCaseOutput(data);

    } catch (error) {
        console.error('Error simplifying case:', error);
        showToast('❌ Failed to process case: ' + (error.message || 'Unknown error'));
    } finally {
        setLoadingState(false);
    }
}

/**
 * Fetch and display full case data
 * DEPRECATED: Combined into simplifyCase for the unified API
 */
async function loadFullCaseData(caseId) {
    document.getElementById('caseName').value = caseId;
    return simplifyCase();
}

/**
 * Render Case Output to UI
 */
function displayCaseOutput(data) {
    const { raw_case, ai_structured_summary, has_full_text, full_text_reason, source, summary_source, disclaimer } = data;
    
    // Switch views
    document.getElementById('inputSection').classList.add('hidden');
    document.getElementById('searchHeader').classList.add('hidden');
    document.getElementById('outputSection').classList.remove('hidden');

    // Update Header Information
    document.getElementById('outputCaseName').textContent = raw_case.case_name || 'Case title unavailable (Authoritative source limitation)';
    document.getElementById('outputCourt').textContent = raw_case.court || 'Court';
    document.getElementById('outputYear').textContent = raw_case.citation || '';
    
    // Importance badge - show metadata-only indicator if no full text
    const importanceBadge = document.getElementById('outputImportance');
    if (has_full_text) {
        importanceBadge.textContent = 'Full Text Available';
        importanceBadge.style.background = '#10b981';
    } else {
        importanceBadge.textContent = 'Metadata-Only';
        importanceBadge.style.background = '#f59e0b';
    }

    // Render Full Judgment (Left Panel - Authoritative)
    const judgmentContainer = document.getElementById('fullJudgmentText');
    const panelHeader = document.querySelector('.judgment-panel .panel-header');
    
    // Add Fullscreen toggle button if not exists
    if (!document.getElementById('fullscreenPdfBtn')) {
        const headerActions = document.createElement('div');
        headerActions.className = 'panel-header-actions';
        headerActions.innerHTML = `
            <button id="fullscreenPdfBtn" class="fullscreen-btn" onclick="toggleFullscreenPdf()">
                <span>⛶</span> Fullscreen PDF
            </button>
        `;
        panelHeader.appendChild(headerActions);
    }
    
    // Check for Local PDF Override (Landmark Case)
    if (raw_case.pdf_url) {
        judgmentContainer.style.padding = '0'; // PDF needs no padding
        judgmentContainer.innerHTML = `
            <div style="height: 100%; border: none; background: #f8fafc;">
                <iframe 
                    src="${raw_case.pdf_url}#toolbar=1&view=FitH" 
                    width="100%" 
                    height="100%" 
                    style="border: none; display: block;"
                ></iframe>
            </div>
        `;
        // Update header for PDF
        const h3 = panelHeader.querySelector('h3');
        if (h3) h3.textContent = '⚖️ Official Supreme Court PDF';
    } else if (has_full_text && raw_case.judgment && raw_case.judgment.trim()) {
        judgmentContainer.style.padding = '2.5rem';
        judgmentContainer.innerHTML = `<h4>Full Judgment</h4><div>${formatLegalText(raw_case.judgment)}</div>`;
        const h3 = panelHeader.querySelector('h3');
        if (h3) h3.textContent = '⚖️ Full Judgment';
    } else {
        judgmentContainer.style.padding = '2.5rem';
        const reasonText = full_text_reason || 'metadata-only case';
        const disclaimerText = disclaimer || 'Full judgment text unavailable due to publisher restrictions. Summary generated from case metadata and established legal principles.';
        const summarySourceText = summary_source || 'Authoritative metadata + AI legal reasoning';
        judgmentContainer.innerHTML = `
            <div style="background: rgba(234, 179, 8, 0.1); border-left: 4px solid #eab308; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
                <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px;">
                    <span style="font-size: 1.5rem;">⚠️</span>
                    <h4 style="color: #854d0e; margin: 0; font-weight: 600;">Metadata-Only Case</h4>
                </div>
                <p style="color: #854d0e; margin: 0 0 12px 0; font-size: 0.95em;">
                    ${disclaimerText}
                </p>
                <div style="background: rgba(255,255,255,0.5); padding: 12px; border-radius: 6px; margin-top: 12px;">
                    <p style="color: #78350f; margin: 0; font-size: 0.85em;">
                        <strong>Reason:</strong> ${reasonText}
                    </p>
                    <p style="color: #78350f; margin: 8px 0 0 0; font-size: 0.85em;">
                        <strong>Summary Source:</strong> ${summarySourceText}
                    </p>
                    <p style="color: #78350f; margin: 8px 0 0 0; font-size: 0.85em;">
                        <strong>Data Provider:</strong> ${source || 'Kanoon'}
                    </p>
                </div>
            </div>
            <div style="background: #f0f9ff; border: 1px solid #0ea5e9; padding: 16px; border-radius: 8px;">
                <p style="color: #0369a1; margin: 0; font-size: 0.9em;">
                    <strong>Note:</strong> The AI-generated summary on the right panel uses authoritative case metadata combined with established legal principles to provide educational insights.
                </p>
            </div>
        `;
    }

    // Render AI Summary Sections (Right Panel)
    const academicContainer = document.getElementById('academicSummaryContainer');
    const partBLabel = document.getElementById('partBLabel');
    
    // Check for Deterministic Academic Summary (Part A)
    if (data.ai_summary_full) {
        academicContainer.innerHTML = `
            <div class="summary-section-academic" style="border: 2px solid #2563eb; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);">
                <div class="section-header-academic" style="background: #2563eb; color: white; padding: 16px 20px;">
                    <h3 style="color: white; margin: 0; font-size: 1.25rem; font-weight: 800; letter-spacing: -0.025em;">AI-Generated Academic Summary</h3>
                </div>
                <div class="academic-summary-scroll">
                    <div style="padding: 24px; line-height: 1.8; font-size: 16px; color: #0f172a;">
                        <div style="margin-bottom: 20px; padding-bottom: 12px; border-bottom: 1px solid #e2e8f0; display: flex; align-items: center; justify-content: space-between;">
                            <span style="background: #dbeafe; color: #1e40af; padding: 4px 10px; border-radius: 4px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase;">
                                Authoritative Reconstruct
                            </span>
                            <span style="color: #64748b; font-size: 0.85rem; font-style: italic;">
                                Source: Supreme Court of India Official Judgment
                            </span>
                        </div>
                        <div style="font-family: 'Inter', sans-serif;">
                            ${formatLegalText(data.ai_summary_full)}
                        </div>
                    </div>
                </div>
            </div>
        `;
        partBLabel.classList.remove('hidden');
    } else {
        academicContainer.innerHTML = '';
        partBLabel.classList.add('hidden');
    }

    if (ai_structured_summary) {
        renderSummarySection('factsText', ai_structured_summary.facts);
        renderSummarySection('issuesText', ai_structured_summary.issues);
        renderSummarySection('argumentsText', ai_structured_summary.arguments);
        renderSummarySection('judgmentText', ai_structured_summary.judgment);
        renderSummarySection('ratioText', ai_structured_summary.ratio_decidendi);
        renderSummarySection('significanceText', ai_structured_summary.exam_importance || "Focus on the ratio decidendi for exam preparation.");
        
        // Ensure all sections are expanded for the demo
        document.querySelectorAll('.summary-section').forEach(s => s.classList.add('active'));
    } else {
        const summaryFields = ['factsText', 'issuesText', 'argumentsText', 'judgmentText', 'ratioText', 'significanceText'];
        summaryFields.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.innerHTML = '<p class="text-muted">AI summary unavailable.</p>';
        });
    }

    // Scroll to top of output
    document.getElementById('outputSection').scrollIntoView({ behavior: 'smooth' });
}

/**
 * Fullscreen PDF Toggle
 */
function toggleFullscreenPdf() {
    const panel = document.querySelector('.judgment-panel');
    const btn = document.getElementById('fullscreenPdfBtn');
    
    if (!document.fullscreenElement) {
        panel.classList.add('fullscreen');
        btn.innerHTML = '<span>✕</span> Close Fullscreen';
        // Optional: Use browser Fullscreen API if available
        if (panel.requestFullscreen) {
            panel.requestFullscreen().catch(err => console.log(err));
        }
    } else {
        if (document.exitFullscreen) {
            document.exitFullscreen();
        }
    }
}

// Handle browser fullscreen change
document.addEventListener('fullscreenchange', () => {
    const panel = document.querySelector('.judgment-panel');
    const btn = document.getElementById('fullscreenPdfBtn');
    if (!document.fullscreenElement) {
        panel.classList.remove('fullscreen');
        btn.innerHTML = '<span>⛶</span> Fullscreen PDF';
    }
});

/**
 * Helper to render summary sections with fallback
 */
function renderSummarySection(elementId, content) {
    const element = document.getElementById(elementId);
    if (!element) return;
    
    if (!content || content === "N/A" || content.toLowerCase().includes("not found")) {
        element.innerHTML = '<p class="text-muted">Information not available in judgment text.</p>';
    } else {
        // If content contains "Not available from authoritative source", it's still content we want to show
        // but maybe with a different style if it's the ONLY thing there.
        element.innerHTML = formatLegalText(content);
    }
}

/**
 * Format text for legal reading (bullet points, paragraphs)
 */
function formatLegalText(text) {
    if (!text) return '';
    
    // Handle bullet points
    let formatted = text.replace(/^\s*[-•*]\s*(.+)/gm, '<li>$1</li>');
    formatted = formatted.replace(/(<li>.*<\/li>)+/g, '<ul>$&</ul>');
    
    // Handle paragraphs
    formatted = formatted.split('\n\n').map(p => `<p>${p.trim()}</p>`).join('');
    
    return formatted;
}

/**
 * Toggle summary section visibility
 */
function toggleSummarySection(header) {
    const section = header.parentElement;
    section.classList.toggle('active');
    
    // Close others if open (optional)
    /*
    document.querySelectorAll('.summary-section').forEach(s => {
        if (s !== section) s.classList.remove('active');
    });
    */
}

/**
 * Search functionality within judgment
 */
function searchInJudgment() {
    const query = document.getElementById('judgmentSearch').value.toLowerCase();
    const container = document.getElementById('fullJudgmentText');
    const paragraphs = container.getElementsByTagName('p');
    
    for (let p of paragraphs) {
        if (p.textContent.toLowerCase().includes(query)) {
            p.style.backgroundColor = query ? '#fef3c7' : 'transparent';
            if (query && p.scrollIntoView && paragraphs[0] === p) {
                // p.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        } else {
            p.style.backgroundColor = 'transparent';
        }
    }
}

/**
 * Load popular cases
 */
async function loadPopularCase(key) {
    const caseNames = {
        'kesavananda': 'Kesavananda Bharati v. State of Kerala',
        'maneka': 'Maneka Gandhi v. Union of India',
        'nanavati': 'K.M. Nanavati v. State of Maharashtra',
        'carlill': 'Carlill v. Carbolic Smoke Ball Co'
    };
    
    const name = caseNames[key];
    if (name) {
        document.getElementById('caseName').value = name;
        simplifyCase();
    }
}

/**
 * Save case to local storage
 */
function saveCase() {
    if (!currentCase) return;
    
    const saved = JSON.parse(localStorage.getItem('savedCases') || '[]');
    const newSave = {
        id: currentCase.raw_case.id || Date.now(),
        name: currentCase.raw_case.case_name,
        court: currentCase.raw_case.court,
        citation: currentCase.raw_case.citation,
        date: new Date().toISOString()
    };
    
    // Avoid duplicates
    if (!saved.some(s => s.name === newSave.name)) {
        saved.unshift(newSave);
        localStorage.setItem('savedCases', JSON.stringify(saved.slice(0, 15)));
        showToast('✅ Case saved successfully!');
        loadSavedCases();
    } else {
        showToast('ℹ️ Case already saved');
    }
}

/**
 * Load saved cases from local storage
 */
function loadSavedCases() {
    const saved = JSON.parse(localStorage.getItem('savedCases') || '[]');
    const list = document.getElementById('savedCasesList');
    if (!list) return;

    if (saved.length === 0) {
        list.innerHTML = '<p class="empty-state">No saved cases yet.</p>';
        return;
    }

    list.innerHTML = saved.map(s => `
        <div class="saved-item" onclick="loadFullCaseData('${s.id}')">
            <div class="saved-item-title">${s.name}</div>
            <div class="saved-item-meta">${s.court} • ${s.citation || ''}</div>
        </div>
    `).join('');
}

/**
 * UI Loading state helper
 */
function setLoadingState(isLoading) {
    const btn = document.querySelector('.btn-simplify');
    if (!btn) return;
    
    if (isLoading) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> Processing...';
        showToast('⚡ Analyzing judgment and generating summary...');
    } else {
        btn.disabled = false;
        btn.innerHTML = '<span class="btn-icon">✨</span> Simplify This Case';
    }
}

/**
 * Add current case to notes - Phase 3.4 integration
 */
function addToNotes() {
    if (!currentCase || !currentCase.raw_case) {
        showToast('⚠️ No case loaded to add notes to');
        return;
    }

    const caseId = currentCase.raw_case.id;
    const subjectId = currentCase.raw_case.subject_id || '';
    
    const notesUrl = `./my-notes.html?action=new&case_id=${caseId}${subjectId ? `&subject_id=${subjectId}` : ''}`;
    window.location.href = notesUrl;
}

function showToast(message) {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = message;
    toast.className = 'toast show';
    setTimeout(() => { toast.className = 'toast'; }, 3000);
}
