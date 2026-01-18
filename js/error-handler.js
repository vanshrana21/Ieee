/**
 * error-handler.js
 * Phase 9.4: Global Error Handling & Robustness Utilities
 * 
 * Provides:
 * - Unified error handling with user-friendly messages
 * - Loading states management
 * - Empty states management
 * - Session/token recovery
 * - Navigation guardrails
 * - Network retry logic
 */

(function() {
    'use strict';

    const ErrorHandler = {
        ERROR_TYPES: {
            NETWORK: 'network',
            AUTH: 'auth',
            NOT_FOUND: 'not_found',
            VALIDATION: 'validation',
            SERVER: 'server',
            TIMEOUT: 'timeout',
            UNKNOWN: 'unknown'
        },

        USER_MESSAGES: {
            network: 'Unable to connect. Please check your internet connection.',
            auth: 'Your session has expired. Please log in again.',
            not_found: 'The requested content could not be found.',
            validation: 'Please check your input and try again.',
            server: 'Something went wrong on our end. Please try again.',
            timeout: 'The request took too long. Please try again.',
            unknown: 'An unexpected error occurred. Please try again.'
        },

        classifyError(error, status) {
            if (!navigator.onLine) return this.ERROR_TYPES.NETWORK;
            if (status === 401 || status === 403) return this.ERROR_TYPES.AUTH;
            if (status === 404) return this.ERROR_TYPES.NOT_FOUND;
            if (status === 400 || status === 422) return this.ERROR_TYPES.VALIDATION;
            if (status >= 500) return this.ERROR_TYPES.SERVER;
            if (error?.name === 'AbortError' || error?.message?.includes('timeout')) return this.ERROR_TYPES.TIMEOUT;
            if (error?.message?.includes('fetch') || error?.message?.includes('network')) return this.ERROR_TYPES.NETWORK;
            return this.ERROR_TYPES.UNKNOWN;
        },

        getUserMessage(errorType, customMessage) {
            if (customMessage && typeof customMessage === 'string' && !customMessage.includes('500') && !customMessage.includes('Internal')) {
                return customMessage;
            }
            return this.USER_MESSAGES[errorType] || this.USER_MESSAGES.unknown;
        },

        handle(error, options = {}) {
            const {
                status = null,
                context = '',
                showToast = true,
                redirect = true,
                customMessage = null
            } = options;

            const errorType = this.classifyError(error, status);
            const userMessage = this.getUserMessage(errorType, customMessage);

            console.error(`[${context || 'Error'}]`, error);

            if (errorType === this.ERROR_TYPES.AUTH && redirect) {
                this.handleAuthError();
                return { errorType, userMessage, handled: true };
            }

            if (showToast) {
                this.showToast(userMessage, 'error');
            }

            return { errorType, userMessage, handled: false };
        },

        handleAuthError() {
            const currentPath = window.location.pathname + window.location.search;
            
            localStorage.removeItem('access_token');
            localStorage.removeItem('user_role');
            
            if (!currentPath.includes('login.html')) {
                sessionStorage.setItem('redirect_after_login', currentPath);
                this.showSessionExpiredModal();
            }
        },

        showSessionExpiredModal() {
            const existing = document.getElementById('sessionExpiredModal');
            if (existing) existing.remove();

            const modal = document.createElement('div');
            modal.id = 'sessionExpiredModal';
            modal.innerHTML = `
                <div style="position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:10000;display:flex;align-items:center;justify-content:center;">
                    <div style="background:white;border-radius:16px;padding:32px;max-width:400px;text-align:center;margin:20px;">
                        <div style="font-size:48px;margin-bottom:16px;">🔒</div>
                        <h2 style="margin:0 0 8px;color:#0F172A;font-size:20px;">Session Expired</h2>
                        <p style="color:#64748B;margin:0 0 24px;font-size:14px;">Your session has expired for security. Please log in again to continue.</p>
                        <button onclick="window.location.href='/html/login.html'" style="background:#0066FF;color:white;border:none;padding:14px 32px;border-radius:10px;font-size:15px;font-weight:600;cursor:pointer;width:100%;">Log In Again</button>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
        },

        showToast(message, type = 'info', duration = 4000) {
            let container = document.getElementById('globalToastContainer');
            if (!container) {
                container = document.createElement('div');
                container.id = 'globalToastContainer';
                Object.assign(container.style, {
                    position: 'fixed',
                    bottom: '24px',
                    right: '24px',
                    zIndex: '9999',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '8px',
                    maxWidth: '90vw'
                });
                document.body.appendChild(container);
            }

            const colors = {
                error: { bg: '#FEE2E2', color: '#991B1B', border: '#FECACA' },
                success: { bg: '#D1FAE5', color: '#065F46', border: '#A7F3D0' },
                warning: { bg: '#FEF3C7', color: '#92400E', border: '#FDE68A' },
                info: { bg: '#DBEAFE', color: '#1E40AF', border: '#BFDBFE' }
            };

            const style = colors[type] || colors.info;

            const toast = document.createElement('div');
            Object.assign(toast.style, {
                background: style.bg,
                color: style.color,
                border: `1px solid ${style.border}`,
                padding: '14px 20px',
                borderRadius: '12px',
                fontSize: '14px',
                fontWeight: '500',
                boxShadow: '0 4px 20px rgba(0,0,0,0.1)',
                transform: 'translateX(100%)',
                opacity: '0',
                transition: 'all 0.3s ease'
            });
            toast.textContent = message;
            container.appendChild(toast);

            requestAnimationFrame(() => {
                toast.style.transform = 'translateX(0)';
                toast.style.opacity = '1';
            });

            setTimeout(() => {
                toast.style.transform = 'translateX(100%)';
                toast.style.opacity = '0';
                setTimeout(() => {
                    if (container.contains(toast)) container.removeChild(toast);
                }, 300);
            }, duration);
        }
    };

    const LoadingStates = {
        skeletons: {
            card: `
                <div class="skeleton-card" style="background:#F8FAFC;border-radius:12px;padding:20px;animation:skeleton-pulse 1.5s infinite;">
                    <div style="background:#E2E8F0;height:24px;width:60%;border-radius:6px;margin-bottom:12px;"></div>
                    <div style="background:#E2E8F0;height:16px;width:100%;border-radius:4px;margin-bottom:8px;"></div>
                    <div style="background:#E2E8F0;height:16px;width:80%;border-radius:4px;"></div>
                </div>
            `,
            list: `
                <div class="skeleton-list" style="animation:skeleton-pulse 1.5s infinite;">
                    ${[1,2,3].map(() => `
                        <div style="display:flex;gap:12px;padding:16px 0;border-bottom:1px solid #F1F5F9;">
                            <div style="background:#E2E8F0;width:40px;height:40px;border-radius:8px;"></div>
                            <div style="flex:1;">
                                <div style="background:#E2E8F0;height:16px;width:70%;border-radius:4px;margin-bottom:8px;"></div>
                                <div style="background:#E2E8F0;height:12px;width:50%;border-radius:4px;"></div>
                            </div>
                        </div>
                    `).join('')}
                </div>
            `,
            stats: `
                <div class="skeleton-stats" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:16px;animation:skeleton-pulse 1.5s infinite;">
                    ${[1,2,3,4].map(() => `
                        <div style="background:#F8FAFC;border-radius:12px;padding:20px;">
                            <div style="background:#E2E8F0;height:32px;width:50%;border-radius:6px;margin-bottom:8px;"></div>
                            <div style="background:#E2E8F0;height:14px;width:70%;border-radius:4px;"></div>
                        </div>
                    `).join('')}
                </div>
            `
        },

        injectStyles() {
            if (document.getElementById('loading-states-styles')) return;
            
            const style = document.createElement('style');
            style.id = 'loading-states-styles';
            style.textContent = `
                @keyframes skeleton-pulse {
                    0%, 100% { opacity: 1; }
                    50% { opacity: 0.5; }
                }
                @keyframes spin {
                    to { transform: rotate(360deg); }
                }
                .loading-spinner {
                    width: 32px;
                    height: 32px;
                    border: 3px solid #E2E8F0;
                    border-top-color: #0066FF;
                    border-radius: 50%;
                    animation: spin 1s linear infinite;
                }
                .loading-overlay {
                    position: absolute;
                    inset: 0;
                    background: rgba(255,255,255,0.8);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    z-index: 100;
                }
                .btn-loading {
                    position: relative;
                    color: transparent !important;
                    pointer-events: none;
                }
                .btn-loading::after {
                    content: '';
                    position: absolute;
                    width: 16px;
                    height: 16px;
                    top: 50%;
                    left: 50%;
                    margin: -8px 0 0 -8px;
                    border: 2px solid currentColor;
                    border-top-color: transparent;
                    border-radius: 50%;
                    animation: spin 0.6s linear infinite;
                }
            `;
            document.head.appendChild(style);
        },

        showSkeleton(container, type = 'card') {
            this.injectStyles();
            if (!container) return;
            container.innerHTML = this.skeletons[type] || this.skeletons.card;
        },

        showSpinner(container, message = 'Loading...') {
            this.injectStyles();
            if (!container) return;
            container.innerHTML = `
                <div style="text-align:center;padding:48px 24px;">
                    <div class="loading-spinner" style="margin:0 auto 16px;"></div>
                    <p style="color:#64748B;font-size:14px;margin:0;">${message}</p>
                </div>
            `;
        },

        showOverlay(container) {
            this.injectStyles();
            if (!container) return;
            
            const existing = container.querySelector('.loading-overlay');
            if (existing) return;
            
            container.style.position = 'relative';
            const overlay = document.createElement('div');
            overlay.className = 'loading-overlay';
            overlay.innerHTML = '<div class="loading-spinner"></div>';
            container.appendChild(overlay);
        },

        hideOverlay(container) {
            if (!container) return;
            const overlay = container.querySelector('.loading-overlay');
            if (overlay) overlay.remove();
        },

        setButtonLoading(button, loading = true) {
            if (!button) return;
            if (loading) {
                button.classList.add('btn-loading');
                button.dataset.originalText = button.textContent;
                button.disabled = true;
            } else {
                button.classList.remove('btn-loading');
                if (button.dataset.originalText) {
                    button.textContent = button.dataset.originalText;
                }
                button.disabled = false;
            }
        }
    };

    const EmptyStates = {
        templates: {
            noSubjects: {
                icon: '📚',
                title: 'No Subjects Yet',
                message: 'Your curriculum will appear here once you\'re enrolled in a course.',
                action: { text: 'Go to Dashboard', href: '/html/dashboard-student.html' }
            },
            noContent: {
                icon: '📖',
                title: 'Content Coming Soon',
                message: 'We\'re preparing content for this subject. Check back soon!',
                action: null
            },
            noProgress: {
                icon: '🚀',
                title: 'Start Your Journey',
                message: 'Begin learning to track your progress here.',
                action: { text: 'Start Learning', href: '/html/start-studying.html' }
            },
            noPractice: {
                icon: '✍️',
                title: 'No Practice Questions',
                message: 'Practice questions for this module aren\'t available yet.',
                action: { text: 'Browse Subjects', href: '/html/start-studying.html' }
            },
            noActivity: {
                icon: '📋',
                title: 'No Recent Activity',
                message: 'Start learning to see your activity history here.',
                action: null
            },
            noResults: {
                icon: '🔍',
                title: 'No Results Found',
                message: 'Try adjusting your search or browse available content.',
                action: null
            },
            noNotes: {
                icon: '📝',
                title: 'No Notes Yet',
                message: 'Create notes while studying to see them here.',
                action: null
            },
            notFound: {
                icon: '🔎',
                title: 'Page Not Found',
                message: 'The page you\'re looking for doesn\'t exist or has been moved.',
                action: { text: 'Go to Dashboard', href: '/html/dashboard-student.html' }
            },
            error: {
                icon: '⚠️',
                title: 'Something Went Wrong',
                message: 'We encountered an error. Please try again.',
                action: { text: 'Retry', onclick: 'window.location.reload()' }
            }
        },

        render(container, type, customOptions = {}) {
            if (!container) return;

            const template = this.templates[type] || this.templates.error;
            const options = { ...template, ...customOptions };

            let actionHtml = '';
            if (options.action) {
                if (options.action.href) {
                    actionHtml = `<a href="${options.action.href}" class="empty-state-btn" style="display:inline-block;background:#0066FF;color:white;padding:12px 24px;border-radius:10px;text-decoration:none;font-weight:600;font-size:14px;margin-top:8px;">${options.action.text}</a>`;
                } else if (options.action.onclick) {
                    actionHtml = `<button onclick="${options.action.onclick}" class="empty-state-btn" style="background:#0066FF;color:white;padding:12px 24px;border-radius:10px;border:none;cursor:pointer;font-weight:600;font-size:14px;margin-top:8px;">${options.action.text}</button>`;
                }
            }

            container.innerHTML = `
                <div class="empty-state" style="text-align:center;padding:48px 24px;">
                    <div style="font-size:48px;margin-bottom:16px;line-height:1;">${options.icon}</div>
                    <h3 style="color:#0F172A;font-size:18px;font-weight:600;margin:0 0 8px;">${options.title}</h3>
                    <p style="color:#64748B;font-size:14px;margin:0 auto 16px;max-width:300px;line-height:1.5;">${options.message}</p>
                    ${actionHtml}
                </div>
            `;
        }
    };

    const NavigationGuard = {
        requiredParams: {
            'learn-content.html': ['id'],
            'case-detail.html': ['id'],
            'module-content.html': ['module_id']
        },

        safeFallbacks: {
            'learn-content.html': '/html/start-studying.html',
            'case-detail.html': '/html/start-studying.html',
            'module-content.html': '/html/start-studying.html',
            'practice-content.html': '/html/start-studying.html'
        },

        validateNavigation() {
            const path = window.location.pathname;
            const params = new URLSearchParams(window.location.search);
            const pageName = path.split('/').pop();

            const required = this.requiredParams[pageName];
            if (required) {
                const missing = required.filter(param => !params.get(param));
                if (missing.length > 0) {
                    console.warn(`Missing required params: ${missing.join(', ')}`);
                    const fallback = this.safeFallbacks[pageName] || '/html/dashboard-student.html';
                    window.location.href = fallback;
                    return false;
                }
            }

            return true;
        },

        safeNavigate(url, fallback = '/html/dashboard-student.html') {
            try {
                if (!url || typeof url !== 'string') {
                    window.location.href = fallback;
                    return;
                }
                window.location.href = url;
            } catch (e) {
                console.error('Navigation error:', e);
                window.location.href = fallback;
            }
        },

        validateId(id, fallbackUrl) {
            const numId = parseInt(id, 10);
            if (isNaN(numId) || numId <= 0) {
                if (fallbackUrl) {
                    window.location.href = fallbackUrl;
                }
                return null;
            }
            return numId;
        }
    };

    const NetworkRetry = {
        async fetchWithRetry(url, options = {}, retries = 3, delay = 1000) {
            const timeout = options.timeout || 30000;
            
            for (let attempt = 1; attempt <= retries; attempt++) {
                try {
                    const controller = new AbortController();
                    const timeoutId = setTimeout(() => controller.abort(), timeout);

                    const response = await fetch(url, {
                        ...options,
                        signal: controller.signal
                    });

                    clearTimeout(timeoutId);

                    if (!response.ok && response.status >= 500 && attempt < retries) {
                        await this.sleep(delay * attempt);
                        continue;
                    }

                    return response;
                } catch (error) {
                    if (attempt === retries) throw error;
                    if (error.name === 'AbortError') throw error;
                    await this.sleep(delay * attempt);
                }
            }
        },

        sleep(ms) {
            return new Promise(resolve => setTimeout(resolve, ms));
        }
    };

    const SessionManager = {
        checkAuth() {
            const token = localStorage.getItem('access_token');
            return !!token;
        },

        requireAuth(redirectUrl = '/html/login.html') {
            if (!this.checkAuth()) {
                const currentPath = window.location.pathname + window.location.search;
                sessionStorage.setItem('redirect_after_login', currentPath);
                window.location.href = redirectUrl;
                return false;
            }
            return true;
        },

        getRedirectAfterLogin() {
            const redirect = sessionStorage.getItem('redirect_after_login');
            sessionStorage.removeItem('redirect_after_login');
            return redirect || '/html/dashboard-student.html';
        },

        handleLoginSuccess() {
            const redirect = this.getRedirectAfterLogin();
            window.location.href = redirect;
        }
    };

    LoadingStates.injectStyles();

    window.JurisErrorHandler = ErrorHandler;
    window.JurisLoadingStates = LoadingStates;
    window.JurisEmptyStates = EmptyStates;
    window.JurisNavigationGuard = NavigationGuard;
    window.JurisNetworkRetry = NetworkRetry;
    window.JurisSessionManager = SessionManager;

    window.showToast = (msg, type) => ErrorHandler.showToast(msg, type);
    window.showError = (msg) => ErrorHandler.showToast(msg, 'error');
    window.showSuccess = (msg) => ErrorHandler.showToast(msg, 'success');

})();
