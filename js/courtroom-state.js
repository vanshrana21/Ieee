/**
 * Phase 0: Virtual Courtroom Infrastructure - Global State Management
 * 
 * Centralized state management for courtroom UI.
 * Implements observer pattern for state change notifications.
 */

class CourtroomState {
    /**
     * Creates a new CourtroomState instance.
     * @param {number} roundId - The round ID to manage state for
     */
    constructor(roundId) {
        this.roundId = roundId;
        
        // State structure matching backend schema
        this.state = {
            // Authentication
            currentUser: {
                id: null,
                name: null,
                role: null, // "judge" | "student" | "admin"
                teamId: null
            },
            
            // Round Information
            round: {
                id: roundId,
                competitionId: null,
                roundNumber: null,
                petitionerTeamId: null,
                respondentTeamId: null,
                status: "scheduled" // "scheduled" | "in_progress" | "completed"
            },
            
            // Timer State
            timer: {
                timeRemaining: null,
                isPaused: false,
                currentSpeaker: "none", // "petitioner" | "respondent" | "judge" | "none"
                startTime: null,
                endTime: null
            },
            
            // Objections
            objections: [],
            
            // Transcript
            transcript: [],
            
            // Scores
            scores: [],
            
            // WebSocket Connection
            connection: {
                isConnected: false,
                participants: []
            },
            
            // UI State
            ui: {
                errorMessage: null,
                isLoading: false,
                activeModal: "none", // "none" | "objection" | "scoring" | "transcript"
                expandedSections: []
            }
        };
        
        // Observer pattern - list of callbacks
        this.listeners = new Set();
        
        // Bind methods
        this.initialize = this.initialize.bind(this);
        this.updateTimer = this.updateTimer.bind(this);
        this.addObjection = this.addObjection.bind(this);
        this.updateObjection = this.updateObjection.bind(this);
        this.addTranscriptSegment = this.addTranscriptSegment.bind(this);
        this.addScore = this.addScore.bind(this);
        this.setError = this.setError.bind(this);
        this.clearError = this.clearError.bind(this);
        this.subscribe = this.subscribe.bind(this);
        this.unsubscribe = this.unsubscribe.bind(this);
        this.getState = this.getState.bind(this);
        this.setState = this.setState.bind(this);
        
        console.log(`[CourtroomState] Initialized for round ${roundId}`);
    }
    
    /**
     * Set initial state with user and round data.
     * @param {Object} userData - { id, name, role, teamId }
     * @param {Object} roundData - { competitionId, roundNumber, petitionerTeamId, respondentTeamId, status }
     */
    initialize(userData, roundData) {
        this.setState({
            currentUser: {
                ...this.state.currentUser,
                ...userData
            },
            round: {
                ...this.state.round,
                ...roundData
            }
        });
        console.log('[CourtroomState] Initialized with user and round data');
    }
    
    /**
     * Update timer state and notify listeners.
     * @param {Object} newTimerState - { timeRemaining, isPaused, currentSpeaker }
     */
    updateTimer(newTimerState) {
        this.setState({
            timer: {
                ...this.state.timer,
                ...newTimerState
            }
        });
    }
    
    /**
     * Add a new objection to the state.
     * @param {Object} objection - { id, raisedByTeamId, objectionType, objectionText, ruling, isResolved, timestamp }
     */
    addObjection(objection) {
        const newObjections = [...this.state.objections, objection];
        this.setState({ objections: newObjections });
        console.log(`[CourtroomState] Added objection ${objection.id}`);
    }
    
    /**
     * Update an existing objection.
     * @param {number} objectionId - ID of objection to update
     * @param {Object} updates - Fields to update
     */
    updateObjection(objectionId, updates) {
        const newObjections = this.state.objections.map(obj => {
            if (obj.id === objectionId) {
                return { ...obj, ...updates };
            }
            return obj;
        });
        this.setState({ objections: newObjections });
        console.log(`[CourtroomState] Updated objection ${objectionId}`);
    }
    
    /**
     * Add a transcript segment.
     * @param {Object} segment - { segmentId, speakerRole, text, timestamp, confidence }
     */
    addTranscriptSegment(segment) {
        const newTranscript = [...this.state.transcript, segment];
        this.setState({ transcript: newTranscript });
    }
    
    /**
     * Add a score entry.
     * @param {Object} score - { id, judgeId, teamId, teamSide, criteria, totalScore, isDraft }
     */
    addScore(score) {
        // Remove existing score from same judge for same team if draft
        const filteredScores = this.state.scores.filter(s => {
            if (s.judgeId === score.judgeId && s.teamId === score.teamId && s.isDraft) {
                return false;
            }
            return true;
        });
        
        const newScores = [...filteredScores, score];
        this.setState({ scores: newScores });
        console.log(`[CourtroomState] Added score ${score.id} for team ${score.teamId}`);
    }
    
    /**
     * Update WebSocket connection state.
     * @param {boolean} isConnected - Connection status
     * @param {Array} participants - List of connected participants
     */
    updateConnection(isConnected, participants = null) {
        this.setState({
            connection: {
                isConnected,
                participants: participants !== null ? participants : this.state.connection.participants
            }
        });
    }
    
    /**
     * Set error message in UI state.
     * @param {string} message - Error message to display
     */
    setError(message) {
        this.setState({
            ui: {
                ...this.state.ui,
                errorMessage: message
            }
        });
        console.error(`[CourtroomState] Error: ${message}`);
    }
    
    /**
     * Clear error message from UI state.
     */
    clearError() {
        this.setState({
            ui: {
                ...this.state.ui,
                errorMessage: null
            }
        });
    }
    
    /**
     * Set loading state.
     * @param {boolean} isLoading - Loading status
     */
    setLoading(isLoading) {
        this.setState({
            ui: {
                ...this.state.ui,
                isLoading
            }
        });
    }
    
    /**
     * Set active modal.
     * @param {string} modal - Modal name ("none" | "objection" | "scoring" | "transcript")
     */
    setActiveModal(modal) {
        this.setState({
            ui: {
                ...this.state.ui,
                activeModal: modal
            }
        });
    }
    
    /**
     * Toggle section expansion.
     * @param {string} sectionId - Section identifier
     */
    toggleSection(sectionId) {
        const expanded = new Set(this.state.ui.expandedSections);
        if (expanded.has(sectionId)) {
            expanded.delete(sectionId);
        } else {
            expanded.add(sectionId);
        }
        this.setState({
            ui: {
                ...this.state.ui,
                expandedSections: Array.from(expanded)
            }
        });
    }
    
    /**
     * Subscribe to state changes.
     * @param {Function} callback - Function to call on state change
     * @returns {Function} Unsubscribe function
     */
    subscribe(callback) {
        this.listeners.add(callback);
        
        // Return unsubscribe function
        return () => {
            this.listeners.delete(callback);
        };
    }
    
    /**
     * Unsubscribe from state changes.
     * @param {Function} callback - Function to remove
     */
    unsubscribe(callback) {
        this.listeners.delete(callback);
    }
    
    /**
     * Notify all listeners of state change.
     * @param {Object} newState - New state object
     * @param {Object} prevState - Previous state object
     */
    notifyListeners(newState, prevState) {
        this.listeners.forEach(callback => {
            try {
                callback(newState, prevState);
            } catch (error) {
                console.error('[CourtroomState] Error in listener:', error);
            }
        });
    }
    
    /**
     * Get current state.
     * @returns {Object} Current state
     */
    getState() {
        return { ...this.state };
    }
    
    /**
     * Update state and notify listeners.
     * @param {Object} partialState - Partial state to merge
     */
    setState(partialState) {
        const prevState = { ...this.state };
        this.state = {
            ...this.state,
            ...partialState
        };
        this.notifyListeners(this.state, prevState);
    }
    
    /**
     * Reset state to initial values.
     */
    reset() {
        this.state = {
            currentUser: { id: null, name: null, role: null, teamId: null },
            round: {
                id: this.roundId,
                competitionId: null,
                roundNumber: null,
                petitionerTeamId: null,
                respondentTeamId: null,
                status: "scheduled"
            },
            timer: {
                timeRemaining: null,
                isPaused: false,
                currentSpeaker: "none",
                startTime: null,
                endTime: null
            },
            objections: [],
            transcript: [],
            scores: [],
            connection: {
                isConnected: false,
                participants: []
            },
            ui: {
                errorMessage: null,
                isLoading: false,
                activeModal: "none",
                expandedSections: []
            }
        };
        this.notifyListeners(this.state, {});
        console.log('[CourtroomState] State reset');
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CourtroomState;
}
