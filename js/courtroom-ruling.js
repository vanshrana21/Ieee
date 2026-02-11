/**
 * Phase 2: Virtual Courtroom Infrastructure - Objection Ruling Workflow
 *
 * Handles objection submission and ruling with WebSocket sync.
 * Integrates with Phase 0 state management, Phase 1 UI, and timer auto-pause/resume.
 */

class CourtroomRuling {
    /**
     * Creates a new CourtroomRuling instance.
     * @param {number} roundId - The round ID
     * @param {CourtroomState} stateManager - Phase 0 state manager instance
     * @param {CourtroomTimer} timer - Timer instance for auto-pause/resume
     * @param {CourtroomAudio} audioManager - Audio manager instance
     */
    constructor(roundId, stateManager, timer, audioManager) {
        this.roundId = roundId;
        this.stateManager = stateManager;
        this.timer = timer;
        this.audioManager = audioManager;
        this.webSocketManager = null;

        // Track pending objections awaiting ruling
        this.pendingObjections = [];

        // Bind methods
        this.initialize = this.initialize.bind(this);
        this.handleWebSocketMessage = this.handleWebSocketMessage.bind(this);
        this.handleObjectionRaised = this.handleObjectionRaised.bind(this);
        this.handleObjectionRuling = this.handleObjectionRuling.bind(this);
        this.submitObjection = this.submitObjection.bind(this);
        this.submitRuling = this.submitRuling.bind(this);
        this.showRulingModal = this.showRulingModal.bind(this);
        this.closeRulingModal = this.closeRulingModal.bind(this);
        this.handleTimerResumeAfterRuling = this.handleTimerResumeAfterRuling.bind(this);
        this.validateObjection = this.validateObjection.bind(this);
        this.validateRuling = this.validateRuling.bind(this);
        this.getPendingObjection = this.getPendingObjection.bind(this);
        this.cleanup = this.cleanup.bind(this);

        console.log(`[CourtroomRuling] Initialized for round ${roundId}`);
    }

    /**
     * Initialize the ruling system with WebSocket connection.
     * @param {WebSocketManager} webSocketManager - WebSocket manager instance
     */
    initialize(webSocketManager) {
        this.webSocketManager = webSocketManager;

        // Subscribe to WebSocket messages
        this.webSocketManager.onMessage('objection_raised', this.handleWebSocketMessage);
        this.webSocketManager.onMessage('objection_ruling', this.handleWebSocketMessage);

        console.log('[CourtroomRuling] Ruling system initialized with WebSocket');
    }

    /**
     * Handle incoming WebSocket messages.
     * @param {Object} message - WebSocket message
     */
    handleWebSocketMessage(message) {
        const { event, data } = message;

        console.log(`[CourtroomRuling] Received WebSocket message: ${event}`, data);

        switch (event) {
            case 'objection_raised':
                this.handleObjectionRaised(data);
                break;
            case 'objection_ruling':
                this.handleObjectionRuling(data);
                break;
            default:
                console.warn(`[CourtroomRuling] Unknown event: ${event}`);
        }
    }

    /**
     * Handle objection raised event.
     * @param {Object} data - Objection data
     */
    handleObjectionRaised(data) {
        // Add to state
        const objection = {
            id: data.objection_id,
            type: data.objection_type,
            reason: data.objection_text,
            raisedBy: data.raised_by_user_id,
            raisedByTeam: data.raised_by_team_id,
            interruptedSpeaker: data.interrupted_speaker,
            timeRemainingBefore: data.time_remaining_before,
            timestamp: data.timestamp,
            status: 'pending',
            ruling: null,
            rulingNotes: null
        };

        // Add to pending objections
        this.pendingObjections.push(objection);

        // Update state
        const currentObjections = this.stateManager.state.objections;
        this.stateManager.setState({
            objections: [...currentObjections, objection]
        });

        // Play objection audio cue
        this.audioManager.play('objection');

        // Auto-pause timer if running
        if (this.timer && !this.timer.getState().isPaused) {
            this.timer.pause();
        }

        // Show objection notification
        this.showObjectionNotification(objection);

        // If user is judge, show ruling modal
        const auth = window.courtroomAuth;
        if (auth && auth.isJudge()) {
            this.showRulingModal(objection);
        }

        console.log('[CourtroomRuling] Objection raised:', objection);
    }

    /**
     * Handle objection ruling event.
     * @param {Object} data - Ruling data
     */
    handleObjectionRuling(data) {
        // Find the objection
        const objection = this.pendingObjections.find(
            obj => obj.id === data.objection_id
        );

        if (!objection) {
            console.warn('[CourtroomRuling] Ruling for unknown objection:', data.objection_id);
            return;
        }

        // Update objection
        objection.status = 'resolved';
        objection.ruling = data.ruling;
        objection.rulingNotes = data.ruling_reason;
        objection.rulingTimestamp = data.timestamp;

        // Update state
        const currentObjections = this.stateManager.state.objections;
        const updatedObjections = currentObjections.map(obj =>
            obj.id === objection.id ? objection : obj
        );
        this.stateManager.setState({ objections: updatedObjections });

        // Remove from pending
        this.pendingObjections = this.pendingObjections.filter(
            obj => obj.id !== data.objection_id
        );

        // Play ruling audio cue
        if (data.ruling === 'sustained') {
            this.audioManager.play('sustained');
        } else if (data.ruling === 'overruled') {
            this.audioManager.play('overruled');
        }

        // Show ruling notification
        this.showRulingNotification(objection);

        // Auto-resume timer after ruling
        this.handleTimerResumeAfterRuling();

        console.log('[CourtroomRuling] Objection ruled:', objection);
    }

    /**
     * Submit a new objection to the backend.
     * @param {Object} objectionData - Objection data
     * @returns {Promise<Object>} Created objection
     */
    async submitObjection(objectionData) {
        // Validate
        const validation = this.validateObjection(objectionData);
        if (!validation.valid) {
            throw new Error(validation.error);
        }

        try {
            const token = localStorage.getItem('access_token') || '';
            const response = await fetch(
                `/api/oral-rounds/${this.roundId}/objections`,
                {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify(objectionData)
                }
            );

            if (!response.ok) {
                if (response.status === 403) {
                    throw new Error('Permission denied: Cannot raise objection');
                }
                throw new Error(`HTTP ${response.status}`);
            }

            const result = await response.json();

            // Broadcast via WebSocket
            this.webSocketManager.sendMessage({
                event: 'objection_raised',
                data: {
                    objection_id: result.id,
                    objection_type: objectionData.objection_type,
                    objection_text: objectionData.objection_text,
                    raised_by_team_id: objectionData.raised_by_team_id,
                    raised_by_user_id: objectionData.raised_by_user_id,
                    interrupted_speaker: objectionData.interrupted_speaker,
                    time_remaining_before: objectionData.time_remaining_before,
                    timestamp: new Date().toISOString()
                }
            });

            console.log('[CourtroomRuling] Objection submitted:', result);
            return result;

        } catch (error) {
            console.error('[CourtroomRuling] Failed to submit objection:', error);
            throw error;
        }
    }

    /**
     * Submit a ruling on an objection.
     * @param {string} objectionId - Objection ID
     * @param {string} ruling - 'sustained', 'overruled', or 'reserved'
     * @param {string} rulingNotes - Judge's notes
     * @returns {Promise<Object>} Ruling result
     */
    async submitRuling(objectionId, ruling, rulingNotes = '') {
        // Validate
        const validation = this.validateRuling(ruling, rulingNotes);
        if (!validation.valid) {
            throw new Error(validation.error);
        }

        try {
            const token = localStorage.getItem('access_token') || '';
            const response = await fetch(
                `/api/oral-rounds/${this.roundId}/objections/${objectionId}/ruling`,
                {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify({
                        ruling: ruling,
                        ruling_reason: rulingNotes
                    })
                }
            );

            if (!response.ok) {
                if (response.status === 403) {
                    throw new Error('Permission denied: Cannot rule on objection');
                }
                throw new Error(`HTTP ${response.status}`);
            }

            const result = await response.json();

            // Broadcast via WebSocket
            this.webSocketManager.sendMessage({
                event: 'objection_ruling',
                data: {
                    objection_id: objectionId,
                    ruling: ruling,
                    ruling_reason: rulingNotes,
                    timestamp: new Date().toISOString()
                }
            });

            console.log('[CourtroomRuling] Ruling submitted:', result);
            return result;

        } catch (error) {
            console.error('[CourtroomRuling] Failed to submit ruling:', error);
            throw error;
        }
    }

    /**
     * Show the ruling modal for judges.
     * @param {Object} objection - Objection to rule on
     */
    showRulingModal(objection) {
        const modal = document.getElementById('ruling-modal');
        const select = document.getElementById('ruling-select');
        const notes = document.getElementById('ruling-notes');
        const overlay = document.getElementById('modal-overlay');

        if (!modal) return;

        // Set objection reference
        modal.dataset.objectionId = objection.id;

        // Reset form
        if (select) select.value = '';
        if (notes) notes.value = '';

        // Update objection info display
        const objectionInfo = modal.querySelector('.objection-info');
        if (objectionInfo) {
            objectionInfo.innerHTML = `
                <strong>Objection:</strong> ${objection.type}<br>
                <strong>Reason:</strong> ${objection.reason || 'N/A'}<br>
                <strong>Raised by:</strong> ${objection.raisedByTeam}<br>
                <strong>Interrupted:</strong> ${objection.interruptedSpeaker}
            `;
        }

        // Show modal
        modal.style.display = 'block';
        if (overlay) {
            overlay.style.display = 'flex';
            overlay.setAttribute('aria-hidden', 'false');
        }

        // Focus first input
        setTimeout(() => select?.focus(), 100);

        console.log('[CourtroomRuling] Showing ruling modal for:', objection);
    }

    /**
     * Close the ruling modal.
     */
    closeRulingModal() {
        const modal = document.getElementById('ruling-modal');
        const overlay = document.getElementById('modal-overlay');

        if (modal) {
            modal.style.display = 'none';
            modal.dataset.objectionId = '';
        }

        if (overlay) {
            overlay.style.display = 'none';
            overlay.setAttribute('aria-hidden', 'true');
        }
    }

    /**
     * Handle timer auto-resume after ruling.
     */
    handleTimerResumeAfterRuling() {
        // Resume timer if it was paused for this objection
        if (this.timer && this.timer.getState().isPaused) {
            // Small delay to let ruling sink in
            setTimeout(() => {
                this.timer.resume();
                console.log('[CourtroomRuling] Timer auto-resumed after ruling');
            }, 1000);
        }
    }

    /**
     * Validate objection data.
     * @param {Object} data - Objection data
     * @returns {Object} Validation result
     */
    validateObjection(data) {
        const validTypes = ['argumentative', 'leading', 'hearsay', 'relevance', 'other'];

        if (!data.objection_type) {
            return { valid: false, error: 'Objection type is required' };
        }

        if (!validTypes.includes(data.objection_type)) {
            return { valid: false, error: `Invalid objection type: ${data.objection_type}` };
        }

        if (data.objection_text && data.objection_text.length > 200) {
            return { valid: false, error: 'Reason must be 200 characters or less' };
        }

        if (!data.raised_by_team_id || !data.raised_by_user_id) {
            return { valid: false, error: 'User and team information required' };
        }

        return { valid: true };
    }

    /**
     * Validate ruling data.
     * @param {string} ruling - Ruling value
     * @param {string} notes - Ruling notes
     * @returns {Object} Validation result
     */
    validateRuling(ruling, notes) {
        const validRulings = ['sustained', 'overruled', 'reserved'];

        if (!ruling) {
            return { valid: false, error: 'Ruling is required' };
        }

        if (!validRulings.includes(ruling)) {
            return { valid: false, error: `Invalid ruling: ${ruling}` };
        }

        if (notes && notes.length > 500) {
            return { valid: false, error: 'Notes must be 500 characters or less' };
        }

        return { valid: true };
    }

    /**
     * Get a pending objection by ID.
     * @param {string} objectionId - Objection ID
     * @returns {Object|null} Objection or null
     */
    getPendingObjection(objectionId) {
        return this.pendingObjections.find(obj => obj.id === objectionId) || null;
    }

    /**
     * Get all pending objections.
     * @returns {Array} Pending objections
     */
    getAllPendingObjections() {
        return [...this.pendingObjections];
    }

    /**
     * Show objection notification toast.
     * @param {Object} objection - Objection data
     */
    showObjectionNotification(objection) {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = 'objection-notification';
        notification.setAttribute('role', 'alert');
        notification.innerHTML = `
            <div class="notification-content">
                <span class="notification-icon">⚠️</span>
                <div class="notification-text">
                    <strong>Objection Raised!</strong>
                    <span>${objection.type}</span>
                </div>
            </div>
        `;

        // Add to page
        document.body.appendChild(notification);

        // Animate in
        requestAnimationFrame(() => {
            notification.classList.add('show');
        });

        // Auto-remove
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => notification.remove(), 300);
        }, 5000);
    }

    /**
     * Show ruling notification toast.
     * @param {Object} objection - Objection with ruling
     */
    showRulingNotification(objection) {
        const icon = objection.ruling === 'sustained' ? '✅' : '❌';
        const notification = document.createElement('div');
        notification.className = 'ruling-notification';
        notification.setAttribute('role', 'alert');
        notification.innerHTML = `
            <div class="notification-content">
                <span class="notification-icon">${icon}</span>
                <div class="notification-text">
                    <strong>Objection ${objection.ruling.toUpperCase()}</strong>
                    <span>${objection.type}</span>
                </div>
            </div>
        `;

        document.body.appendChild(notification);

        requestAnimationFrame(() => {
            notification.classList.add('show');
        });

        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => notification.remove(), 300);
        }, 5000);
    }

    /**
     * Cleanup resources.
     */
    cleanup() {
        if (this.webSocketManager) {
            this.webSocketManager.offMessage('objection_raised', this.handleWebSocketMessage);
            this.webSocketManager.offMessage('objection_ruling', this.handleWebSocketMessage);
        }
        this.pendingObjections = [];
        console.log('[CourtroomRuling] Cleaned up');
    }
}

// Export for module use
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CourtroomRuling;
}
