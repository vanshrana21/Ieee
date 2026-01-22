/**
 * modules.js
 * Phase 4: Subject Modules List with Progress
 */

(function() {
    'use strict';

    const state = {
        subjectId: null,
        subjectName: '',
        courseName: '',
        modules: [],
        isLoading: true
    };

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

    async function loadModules() {
        const modulesList = document.getElementById('modulesList');
        if (!modulesList) return;

        try {
            // Step 1: Fetch academic profile to detect BA LLB
            const profile = await api.get('/api/student/academic-profile').catch(() => ({}));
            state.courseName = profile.course_name || '';

            const isBALLB = state.courseName && (
                state.courseName.toUpperCase().includes('BA LLB') || 
                state.courseName.toUpperCase().includes('BA.LLB') ||
                state.courseName.toUpperCase().includes('BACHELOR OF ARTS')
            );

            let response;
            if (isBALLB) {
                console.log('BA LLB detected in modules. Fetching units...');
                response = await api.get(`/api/ba-llb/subjects/${state.subjectId}/modules`);
                state.modules = response.modules.map(m => ({
                    ...m,
                    is_unit: true,
                    total_contents: 0 // BA LLB currently uses direct module content or placeholder
                }));
                state.subjectName = response.subject.name;
            } else {
                response = await api.getSubjectModules(state.subjectId);
                state.modules = response.modules;
                state.subjectName = response.subject_name;
            }

            state.isLoading = false;
            
            document.getElementById('subjectTitle').textContent = state.subjectName;
            
            const unitType = isBALLB ? 'Unit' : 'Module';
            document.getElementById('subjectSubtitle').textContent = 
                `${state.modules.length} ${unitType}${state.modules.length !== 1 ? 's' : ''} • Select a ${unitType.toLowerCase()} to start learning`;
            
            renderModules(isBALLB);
        } catch (error) {
            console.error('Failed to load modules:', error);
            modulesList.innerHTML = `
                <div class="error-state" style="text-align: center; padding: 40px;">
                    <div style="font-size: 48px; margin-bottom: 16px;">⚠️</div>
                    <p style="color: #ef4444; margin-bottom: 16px;">Failed to load modules. ${escapeHtml(error.message)}</p>
                    <button onclick="window.location.reload()" style="background: #0066ff; color: white; border: none; padding: 12px 24px; border-radius: 8px; cursor: pointer; font-weight: 600;">Retry</button>
                </div>
            `;
        }
    }

    function renderModules(isBALLB = false) {
        const modulesList = document.getElementById('modulesList');
        if (!modulesList) return;

        if (state.modules.length === 0) {
            const unitType = isBALLB ? 'Units' : 'Modules';
            modulesList.innerHTML = `
                <div class="empty-state" style="text-align: center; padding: 40px; background: white; border-radius: 12px; border: 1px solid #e2e8f0;">
                    <div style="font-size: 48px; margin-bottom: 16px;">📚</div>
                    <h3 style="margin: 0 0 8px 0; color: #0f172a;">No ${unitType} Added Yet</h3>
                    <p style="color: #64748b; margin: 0;">Learning materials for this subject are being prepared. Check back soon!</p>
                </div>
            `;
            return;
        }

        const unitType = isBALLB ? 'Unit' : 'Module';

        modulesList.innerHTML = state.modules.map((module, index) => {
            const hasContent = isBALLB || module.total_contents > 0;
            const progressPercent = module.total_contents > 0 
                ? Math.round((module.completed_contents / module.total_contents) * 100) 
                : 0;
            
            const rawOrder = module.sequence_order || module.order_index || (index + 1);
            const moduleNumber = isBALLB ? toRoman(rawOrder) : rawOrder;
            const moduleId = module.module_id || module.id;
            
            const buttonText = isBALLB ? 'Learn' : (module.completed_contents === 0 ? 'Start' : 
                                module.is_completed ? 'Review' : 'Continue');
            const buttonClass = (!isBALLB && module.is_completed) ? 'secondary' : '';
            
            const metaInfo = isBALLB 
                ? `${unitType} ${moduleNumber}`
                : `${unitType} ${moduleNumber} • ${module.total_contents} lesson${module.total_contents !== 1 ? 's' : ''}`;

            return `
                <div class="module-card ${!hasContent ? 'no-content' : ''}" onclick="navigateToModule(${moduleId}, ${isBALLB})">
                    <div class="module-card-header">
                        <div class="module-info">
                            <h3>${escapeHtml(module.title)}</h3>
                            <div class="module-meta">
                                ${metaInfo}
                            </div>
                            ${isBALLB && module.description ? `<p style="margin-top: 8px; font-size: 14px; color: #64748b;">${escapeHtml(module.description)}</p>` : ''}
                        </div>
                        <div class="module-status">
                            ${(!isBALLB && module.is_completed) ? '<span class="completion-badge">Completed</span>' : ''}
                            ${hasContent ? `<button class="module-action-btn ${buttonClass}" onclick="event.stopPropagation(); navigateToModule(${moduleId}, ${isBALLB})">${buttonText}</button>` : ''}
                        </div>
                    </div>
                    ${(!isBALLB && hasContent) ? `
                        <div class="progress-section">
                            <div class="progress-bar">
                                <div class="progress-fill ${module.is_completed ? 'completed' : ''}" style="width: ${progressPercent}%"></div>
                            </div>
                            <div class="progress-text">${module.completed_contents} of ${module.total_contents} completed (${progressPercent}%)</div>
                        </div>
                    ` : (isBALLB ? '' : `
                        <div class="no-content-msg">No learning content added yet</div>
                    `)}
                </div>
            `;
        }).join('');
    }

    window.navigateToModule = async function(moduleId, isBALLB = false) {
        if (isBALLB) {
            // For BA LLB, we might go to a different content view or show a "Coming Soon" if no lessons are linked
            // For now, let's try the standard content list
            window.location.href = `module-content.html?module_id=${moduleId}&subject_id=${state.subjectId}&course=ba-llb`;
            return;
        }

        try {
            const resumeData = await api.getModuleResume(moduleId);
            
            if (resumeData.next_content_id) {
                window.location.href = `learn-content.html?id=${resumeData.next_content_id}&module_id=${moduleId}&subject_id=${state.subjectId}`;
            } else {
                window.location.href = `module-content.html?module_id=${moduleId}&subject_id=${state.subjectId}`;
            }
        } catch (error) {
            console.error('Failed to get module resume:', error);
            window.location.href = `module-content.html?module_id=${moduleId}&subject_id=${state.subjectId}`;
        }
    };

    function init() {
        const urlParams = new URLSearchParams(window.location.search);
        state.subjectId = urlParams.get('subject_id');

        if (!state.subjectId) {
            window.location.href = 'start-studying.html';
            return;
        }

        const backLink = document.getElementById('backToSubject');
        if (backLink) {
            backLink.href = `start-studying.html?subject=${state.subjectId}`;
        }

        loadModules();
    }

    document.addEventListener('DOMContentLoaded', init);
})();
