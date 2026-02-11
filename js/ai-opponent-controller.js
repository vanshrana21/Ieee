/**
 * js/ai-opponent-controller.js
 * Phase 4 + Dynamic AI: AI Opponent Controller with Context-Aware Rebuttals
 * Handles AI teammate enable/disable and dynamic argument generation
 */

class AIOpponentController {
    constructor(roundId, teamId) {
        this.roundId = roundId;
        this.teamId = teamId;
        this.selectedRole = null;
        this.selectedSide = null;
        this.sessionId = null;
        this.baseUrl = 'http://localhost:8000/api';
        this.isCaptain = false;
        
        // Dynamic AI properties
        this.isActive = false;
        this.opponentSide = null;
        this.mootContext = null;
        this.previousArguments = [];
        this.rebuttalHistory = [];
        
        this.init();
    }

    init() {
        this.checkUserRole();
        this.loadSessions();
        this.loadMootContext();
    }

    // =========================================================================
    // DYNAMIC AI OPPONENT METHODS (NEW)
    // =========================================================================

    async loadMootContext() {
        // Fetch moot problem context for transparency and AI generation
        try {
            const token = this.getAuthToken();
            const response = await fetch(
                `${this.baseUrl}/ai-opponent/${this.roundId}/context`,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );

            if (response.ok) {
                this.mootContext = await response.json();
                console.log("📋 Moot context loaded:", this.mootContext);
                this.displayMootContext();
            } else {
                console.warn("Failed to load moot context");
            }
        } catch (error) {
            console.error('Error loading moot context:', error);
        }
    }

    displayMootContext() {
        // Display moot problem context in the UI for transparency
        const contextPanel = document.getElementById('moot-context-panel');
        if (!contextPanel || !this.mootContext) return;

        contextPanel.innerHTML = `
            <div class="context-section">
                <h4>📋 Moot Problem: ${this.mootContext.problem_title}</h4>
                <p class="fact-sheet">${this.mootContext.fact_sheet.substring(0, 300)}...</p>
                
                <div class="legal-issues">
                    <strong>Legal Issues:</strong>
                    <ul>
                        ${this.mootContext.legal_issues.map(issue => `<li>${issue}</li>`).join('')}
                    </ul>
                </div>
                
                <div class="relevant-cases">
                    <strong>Relevant Cases:</strong>
                    <ul>
                        ${this.mootContext.relevant_cases.map(c => `<li>${c}</li>`).join('')}
                    </ul>
                </div>
            </div>
        `;
    }

    async generateRebuttal(userArgument, previousArguments = []) {
        // Generate dynamic AI rebuttal based on user's argument and case context.
        // Args:
        //   userArgument: The user's argument text to rebut
        //   previousArguments: List of previous arguments in this round (to avoid repetition)
        // Returns:
        //   Rebuttal object with text, legal points, and suggested cases
        if (!this.opponentSide) {
            console.error("AI Opponent side not set");
            return null;
        }

        // Use cached previous arguments if none provided
        const prevArgs = previousArguments.length > 0 ? previousArguments : this.previousArguments;

        const payload = {
            round_id: this.roundId,
            user_argument: userArgument,
            opponent_side: this.opponentSide,
            previous_arguments: prevArgs
        };

        try {
            this.showLoadingState("AI Opponent is thinking...");

            const token = this.getAuthToken();
            const response = await fetch(`${this.baseUrl}/ai-opponent/generate-rebuttal`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });

            if (response.ok) {
                const rebuttal = await response.json();
                
                // Store for history tracking
                this.rebuttalHistory.push(rebuttal);
                this.previousArguments.push(rebuttal.rebuttal_text);
                
                // Display the rebuttal
                this.displayRebuttal(rebuttal);
                
                // Add to activity feed
                this.addActivity('AI Rebuttal Generated', `Side: ${this.opponentSide}`);
                
                this.hideLoadingState();
                return rebuttal;
            } else if (response.status === 429) {
                alert('Rate limit exceeded. Please wait 30 seconds before generating another rebuttal.');
                this.hideLoadingState();
                return null;
            } else if (response.status === 503) {
                alert('AI opponent service temporarily unavailable. Please try again.');
                this.hideLoadingState();
                return null;
            } else {
                const error = await response.json();
                console.error('Rebuttal generation failed:', error);
                this.hideLoadingState();
                return null;
            }
        } catch (error) {
            console.error('Error generating rebuttal:', error);
            this.hideLoadingState();
            alert('Network error. Please try again.');
            return null;
        }
    }

    displayRebuttal(rebuttal) {
        // Display AI-generated rebuttal in the courtroom transcript.
        // Shows rebuttal text, legal points, and suggested cases.
        const transcript = document.getElementById('transcript-container');
        if (!transcript) {
            console.error('Transcript container not found');
            return;
        }

        // Build legal points HTML
        const legalPointsHtml = rebuttal.legal_points && rebuttal.legal_points.length > 0
            ? `<div class="legal-points">
                <strong>Key Legal Points:</strong>
                <ul>
                    ${rebuttal.legal_points.map(p => `<li>${p}</li>`).join('')}
                </ul>
               </div>`
            : '';

        // Build suggested cases HTML
        const suggestedCasesHtml = rebuttal.suggested_cases && rebuttal.suggested_cases.length > 0
            ? `<div class="suggested-cases">
                <strong>Suggested Cases to Cite:</strong>
                <ul>
                    ${rebuttal.suggested_cases.map(c => `<li>${c}</li>`).join('')}
                </ul>
               </div>`
            : '';

        // Build doctrine HTML
        const doctrineHtml = rebuttal.doctrine_applied
            ? `<div class="doctrine-applied">
                <strong>Doctrine Applied:</strong> ${rebuttal.doctrine_applied}
               </div>`
            : '';

        // Create AI opponent message
        const aiMessage = document.createElement('div');
        aiMessage.className = 'transcript-entry ai-opponent';
        aiMessage.innerHTML = `
            <div class="message-header">
                <span class="speaker-badge ai">🤖 AI Opponent (${this.opponentSide.toUpperCase()})</span>
                <span class="timestamp">${new Date().toLocaleTimeString()}</span>
                ${rebuttal.generation_source === 'template' ? '<span class="badge template">Template</span>' : '<span class="badge llm">AI Generated</span>'}
            </div>
            <div class="message-content">
                <div class="rebuttal-text">
                    ${this.formatRebuttalText(rebuttal.rebuttal_text)}
                </div>
                ${legalPointsHtml}
                ${doctrineHtml}
                ${suggestedCasesHtml}
            </div>
        `;

        transcript.appendChild(aiMessage);
        transcript.scrollTop = transcript.scrollHeight;

        // Play notification sound if available
        this.playNotificationSound();
    }

    formatRebuttalText(text) {
        // Format rebuttal text with proper paragraph breaks and emphasis
        return text
            .split('\n\n')
            .map(para => `<p>${para}</p>`)
            .join('');
    }

    playNotificationSound() {
        // Play subtle notification sound for AI rebuttal
        const sound = document.getElementById('ai-rebuttal-sound');
        if (sound) {
            sound.play().catch(e => console.log('Audio play failed:', e));
        }
    }

    showLoadingState(message) {
        // Show loading indicator while AI generates rebuttal
        const loadingEl = document.getElementById('ai-loading');
        if (loadingEl) {
            loadingEl.textContent = message;
            loadingEl.classList.remove('hidden');
        }
    }

    hideLoadingState() {
        // Hide loading indicator
        const loadingEl = document.getElementById('ai-loading');
        if (loadingEl) {
            loadingEl.classList.add('hidden');
        }
    }

    async enableAIOpponent(teamId, aiRole, opponentSide) {
        // Enable AI opponent with full context awareness.
        // Fetches moot problem context before enabling.
        // Fetch moot problem context first
        await this.loadMootContext();
        
        if (!this.mootContext) {
            console.warn("Could not load moot context, proceeding without it");
        }

        // Enable AI opponent
        const response = await fetch(`${this.baseUrl}/oral-rounds/${this.roundId}/ai-opponent/enable`, {
            method: 'POST',
            headers: { 
                'Authorization': `Bearer ${this.getAuthToken()}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 
                teamId, 
                aiRole, 
                opponentSide,
                context: this.mootContext
            })
        });

        if (response.ok) {
            this.isActive = true;
            this.opponentSide = opponentSide;
            console.log("AI Opponent enabled with context:", this.mootContext);
            
            // Show context to user for transparency
            this.displayMootContext();
        }
        
        return response;
    }

    checkUserRole() {
        const token = this.getAuthToken();
        if (token) {
            try {
                const payload = JSON.parse(atob(token.split('.')[1]));
                // For demo, assume user is captain if team_id matches
                this.isCaptain = true;
            } catch (e) {
                console.error('Error decoding token:', e);
            }
        }
    }

    getAuthToken() {
        return localStorage.getItem('access_token') || '';
    }

    updateRole() {
        const select = document.getElementById('ai-role');
        this.selectedRole = select.value;
        this.updateUI();
    }

    selectSide(side) {
        this.selectedSide = side;
        document.querySelectorAll('.side-btn').forEach(btn => btn.classList.remove('active'));
        document.getElementById(`btn-op-${side}`)?.classList.add('active');
        this.updateUI();
    }

    updateUI() {
        const canEnable = this.selectedRole && this.selectedSide;
        document.getElementById('ai-toggle').disabled = !canEnable;
    }

    async toggleAI() {
        const toggle = document.getElementById('ai-toggle');
        
        if (toggle.checked) {
            await this.enableAI();
        } else {
            await this.disableAI();
        }
    }

    async enableAI() {
        if (!this.selectedRole || !this.selectedSide) {
            alert('Please select AI role and team side first');
            document.getElementById('ai-toggle').checked = false;
            return;
        }

        const token = this.getAuthToken();
        const payload = {
            team_id: this.teamId,
            ai_role: this.selectedRole,
            opponent_side: this.selectedSide,
            context_summary: document.getElementById('ai-context')?.value || ''
        };

        try {
            const response = await fetch(
                `${this.baseUrl}/oral-rounds/${this.roundId}/ai-opponent/enable`,
                {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(payload)
                }
            );

            if (response.ok) {
                const result = await response.json();
                this.sessionId = result.id;
                this.opponentSide = this.selectedSide;
                this.isActive = true;
                this.updateStatus(true);
                this.showSessionInfo(result);
                this.addActivity('AI Teammate Enabled', `${result.ai_role} for ${result.opponent_side}`);
                
                // Load moot context for dynamic rebuttals
                await this.loadMootContext();
            } else {
                const error = await response.json();
                alert(`Error: ${error.detail || 'Failed to enable AI'}`);
                document.getElementById('ai-toggle').checked = false;
            }
        } catch (error) {
            console.error('Error enabling AI:', error);
            alert('Network error. Please try again.');
            document.getElementById('ai-toggle').checked = false;
        }
    }

    async disableAI() {
        if (!this.sessionId) return;

        const token = this.getAuthToken();
        try {
            const response = await fetch(
                `${this.baseUrl}/oral-rounds/${this.roundId}/ai-opponent/disable?team_id=${this.teamId}`,
                {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` }
                }
            );

            if (response.ok) {
                this.sessionId = null;
                this.isActive = false;
                this.opponentSide = null;
                this.updateStatus(false);
                this.hideSessionInfo();
                document.getElementById('ai-toggle').checked = false;
                this.addActivity('AI Teammate Disabled', 'Returned to manual control');
            } else {
                const error = await response.json();
                alert(`Error: ${error.detail || 'Failed to disable AI'}`);
            }
        } catch (error) {
            console.error('Error disabling AI:', error);
        }
    }

    updateStatus(isActive) {
        const dot = document.querySelector('.status-dot');
        const text = document.querySelector('.status-text');
        
        if (isActive) {
            dot?.classList.remove('inactive');
            dot?.classList.add('active');
            if (text) text.textContent = 'Active';
        } else {
            dot?.classList.remove('active');
            dot?.classList.add('inactive');
            if (text) text.textContent = 'Inactive';
        }
    }

    showSessionInfo(session) {
        document.getElementById('role-section')?.classList.add('hidden');
        document.getElementById('side-section')?.classList.add('hidden');
        document.getElementById('context-section')?.classList.add('hidden');
        
        document.getElementById('session-info')?.classList.remove('hidden');
        const sessionRole = document.getElementById('session-role');
        const sessionSide = document.getElementById('session-side');
        const sessionTime = document.getElementById('session-time');
        
        if (sessionRole) sessionRole.textContent = session.ai_role.replace('_', ' ').toUpperCase();
        if (sessionSide) sessionSide.textContent = session.opponent_side.toUpperCase();
        if (sessionTime) sessionTime.textContent = new Date(session.created_at).toLocaleTimeString();
    }

    hideSessionInfo() {
        document.getElementById('role-section')?.classList.remove('hidden');
        document.getElementById('side-section')?.classList.remove('hidden');
        document.getElementById('context-section')?.classList.remove('hidden');
        
        document.getElementById('session-info')?.classList.add('hidden');
    }

    async loadSessions() {
        const token = this.getAuthToken();
        try {
            const response = await fetch(
                `${this.baseUrl}/oral-rounds/${this.roundId}/ai-opponent/sessions`,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );

            if (response.ok) {
                const sessions = await response.json();
                const activeSession = sessions.find(s => s.is_active && s.team_id === this.teamId);
                
                if (activeSession) {
                    this.sessionId = activeSession.id;
                    this.selectedRole = activeSession.ai_role;
                    this.selectedSide = activeSession.opponent_side;
                    this.opponentSide = activeSession.opponent_side;
                    this.isActive = true;
                    document.getElementById('ai-toggle').checked = true;
                    document.getElementById('ai-role').value = this.selectedRole;
                    this.updateStatus(true);
                    this.showSessionInfo(activeSession);
                    
                    // Load moot context for existing session
                    await this.loadMootContext();
                }
            }
        } catch (error) {
            console.error('Error loading sessions:', error);
        }
    }

    addActivity(title, description) {
        const container = document.getElementById('ai-activity-list');
        if (!container) return;

        // Remove "no activity" message if present
        const noActivity = container.querySelector('.no-activity');
        if (noActivity) noActivity.remove();

        const item = document.createElement('div');
        item.className = 'activity-item';
        item.innerHTML = `
            <span class="activity-icon">🤖</span>
            <div class="activity-content">
                <div class="activity-title">${title}</div>
                <div class="activity-time">${new Date().toLocaleTimeString()} - ${description}</div>
            </div>
        `;

        container.insertBefore(item, container.firstChild);

        // Keep only last 5 activities
        while (container.children.length > 5) {
            container.removeChild(container.lastChild);
        }
    }
}
