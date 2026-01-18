/**
 * empty-states.js
 * Phase 11.2: Empty State & Graceful Degradation
 * 
 * CORE PRINCIPLE:
 * Empty state ≠ Error state
 * 
 * Empty = "You haven't done this yet — here's what to do."
 * Error = "Something went wrong."
 * 
 * These must NEVER be confused.
 */

window.JurisEmptyStates = (function() {
    'use strict';

    const EMPTY_STATE_CONFIGS = {
        subjects: {
            icon: '📚',
            title: 'No Subjects Yet',
            message: 'Your curriculum will appear here once enrollment is complete.',
            action: {
                text: 'Complete Enrollment',
                href: 'onboarding.html'
            }
        },
        
        progress: {
            icon: '📊',
            title: 'No Progress Yet',
            message: "You haven't started learning yet. Begin your first lesson to track progress.",
            action: {
                text: 'Start Learning',
                href: 'start-studying.html'
            }
        },
        
        activity: {
            icon: '📋',
            title: 'No Recent Activity',
            message: 'Your learning history will appear here as you progress through content.',
            action: {
                text: 'Begin Studying',
                href: 'start-studying.html'
            }
        },
        
        practice: {
            icon: '✏️',
            title: 'No Practice Attempts',
            message: "You haven't attempted any practice questions yet. Practice helps reinforce your learning.",
            action: {
                text: 'Start Practice',
                href: 'practice-content.html'
            }
        },
        
        analytics: {
            icon: '📈',
            title: 'Analytics Coming Soon',
            message: 'Complete more content to see detailed performance analytics.',
            action: null,
            minDataNote: 'Requires at least 5 practice attempts for meaningful insights.'
        },
        
        focus: {
            icon: '🎯',
            title: 'No Focus Topics Yet',
            message: 'Start practicing to receive personalized study recommendations.',
            action: {
                text: 'Start Practice',
                href: 'practice-content.html'
            }
        },
        
        cases: {
            icon: '⚖️',
            title: 'No Case Studies',
            message: 'Case studies for this module will appear here.',
            action: null
        },
        
        notes: {
            icon: '📝',
            title: 'No Notes Yet',
            message: "You haven't saved any notes. Notes help you remember key concepts.",
            action: {
                text: 'Start Learning',
                href: 'start-studying.html'
            }
        },
        
        tutor_history: {
            icon: '💬',
            title: 'No Tutor Interactions',
            message: "You haven't used the AI tutor yet. Use 'Explain' buttons while learning.",
            action: null
        },
        
        search: {
            icon: '🔍',
            title: 'No Results Found',
            message: 'Try different keywords or check your spelling.',
            action: null
        },
        
        modules: {
            icon: '📦',
            title: 'No Modules Available',
            message: 'Modules for this subject are being prepared.',
            action: null
        },
        
        content: {
            icon: '📄',
            title: 'No Content Available',
            message: 'Content for this module is coming soon.',
            action: null
        },

        mastery: {
            icon: '🏆',
            title: 'Mastery Data Unavailable',
            message: 'Complete more practice to calculate your mastery level.',
            action: {
                text: 'Practice Now',
                href: 'practice-content.html'
            }
        },

        streak: {
            icon: '🔥',
            title: 'Start Your Streak',
            message: 'Study daily to build your learning streak.',
            action: {
                text: 'Learn Today',
                href: 'start-studying.html'
            }
        }
    };

    function createEmptyState(type, options = {}) {
        const config = EMPTY_STATE_CONFIGS[type];
        if (!config) {
            console.warn(`[EmptyStates] Unknown empty state type: ${type}`);
            return createGenericEmptyState(options);
        }

        const {
            icon = config.icon,
            title = config.title,
            message = config.message,
            action = config.action,
            minDataNote = config.minDataNote,
            compact = false,
            className = ''
        } = { ...config, ...options };

        const container = document.createElement('div');
        container.className = `empty-state empty-state-${type} ${compact ? 'empty-state-compact' : ''} ${className}`.trim();
        container.setAttribute('role', 'status');
        container.setAttribute('aria-label', title);

        container.innerHTML = `
            <div class="empty-state-icon">${icon}</div>
            <h3 class="empty-state-title">${escapeHtml(title)}</h3>
            <p class="empty-state-message">${escapeHtml(message)}</p>
            ${minDataNote ? `<p class="empty-state-note">${escapeHtml(minDataNote)}</p>` : ''}
            ${action ? `
                <a href="${action.href}" class="empty-state-action">
                    ${escapeHtml(action.text)}
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M5 12h14M12 5l7 7-7 7"/>
                    </svg>
                </a>
            ` : ''}
        `;

        return container;
    }

    function createGenericEmptyState(options = {}) {
        const {
            icon = '📭',
            title = 'No Data',
            message = 'No data available yet.',
            action = null,
            compact = false
        } = options;

        const container = document.createElement('div');
        container.className = `empty-state ${compact ? 'empty-state-compact' : ''}`;

        container.innerHTML = `
            <div class="empty-state-icon">${icon}</div>
            <h3 class="empty-state-title">${escapeHtml(title)}</h3>
            <p class="empty-state-message">${escapeHtml(message)}</p>
            ${action ? `
                <a href="${action.href}" class="empty-state-action">${escapeHtml(action.text)}</a>
            ` : ''}
        `;

        return container;
    }

    function renderEmptyState(container, type, options = {}) {
        if (!container) {
            console.warn('[EmptyStates] No container provided');
            return null;
        }

        if (typeof container === 'string') {
            container = document.querySelector(container);
        }

        if (!container) {
            console.warn('[EmptyStates] Container not found');
            return null;
        }

        const emptyState = createEmptyState(type, options);
        container.innerHTML = '';
        container.appendChild(emptyState);
        return emptyState;
    }

    function isDataEmpty(data) {
        if (data === null || data === undefined) return true;
        if (Array.isArray(data)) return data.length === 0;
        if (typeof data === 'object') return Object.keys(data).length === 0;
        if (typeof data === 'string') return data.trim() === '';
        if (typeof data === 'number') return isNaN(data);
        return false;
    }

    function hasMinimumData(data, minCount = 1) {
        if (Array.isArray(data)) return data.length >= minCount;
        if (typeof data === 'number') return data >= minCount;
        return !isDataEmpty(data);
    }

    function safeNumber(value, defaultValue = 0) {
        if (value === null || value === undefined) return defaultValue;
        const num = Number(value);
        if (isNaN(num) || !isFinite(num)) return defaultValue;
        return num;
    }

    function safePercentage(value, defaultValue = 0) {
        const num = safeNumber(value, defaultValue);
        return Math.max(0, Math.min(100, num));
    }

    function safeDivide(numerator, denominator, defaultValue = 0) {
        const num = safeNumber(numerator, 0);
        const den = safeNumber(denominator, 0);
        if (den === 0) return defaultValue;
        const result = num / den;
        if (isNaN(result) || !isFinite(result)) return defaultValue;
        return result;
    }

    function safeArray(value) {
        if (Array.isArray(value)) return value;
        if (value === null || value === undefined) return [];
        return [value];
    }

    function safeString(value, defaultValue = '') {
        if (value === null || value === undefined) return defaultValue;
        return String(value);
    }

    function safeObject(value, defaultValue = {}) {
        if (value && typeof value === 'object' && !Array.isArray(value)) return value;
        return defaultValue;
    }

    function formatEmptyValue(value, format = 'text') {
        if (isDataEmpty(value)) {
            switch (format) {
                case 'percentage': return '—%';
                case 'number': return '—';
                case 'time': return '—';
                case 'count': return '0';
                default: return '—';
            }
        }

        switch (format) {
            case 'percentage':
                return `${safePercentage(value)}%`;
            case 'number':
                return safeNumber(value).toLocaleString();
            case 'time':
                const seconds = safeNumber(value);
                const hours = Math.floor(seconds / 3600);
                const mins = Math.floor((seconds % 3600) / 60);
                if (hours > 0) return `${hours}h ${mins}m`;
                if (mins > 0) return `${mins}m`;
                return '< 1m';
            case 'count':
                return safeNumber(value, 0).toString();
            default:
                return safeString(value, '—');
        }
    }

    function getGuidanceForEmptyState(type) {
        const guidance = {
            subjects: {
                reason: 'Your course enrollment determines which subjects appear here.',
                nextStep: 'Complete course selection in onboarding to see your subjects.',
                estimated: 'Subjects will appear immediately after enrollment.'
            },
            progress: {
                reason: 'Progress is tracked as you complete lessons and practice questions.',
                nextStep: 'Start with any subject to begin tracking your progress.',
                estimated: 'Progress updates in real-time as you learn.'
            },
            analytics: {
                reason: 'Analytics require sufficient data to provide meaningful insights.',
                nextStep: 'Complete at least 5 practice questions to unlock analytics.',
                estimated: 'Initial analytics available after 5+ practice attempts.'
            },
            focus: {
                reason: 'Focus recommendations are personalized based on your practice performance.',
                nextStep: 'Practice questions to receive smart study recommendations.',
                estimated: 'Recommendations appear after 10+ practice attempts.'
            },
            mastery: {
                reason: 'Mastery is calculated from your practice performance over time.',
                nextStep: 'Continue practicing to build mastery in each topic.',
                estimated: 'Mastery scores appear after 3+ attempts per topic.'
            }
        };

        return guidance[type] || {
            reason: 'No data available yet.',
            nextStep: 'Start using this feature to see data here.',
            estimated: 'Data will appear as you use the platform.'
        };
    }

    function checkAndRenderEmpty(container, data, type, options = {}) {
        const isEmpty = isDataEmpty(data);
        const hasMinData = hasMinimumData(data, options.minRequired || 1);

        if (isEmpty) {
            renderEmptyState(container, type, options);
            return true;
        }

        if (!hasMinData && options.showInsufficientWarning) {
            const guidance = getGuidanceForEmptyState(type);
            renderEmptyState(container, type, {
                ...options,
                minDataNote: guidance.estimated
            });
            return true;
        }

        return false;
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function getResumeGuidance(hasSubjects, hasProgress, hasActivity) {
        if (!hasSubjects) {
            return {
                type: 'enrollment',
                title: 'Complete Your Enrollment',
                message: 'Set up your course to access subjects',
                href: 'onboarding.html',
                buttonText: 'Get Started'
            };
        }

        if (!hasProgress) {
            return {
                type: 'first_start',
                title: 'Begin Your Learning Journey',
                message: 'Start your first lesson today',
                href: 'start-studying.html',
                buttonText: 'Start Learning'
            };
        }

        if (!hasActivity) {
            return {
                type: 'continue',
                title: 'Continue Learning',
                message: 'Pick up where you left off',
                href: 'start-studying.html',
                buttonText: 'Continue'
            };
        }

        return {
            type: 'resume',
            title: 'Resume Learning',
            message: 'Continue your recent activity',
            href: 'start-studying.html',
            buttonText: 'Resume'
        };
    }

    function renderInlineEmpty(message, compact = true) {
        const span = document.createElement('span');
        span.className = `inline-empty ${compact ? 'inline-empty-compact' : ''}`;
        span.textContent = message || '—';
        return span;
    }

    function renderStatEmpty(container, label = 'No data') {
        if (!container) return;
        container.textContent = '—';
        container.setAttribute('title', label);
        container.classList.add('stat-empty');
    }

    return {
        CONFIGS: EMPTY_STATE_CONFIGS,
        create: createEmptyState,
        render: renderEmptyState,
        check: checkAndRenderEmpty,
        
        isDataEmpty,
        hasMinimumData,
        
        safeNumber,
        safePercentage,
        safeDivide,
        safeArray,
        safeString,
        safeObject,
        
        formatEmptyValue,
        getGuidance: getGuidanceForEmptyState,
        getResumeGuidance,
        
        renderInlineEmpty,
        renderStatEmpty
    };

})();

if (typeof module !== 'undefined' && module.exports) {
    module.exports = window.JurisEmptyStates;
}
