/**
 * Phase 1 + 2: Virtual Courtroom Infrastructure - UI Controller
 * 
 * Renders and updates courtroom UI based on state changes.
 * Integrates Phase 2 real-time functionality: timer, audio cues, objection workflow, transcript recording.
 */

class CourtroomUI {
    /**
     * Creates a new CourtroomUI instance.
     * @param {number} roundId - The round ID to manage UI for
     */
    constructor(roundId) {
        this.roundId = roundId;
        this.stateManager = new CourtroomState(roundId);
        this.persistence = new CourtroomStatePersistence('courtroom');
        this.auth = new CourtroomAuth(this.persistence);
        this.errorHandler = new CourtroomErrorHandler(this.stateManager);
        
        // Phase 2: Real-time components
        this.audioManager = new CourtroomAudio();
        this.timer = new CourtroomTimer(roundId, this.stateManager, this.audioManager);
        this.rulingSystem = new CourtroomRuling(roundId, this.stateManager, this.timer, this.audioManager);
        this.transcriptRecorder = new TranscriptRecorder(roundId, this.stateManager);
        this.webSocketManager = null;
        
        // UI state tracking
        this.autoScrollEnabled = true;
        this.currentScoringTeam = 'petitioner';
        
        // DOM element references (cached for performance)
        this.elements = {};
        
        // Bind methods
        this.initialize = this.initialize.bind(this);
        this.cacheElements = this.cacheElements.bind(this);
        this.initializeEventListeners = this.initializeEventListeners.bind(this);
        this.subscribeToState = this.subscribeToState.bind(this);
        
        // State update handlers
        this.updateTimer = this.updateTimer.bind(this);
        this.updateObjections = this.updateObjections.bind(this);
        this.updateTranscript = this.updateTranscript.bind(this);
        this.updateScores = this.updateScores.bind(this);
        this.updateUI = this.updateUI.bind(this);
        
        // Event handlers
        this.handleStartTimer = this.handleStartTimer.bind(this);
        this.handlePauseTimer = this.handlePauseTimer.bind(this);
        this.handleResetTimer = this.handleResetTimer.bind(this);
        this.handleRaiseObjection = this.handleRaiseObjection.bind(this);
        this.handleSubmitObjection = this.handleSubmitObjection.bind(this);
        this.handleCancelObjection = this.handleCancelObjection.bind(this);
        this.handleClearTranscript = this.handleClearTranscript.bind(this);
        this.handleDownloadTranscript = this.handleDownloadTranscript.bind(this);
        this.handleToggleAutoScroll = this.handleToggleAutoScroll.bind(this);
        
        // Modal handlers
        this.showObjectionModal = this.showObjectionModal.bind(this);
        this.closeObjectionModal = this.closeObjectionModal.bind(this);
        this.showErrorModal = this.showErrorModal.bind(this);
        this.closeErrorModal = this.closeErrorModal.bind(this);
        this.showRulingModal = this.showRulingModal.bind(this);
        this.closeRulingModal = this.closeRulingModal.bind(this);
        this.showScoringModal = this.showScoringModal.bind(this);
        this.closeScoringModal = this.closeScoringModal.bind(this);
        
        // Helper methods
        this.formatTime = this.formatTime.bind(this);
        this.checkScreenSize = this.checkScreenSize.bind(this);
        this.cleanup = this.cleanup.bind(this);
        
        console.log(`[CourtroomUI] Initialized for round ${roundId}`);
    }
    
    /**
     * Initialize the UI - cache elements, setup listeners, subscribe to state, init Phase 2 components.
     */
    async initialize() {
        // Initialize audio manager first (user interaction required)
        await this.audioManager.initialize();
        
        // Cache DOM elements
        this.cacheElements();
        
        // Check screen size
        this.checkScreenSize();
        window.addEventListener('resize', this.checkScreenSize);
        
        // Setup event listeners
        this.initializeEventListeners();
        
        // Initialize WebSocket and Phase 2 components
        await this.initializeWebSocket();
        
        // Subscribe to state changes
        this.subscribeToState();
        
        // Initialize auth
        const user = await this.auth.initialize();
        if (user) {
            this.stateManager.initialize(user, {
                competitionId: 1,
                roundNumber: this.roundId,
                status: 'scheduled'
            });
            this.updateUI();
        }
        
        // Keyboard shortcuts
        this.initializeKeyboardShortcuts();
        
        console.log('[CourtroomUI] UI initialized with Phase 2 components');
    }
    
    /**
     * Initialize WebSocket connection and Phase 2 components.
     */
    async initializeWebSocket() {
        const token = localStorage.getItem('access_token') || '';
        
        // Create WebSocket manager
        this.webSocketManager = new CourtroomWebSocket(this.roundId, token, (data) => {
            this.handleWebSocketMessage(data);
        });
        
        // Connect
        this.webSocketManager.connect();
        
        // Initialize Phase 2 components with WebSocket
        this.timer.initialize(this.webSocketManager);
        this.rulingSystem.initialize(this.webSocketManager);
        this.transcriptRecorder.initialize(this.webSocketManager);
        
        console.log('[CourtroomUI] WebSocket and Phase 2 components initialized');
    }
    
    /**
     * Handle incoming WebSocket messages.
     * @param {Object} data - WebSocket message data
     */
    handleWebSocketMessage(data) {
        console.log('[CourtroomUI] WebSocket message:', data);
        
        switch (data.type || data.event) {
            case 'timer_update':
                // Handled by CourtroomTimer
                break;
            case 'objection_raised':
                // Handled by CourtroomRuling
                break;
            case 'objection_ruling':
                // Handled by CourtroomRuling
                break;
            case 'transcript_update':
                // Handled by TranscriptRecorder
                break;
            case 'connection_status':
                this.stateManager.updateConnection(data.status === 'connected', data.participants);
                break;
            case 'error':
                this.errorHandler.showToast(data.message, 'error');
                break;
            default:
                console.log('[CourtroomUI] Unhandled message type:', data.type || data.event);
        }
    }
    
    /**
     * Cache DOM element references for performance.
     */
    cacheElements() {
        // Header elements
        this.elements.roundNumber = document.getElementById('round-number');
        this.elements.caseTitle = document.getElementById('case-title');
        this.elements.scheduledTime = document.getElementById('scheduled-time');
        this.elements.roundStatus = document.getElementById('round-status');
        this.elements.presidingJudge = document.getElementById('presiding-judge');
        
        // Participant zones
        this.elements.petitionerZone = document.getElementById('petitioner-zone');
        this.elements.petitionerTeamName = document.getElementById('petitioner-team-name');
        this.elements.petitionerName = document.getElementById('petitioner-name');
        this.elements.petitionerTime = document.getElementById('petitioner-time');
        this.elements.petitionerScore = document.getElementById('petitioner-score');
        
        this.elements.respondentZone = document.getElementById('respondent-zone');
        this.elements.respondentTeamName = document.getElementById('respondent-team-name');
        this.elements.respondentName = document.getElementById('respondent-name');
        this.elements.respondentTime = document.getElementById('respondent-time');
        this.elements.respondentScore = document.getElementById('respondent-score');
        
        // Timer elements
        this.elements.timerDisplay = document.getElementById('timer-display');
        this.elements.timerProgress = document.getElementById('timer-progress');
        this.elements.timerText = document.getElementById('timer-text');
        this.elements.timerLabel = document.getElementById('timer-label');
        
        // Controls
        this.elements.judgeControls = document.getElementById('judge-controls');
        this.elements.startPetitioner = document.getElementById('start-petitioner');
        this.elements.startRespondent = document.getElementById('start-respondent');
        this.elements.pauseTimer = document.getElementById('pause-timer');
        this.elements.resetTimer = document.getElementById('reset-timer');
        
        this.elements.objectionControls = document.getElementById('objection-controls');
        this.elements.raiseObjection = document.getElementById('raise-objection');
        
        // Connection status
        this.elements.connectionStatus = document.getElementById('connection-status');
        this.elements.statusIndicator = document.getElementById('status-indicator');
        this.elements.statusText = document.getElementById('status-text');
        
        // Transcript
        this.elements.transcriptContent = document.getElementById('transcript-content');
        this.elements.clearTranscript = document.getElementById('clear-transcript');
        this.elements.downloadTranscript = document.getElementById('download-transcript');
        this.elements.toggleAutoScroll = document.getElementById('toggle-auto-scroll');
        
        // Modals
        this.elements.modalOverlay = document.getElementById('modal-overlay');
        this.elements.objectionModal = document.getElementById('objection-modal');
        this.elements.errorModal = document.getElementById('error-modal');
        this.elements.rulingModal = document.getElementById('ruling-modal');
        this.elements.scoringModal = document.getElementById('scoring-modal');
        
        // Objection form
        this.elements.objectionType = document.getElementById('objection-type');
        this.elements.objectionReason = document.getElementById('objection-reason');
        this.elements.charCount = document.getElementById('char-count');
        this.elements.submitObjection = document.getElementById('submit-objection');
        this.elements.cancelObjection = document.getElementById('cancel-objection');
        this.elements.closeObjectionModal = document.getElementById('close-objection-modal');
        
        // Error modal
        this.elements.errorMessage = document.getElementById('error-message');
        this.elements.closeError = document.getElementById('close-error');
        this.elements.closeErrorModal = document.getElementById('close-error-modal');
        
        // Ruling modal
        this.elements.rulingSelect = document.getElementById('ruling-select');
        this.elements.rulingNotes = document.getElementById('ruling-notes');
        this.elements.submitRuling = document.getElementById('submit-ruling');
        this.elements.deferRuling = document.getElementById('defer-ruling');
        this.elements.closeRulingModal = document.getElementById('close-ruling-modal');
        
        // Scoring modal
        this.elements.tabPetitioner = document.getElementById('tab-petitioner');
        this.elements.tabRespondent = document.getElementById('tab-respondent');
        this.elements.totalScore = document.getElementById('total-score');
        this.elements.submitScores = document.getElementById('submit-scores');
        this.elements.saveDraft = document.getElementById('save-draft');
        this.elements.closeScoringModal = document.getElementById('close-scoring-modal');
        
        // Scoring sliders
        this.elements.scoreSliders = {
            legalReasoning: document.getElementById('score-legal-reasoning'),
            citation: document.getElementById('score-citation'),
            etiquette: document.getElementById('score-etiquette'),
            responsiveness: document.getElementById('score-responsiveness'),
            time: document.getElementById('score-time')
        };
        
        this.elements.scoreValues = {
            legalReasoning: document.getElementById('value-legal-reasoning'),
            citation: document.getElementById('value-citation'),
            etiquette: document.getElementById('value-etiquette'),
            responsiveness: document.getElementById('value-responsiveness'),
            time: document.getElementById('value-time')
        };
        
        // Loading overlay
        this.elements.loadingOverlay = document.getElementById('loading-overlay');
        this.elements.loadingMessage = document.getElementById('loading-message');
        
        // Screen warning
        this.elements.screenWarning = document.getElementById('screen-warning');
    }
    
    /**
     * Initialize event listeners for all interactive elements.
     */
    initializeEventListeners() {
        // Judge controls
        if (this.elements.startPetitioner) {
            this.elements.startPetitioner.addEventListener('click', () => this.handleStartTimer('petitioner'));
        }
        if (this.elements.startRespondent) {
            this.elements.startRespondent.addEventListener('click', () => this.handleStartTimer('respondent'));
        }
        if (this.elements.pauseTimer) {
            this.elements.pauseTimer.addEventListener('click', this.handlePauseTimer);
        }
        if (this.elements.resetTimer) {
            this.elements.resetTimer.addEventListener('click', this.handleResetTimer);
        }
        
        // Objection controls
        if (this.elements.raiseObjection) {
            this.elements.raiseObjection.addEventListener('click', this.handleRaiseObjection);
        }
        if (this.elements.submitObjection) {
            this.elements.submitObjection.addEventListener('click', this.handleSubmitObjection);
        }
        if (this.elements.cancelObjection) {
            this.elements.cancelObjection.addEventListener('click', this.handleCancelObjection);
        }
        if (this.elements.closeObjectionModal) {
            this.elements.closeObjectionModal.addEventListener('click', this.closeObjectionModal);
        }
        
        // Character counter for objection reason
        if (this.elements.objectionReason) {
            this.elements.objectionReason.addEventListener('input', (e) => {
                const count = e.target.value.length;
                this.elements.charCount.textContent = count;
            });
        }
        
        // Transcript controls
        if (this.elements.clearTranscript) {
            this.elements.clearTranscript.addEventListener('click', this.handleClearTranscript);
        }
        if (this.elements.downloadTranscript) {
            this.elements.downloadTranscript.addEventListener('click', this.handleDownloadTranscript);
        }
        if (this.elements.toggleAutoScroll) {
            this.elements.toggleAutoScroll.addEventListener('click', this.handleToggleAutoScroll);
        }
        
        // Error modal
        if (this.elements.closeError) {
            this.elements.closeError.addEventListener('click', this.closeErrorModal);
        }
        if (this.elements.closeErrorModal) {
            this.elements.closeErrorModal.addEventListener('click', this.closeErrorModal);
        }
        
        // Ruling modal
        if (this.elements.closeRulingModal) {
            this.elements.closeRulingModal.addEventListener('click', this.closeRulingModal);
        }
        if (this.elements.deferRuling) {
            this.elements.deferRuling.addEventListener('click', this.closeRulingModal);
        }
        
        // Scoring modal tabs
        if (this.elements.tabPetitioner) {
            this.elements.tabPetitioner.addEventListener('click', () => this.switchScoringTab('petitioner'));
        }
        if (this.elements.tabRespondent) {
            this.elements.tabRespondent.addEventListener('click', () => this.switchScoringTab('respondent'));
        }
        
        // Scoring sliders
        Object.keys(this.elements.scoreSliders).forEach(key => {
            const slider = this.elements.scoreSliders[key];
            const valueDisplay = this.elements.scoreValues[key];
            if (slider && valueDisplay) {
                slider.addEventListener('input', (e) => {
                    valueDisplay.textContent = e.target.value;
                    this.updateTotalScore();
                });
            }
        });
        
        // Close modals on overlay click
        if (this.elements.modalOverlay) {
            this.elements.modalOverlay.addEventListener('click', (e) => {
                if (e.target === this.elements.modalOverlay) {
                    this.closeAllModals();
                }
            });
        }
        
        // Escape key to close modals
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeAllModals();
            }
        });
    }
    
    /**
     * Initialize keyboard shortcuts.
     */
    initializeKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Alt + O to raise objection
            if (e.altKey && e.key === 'o') {
                e.preventDefault();
                if (this.auth.hasPermission('raise_objection')) {
                    this.showObjectionModal();
                }
            }
        });
    }
    
    /**
     * Subscribe to state changes.
     */
    subscribeToState() {
        this.stateManager.subscribe((newState, prevState) => {
            // Timer updates
            if (newState.timer !== prevState.timer) {
                this.updateTimer(newState.timer);
            }
            
            // Objections updates
            if (newState.objections !== prevState.objections) {
                this.updateObjections(newState.objections);
            }
            
            // Transcript updates
            if (newState.transcript !== prevState.transcript) {
                this.updateTranscript(newState.transcript);
            }
            
            // Score updates
            if (newState.scores !== prevState.scores) {
                this.updateScores(newState.scores);
            }
            
            // Connection updates
            if (newState.connection !== prevState.connection) {
                this.updateConnectionStatus(newState.connection);
            }
            
            // UI state updates
            if (newState.ui !== prevState.ui) {
                this.updateUIState(newState.ui);
            }
        });
    }
    
    /**
     * Update timer display.
     * @param {Object} timerState - Timer state object
     */
    updateTimer(timerState) {
        const { timeRemaining, isPaused, currentSpeaker } = timerState;
        
        // Update text
        if (this.elements.timerText) {
            this.elements.timerText.textContent = this.formatTime(timeRemaining || 900);
        }
        
        // Update label
        if (this.elements.timerLabel) {
            const speakerLabels = {
                'petitioner': 'Petitioner',
                'respondent': 'Respondent',
                'judge': 'Judge',
                'none': 'Ready'
            };
            this.elements.timerLabel.textContent = speakerLabels[currentSpeaker] || 'Ready';
        }
        
        // Update progress ring
        if (this.elements.timerProgress && timeRemaining !== null) {
            const maxTime = 900; // 15 minutes in seconds
            const circumference = 283; // 2 * PI * 45
            const progress = timeRemaining / maxTime;
            const offset = circumference * (1 - progress);
            this.elements.timerProgress.style.strokeDashoffset = offset;
            
            // Update color based on time remaining
            this.elements.timerProgress.classList.remove('warning', 'critical');
            if (timeRemaining <= 30) {
                this.elements.timerProgress.classList.add('critical');
            } else if (timeRemaining <= 120) {
                this.elements.timerProgress.classList.add('warning');
            }
        }
        
        // Update zone highlights
        if (this.elements.petitionerZone) {
            this.elements.petitionerZone.classList.toggle('active', currentSpeaker === 'petitioner');
        }
        if (this.elements.respondentZone) {
            this.elements.respondentZone.classList.toggle('active', currentSpeaker === 'respondent');
        }
    }
    
    /**
     * Update objections display.
     * @param {Array} objections - Array of objection objects
     */
    updateObjections(objections) {
        // Phase 1: Visual only - no dynamic objection display yet
        console.log('[CourtroomUI] Objections updated:', objections);
    }
    
    /**
     * Update transcript display.
     * @param {Array} transcript - Array of transcript segments
     */
    updateTranscript(transcript) {
        if (!this.elements.transcriptContent) return;
        
        // Clear existing content
        this.elements.transcriptContent.innerHTML = '';
        
        // Render each entry
        transcript.forEach(entry => {
            const article = document.createElement('article');
            article.className = `transcript-entry ${entry.speakerRole || 'system'}`;
            
            const timestamp = document.createElement('span');
            timestamp.className = 'timestamp';
            timestamp.textContent = entry.timestamp || '[00:00:00]';
            
            const speaker = document.createElement('span');
            speaker.className = 'speaker';
            speaker.textContent = `${entry.speaker || 'System'}:`;
            
            const message = document.createElement('span');
            message.className = 'message';
            message.textContent = entry.text || entry.message || '';
            
            article.appendChild(timestamp);
            article.appendChild(speaker);
            article.appendChild(message);
            this.elements.transcriptContent.appendChild(article);
        });
        
        // Auto-scroll to bottom
        if (this.autoScrollEnabled) {
            this.elements.transcriptContent.scrollTop = this.elements.transcriptContent.scrollHeight;
        }
    }
    
    /**
     * Update scores display.
     * @param {Array} scores - Array of score objects
     */
    updateScores(scores) {
        // Calculate totals for each team
        const petitionerScores = scores.filter(s => s.teamSide === 'petitioner' && s.isSubmitted);
        const respondentScores = scores.filter(s => s.teamSide === 'respondent' && s.isSubmitted);
        
        // Calculate averages
        const calculateAverage = (teamScores) => {
            if (teamScores.length === 0) return null;
            const total = teamScores.reduce((sum, s) => sum + s.totalScore, 0);
            return (total / teamScores.length).toFixed(1);
        };
        
        const petitionerAvg = calculateAverage(petitionerScores);
        const respondentAvg = calculateAverage(respondentScores);
        
        // Update displays
        if (this.elements.petitionerScore) {
            this.elements.petitionerScore.textContent = petitionerAvg || '-';
        }
        if (this.elements.respondentScore) {
            this.elements.respondentScore.textContent = respondentAvg || '-';
        }
    }
    
    /**
     * Update connection status display.
     * @param {Object} connection - Connection state object
     */
    updateConnectionStatus(connection) {
        if (!this.elements.statusIndicator || !this.elements.statusText) return;
        
        this.elements.statusIndicator.classList.remove('connected', 'disconnected', 'connecting');
        
        if (connection.isConnected) {
            this.elements.statusIndicator.classList.add('connected');
            this.elements.statusText.textContent = `Connected (${connection.participants.length} online)`;
        } else {
            this.elements.statusIndicator.classList.add('disconnected');
            this.elements.statusText.textContent = 'Disconnected';
        }
    }
    
    /**
     * Update UI based on role and permissions.
     */
    updateUI() {
        const user = this.auth.getCurrentUser();
        
        if (!user) return;
        
        // Show/hide judge controls
        if (this.elements.judgeControls) {
            this.elements.judgeControls.hidden = !this.auth.isJudge();
        }
        
        // Show/hide objection button
        if (this.elements.raiseObjection) {
            this.elements.raiseObjection.hidden = !this.auth.hasPermission('raise_objection');
        }
        
        // Show/hide objection hint
        if (this.elements.objectionControls) {
            this.elements.objectionControls.hidden = !this.auth.hasPermission('raise_objection');
        }
        
        console.log(`[CourtroomUI] UI updated for role: ${user.role}`);
    }
    
    /**
     * Update UI state (loading, errors, etc).
     * @param {Object} uiState - UI state object
     */
    updateUIState(uiState) {
        // Show/hide loading overlay
        if (this.elements.loadingOverlay) {
            this.elements.loadingOverlay.hidden = !uiState.isLoading;
            this.elements.loadingOverlay.setAttribute('aria-hidden', !uiState.isLoading);
        }
        
        // Show error modal if error message exists
        if (uiState.errorMessage) {
            this.showErrorModal(uiState.errorMessage);
        }
    }
    
    /**
     * Handle start timer button click - Phase 2: Delegates to timer.
     * @param {string} speaker - 'petitioner' or 'respondent'
     */
    handleStartTimer(speaker) {
        console.log(`[CourtroomUI] Start timer clicked for ${speaker}`);
        this.timer.start(speaker);
    }
    
    /**
     * Handle pause timer button click - Phase 2: Delegates to timer.
     */
    handlePauseTimer() {
        console.log('[CourtroomUI] Pause timer clicked');
        const currentTimer = this.stateManager.state.timer;
        if (currentTimer.isPaused) {
            this.timer.resume();
        } else {
            this.timer.pause();
        }
    }
    
    /**
     * Handle reset timer button click - Phase 2: Delegates to timer.
     */
    handleResetTimer() {
        console.log('[CourtroomUI] Reset timer clicked');
        this.timer.reset();
    }
    
    /**
     * Handle raise objection button click.
     */
    handleRaiseObjection() {
        if (!this.auth.hasPermission('raise_objection')) {
            this.errorHandler.showToast('You do not have permission to raise objections', 'error');
            return;
        }
        this.showObjectionModal();
    }
    
    /**
     * Handle submit objection button click - Phase 2: Full workflow.
     */
    async handleSubmitObjection() {
        const type = this.elements.objectionType?.value;
        const reason = this.elements.objectionReason?.value;
        
        if (!type) {
            this.errorHandler.showToast('Please select an objection type', 'warning');
            return;
        }
        
        // Get current timer state
        const timerState = this.stateManager.state.timer;
        
        // Create objection data
        const objectionData = {
            round_id: this.roundId,
            objection_type: type,
            objection_text: reason || '',
            raised_by_team_id: this.auth.getTeamId(),
            raised_by_user_id: this.auth.getUserId(),
            interrupted_speaker: timerState.currentSpeaker,
            time_remaining_before: timerState.timeRemaining
        };
        
        try {
            // Submit through ruling system
            await this.rulingSystem.submitObjection(objectionData);
            
            this.closeObjectionModal();
            this.errorHandler.showToast('Objection raised!', 'success');
        } catch (error) {
            console.error('[CourtroomUI] Failed to submit objection:', error);
            this.errorHandler.showToast(error.message || 'Failed to raise objection', 'error');
        }
    }
    
    /**
     * Handle cancel objection button click.
     */
    handleCancelObjection() {
        this.closeObjectionModal();
    }
    
    /**
     * Handle clear transcript button click.
     */
    handleClearTranscript() {
        // Keep only the system message
        const systemEntry = {
            timestamp: new Date().toLocaleTimeString(),
            speaker: 'System',
            text: 'Transcript cleared.',
            speakerRole: 'system'
        };
        this.stateManager.setState({ transcript: [systemEntry] });
    }
    
    /**
     * Handle download transcript button click.
     */
    handleDownloadTranscript() {
        const transcript = this.stateManager.state.transcript;
        let content = 'COURTROOM TRANSCRIPT\n';
        content += `Round: ${this.roundId}\n`;
        content += `Date: ${new Date().toLocaleString()}\n`;
        content += '=' .repeat(50) + '\n\n';
        
        transcript.forEach(entry => {
            content += `[${entry.timestamp}] ${entry.speaker}: ${entry.text}\n`;
        });
        
        const blob = new Blob([content], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `courtroom-transcript-round-${this.roundId}.txt`;
        a.click();
        URL.revokeObjectURL(url);
    }
    
    /**
     * Handle toggle auto-scroll button click.
     */
    handleToggleAutoScroll() {
        this.autoScrollEnabled = !this.autoScrollEnabled;
        if (this.elements.toggleAutoScroll) {
            this.elements.toggleAutoScroll.setAttribute('aria-pressed', this.autoScrollEnabled);
            this.elements.toggleAutoScroll.textContent = this.autoScrollEnabled ? '🔄 Auto' : '⏹️ Manual';
        }
    }
    
    /**
     * Show objection modal.
     */
    showObjectionModal() {
        if (this.elements.modalOverlay) {
            this.elements.modalOverlay.style.display = 'flex';
            this.elements.modalOverlay.setAttribute('aria-hidden', 'false');
        }
        if (this.elements.objectionModal) {
            this.elements.objectionModal.style.display = 'block';
        }
        
        // Reset form
        if (this.elements.objectionType) {
            this.elements.objectionType.value = '';
        }
        if (this.elements.objectionReason) {
            this.elements.objectionReason.value = '';
        }
        if (this.elements.charCount) {
            this.elements.charCount.textContent = '0';
        }
        
        // Focus first input
        setTimeout(() => this.elements.objectionType?.focus(), 100);
    }
    
    /**
     * Close objection modal.
     */
    closeObjectionModal() {
        if (this.elements.objectionModal) {
            this.elements.objectionModal.style.display = 'none';
        }
        this.closeAllModals();
    }
    
    /**
     * Show error modal.
     * @param {string} message - Error message
     */
    showErrorModal(message) {
        if (this.elements.errorMessage) {
            this.elements.errorMessage.textContent = message;
        }
        if (this.elements.modalOverlay) {
            this.elements.modalOverlay.style.display = 'flex';
            this.elements.modalOverlay.setAttribute('aria-hidden', 'false');
        }
        if (this.elements.errorModal) {
            this.elements.errorModal.style.display = 'block';
        }
    }
    
    /**
     * Close error modal.
     */
    closeErrorModal() {
        if (this.elements.errorModal) {
            this.elements.errorModal.style.display = 'none';
        }
        this.closeAllModals();
    }
    
    /**
     * Show ruling modal (for judges).
     */
    showRulingModal() {
        if (this.elements.modalOverlay) {
            this.elements.modalOverlay.style.display = 'flex';
            this.elements.modalOverlay.setAttribute('aria-hidden', 'false');
        }
        if (this.elements.rulingModal) {
            this.elements.rulingModal.style.display = 'block';
        }
    }
    
    /**
     * Close ruling modal.
     */
    closeRulingModal() {
        if (this.elements.rulingModal) {
            this.elements.rulingModal.style.display = 'none';
        }
        this.closeAllModals();
    }
    
    /**
     * Show scoring modal.
     */
    showScoringModal() {
        if (this.elements.modalOverlay) {
            this.elements.modalOverlay.style.display = 'flex';
            this.elements.modalOverlay.setAttribute('aria-hidden', 'false');
        }
        if (this.elements.scoringModal) {
            this.elements.scoringModal.style.display = 'block';
        }
    }
    
    /**
     * Close scoring modal.
     */
    closeScoringModal() {
        if (this.elements.scoringModal) {
            this.elements.scoringModal.style.display = 'none';
        }
        this.closeAllModals();
    }
    
    /**
     * Switch scoring tab.
     * @param {string} team - 'petitioner' or 'respondent'
     */
    switchScoringTab(team) {
        this.currentScoringTeam = team;
        
        // Update tab buttons
        if (this.elements.tabPetitioner) {
            this.elements.tabPetitioner.classList.toggle('active', team === 'petitioner');
            this.elements.tabPetitioner.setAttribute('aria-selected', team === 'petitioner');
        }
        if (this.elements.tabRespondent) {
            this.elements.tabRespondent.classList.toggle('active', team === 'respondent');
            this.elements.tabRespondent.setAttribute('aria-selected', team === 'respondent');
        }
        
        // Reset sliders
        Object.keys(this.elements.scoreSliders).forEach(key => {
            const slider = this.elements.scoreSliders[key];
            const valueDisplay = this.elements.scoreValues[key];
            if (slider && valueDisplay) {
                slider.value = 3;
                valueDisplay.textContent = '3';
            }
        });
        
        this.updateTotalScore();
    }
    
    /**
     * Update total score display.
     */
    updateTotalScore() {
        let total = 0;
        Object.values(this.elements.scoreSliders).forEach(slider => {
            if (slider) {
                total += parseInt(slider.value, 10);
            }
        });
        
        if (this.elements.totalScore) {
            this.elements.totalScore.textContent = total;
        }
    }
    
    /**
     * Close all modals.
     */
    closeAllModals() {
        if (this.elements.objectionModal) {
            this.elements.objectionModal.style.display = 'none';
        }
        if (this.elements.errorModal) {
            this.elements.errorModal.style.display = 'none';
        }
        if (this.elements.rulingModal) {
            this.elements.rulingModal.style.display = 'none';
        }
        if (this.elements.scoringModal) {
            this.elements.scoringModal.style.display = 'none';
        }
        if (this.elements.modalOverlay) {
            this.elements.modalOverlay.style.display = 'none';
            this.elements.modalOverlay.setAttribute('aria-hidden', 'true');
        }
    }
    
    /**
     * Format seconds to MM:SS.
     * @param {number} seconds - Time in seconds
     * @returns {string} Formatted time
     */
    formatTime(seconds) {
        if (seconds === null || seconds === undefined) return '--:--';
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    
    /**
     * Check screen size and show warning if below 1024px.
     */
    checkScreenSize() {
        const width = window.innerWidth;
        if (this.elements.screenWarning) {
            this.elements.screenWarning.style.display = width < 1024 ? 'flex' : 'none';
        }
    }
    
    /**
     * Cleanup resources - Phase 2: Cleanup all components.
     */
    cleanup() {
        window.removeEventListener('resize', this.checkScreenSize);
        
        // Cleanup Phase 2 components
        this.timer?.cleanup();
        this.rulingSystem?.cleanup();
        this.transcriptRecorder?.cleanup();
        this.audioManager?.cleanup();
        this.webSocketManager?.disconnect();
        
        this.stateManager.reset();
        console.log('[CourtroomUI] Cleaned up');
    }
}

// Auto-initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    // Get round ID from URL
    const urlParams = new URLSearchParams(window.location.search);
    const roundId = parseInt(urlParams.get('round_id'), 10) || 1;
    
    // Initialize UI
    window.courtroomUI = new CourtroomUI(roundId);
    window.courtroomUI.initialize();
});

// Export for module use
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CourtroomUI;
}
