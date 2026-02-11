/**
 * Phase 0: Virtual Courtroom Infrastructure - Frontend Error Handler
 * 
 * Catches and handles frontend errors gracefully.
 * Provides user-friendly error display and recovery actions.
 */

class CourtroomErrorHandler {
    /**
     * Creates a new CourtroomErrorHandler instance.
     * @param {CourtroomState} stateManager - CourtroomState instance
     */
    constructor(stateManager) {
        this.stateManager = stateManager;
        
        // Error tracking
        this.errorCount = 0;
        this.maxErrors = 10; // Prevent error spam
        this.recentErrors = []; // Last 5 errors for deduplication
        
        // Retry configuration
        this.retryConfig = {
            maxRetries: 3,
            baseDelay: 1000, // ms
            maxDelay: 10000   // ms
        };
        
        // Bind methods
        this.initialize = this.initialize.bind(this);
        this.handleError = this.handleError.bind(this);
        this.showToast = this.showToast.bind(this);
        this.showModal = this.showModal.bind(this);
        this.logError = this.logError.bind(this);
        this.attemptRecovery = this.attemptRecovery.bind(this);
        this.isDuplicate = this.isDuplicate.bind(this);
        
        // Setup global listeners
        this.initialize();
    }
    
    /**
     * Initialize global error listeners.
     */
    initialize() {
        // Global error handler
        window.addEventListener('error', (event) => {
            this.handleError({
                type: 'JAVASCRIPT_ERROR',
                message: event.message,
                filename: event.filename,
                lineno: event.lineno,
                colno: event.colno,
                error: event.error
            });
            // Don't prevent default - let browser console show it too
        });
        
        // Unhandled promise rejections
        window.addEventListener('unhandledrejection', (event) => {
            this.handleError({
                type: 'PROMISE_REJECTION',
                message: event.reason?.message || 'Unhandled promise rejection',
                error: event.reason
            });
        });
        
        console.log('[CourtroomErrorHandler] Global error listeners initialized');
    }
    
    /**
     * Main error handler - categorizes and routes errors.
     * @param {Object} error - Error object with type, message, and context
     * @param {string} context - Optional context about where error occurred
     */
    handleError(error, context = '') {
        // Prevent error spam
        if (this.errorCount >= this.maxErrors) {
            console.warn('[CourtroomErrorHandler] Max errors reached, suppressing');
            return;
        }
        
        // Deduplicate recent errors
        if (this.isDuplicate(error)) {
            return;
        }
        
        this.errorCount++;
        
        // Categorize error
        const category = this.categorizeError(error);
        
        // Log error
        this.logError(error, category, context);
        
        // Handle based on category
        switch (category) {
            case 'NETWORK_ERROR':
                this.handleNetworkError(error, context);
                break;
            case 'WEBSOCKET_ERROR':
                this.handleWebSocketError(error, context);
                break;
            case 'PERMISSION_ERROR':
                this.handlePermissionError(error, context);
                break;
            case 'VALIDATION_ERROR':
                this.handleValidationError(error, context);
                break;
            case 'STATE_ERROR':
                this.handleStateError(error, context);
                break;
            case 'UI_ERROR':
                this.handleUIError(error, context);
                break;
            default:
                this.handleGenericError(error, context);
        }
    }
    
    /**
     * Categorize error based on type and message.
     * @param {Object} error - Error object
     * @returns {string} Error category
     */
    categorizeError(error) {
        const type = error.type || '';
        const message = (error.message || '').toLowerCase();
        
        if (type === 'NETWORK_ERROR' || message.includes('network') || message.includes('fetch')) {
            return 'NETWORK_ERROR';
        }
        if (type === 'WEBSOCKET_ERROR' || message.includes('websocket')) {
            return 'WEBSOCKET_ERROR';
        }
        if (type === 'PERMISSION_ERROR' || message.includes('permission') || message.includes('unauthorized')) {
            return 'PERMISSION_ERROR';
        }
        if (type === 'VALIDATION_ERROR' || message.includes('validation') || message.includes('invalid')) {
            return 'VALIDATION_ERROR';
        }
        if (type === 'STATE_ERROR' || message.includes('state')) {
            return 'STATE_ERROR';
        }
        if (type === 'UI_ERROR' || message.includes('render') || message.includes('element')) {
            return 'UI_ERROR';
        }
        
        return 'GENERIC_ERROR';
    }
    
    /**
     * Check if error is duplicate of recent error.
     * @param {Object} error - Error to check
     * @returns {boolean} True if duplicate
     */
    isDuplicate(error) {
        const errorKey = `${error.type}:${error.message}`.substring(0, 100);
        const now = Date.now();
        
        // Remove old errors (older than 5 seconds)
        this.recentErrors = this.recentErrors.filter(e => now - e.time < 5000);
        
        // Check for duplicate
        const isDup = this.recentErrors.some(e => e.key === errorKey);
        
        // Add to recent
        this.recentErrors.push({ key: errorKey, time: now });
        
        // Keep only last 5
        if (this.recentErrors.length > 5) {
            this.recentErrors.shift();
        }
        
        return isDup;
    }
    
    /**
     * Handle network errors with retry logic.
     * @param {Object} error - Network error
     * @param {string} context - Error context
     */
    handleNetworkError(error, context) {
        this.showToast('⚠️ Network error. Retrying...', 'warning');
        
        // Attempt recovery with exponential backoff
        this.attemptRecovery(error, async () => {
            // Retry the failed request if we have the original request info
            if (error.retry && typeof error.retry === 'function') {
                await error.retry();
            }
        });
    }
    
    /**
     * Handle WebSocket errors with reconnection.
     * @param {Object} error - WebSocket error
     * @param {string} context - Error context
     */
    handleWebSocketError(error, context) {
        this.showToast('⚠️ Connection lost. Reconnecting...', 'warning');
        
        // Update state
        if (this.stateManager) {
            this.stateManager.updateConnection(false);
        }
        
        // Attempt reconnection
        this.attemptRecovery(error, async () => {
            if (error.reconnect && typeof error.reconnect === 'function') {
                await error.reconnect();
            }
        });
    }
    
    /**
     * Handle permission errors.
     * @param {Object} error - Permission error
     * @param {string} context - Error context
     */
    handlePermissionError(error, context) {
        this.showToast('⛔ Permission denied', 'error');
        
        // Show more details in modal for debugging
        this.showModal({
            title: 'Permission Denied',
            message: error.message || 'You do not have permission to perform this action.',
            type: 'error',
            actions: [
                { label: 'OK', primary: true }
            ]
        });
    }
    
    /**
     * Handle validation errors.
     * @param {Object} error - Validation error
     * @param {string} context - Error context
     */
    handleValidationError(error, context) {
        const details = error.details || {};
        const fieldErrors = details.errors || [];
        
        if (fieldErrors.length > 0) {
            // Show field-specific errors
            fieldErrors.forEach(fieldError => {
                this.showToast(`⚠️ ${fieldError.field}: ${fieldError.message}`, 'warning');
            });
        } else {
            this.showToast(`⚠️ ${error.message || 'Validation error'}`, 'warning');
        }
    }
    
    /**
     * Handle state errors.
     * @param {Object} error - State error
     * @param {string} context - Error context
     */
    handleStateError(error, context) {
        this.showToast('⚠️ State error occurred', 'error');
        
        // Reset to last known good state
        if (this.stateManager) {
            this.stateManager.clearError();
        }
    }
    
    /**
     * Handle UI/rendering errors.
     * @param {Object} error - UI error
     * @param {string} context - Error context
     */
    handleUIError(error, context) {
        this.showToast('⚠️ Display error occurred', 'error');
        console.error('[CourtroomErrorHandler] UI Error:', error);
    }
    
    /**
     * Handle generic/unexpected errors.
     * @param {Object} error - Generic error
     * @param {string} context - Error context
     */
    handleGenericError(error, context) {
        // Show user-friendly message
        const message = error.log_id 
            ? `An error occurred (ID: ${error.log_id}). Please try again.`
            : 'An unexpected error occurred. Please try again.';
        
        this.showToast(message, 'error');
    }
    
    /**
     * Attempt recovery with exponential backoff retry.
     * @param {Object} error - Original error
     * @param {Function} recoveryFn - Recovery function to attempt
     */
    async attemptRecovery(error, recoveryFn) {
        let attempt = 0;
        
        while (attempt < this.retryConfig.maxRetries) {
            attempt++;
            
            // Calculate delay with exponential backoff
            const delay = Math.min(
                this.retryConfig.baseDelay * Math.pow(2, attempt - 1),
                this.retryConfig.maxDelay
            );
            
            console.log(`[CourtroomErrorHandler] Recovery attempt ${attempt}/${this.retryConfig.maxRetries} in ${delay}ms`);
            
            await new Promise(resolve => setTimeout(resolve, delay));
            
            try {
                await recoveryFn();
                console.log('[CourtroomErrorHandler] Recovery successful');
                this.showToast('✅ Connection restored', 'success');
                return;
            } catch (recoveryError) {
                console.warn(`[CourtroomErrorHandler] Recovery attempt ${attempt} failed:`, recoveryError);
            }
        }
        
        // All retries failed
        console.error('[CourtroomErrorHandler] All recovery attempts failed');
        this.showModal({
            title: 'Connection Failed',
            message: 'Unable to reconnect after multiple attempts. Please refresh the page.',
            type: 'error',
            actions: [
                { 
                    label: 'Refresh Page', 
                    primary: true,
                    action: () => window.location.reload()
                },
                { label: 'Dismiss' }
            ]
        });
    }
    
    /**
     * Show non-blocking toast notification.
     * @param {string} message - Message to display
     * @param {string} type - Type: 'success', 'warning', 'error'
     * @param {number} duration - Display duration in ms
     */
    showToast(message, type = 'info', duration = 5000) {
        // Create toast element
        const toast = document.createElement('div');
        toast.className = `courtroom-toast courtroom-toast--${type}`;
        toast.textContent = message;
        
        // Add to container
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 10000;
                display: flex;
                flex-direction: column;
                gap: 10px;
            `;
            document.body.appendChild(container);
        }
        
        container.appendChild(toast);
        
        // Remove after duration
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }
    
    /**
     * Show modal dialog for critical errors.
     * @param {Object} options - Modal options
     * @param {string} options.title - Modal title
     * @param {string} options.message - Modal message
     * @param {string} options.type - Modal type: 'error', 'warning', 'info'
     * @param {Array} options.actions - Array of {label, primary, action}
     */
    showModal(options) {
        const { title, message, type = 'error', actions = [] } = options;
        
        // Create modal overlay
        const overlay = document.createElement('div');
        overlay.className = 'courtroom-modal-overlay';
        overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.5);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 10001;
        `;
        
        // Create modal
        const modal = document.createElement('div');
        modal.className = `courtroom-modal courtroom-modal--${type}`;
        modal.style.cssText = `
            background: white;
            padding: 24px;
            border-radius: 8px;
            max-width: 400px;
            width: 90%;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
        `;
        
        // Modal content
        modal.innerHTML = `
            <h3 style="margin: 0 0 16px 0; color: ${type === 'error' ? '#d32f2f' : '#333'}">${title}</h3>
            <p style="margin: 0 0 24px 0; color: #666; line-height: 1.5;">${message}</p>
            <div style="display: flex; gap: 12px; justify-content: flex-end;">
                ${actions.map((action, i) => `
                    <button 
                        class="${action.primary ? 'btn-primary' : 'btn-secondary'}"
                        data-action="${i}"
                        style="
                            padding: 8px 16px;
                            border: none;
                            border-radius: 4px;
                            cursor: pointer;
                            background: ${action.primary ? '#1976d2' : '#f5f5f5'};
                            color: ${action.primary ? 'white' : '#333'};
                        "
                    >${action.label}</button>
                `).join('')}
            </div>
        `;
        
        overlay.appendChild(modal);
        document.body.appendChild(overlay);
        
        // Handle button clicks
        modal.querySelectorAll('button').forEach((btn, i) => {
            btn.addEventListener('click', () => {
                const action = actions[i];
                if (action.action) {
                    action.action();
                }
                overlay.remove();
            });
        });
        
        // Close on overlay click
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                overlay.remove();
            }
        });
    }
    
    /**
     * Log error to backend for monitoring.
     * @param {Object} error - Error object
     * @param {string} category - Error category
     * @param {string} context - Error context
     */
    async logError(error, category, context) {
        // Collect error details
        const errorData = {
            type: error.type || category,
            category: category,
            message: error.message || 'Unknown error',
            context: context,
            url: window.location.href,
            userAgent: navigator.userAgent,
            timestamp: new Date().toISOString(),
            stack: error.error?.stack || null,
            user_id: this.stateManager?.state?.currentUser?.id || null
        };
        
        console.error('[CourtroomErrorHandler]', errorData);
        
        // Send to backend (non-blocking)
        try {
            const response = await fetch('/api/errors/log', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(errorData),
                // Don't wait for response
                keepalive: true
            });
            
            if (!response.ok) {
                console.warn('[CourtroomErrorHandler] Failed to log error to backend');
            }
        } catch (e) {
            // Silently fail - don't create infinite loop
            console.warn('[CourtroomErrorHandler] Error logging failed:', e);
        }
    }
    
    /**
     * Reset error count (call after successful recovery).
     */
    resetErrorCount() {
        this.errorCount = 0;
        this.recentErrors = [];
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CourtroomErrorHandler;
}
