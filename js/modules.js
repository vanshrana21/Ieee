(function() {
    'use strict';

    const API_BASE = window.__API_BASE__ || (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' ? `${window.location.protocol}//${window.location.hostname}:8000` : '');

    const state = {
        subjectId: null,
        subjectName: '',
        courseName: '',
        semester: 1,
        modules: [],
        isLoading: true
    };

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function toRoman(num) {
        const roman = { M: 1000, CM: 900, D: 500, CD: 400, C: 100, XC: 90, L: 50, XL: 40, X: 10, IX: 9, V: 5, IV: 4, I: 1 };
        let str = '';
        for (let i in roman) {
            while (num >= roman[i]) {
                str += i;
                num -= roman[i];
            }
        }
        return str;
    }

    async function fetchJson(url, opts = {}) {
        const token = window.auth?.getToken?.() || localStorage.getItem('access_token');
        
        if (!token) {
            window.location.href = 'login.html';
            throw new Error('Not authenticated');
        }
        
        const headers = { ...opts.headers };
        headers['Authorization'] = `Bearer ${token}`;
        headers['Content-Type'] = headers['Content-Type'] || 'application/json';

        const resp = await fetch(url, { ...opts, headers });
        
        if (resp.status === 401) {
            localStorage.removeItem('access_token');
            window.location.href = 'login.html';
            throw new Error('Session expired');
        }
        
        const text = await resp.text();
        let json;
        try { json = text ? JSON.parse(text) : null; } catch { json = null; }
        if (!resp.ok) throw new Error(json?.detail || json?.error || resp.statusText);
        return json;
    }

    function getModuleStatus(module, isBALLB) {
        if (isBALLB) return 'not-started';
        
        const totalContents = module.total_contents || 0;
        const completedContents = module.completed_contents || 0;
        
        if (totalContents === 0) return 'not-started';
        if (module.is_completed || completedContents >= totalContents) return 'completed';
        if (completedContents > 0) return 'in-progress';
        return 'not-started';
    }

    function getStatusLabel(status) {
        const labels = {
            'not-started': 'Not Started',
            'in-progress': 'In Progress',
            'completed': 'Completed'
        };
        return labels[status] || 'Not Started';
    }

    function getCtaText(status) {
        if (status === 'completed') return 'Review';
        if (status === 'in-progress') return 'Continue';
        return 'Start';
    }

    async function loadModules() {
        const modulesList = document.getElementById('modulesList');
        if (!modulesList) return;

        try {
            const profile = await fetchJson(`${API_BASE}/api/student/academic-profile`).catch(() => ({}));
            state.courseName = profile.course_name || '';
            state.semester = profile.current_semester || 1;

            const isBALLB = state.courseName && (
                state.courseName.toUpperCase().includes('BA LLB') || 
                state.courseName.toUpperCase().includes('BA.LLB') ||
                state.courseName.toUpperCase().includes('BACHELOR OF ARTS')
            );

            let response;
            if (isBALLB) {
                response = await fetchJson(`${API_BASE}/api/ba-llb/subjects/${state.subjectId}/modules`);
                const unitsArray = response.units || response.modules || [];
                state.modules = unitsArray.map(m => ({
                    ...m,
                    is_unit: true,
                    total_contents: 0
                }));
                state.subjectName = response.subject?.name || response.subject_name || 'Subject';
            } else {
                response = await fetchJson(`${API_BASE}/api/student/subject/${state.subjectId}/modules`);
                const unitsArray = response.units || response.modules || [];
                state.modules = unitsArray.map(m => ({
                    ...m,
                    is_unit: false,
                    total_contents: m.total_contents || 0
                }));
                state.subjectName = response.subject_name || 'Subject';
            }

            state.isLoading = false;
            
            document.getElementById('subjectTitle').textContent = state.subjectName;
            document.getElementById('semesterBadge').textContent = `Semester ${state.semester}`;
            
            const moduleCount = state.modules.length;
            const unitType = isBALLB ? 'unit' : 'module';
            document.getElementById('headerSubtitle').textContent = 
                moduleCount > 0 
                    ? `${moduleCount} ${unitType}${moduleCount !== 1 ? 's' : ''} available`
                    : 'Select a module to begin learning';
            
            renderModules(isBALLB);
        } catch (error) {
            console.error('Failed to load modules:', error);
            modulesList.innerHTML = `
                <div class="error-state">
                    <p>Failed to load modules. ${escapeHtml(error.message)}</p>
                    <button class="retry-btn" onclick="window.location.reload()">Retry</button>
                </div>
            `;
        }
    }

    function renderModules(isBALLB = false) {
        const modulesList = document.getElementById('modulesList');
        if (!modulesList) return;

        if (state.modules.length === 0) {
            modulesList.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                            <line x1="9" y1="7" x2="15" y2="7"/>
                            <line x1="9" y1="11" x2="15" y2="11"/>
                        </svg>
                    </div>
                    <h3 class="empty-title">Modules are being prepared</h3>
                    <p class="empty-subtitle">Content for this subject is currently being developed. You will be notified once learning materials are available.</p>
                </div>
            `;
            return;
        }

        const unitType = isBALLB ? 'Unit' : 'Module';

        modulesList.innerHTML = state.modules.map((module, index) => {
            const status = getModuleStatus(module, isBALLB);
            const statusLabel = getStatusLabel(status);
            const ctaText = getCtaText(status);
            const hasContent = true;
            
            const rawOrder = module.sequence_order || module.order_index || (index + 1);
            const moduleNumber = isBALLB ? toRoman(rawOrder) : rawOrder;
            const moduleId = module.module_id || module.id;
            
            const progressPercent = module.total_contents > 0 
                ? Math.round((module.completed_contents / module.total_contents) * 100) 
                : 0;

            const description = module.description || '';
            const truncatedDesc = description.length > 120 
                ? description.substring(0, 120) + '...' 
                : description;

            return `
                <div class="module-card ${!hasContent ? 'no-content' : ''}" onclick="window.modulesPage.navigateToModule(${moduleId}, ${isBALLB})">
                    <div class="module-header">
                        <div class="module-info">
                            <p class="module-number">${unitType} ${moduleNumber}</p>
                            <h3 class="module-title">${escapeHtml(module.title)}</h3>
                            ${truncatedDesc ? `<p class="module-description">${escapeHtml(truncatedDesc)}</p>` : ''}
                        </div>
                        <div class="module-actions">
                            <span class="status-badge ${status}">${statusLabel}</span>
                            ${hasContent ? `
                                <button class="module-cta ${status === 'completed' ? 'secondary' : ''}" 
                                        onclick="event.stopPropagation(); window.modulesPage.navigateToModule(${moduleId}, ${isBALLB})">
                                    ${ctaText}
                                </button>
                            ` : ''}
                        </div>
                    </div>
                    ${(!isBALLB && hasContent && module.total_contents > 0) ? `
                        <div class="module-progress">
                            <div class="progress-bar">
                                <div class="progress-fill ${status === 'completed' ? 'completed' : ''}" style="width: ${progressPercent}%"></div>
                            </div>
                            <p class="progress-text">${module.completed_contents || 0} of ${module.total_contents} lessons completed</p>
                        </div>
                    ` : ''}
                </div>
            `;
        }).join('');
    }

    async function navigateToModule(moduleId, isBALLB = false) {
        if (isBALLB) {
            window.location.href = `module-content.html?module_id=${moduleId}&subject_id=${state.subjectId}&course=ba-llb`;
            return;
        }

        try {
            const resumeData = await fetchJson(`${API_BASE}/api/student/modules/${moduleId}/resume`);
            
            if (resumeData.next_content_id) {
                window.location.href = `learn-content.html?id=${resumeData.next_content_id}&module_id=${moduleId}&subject_id=${state.subjectId}`;
            } else {
                window.location.href = `module-content.html?module_id=${moduleId}&subject_id=${state.subjectId}`;
            }
        } catch (error) {
            console.error('Failed to get module resume:', error);
            window.location.href = `module-content.html?module_id=${moduleId}&subject_id=${state.subjectId}`;
        }
    }

    function init() {
        const urlParams = new URLSearchParams(window.location.search);
        state.subjectId = urlParams.get('subject_id');

        if (!state.subjectId) {
            window.location.href = 'dashboard-student.html';
            return;
        }

        loadModules();
    }

    window.modulesPage = {
        navigateToModule
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
