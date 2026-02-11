/**
 * Phase 0: Virtual Courtroom Infrastructure - State Persistence
 * 
 * Persists critical state across page refreshes using localStorage.
 * Handles session recovery on page load.
 */

class CourtroomStatePersistence {
    /**
     * Creates a new CourtroomStatePersistence instance.
     * @param {string} storageKey - Prefix for localStorage keys
     */
    constructor(storageKey = 'courtroom') {
        this.storageKey = storageKey;
        
        // Keys for different data types
        this.keys = {
            roundId: `${storageKey}_roundId`,
            currentSpeaker: `${storageKey}_lastSpeaker`,
            timerRemaining: `${storageKey}_timerRemaining`,
            uiPreferences: `${storageKey}_uiPrefs`,
            authToken: `${storageKey}_token`,
            userData: `${storageKey}_user`
        };
        
        // Bind methods
        this.saveState = this.saveState.bind(this);
        this.loadState = this.loadState.bind(this);
        this.clearState = this.clearState.bind(this);
        this.shouldRecover = this.shouldRecover.bind(this);
        this.recoverSession = this.recoverSession.bind(this);
    }
    
    /**
     * Serialize and save state to localStorage.
     * Only saves non-sensitive data.
     * @param {Object} state - CourtroomState state object
     */
    saveState(state) {
        try {
            // Save round ID
            if (state.round?.id) {
                localStorage.setItem(this.keys.roundId, state.round.id.toString());
            }
            
            // Save last speaker (for timer resume)
            if (state.timer?.currentSpeaker) {
                localStorage.setItem(this.keys.currentSpeaker, state.timer.currentSpeaker);
            }
            
            // Save timer remaining (for recovery)
            if (state.timer?.timeRemaining !== null && state.timer?.timeRemaining !== undefined) {
                localStorage.setItem(this.keys.timerRemaining, state.timer.timeRemaining.toString());
            }
            
            // Save UI preferences
            const uiPrefs = {
                expandedSections: state.ui?.expandedSections || [],
                activeModal: state.ui?.activeModal || 'none',
                lastUpdated: new Date().toISOString()
            };
            localStorage.setItem(this.keys.uiPreferences, JSON.stringify(uiPrefs));
            
            console.log('[CourtroomPersistence] State saved to localStorage');
        } catch (error) {
            console.error('[CourtroomPersistence] Error saving state:', error);
        }
    }
    
    /**
     * Load and parse state from localStorage.
     * @returns {Object|null} Persisted state or null if none exists
     */
    loadState() {
        try {
            const roundId = localStorage.getItem(this.keys.roundId);
            const currentSpeaker = localStorage.getItem(this.keys.currentSpeaker);
            const timerRemaining = localStorage.getItem(this.keys.timerRemaining);
            const uiPrefsJson = localStorage.getItem(this.keys.uiPreferences);
            
            const state = {};
            
            if (roundId) {
                state.roundId = parseInt(roundId, 10);
            }
            
            if (currentSpeaker) {
                state.currentSpeaker = currentSpeaker;
            }
            
            if (timerRemaining) {
                state.timeRemaining = parseInt(timerRemaining, 10);
            }
            
            if (uiPrefsJson) {
                try {
                    state.uiPreferences = JSON.parse(uiPrefsJson);
                } catch (e) {
                    console.warn('[CourtroomPersistence] Failed to parse UI preferences');
                }
            }
            
            return Object.keys(state).length > 0 ? state : null;
        } catch (error) {
            console.error('[CourtroomPersistence] Error loading state:', error);
            return null;
        }
    }
    
    /**
     * Remove all persisted state from localStorage.
     */
    clearState() {
        try {
            Object.values(this.keys).forEach(key => {
                localStorage.removeItem(key);
            });
            console.log('[CourtroomPersistence] State cleared from localStorage');
        } catch (error) {
            console.error('[CourtroomPersistence] Error clearing state:', error);
        }
    }
    
    /**
     * Check if recovery is possible (roundId exists in storage).
     * @returns {boolean} True if recovery data exists
     */
    shouldRecover() {
        const roundId = localStorage.getItem(this.keys.roundId);
        return !!roundId;
    }
    
    /**
     * Recover session after page refresh.
     * Fetches current round state from API and restores UI state.
     * @param {CourtroomState} courtroomState - State manager instance
     * @param {Function} onReconnect - Callback to reconnect WebSocket
     * @returns {Promise<boolean>} True if recovery successful
     */
    async recoverSession(courtroomState, onReconnect) {
        try {
            console.log('[CourtroomPersistence] Attempting session recovery...');
            
            const savedState = this.loadState();
            if (!savedState) {
                console.log('[CourtroomPersistence] No saved state to recover');
                return false;
            }
            
            // Restore UI preferences
            if (savedState.uiPreferences) {
                // Apply saved UI state
                const prefs = savedState.uiPreferences;
                if (prefs.expandedSections) {
                    // Restore expanded sections
                    prefs.expandedSections.forEach(section => {
                        // This will be applied by the UI controller
                    });
                }
            }
            
            // Fetch current round state from API
            const roundId = savedState.roundId || courtroomState.roundId;
            const token = localStorage.getItem(this.keys.authToken);
            
            if (!token) {
                console.warn('[CourtroomPersistence] No auth token for recovery');
                return false;
            }
            
            // Fetch round data
            const response = await fetch(`/api/oral-rounds/${roundId}`, {
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                }
            });
            
            if (!response.ok) {
                console.warn('[CourtroomPersistence] Failed to fetch round data');
                return false;
            }
            
            const roundData = await response.json();
            
            // Update state with recovered data
            courtroomState.setState({
                round: {
                    ...courtroomState.state.round,
                    ...roundData,
                    id: roundId
                },
                timer: {
                    ...courtroomState.state.timer,
                    currentSpeaker: savedState.currentSpeaker || roundData.current_state?.current_speaker || 'none',
                    timeRemaining: roundData.current_state?.time_remaining || savedState.timeRemaining || null,
                    isPaused: roundData.current_state?.is_paused || false
                }
            });
            
            // Reconnect WebSocket if round is in_progress
            if (roundData.current_state?.status === 'in_progress' && onReconnect) {
                console.log('[CourtroomPersistence] Round in progress, reconnecting WebSocket...');
                await onReconnect();
            }
            
            console.log('[CourtroomPersistence] Session recovered successfully');
            return true;
            
        } catch (error) {
            console.error('[CourtroomPersistence] Session recovery failed:', error);
            return false;
        }
    }
    
    /**
     * Save authentication token.
     * @param {string} token - JWT token
     */
    saveToken(token) {
        try {
            localStorage.setItem(this.keys.authToken, token);
        } catch (error) {
            console.error('[CourtroomPersistence] Error saving token:', error);
        }
    }
    
    /**
     * Get authentication token.
     * @returns {string|null} JWT token or null
     */
    getToken() {
        return localStorage.getItem(this.keys.authToken);
    }
    
    /**
     * Clear authentication token.
     */
    clearToken() {
        localStorage.removeItem(this.keys.authToken);
    }
    
    /**
     * Save user data.
     * @param {Object} userData - User data object
     */
    saveUser(userData) {
        try {
            localStorage.setItem(this.keys.userData, JSON.stringify(userData));
        } catch (error) {
            console.error('[CourtroomPersistence] Error saving user:', error);
        }
    }
    
    /**
     * Get user data.
     * @returns {Object|null} User data or null
     */
    getUser() {
        try {
            const data = localStorage.getItem(this.keys.userData);
            return data ? JSON.parse(data) : null;
        } catch (error) {
            console.error('[CourtroomPersistence] Error loading user:', error);
            return null;
        }
    }
    
    /**
     * Clear user data.
     */
    clearUser() {
        localStorage.removeItem(this.keys.userData);
    }
    
    /**
     * Cleanup on round completion.
     * Clears round-specific state but keeps user auth.
     * @param {CourtroomState} courtroomState - State manager instance
     */
    cleanupOnExit(courtroomState) {
        // Clear round-specific data
        localStorage.removeItem(this.keys.roundId);
        localStorage.removeItem(this.keys.currentSpeaker);
        localStorage.removeItem(this.keys.timerRemaining);
        localStorage.removeItem(this.keys.uiPreferences);
        
        // Reset state
        courtroomState.reset();
        
        console.log('[CourtroomPersistence] Cleanup completed on round exit');
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CourtroomStatePersistence;
}
