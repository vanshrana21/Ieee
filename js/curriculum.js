(function() {
    'use strict';

    const API_BASE = window.__API_BASE__ || (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' ? `${window.location.protocol}//${window.location.hostname}:8000` : '');

    const state = {
        semesters: [],
        currentSemester: null,
        subjects: [],
        currentSubject: null,
        modules: [],
        stats: {
            totalSemesters: 0,
            totalSubjects: 0,
            totalModules: 0
        }
    };

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function formatSubjectType(type) {
        const typeMap = {
            'core': 'Core',
            'major': 'Major',
            'minor_i': 'Minor I',
            'minor_ii': 'Minor II',
            'optional': 'Optional',
            'clinical': 'Clinical',
            'foundation': 'Foundation'
        };
        return typeMap[type] || type;
    }

    function showView(viewId) {
        console.log(`Switching to view: ${viewId}`);
        document.querySelectorAll('.view-section').forEach(section => {
            section.classList.add('hidden');
        });
        const view = document.getElementById(viewId);
        if (view) {
            view.classList.remove('hidden');
        } else {
            console.error(`View not found: ${viewId}`);
        }
    }

    async function fetchSemesters() {
        console.log('Fetching semesters...');
        const grid = document.getElementById('semesterGrid');
        if (!grid) return;
        
        grid.innerHTML = '<div class="loading-placeholder">Loading semesters...</div>';

        try {
            const url = `${API_BASE}/api/ba-llb/semesters`;
            console.log(`GET ${url}`);
            const response = await fetch(url);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            
            const data = await response.json();
            console.log('Semesters data received:', data);
            state.semesters = data.semesters || [];

            let totalSubjects = 0;
            let totalModules = 0;
            state.semesters.forEach(sem => {
                totalSubjects += sem.subject_count || 0;
                totalModules += sem.total_modules || 0;
            });
            
            state.stats.totalSemesters = state.semesters.length;
            state.stats.totalSubjects = totalSubjects;
            state.stats.totalModules = totalModules;
            
            updateStatsDisplay();
            renderSemesters();
        } catch (error) {
            console.error('Error fetching semesters:', error);
            grid.innerHTML = `
                <div class="error-state">
                    <h3>Failed to load semesters</h3>
                    <p>${escapeHtml(error.message)}</p>
                    <button onclick="window.curriculumApp.init()">Retry</button>
                </div>
            `;
        }
    }

    function updateStatsDisplay() {
        const elSem = document.getElementById('totalSemesters');
        const elSub = document.getElementById('totalSubjects');
        const elMod = document.getElementById('totalModules');
        
        if (elSem) elSem.textContent = state.stats.totalSemesters;
        if (elSub) elSub.textContent = state.stats.totalSubjects;
        if (elMod) elMod.textContent = state.stats.totalModules;
    }

    function renderSemesters() {
        const grid = document.getElementById('semesterGrid');
        if (!grid) return;
        
        if (state.semesters.length === 0) {
            grid.innerHTML = `
                <div class="empty-state">
                    <h3>No Semesters Found</h3>
                    <p>The curriculum data has not been seeded yet. Please run the seed script.</p>
                </div>
            `;
            return;
        }

        grid.innerHTML = state.semesters.map(semester => `
            <div class="semester-card" onclick="window.curriculumApp.selectSemester(${semester.semester_number})">
                <div class="semester-number">${semester.semester_number}</div>
                <div class="semester-name">${escapeHtml(semester.name)}</div>
                <div class="semester-stats">
                    <span class="semester-stat">${semester.subject_count} Subjects</span>
                    <span class="semester-stat">${semester.total_modules} Units</span>
                </div>
            </div>
        `).join('');
    }

    async function selectSemester(semesterNumber) {
        console.log(`Selecting semester: ${semesterNumber}`);
        state.currentSemester = semesterNumber;
        
        const elCrumb = document.getElementById('currentSemesterBreadcrumb');
        const elTitle = document.getElementById('semesterTitle');
        const elBread = document.getElementById('semesterBreadcrumb');
        
        if (elCrumb) elCrumb.textContent = `Semester ${semesterNumber}`;
        if (elTitle) elTitle.textContent = `Semester ${semesterNumber} - Subjects`;
        if (elBread) elBread.textContent = `Semester ${semesterNumber}`;
        
        const grid = document.getElementById('subjectGrid');
        if (grid) {
            grid.innerHTML = '<div class="loading-placeholder">Loading subjects...</div>';
        }
        
        showView('subjectView');

        try {
            const url = `${API_BASE}/api/ba-llb/semesters/${semesterNumber}/subjects`;
            console.log(`GET ${url}`);
            const response = await fetch(url);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            
            const data = await response.json();
            console.log('Subjects data received:', data);
            
            // Critical Fix: Ensure we extract the subjects array correctly
            state.subjects = data.subjects || [];
            console.log(`State updated with ${state.subjects.length} subjects`);
            
            renderSubjects();
        } catch (error) {
            console.error('Error fetching subjects:', error);
            if (grid) {
                grid.innerHTML = `
                    <div class="error-state">
                        <h3>Failed to load subjects</h3>
                        <p>${escapeHtml(error.message)}</p>
                        <button onclick="window.curriculumApp.selectSemester(${semesterNumber})">Retry</button>
                    </div>
                `;
            }
        }
    }

    function renderSubjects() {
        console.log('Rendering subjects, count:', state.subjects.length);
        const grid = document.getElementById('subjectGrid');
        if (!grid) return;
        
        if (!state.subjects || state.subjects.length === 0) {
            grid.innerHTML = `
                <div class="empty-state">
                    <h3>No Subjects Found</h3>
                    <p>No subjects have been added to this semester yet.</p>
                </div>
            `;
            return;
        }

        grid.innerHTML = state.subjects.map(subject => {
            const isFoundation = subject.is_foundation || subject.subject_type === 'foundation' || subject.name.includes('Foundation Course');
            const typeBadgeClass = isFoundation ? 'foundation' : (subject.subject_type || 'core');
            const typeLabel = isFoundation ? 'Foundation' : formatSubjectType(subject.subject_type);

            return `
                <div class="subject-card" onclick="window.curriculumApp.selectSubject(${subject.id})">
                    <span class="subject-type-badge ${typeBadgeClass}">${typeLabel}</span>
                    <div class="subject-name">${escapeHtml(subject.name)}</div>
                    <div class="subject-code">${escapeHtml(subject.code)}</div>
                    <div class="subject-footer">
                        <div class="module-count">
                            <span class="module-count-number">${subject.module_count || 0}</span>
                            Unit${subject.module_count !== 1 ? 's' : ''}
                        </div>
                        <button class="view-modules-btn" onclick="event.stopPropagation(); window.curriculumApp.selectSubject(${subject.id})">
                            View Units
                        </button>
                    </div>
                </div>
            `;
        }).join('');
    }

    async function selectSubject(subjectId) {
        const subject = state.subjects.find(s => s.id === subjectId);
        if (!subject) return;
        
        state.currentSubject = subject;
        
        document.getElementById('currentSubjectBreadcrumb').textContent = subject.name;
        document.getElementById('subjectTitle').textContent = subject.name;
        document.getElementById('subjectMeta').textContent = `${formatSubjectType(subject.subject_type)} Subject | Code: ${subject.code}`;
        
        const list = document.getElementById('moduleList');
        list.innerHTML = '<div class="loading-placeholder">Loading modules...</div>';
        
        showView('moduleView');

        try {
            const response = await fetch(`${API_BASE}/api/ba-llb/subjects/${subjectId}/modules`);
            if (!response.ok) throw new Error('Failed to fetch modules');
            
            const data = await response.json();
            state.modules = data.modules || [];
            
            renderModules();
        } catch (error) {
            console.error('Error fetching modules:', error);
            list.innerHTML = `
                <div class="error-state">
                    <h3>Failed to load modules</h3>
                    <p>${escapeHtml(error.message)}</p>
                    <button onclick="window.curriculumApp.selectSubject(${subjectId})">Retry</button>
                </div>
            `;
        }
    }

    function renderModules() {
        const list = document.getElementById('moduleList');
        
        if (state.modules.length === 0) {
            list.innerHTML = `
                <div class="empty-state">
                    <h3>No Modules Found</h3>
                    <p>No modules have been added to this subject yet.</p>
                </div>
            `;
            return;
        }

        list.innerHTML = state.modules.map(module => `
            <div class="module-item" onclick="window.curriculumApp.openModule(${module.id})">
                <div class="module-order">${module.sequence_order}</div>
                <div class="module-title">${escapeHtml(module.title)}</div>
                <div class="module-arrow">→</div>
            </div>
        `).join('');
    }

    function openModule(moduleId) {
        console.log('Opening module:', moduleId);
    }

    function backToSemesters() {
        state.currentSemester = null;
        state.subjects = [];
        showView('semesterSelection');
    }

    function backToSubjects() {
        state.currentSubject = null;
        state.modules = [];
        showView('subjectView');
    }

    function init() {
        fetchSemesters();
    }

    window.curriculumApp = {
        init,
        selectSemester,
        selectSubject,
        openModule,
        backToSemesters,
        backToSubjects
    };

    window.backToSemesters = backToSemesters;
    window.backToSubjects = backToSubjects;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
