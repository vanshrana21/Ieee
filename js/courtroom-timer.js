/**
 * js/courtroom-timer.js
 * Phase 3.1 + WebSocket: Courtroom Timer Logic with Real-Time Sync
 * Handles countdown, color transitions, and WebSocket sync
 */

/**
 * CourtroomWebSocket - WebSocket client for real-time courtroom updates
 */
class CourtroomWebSocket {
    constructor(roundId, token, onMessage) {
        this.roundId = roundId;
        this.token = token;
        this.onMessage = onMessage;
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 3000;
        this.isConnected = false;
    }

    connect() {
        const wsUrl = `ws://localhost:8000/ws/courtroom/${this.roundId}?token=${this.token}`;
        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log("✅ WebSocket connected to courtroom");
            this.isConnected = true;
            this.reconnectAttempts = 0;
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                console.log("📨 WebSocket message:", data);
                if (this.onMessage) {
                    this.onMessage(data);
                }
            } catch (e) {
                console.error("Failed to parse WebSocket message:", e);
            }
        };

        this.ws.onclose = () => {
            console.log("❌ WebSocket disconnected");
            this.isConnected = false;
            this.attemptReconnect();
        };

        this.ws.onerror = (error) => {
            console.error("WebSocket error:", error);
        };
    }

    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            console.log(`🔄 Reconnecting... Attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts}`);
            setTimeout(() => this.connect(), this.reconnectDelay);
        } else {
            console.error("Max reconnect attempts reached");
        }
    }

    sendMessage(type, payload) {
        if (this.isConnected && this.ws) {
            const message = JSON.stringify({ type, ...payload });
            this.ws.send(message);
        } else {
            console.warn("WebSocket not connected, cannot send message");
        }
    }

    disconnect() {
        if (this.ws) {
            this.ws.close();
        }
    }
}

class CourtroomTimer {
    constructor(roundId) {
        this.roundId = roundId;
        this.interval = null;
        this.timeRemaining = 300; // Default 5 minutes
        this.isPaused = true;
        this.currentSpeaker = 'none';
        this.warningPlayed = false;
        this.gavelPlayed = false;
        
        // Audio elements
        this.warningSound = document.getElementById('warning-sound');
        this.gavelSound = document.getElementById('gavel-sound');
        
        // Timer circle constants
        this.circleCircumference = 2 * Math.PI * 90; // r=90
        
        // DOM elements
        this.timerDisplay = document.getElementById('timer-display');
        this.timerProgress = document.getElementById('timer-progress');
        this.speakerLabel = document.getElementById('speaker-label');
        this.petitionerZone = document.getElementById('petitioner-zone');
        this.respondentZone = document.getElementById('respondent-zone');
        this.petitionerStatus = document.getElementById('petitioner-status');
        this.respondentStatus = document.getElementById('respondent-status');
        this.btnPause = document.getElementById('btn-pause');
        this.roundStatus = document.getElementById('round-status');
        this.timerStatus = document.getElementById('timer-status');
        
        // WebSocket
        this.ws = null;
    }

    initWebSocket() {
        const token = localStorage.getItem('access_token') || '';
        this.ws = new CourtroomWebSocket(this.roundId, token, (data) => {
            this.handleWebSocketMessage(data);
        });
        this.ws.connect();
    }

    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'timer_update':
                this.handleTimerUpdate(data);
                break;
            case 'objection_raised':
                this.showObjection(data);
                break;
            case 'objection_ruling':
                this.handleObjectionRuling(data);
                break;
            case 'speaker_change':
                this.handleSpeakerChange(data);
                break;
            case 'score_update':
                this.handleScoreUpdate(data);
                break;
            case 'round_complete':
                this.handleRoundComplete(data);
                break;
            case 'room_state':
                // Initial state sync
                if (data.data) {
                    this.timeRemaining = data.data.time_remaining || 300;
                    this.isPaused = !data.data.timer_running;
                    this.currentSpeaker = data.data.current_speaker || 'none';
                    this.updateDisplay();
                    this.updateSpeakerUI();
                }
                break;
        }
    }

    handleTimerUpdate(data) {
        this.timeRemaining = data.time_remaining || this.timeRemaining;
        
        if (data.action === 'start') {
            this.isPaused = false;
            this.currentSpeaker = data.speaker_role || this.currentSpeaker;
            this.warningPlayed = false;
            this.gavelPlayed = false;
            this.startInterval();
        } else if (data.action === 'pause') {
            this.isPaused = true;
            this.stopInterval();
        } else if (data.action === 'reset') {
            this.isPaused = true;
            this.stopInterval();
        }
        
        this.updateDisplay();
        this.updateSpeakerUI();
        this.updateButtonState();
        this.updateStatusText();
    }

    handleSpeakerChange(data) {
        this.currentSpeaker = data.new_speaker || 'none';
        this.timeRemaining = data.new_time_remaining || 300;
        this.warningPlayed = false;
        this.gavelPlayed = false;
        this.updateDisplay();
        this.updateSpeakerUI();
    }

    showObjection(data) {
        // Show objection notification
        const notification = document.createElement('div');
        notification.className = 'objection-notification';
        notification.innerHTML = `
            <div class="objection-content">
                <h4>⚠️ OBJECTION RAISED</h4>
                <p><strong>${data.objection_type}</strong> by ${data.raised_by_role}</p>
                ${data.reason ? `<p>Reason: ${data.reason}</p>` : ''}
            </div>
        `;
        document.body.appendChild(notification);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            notification.remove();
        }, 5000);
        
        // Pause timer if running
        if (!this.isPaused) {
            this.togglePause();
        }
    }

    handleObjectionRuling(data) {
        const ruling = data.ruling === 'sustained' ? '✅ SUSTAINED' : '❌ OVERRULED';
        alert(`Objection ${ruling}\n${data.ruling_reason || ''}`);
    }

    handleScoreUpdate(data) {
        console.log("Score updated:", data);
        // Update score display if exists
        const scoreEl = document.getElementById(`score-${data.team_id}`);
        if (scoreEl) {
            scoreEl.textContent = data.score;
        }
    }

    handleRoundComplete(data) {
        this.stopInterval();
        this.isPaused = true;
        this.updateButtonState();
        this.updateStatus('completed');
        alert('Round completed! Final scores: ' + JSON.stringify(data.final_scores));
    }

    async loadState() {
        // Initial state load via REST API, then WebSocket takes over
        try {
            const token = localStorage.getItem('access_token') || '';
            const response = await fetch(`http://localhost:8000/api/oral-rounds/${this.roundId}/timer/state`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            
            if (response.ok) {
                const state = await response.json();
                this.timeRemaining = state.time_remaining || 300;
                this.isPaused = state.is_paused;
                this.currentSpeaker = state.current_speaker;
                
                this.updateDisplay();
                this.updateSpeakerUI();
                this.updateStatus(state.status);
                
                // If timer is running, start local countdown
                if (!this.isPaused && this.currentSpeaker !== 'none') {
                    this.startInterval();
                }
            } else {
                console.log('Timer state not available, using defaults');
                this.updateDisplay();
            }
        } catch (error) {
            console.error('Failed to load timer state:', error);
            this.updateDisplay();
        }
        
        // Initialize WebSocket for real-time updates
        this.initWebSocket();
    }

    async start(speakerRole) {
        // Send via WebSocket instead of HTTP
        if (this.ws && this.ws.isConnected) {
            this.ws.sendMessage('timer_start', {
                speaker_role: speakerRole,
                time_remaining: 300,
                timestamp: Date.now()
            });
        } else {
            // Fallback to HTTP if WebSocket not ready
            this.startHTTP(speakerRole);
        }
    }

    async startHTTP(speakerRole) {
        // HTTP fallback
        try {
            const token = localStorage.getItem('access_token') || '';
            const response = await fetch(`http://localhost:8000/api/oral-rounds/${this.roundId}/timer/start`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ speaker_role: speakerRole })
            });
            
            if (response.ok) {
                const data = await response.json();
                this.timeRemaining = data.time_remaining;
                this.currentSpeaker = speakerRole;
                this.isPaused = false;
                this.warningPlayed = false;
                this.gavelPlayed = false;
                
                this.updateDisplay();
                this.updateSpeakerUI();
                this.startInterval();
                this.updateButtonState();
            } else if (response.status === 403) {
                alert('Only judges and admins can control the timer.');
            }
        } catch (error) {
            console.error('Error starting timer:', error);
        }
    }

    async togglePause() {
        const newPauseState = !this.isPaused;
        
        // Send via WebSocket
        if (this.ws && this.ws.isConnected) {
            this.ws.sendMessage(newPauseState ? 'timer_pause' : 'timer_start', {
                time_remaining: this.timeRemaining,
                timestamp: Date.now()
            });
        } else {
            // Fallback to HTTP
            this.togglePauseHTTP(newPauseState);
        }
    }

    async togglePauseHTTP(newPauseState) {
        try {
            const token = localStorage.getItem('access_token') || '';
            const response = await fetch(`http://localhost:8000/api/oral-rounds/${this.roundId}/timer/pause`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ is_paused: newPauseState })
            });
            
            if (response.ok) {
                this.isPaused = newPauseState;
                
                if (this.isPaused) {
                    this.stopInterval();
                } else {
                    this.startInterval();
                }
                
                this.updateButtonState();
                this.updateStatusText();
            } else if (response.status === 403) {
                alert('Only judges and admins can control the timer.');
            }
        } catch (error) {
            console.error('Error toggling pause:', error);
        }
    }

    async complete() {
        if (!confirm('Are you sure you want to complete this round?')) {
            return;
        }
        
        // Send via WebSocket
        if (this.ws && this.ws.isConnected) {
            this.ws.sendMessage('round_complete', {
                final_scores: {},
                timestamp: Date.now()
            });
        } else {
            this.completeHTTP();
        }
    }

    async completeHTTP() {
        try {
            const token = localStorage.getItem('access_token') || '';
            const response = await fetch(`http://localhost:8000/api/oral-rounds/${this.roundId}/timer/complete`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            
            if (response.ok) {
                this.stopInterval();
                this.isPaused = true;
                this.currentSpeaker = 'none';
                this.updateDisplay();
                this.updateSpeakerUI();
                this.updateButtonState();
                this.updateStatus('completed');
                alert('Round completed successfully!');
            } else if (response.status === 403) {
                alert('Only judges and admins can complete the round.');
            }
        } catch (error) {
            console.error('Error completing round:', error);
        }
    }

    raiseObjection(objectionType, reason) {
        if (this.ws && this.ws.isConnected) {
            this.ws.sendMessage('objection_raised', {
                objection_type: objectionType,
                reason: reason,
                timestamp: Date.now()
            });
        } else {
            alert('WebSocket not connected. Cannot raise objection.');
        }
    }

    ruleOnObjection(objectionId, ruling, reason, penalty) {
        if (this.ws && this.ws.isConnected) {
            this.ws.sendMessage('objection_ruling', {
                objection_id: objectionId,
                ruling: ruling,
                ruling_reason: reason,
                penalty_applied: penalty,
                timestamp: Date.now()
            });
        }
    }

    changeSpeaker(newSpeaker) {
        if (this.ws && this.ws.isConnected) {
            this.ws.sendMessage('speaker_change', {
                previous_speaker: this.currentSpeaker,
                new_speaker: newSpeaker,
                new_time_remaining: 300,
                timestamp: Date.now()
            });
        }
    }

    reset() {
        // Local reset - doesn't affect backend
        this.stopInterval();
        this.timeRemaining = 300;
        this.isPaused = true;
        this.currentSpeaker = 'none';
        this.warningPlayed = false;
        this.gavelPlayed = false;
        this.updateDisplay();
        this.updateSpeakerUI();
        this.updateButtonState();
    }

    startInterval() {
        this.stopInterval();
        this.interval = setInterval(() => this.tick(), 1000);
    }

    stopInterval() {
        if (this.interval) {
            clearInterval(this.interval);
            this.interval = null;
        }
    }

    tick() {
        if (this.isPaused || this.timeRemaining <= 0) {
            return;
        }
        
        this.timeRemaining--;
        this.updateDisplay();
        this.checkAudioCues();
        
        // Auto-stop at 0
        if (this.timeRemaining <= 0) {
            this.timeRemaining = 0;
            this.isPaused = true;
            this.stopInterval();
            this.updateButtonState();
        }
    }

    checkAudioCues() {
        // Warning beep at 120 seconds (2 minutes)
        if (this.timeRemaining <= 120 && !this.warningPlayed && this.warningSound) {
            this.warningSound.play().catch(e => console.log('Audio play failed:', e));
            this.warningPlayed = true;
        }
        
        // Gavel sound at 0 seconds
        if (this.timeRemaining <= 0 && !this.gavelPlayed && this.gavelSound) {
            this.gavelSound.play().catch(e => console.log('Audio play failed:', e));
            this.gavelPlayed = true;
        }
    }

    updateDisplay() {
        // Format time as MM:SS
        const minutes = Math.floor(this.timeRemaining / 60);
        const seconds = this.timeRemaining % 60;
        const formatted = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
        
        if (this.timerDisplay) {
            this.timerDisplay.textContent = formatted;
        }
        
        // Update progress circle
        if (this.timerProgress) {
            const offset = this.circleCircumference - (this.timeRemaining / 300) * this.circleCircumference;
            this.timerProgress.style.strokeDashoffset = offset;
            
            // Update color based on time remaining
            this.timerProgress.classList.remove('timer-green', 'timer-yellow', 'timer-red');
            
            if (this.timeRemaining <= 30) {
                this.timerProgress.classList.add('timer-red');
            } else if (this.timeRemaining <= 120) {
                this.timerProgress.classList.add('timer-yellow');
            } else {
                this.timerProgress.classList.add('timer-green');
            }
        }
        
        // Update speaker label
        if (this.speakerLabel) {
            this.speakerLabel.textContent = this.currentSpeaker === 'none' ? 'READY' : this.currentSpeaker.toUpperCase();
        }
    }

    updateSpeakerUI() {
        // Reset zones
        this.petitionerZone?.classList.remove('active');
        this.respondentZone?.classList.remove('active');
        
        if (this.petitionerStatus) {
            this.petitionerStatus.textContent = 'Waiting...';
            this.petitionerStatus.classList.remove('speaking');
        }
        
        if (this.respondentStatus) {
            this.respondentStatus.textContent = 'Waiting...';
            this.respondentStatus.classList.remove('speaking');
        }
        
        // Highlight active speaker
        if (this.currentSpeaker === 'petitioner') {
            this.petitionerZone?.classList.add('active');
            if (this.petitionerStatus) {
                this.petitionerStatus.textContent = 'Speaking Now';
                this.petitionerStatus.classList.add('speaking');
            }
        } else if (this.currentSpeaker === 'respondent') {
            this.respondentZone?.classList.add('active');
            if (this.respondentStatus) {
                this.respondentStatus.textContent = 'Speaking Now';
                this.respondentStatus.classList.add('speaking');
            }
        }
    }

    updateButtonState() {
        if (this.btnPause) {
            this.btnPause.textContent = this.isPaused ? '▶ Resume' : '⏸ Pause';
        }
    }

    updateStatusText() {
        if (this.timerStatus) {
            if (this.isPaused) {
                this.timerStatus.textContent = 'Timer: Paused';
            } else if (this.currentSpeaker !== 'none') {
                this.timerStatus.textContent = `Timer: Running (${this.currentSpeaker})`;
            } else {
                this.timerStatus.textContent = 'Timer: Ready';
            }
        }
    }

    updateStatus(status) {
        if (this.roundStatus) {
            const formatted = status.replace('_', ' ').toUpperCase();
            this.roundStatus.textContent = `Round Status: ${formatted}`;
        }
        this.updateStatusText();
    }

    async syncState() {
        // Sync current state to backend every 5 seconds
        // This ensures timer continues correctly if page refreshes
        try {
            const token = localStorage.getItem('access_token') || '';
            const response = await fetch(`http://localhost:8000/api/oral-rounds/${this.roundId}/timer/state`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            
            if (response.ok) {
                const state = await response.json();
                // Only update if backend has different info and we're not currently running
                if (this.isPaused && state.time_remaining !== this.timeRemaining) {
                    this.timeRemaining = state.time_remaining;
                    this.updateDisplay();
                }
            }
        } catch (error) {
            // Silent fail - timer continues locally
            console.log('Sync failed, continuing locally');
        }
    }

    destroy() {
        this.stopInterval();
        // Disconnect WebSocket
        if (this.ws) {
            this.ws.disconnect();
        }
    }
}

// Handle page unload
window.addEventListener('beforeunload', () => {
    if (window.timer) {
        window.timer.destroy();
    }
});
