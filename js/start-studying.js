/**
 * START STUDYING PAGE - UPDATED FOR DYNAMIC SUBJECT LOADING
 * ===========================================================
 * This file now uses the centralized SubjectsDB for all subject data.
 * Subjects are rendered dynamically from subjects-data.js
 */

// Import note: In your HTML, include subjects-data.js BEFORE this file:
// <script src="../js/subjects-data.js"></script>
// <script src="../js/start-studying.js"></script>

// Global state
let currentSubject = '';
let currentMode = '';

// ===================================================
// INITIALIZATION
// ===================================================

document.addEventListener('DOMContentLoaded', function() {
    // Ensure subject selection is visible
    const subjectSelection = document.getElementById('subjectSelection');
    if (subjectSelection) {
        subjectSelection.classList.remove('hidden');
    }
    
    // Render subjects
    renderSubjectSelection();
    
    // Hide study hub initially
    const studyHub = document.getElementById('studyHub');
    if (studyHub) {
        studyHub.classList.add('hidden');
    }
});

// ===================================================
// SUBJECT SELECTION RENDERING
// ===================================================

function renderSubjectSelection() {
    const subjectGrid = document.querySelector('.subject-grid');
    if (!subjectGrid) {
        console.error('Subject grid not found');
        return;
    }
    
    // Check if SubjectsDB is loaded
    if (!window.SubjectsDB) {
        console.error('SubjectsDB not loaded');
        subjectGrid.innerHTML = '<div style="grid-column: 1 / -1; text-align: center; padding: 3rem; color: red;">Error: Subject database not loaded. Check console.</div>';
        return;
    }
    
    // Clear loading message
    subjectGrid.innerHTML = '';
    
    // Get subjects grouped by category
    const categories = window.SubjectsDB.getSubjectsByCategory();
    
    // Render each category
    Object.entries(categories).forEach(([categoryName, subjects]) => {
        if (subjects.length === 0) return;
        
        const categoryHeader = document.createElement('div');
        categoryHeader.className = 'category-header';
        categoryHeader.innerHTML = `
            <h2>${categoryName} Subjects</h2>
            <p>${getCategoryDescription(categoryName)}</p>
        `;
        subjectGrid.appendChild(categoryHeader);
        
        subjects.forEach(subject => {
            const card = createSubjectCard(subject);
            subjectGrid.appendChild(card);
        });
    });
}

function getCategoryDescription(category) {
    const descriptions = {
        'Foundation': 'Foundational courses for early semesters',
        'Core': 'Essential substantive law subjects',
        'Procedural': 'Practical and procedural law courses',
        'Elective': 'Advanced and specialized subjects'
    };
    return descriptions[category] || '';
}

function createSubjectCard(subject) {
    const card = document.createElement('div');
    card.className = `subject-card ${subject.status === 'coming-soon' ? 'disabled' : ''}`;
    
    if (subject.status === 'active') {
        card.onclick = () => selectSubject(subject.id);
    }
    
    card.innerHTML = `
        <div class="subject-icon">${subject.icon}</div>
        <h3>${subject.name}</h3>
        <p>${subject.description}</p>
        <div class="card-footer">
            ${subject.status === 'active' ? `
                <span class="topic-count">${subject.topics} Topics</span>
                <span class="case-count">${subject.cases} Cases</span>
            ` : `
                <span class="coming-soon-badge">Coming Soon</span>
            `}
        </div>
        ${subject.semester !== 'Multiple' ? `
            <div class="semester-badge">Semester ${subject.semester}</div>
        ` : ''}
    `;
    
    return card;
}

// ===================================================
// NAVIGATION FUNCTIONS
// ===================================================

function goBackToDashboard() {
    window.location.href = 'dashboard-student.html';
}

function selectSubject(subjectId) {
    currentSubject = subjectId;
    const subject = window.SubjectsDB.getSubjectById(subjectId);
    
    if (!subject) {
        console.error('Subject not found:', subjectId);
        return;
    }
    
    // Hide subject selection
    document.getElementById('subjectSelection').classList.add('hidden');
    
    // Show study hub
    const studyHub = document.getElementById('studyHub');
    studyHub.classList.remove('hidden');
    
    // Update subject name
    document.getElementById('currentSubject').textContent = subject.name;
    document.getElementById('subjectTitle').textContent = subject.name;
    
    // Hide content area
    document.getElementById('contentArea').classList.add('hidden');
}

function backToSubjects() {
    // Hide study hub
    document.getElementById('studyHub').classList.add('hidden');
    
    // Show subject selection
    document.getElementById('subjectSelection').classList.remove('hidden');
    
    // Reset state
    currentSubject = '';
    currentMode = '';
}

function openMode(mode) {
    currentMode = mode;
    
    // Show content area
    const contentArea = document.getElementById('contentArea');
    contentArea.classList.remove('hidden');
    
    // Update title and load content
    const titles = {
        concepts: 'Learn Concepts',
        cases: 'Landmark Cases',
        practice: 'Answer Writing Practice',
        notes: 'My Notes'
    };
    
    document.getElementById('contentTitle').textContent = titles[mode];
    
    // Load appropriate content
    loadContent(mode);
    
    // Scroll to content
    contentArea.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function backToModes() {
    document.getElementById('contentArea').classList.add('hidden');
    currentMode = '';
}

// ===================================================
// CONTENT LOADING
// ===================================================

function loadContent(mode) {
    const contentBody = document.getElementById('contentBody');
    const subject = window.SubjectsDB.getSubjectById(currentSubject);
    const content = window.SubjectsDB.getSubjectContent(currentSubject);
    
    // If no content available (coming soon subjects)
    if (!content) {
        contentBody.innerHTML = `
            <div class="coming-soon-message">
                <div class="icon">🚧</div>
                <h3>Content Coming Soon</h3>
                <p>We're currently developing comprehensive content for <strong>${subject.name}</strong>.</p>
                <p>Check back soon for concepts, cases, and practice questions!</p>
            </div>
        `;
        return;
    }
    
    // Load content based on mode
    if (mode === 'concepts') {
        renderConcepts(contentBody, content.concepts);
    } else if (mode === 'cases') {
        renderCases(contentBody, content.cases);
    } else if (mode === 'practice') {
        renderQuestions(contentBody, content.questions);
    } else if (mode === 'notes') {
        renderNotesEditor(contentBody, subject);
    }
}

function renderConcepts(container, concepts) {
    container.innerHTML = `
        <div class="topic-list">
            ${concepts.map((topic, index) => `
                <div class="topic-item">
                    <h4>${index + 1}. ${topic.title}</h4>
                    <p><strong>Overview:</strong> ${topic.description}</p>
                    <p><strong>Key Points:</strong> ${topic.details}</p>
                </div>
            `).join('')}
        </div>
    `;
}

function renderCases(container, cases) {
    container.innerHTML = `
        <div class="case-list">
            ${cases.map((caseItem, index) => `
                <div class="case-item">
                    <h4>${index + 1}. ${caseItem.title}</h4>
                    <div class="case-meta">
                        <span class="meta-tag">Year: ${caseItem.year}</span>
                        <span class="meta-tag">${caseItem.importance}</span>
                    </div>
                    <p><strong>Facts & Issue:</strong> ${caseItem.description}</p>
                    <p><strong>Ratio Decidendi:</strong> ${caseItem.ratio}</p>
                </div>
            `).join('')}
        </div>
    `;
}

function renderQuestions(container, questions) {
    container.innerHTML = `
        <div class="question-list">
            ${questions.map((question, index) => `
                <div class="question-item">
                    <h4>Q${index + 1}. ${question.title}</h4>
                    <div class="question-meta">
                        <span class="meta-tag">${question.marks} Marks</span>
                        <span class="meta-tag">Difficulty: ${question.difficulty}</span>
                    </div>
                    <p><strong>💡 Hint:</strong> ${question.hint}</p>
                </div>
            `).join('')}
        </div>
    `;
}

function renderNotesEditor(container, subject) {
    container.innerHTML = `
        <div class="notes-editor">
            <h3>📝 Create Your Notes for ${subject.name}</h3>
            <p style="color: #64748b; margin-bottom: 1rem;">Write your personal notes, summaries, and key points here. They will be saved locally.</p>
            <textarea placeholder="Start typing your notes here...

Example:
- Important cases to remember
- Key principles
- Exam tips
- Memory tricks"></textarea>
            <button class="btn-save" onclick="saveNotes()">💾 Save Notes</button>
        </div>
    `;
}

// ===================================================
// NOTES FUNCTIONALITY
// ===================================================

function saveNotes() {
    const textarea = document.querySelector('.notes-editor textarea');
    const notes = textarea.value;
    
    if (notes.trim()) {
        // In a real app, this would save to localStorage or backend
        // For demo, just show confirmation
        const btn = document.querySelector('.btn-save');
        const originalText = btn.textContent;
        btn.textContent = '✅ Saved!';
        btn.style.background = '#10b981';
        
        setTimeout(() => {
            btn.textContent = originalText;
            btn.style.background = '#667eea';
        }, 2000);
    }
}

// ===================================================
// SEARCH FUNCTIONALITY (Optional Enhancement)
// ===================================================

function initializeSearch() {
    const searchInput = document.getElementById('subjectSearch');
    if (!searchInput) return;
    
    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.trim();
        
        if (query.length === 0) {
            renderSubjectSelection();
            return;
        }
        
        const results = window.SubjectsDB.searchSubjects(query);
        renderSearchResults(results);
    });
}

function renderSearchResults(results) {
    const subjectGrid = document.querySelector('.subject-grid');
    if (!subjectGrid) return;
    
    subjectGrid.innerHTML = '';
    
    if (results.length === 0) {
        subjectGrid.innerHTML = `
            <div class="no-results">
                <p>No subjects found matching your search.</p>
            </div>
        `;
        return;
    }
    
    results.forEach(subject => {
        const card = createSubjectCard(subject);
        subjectGrid.appendChild(card);
    });
}