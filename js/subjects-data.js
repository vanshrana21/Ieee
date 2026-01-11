/**
 * EXAMPLE INTEGRATIONS FOR OTHER PAGES
 * =====================================
 * This file uses the ACTUAL SubjectsDB (from subjects-data.js).
 * It assumes:
 * - subjects-data.js is loaded FIRST
 * - window.SubjectsDB exists
 */

// ===================================================
// 1. CASE SIMPLIFIER PAGE
// ===================================================

function initializeCaseSimplifier() {
    if (!window.SubjectsDB) return console.error('SubjectsDB not loaded');

    populateSubjectDropdown();

    const select = document.getElementById('subjectSelect');
    if (!select) return;

    select.addEventListener('change', (e) => {
        const subjectId = e.target.value;
        if (subjectId) loadCasesForSubject(subjectId);
    });
}

function populateSubjectDropdown() {
    const dropdown = document.getElementById('subjectSelect');
    if (!dropdown) return;

    dropdown.innerHTML = '<option value="">-- Select Subject --</option>';

    const subjects = window.SubjectsDB.getSubjects({ status: 'active' });
    const grouped = {};

    subjects.forEach(s => {
        if (!grouped[s.category]) grouped[s.category] = [];
        grouped[s.category].push(s);
    });

    Object.entries(grouped).forEach(([category, list]) => {
        const optgroup = document.createElement('optgroup');
        optgroup.label = category;

        list.forEach(subject => {
            const option = document.createElement('option');
            option.value = subject.id;
            option.textContent = subject.name;
            optgroup.appendChild(option);
        });

        dropdown.appendChild(optgroup);
    });

    const comingSoon = window.SubjectsDB.getSubjects({ status: 'coming-soon' });
    if (comingSoon.length) {
        const optgroup = document.createElement('optgroup');
        optgroup.label = 'Coming Soon';

        comingSoon.forEach(subject => {
            const option = document.createElement('option');
            option.textContent = `${subject.name} (Coming Soon)`;
            option.disabled = true;
            optgroup.appendChild(option);
        });

        dropdown.appendChild(optgroup);
    }
}

function loadCasesForSubject(subjectId) {
    const subject = window.SubjectsDB.getSubjectById(subjectId);
    const content = window.SubjectsDB.getSubjectContent(subjectId);

    if (!content || !content.cases) {
        document.getElementById('casesContainer').innerHTML =
            `<p>No cases available for ${subject.name}</p>`;
        return;
    }

    renderCasesList(content.cases, subject.name);
}

function renderCasesList(cases, subjectName) {
    const container = document.getElementById('casesContainer');
    if (!container) return;

    container.innerHTML = `
        <h3>Landmark Cases in ${subjectName}</h3>
        <div class="cases-grid">
            ${cases.map((c, i) => `
                <div class="case-card">
                    <strong>${i + 1}. ${c.title}</strong>
                    <p>${c.description}</p>
                    <small>${c.year} • ${c.importance}</small>
                </div>
            `).join('')}
        </div>
    `;
}

// ===================================================
// 2. ANSWER WRITING PRACTICE PAGE
// ===================================================

function initializeAnswerPractice() {
    if (!window.SubjectsDB) return console.error('SubjectsDB not loaded');
    renderPracticeSubjects();
    initializeFilters();
}

function renderPracticeSubjects() {
    const container = document.getElementById('subjectSelectionContainer');
    if (!container) return;

    const categories = window.SubjectsDB.getSubjectsByCategory();

    container.innerHTML = Object.entries(categories).map(([category, subjects]) => `
        <section class="category-section" data-category="${category}">
            <h3>${category}</h3>
            <div class="subject-cards">
                ${subjects.filter(s => s.status === 'active').map(subject => `
                    <div class="subject-card"
                         data-semester="${subject.semester}"
                         onclick="selectSubjectForPractice('${subject.id}')">
                        <span>${subject.icon}</span>
                        <h4>${subject.name}</h4>
                        <small>${getQuestionCount(subject.id)} Questions</small>
                    </div>
                `).join('')}
            </div>
        </section>
    `).join('');
}

function getQuestionCount(subjectId) {
    const content = window.SubjectsDB.getSubjectContent(subjectId);
    return content?.questions?.length || 0;
}

function selectSubjectForPractice(subjectId) {
    const subject = window.SubjectsDB.getSubjectById(subjectId);
    const content = window.SubjectsDB.getSubjectContent(subjectId);

    if (!content || !content.questions) return alert('No questions yet');

    document.getElementById('subjectSelectionContainer')?.classList.add('hidden');
    showPracticeArea(subject, content.questions);
}

function showPracticeArea(subject, questions) {
    const container = document.getElementById('practiceArea');
    if (!container) return;

    container.classList.remove('hidden');
    container.innerHTML = `
        <h2>${subject.name} – Practice</h2>
        ${questions.map((q, i) => `
            <div class="question-card">
                <strong>Q${i + 1}. ${q.title}</strong>
                <small>${q.marks} Marks • ${q.difficulty}</small>
            </div>
        `).join('')}
    `;
}

function initializeFilters() {
    const categoryFilter = document.getElementById('categoryFilter');
    const semesterFilter = document.getElementById('semesterFilter');

    if (categoryFilter) categoryFilter.addEventListener('change', filterSubjects);
    if (semesterFilter) semesterFilter.addEventListener('change', filterSubjects);
}

function filterSubjects() {
    const category = document.getElementById('categoryFilter')?.value;
    const semester = document.getElementById('semesterFilter')?.value;

    document.querySelectorAll('.category-section').forEach(section => {
        const matchCategory = !category || section.dataset.category === category;
        section.style.display = matchCategory ? 'block' : 'none';

        section.querySelectorAll('.subject-card').forEach(card => {
            const matchSemester =
                !semester ||
                card.dataset.semester === semester ||
                card.dataset.semester === 'Multiple';
            card.style.display = matchSemester ? 'block' : 'none';
        });
    });
}

// ===================================================
// 3. MY NOTES PAGE
// ===================================================

function initializeNotesPage() {
    if (!window.SubjectsDB) return console.error('SubjectsDB not loaded');
    renderSubjectSidebar();
}

function renderSubjectSidebar() {
    const sidebar = document.getElementById('subjectSidebar');
    if (!sidebar) return;

    const categories = window.SubjectsDB.getSubjectsByCategory();

    sidebar.innerHTML = Object.entries(categories).map(([category, subjects]) => `
        <div class="category-group">
            <h4>${category}</h4>
            ${subjects.map(subject => `
                <div class="subject-item ${subject.status}">
                    ${subject.icon} ${subject.name}
                </div>
            `).join('')}
        </div>
    `).join('');
}

// ===================================================
// PAGE BOOTSTRAP
// ===================================================

document.addEventListener('DOMContentLoaded', () => {
    const page = document.body.dataset.page;

    if (page === 'case-simplifier') initializeCaseSimplifier();
    if (page === 'answer-practice') initializeAnswerPractice();
    if (page === 'my-notes') initializeNotesPage();

    console.log('✅ SubjectsDB integration loaded');
});
