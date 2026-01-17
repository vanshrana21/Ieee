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
 * Main Simplify Case function
 * Searches for case, fetches full data, and renders output
 */
async function simplifyCase() {
    const caseName = document.getElementById('caseName').value.trim();
    if (!caseName) {
        showToast('⚠️ Please enter a case name');
        return;
    }

    // Show loading state
    setLoadingState(true);

    try {
        // Step 1: Search for the case
        // We search curriculum first for better quality
        const searchResponse = await api.get(`/api/search/content?q=${encodeURIComponent(caseName)}&content_types=cases`);
        let cases = searchResponse.results || [];

        // If not found in curriculum, try CourtListener
        if (cases.length === 0) {
            const publicSearch = await api.post('/api/search/search', { query: caseName });
            cases = publicSearch.results || [];
        }

        if (cases.length === 0) {
            showToast('❌ No cases found matching that name');
            setLoadingState(false);
            return;
        }

        // If multiple cases found, for simplicity we'll take the first best match
        // In a real app, we'd show a selection list
        const targetCase = cases[0];
        await loadFullCaseData(targetCase.id);

    } catch (error) {
        console.error('Error simplifying case:', error);
        showToast('❌ Failed to process case: ' + (error.message || 'Unknown error'));
        setLoadingState(false);
    }
}

/**
 * Fetch and display full case data
 */
async function loadFullCaseData(caseId) {
    try {
        setLoadingState(true);
        
        // Call the new Phase 3.2 API
        const data = await api.get(`/api/cases/${caseId}/full`);
        
        if (!data || !data.case) {
            throw new Error('Invalid case data received');
        }

        currentCase = data;
        displayCaseOutput(data);
        
    } catch (error) {
        console.error('Error loading full case:', error);
        showToast('❌ Error fetching judgment details');
    } finally {
        setLoadingState(false);
    }
}

/**
 * Render Case Output to UI
 */
function displayCaseOutput(data) {
    const { case: caseMeta, full_text, summary, is_curriculum_case } = data;
    
    // Switch views
    document.getElementById('inputSection').classList.add('hidden');
    document.getElementById('searchHeader').classList.add('hidden');
    document.getElementById('outputSection').classList.remove('hidden');

    // Update Header Information
    document.getElementById('outputCaseName').textContent = caseMeta.title;
    document.getElementById('outputCourt').textContent = caseMeta.court;
    document.getElementById('outputYear').textContent = caseMeta.year;
    
    // Syllabus Warning
    const warningBadge = document.getElementById('syllabusWarning');
    if (is_curriculum_case) {
        warningBadge.classList.add('hidden');
    } else {
        warningBadge.classList.remove('hidden');
    }

    // Render Full Judgment
    const judgmentContainer = document.getElementById('fullJudgmentText');
    judgmentContainer.innerHTML = formatLegalText(full_text);

    // Render Summary Sections
    renderSummarySection('factsText', summary.facts);
    renderSummarySection('issuesText', summary.issues);
    renderSummarySection('argumentsText', summary.arguments);
    renderSummarySection('judgmentText', summary.judgment);
    renderSummarySection('ratioText', summary.ratio);
    renderSummarySection('significanceText', summary.exam_significance);

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
        id: currentCase.case.id || Date.now(),
        name: currentCase.case.title,
        court: currentCase.case.court,
        year: currentCase.case.year,
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
 * Placeholder functions
 */
function addToNotes() {
    showToast('📝 Integration with My Notes coming in Phase 4!');
}

function showToast(message) {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = message;
    toast.className = 'toast show';
    setTimeout(() => { toast.className = 'toast'; }, 3000);
}
