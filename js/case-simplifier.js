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
    const { raw_case, ai_structured_summary } = data;
    
    // Switch views
    document.getElementById('inputSection').classList.add('hidden');
    document.getElementById('searchHeader').classList.add('hidden');
    document.getElementById('outputSection').classList.remove('hidden');

    // Update Header Information
    document.getElementById('outputCaseName').textContent = raw_case.case_name || 'Judgment';
    document.getElementById('outputCourt').textContent = raw_case.court || 'Court';
    document.getElementById('outputYear').textContent = raw_case.year || '';
    
    // Importance badge (static for now)
    document.getElementById('outputImportance').textContent = 'Authoritative Source';

    // Render Full Judgment (Left Panel - Authoritative)
    const judgmentContainer = document.getElementById('fullJudgmentText');
    const sections = [
        { title: 'Facts', content: raw_case.facts },
        { title: 'Issues', content: raw_case.issues },
        { title: 'Arguments', content: raw_case.arguments },
        { title: 'Judgment', content: raw_case.judgment },
        { title: 'Ratio Decidendi', content: raw_case.ratio }
    ];
    
    judgmentContainer.innerHTML = sections
        .filter(s => s.content && s.content.trim())
        .map(s => `<h4>${s.title}</h4><div>${formatLegalText(s.content)}</div>`)
        .join('<hr style="margin: 20px 0; opacity: 0.1;">');

    // Render AI Summary Sections (Right Panel - Assistive)
    if (ai_structured_summary) {
        renderSummarySection('factsText', ai_structured_summary.facts);
        renderSummarySection('issuesText', ai_structured_summary.issues);
        renderSummarySection('argumentsText', "Arguments omitted for concise summary.");
        renderSummarySection('judgmentText', ai_structured_summary.judgment);
        renderSummarySection('ratioText', ai_structured_summary.ratio_decidendi);
        renderSummarySection('significanceText', "Focus on the ratio decidendi for exam preparation.");
    } else {
        // Graceful degradation for AI failure
        const summaryFields = ['factsText', 'issuesText', 'argumentsText', 'judgmentText', 'ratioText', 'significanceText'];
        summaryFields.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.innerHTML = '<p class="text-muted">Summary currently unavailable. Please refer to the full judgment.</p>';
        });
        showToast('ℹ️ AI Summary unavailable, showing full judgment');
    }

    // Scroll to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

/**
 * Helper to render summary sections with fallback
 */
function renderSummarySection(elementId, content) {
    const element = document.getElementById(elementId);
    if (!element) return;
    
    if (!content || content === "N/A" || content.includes("Not found")) {
        element.innerHTML = '<p class="text-muted">Information not available in judgment text.</p>';
    } else {
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
        year: currentCase.raw_case.year,
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
            <div class="saved-item-meta">${s.court} • ${s.year}</div>
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
