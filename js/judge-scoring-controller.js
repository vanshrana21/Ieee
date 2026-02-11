/**
 * js/judge-scoring-controller.js
 * Phase 3.2: Judge Scoring Controller
 * Handles score input, preview updates, draft/submit workflow
 */

class JudgeScoringController {
    constructor(roundId) {
        this.roundId = roundId;
        this.currentTeamId = null;
        this.currentTeamSide = null;
        this.isDraft = true;
        this.baseUrl = 'http://localhost:8000/api';
        
        this.init();
    }

    init() {
        this.initEventListeners();
        this.initDraggable();
        this.loadExistingScores();
        this.updatePreview();
    }

    // ================= EVENT LISTENERS =================
    initEventListeners() {
        // Slider inputs - update preview in real-time
        const sliders = document.querySelectorAll('.score-slider');
        sliders.forEach(slider => {
            slider.addEventListener('input', (e) => {
                this.updateSliderValue(e.target);
                this.updatePreview();
            });
        });

        // Minimize button
        const minimizeBtn = document.getElementById('btn-minimize');
        if (minimizeBtn) {
            minimizeBtn.addEventListener('click', () => this.toggleMinimize());
        }
    }

    // ================= DRAGGABLE PANEL =================
    initDraggable() {
        const panel = document.getElementById('judge-scoring-panel');
        const header = document.getElementById('panel-header');
        
        if (!panel || !header) return;

        let isDragging = false;
        let currentX = 0;
        let currentY = 0;
        let initialX = 0;
        let initialY = 0;
        let xOffset = 0;
        let yOffset = 0;

        header.addEventListener('mousedown', dragStart);
        document.addEventListener('mousemove', drag);
        document.addEventListener('mouseup', dragEnd);

        function dragStart(e) {
            initialX = e.clientX - xOffset;
            initialY = e.clientY - yOffset;
            if (e.target === header || e.target.closest('.panel-header')) {
                isDragging = true;
            }
        }

        function drag(e) {
            if (isDragging) {
                e.preventDefault();
                currentX = e.clientX - initialX;
                currentY = e.clientY - initialY;
                xOffset = currentX;
                yOffset = currentY;

                panel.style.transform = `translate(${currentX}px, ${currentY}px)`;
            }
        }

        function dragEnd() {
            initialX = currentX;
            initialY = currentY;
            isDragging = false;
        }
    }

    toggleMinimize() {
        const panel = document.getElementById('judge-scoring-panel');
        panel.classList.toggle('minimized');
        
        const btn = document.getElementById('btn-minimize');
        btn.textContent = panel.classList.contains('minimized') ? '+' : '_';
    }

    // ================= TEAM SELECTION =================
    selectTeam(side) {
        // side is 'petitioner' or 'respondent'
        this.currentTeamSide = side;
        
        // Update UI
        document.querySelectorAll('.btn-team').forEach(btn => {
            btn.classList.remove('active');
        });
        document.getElementById(`btn-score-${side}`).classList.add('active');
        
        const sideLabel = side === 'petitioner' ? 'Petitioner' : 'Respondent';
        document.getElementById('selected-team-display').textContent = 
            `Scoring: ${sideLabel}`;
        
        // TODO: Fetch team_id from round data
        // For now, we'll get it when saving
        this.currentTeamId = null; // Will be resolved on save
        
        // Load existing score for this team if any
        this.loadScoreForTeam(side);
    }

    // ================= SCORE CALCULATION =================
    updateSliderValue(slider) {
        const criterion = slider.id.replace(/-/g, '_');
        const valueDisplay = document.getElementById(slider.id.replace(/-/g, '-') + '-value') ||
                              document.getElementById(slider.id.split('-')[0].substring(0, 2) + '-value');
        
        // Map slider IDs to value display IDs
        const valueMap = {
            'legal-reasoning': 'lr-value',
            'citation-format': 'cf-value',
            'courtroom-etiquette': 'ce-value',
            'responsiveness': 'resp-value',
            'time-management': 'tm-value'
        };
        
        const displayId = valueMap[slider.id];
        const display = document.getElementById(displayId);
        
        if (display) {
            display.textContent = slider.value;
            
            // Color coding based on score
            display.classList.remove('low', 'medium', 'high');
            const val = parseInt(slider.value);
            if (val <= 2) display.classList.add('low');
            else if (val === 3) display.classList.add('medium');
            else display.classList.add('high');
        }
    }

    updatePreview() {
        const scores = [
            parseInt(document.getElementById('legal-reasoning').value),
            parseInt(document.getElementById('citation-format').value),
            parseInt(document.getElementById('courtroom-etiquette').value),
            parseInt(document.getElementById('responsiveness').value),
            parseInt(document.getElementById('time-management').value)
        ];
        
        const total = scores.reduce((a, b) => a + b, 0) / 5;
        const totalDisplay = document.getElementById('total-score');
        const scoreBar = document.getElementById('score-bar');
        
        if (totalDisplay) {
            totalDisplay.textContent = total.toFixed(1);
        }
        
        if (scoreBar) {
            const percentage = (total / 5) * 100;
            scoreBar.style.width = `${percentage}%`;
        }
    }

    // ================= API CALLS =================
    getAuthToken() {
        return localStorage.getItem('access_token') || '';
    }

    async loadExistingScores() {
        try {
            const token = this.getAuthToken();
            const response = await fetch(`${this.baseUrl}/oral-rounds/${this.roundId}/scores`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            
            if (response.ok) {
                const scores = await response.json();
                this.renderScores(scores);
                
                // If there's a score for current team, load it
                if (this.currentTeamSide) {
                    this.loadScoreForTeam(this.currentTeamSide);
                }
            }
        } catch (error) {
            console.error('Failed to load scores:', error);
        }
    }

    async loadScoreForTeam(side) {
        // This would load an existing draft score for the selected team
        // Implementation depends on having the team_id
        // For now, we reset to defaults
        this.resetForm();
    }

    async saveScore(isDraft) {
        if (!this.currentTeamSide) {
            alert('Please select a team to score (Petitioner or Respondent)');
            return;
        }

        const token = this.getAuthToken();
        if (!token) {
            alert('Please log in to submit scores');
            return;
        }

        // Get team_id - in production, this would come from round data
        // For now, we'll use a placeholder that the backend will validate
        const teamId = this.currentTeamId || 1; // Placeholder

        const payload = {
            team_id: teamId,
            team_side: this.currentTeamSide,
            legal_reasoning: parseInt(document.getElementById('legal-reasoning').value),
            citation_format: parseInt(document.getElementById('citation-format').value),
            courtroom_etiquette: parseInt(document.getElementById('courtroom-etiquette').value),
            responsiveness: parseInt(document.getElementById('responsiveness').value),
            time_management: parseInt(document.getElementById('time-management').value),
            written_feedback: document.getElementById('written-feedback').value,
            strengths: this.parseListInput(document.getElementById('strengths').value),
            areas_for_improvement: this.parseListInput(document.getElementById('areas-for-improvement').value),
            is_draft: isDraft
        };

        try {
            const response = await fetch(`${this.baseUrl}/oral-rounds/${this.roundId}/scores`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });

            if (response.ok) {
                const result = await response.json();
                this.isDraft = isDraft;
                this.updateStatus(isDraft ? 'draft' : 'submitted');
                
                if (!isDraft) {
                    alert(`Score submitted! Total: ${result.total_score}/5.0`);
                    this.renderScoreCard(result);
                } else {
                    alert('Draft saved successfully');
                }
                
                // Refresh all scores display
                this.loadExistingScores();
            } else if (response.status === 403) {
                alert('Only judges and faculty can submit scores.');
            } else {
                const error = await response.json();
                alert(`Error: ${error.detail || 'Failed to save score'}`);
            }
        } catch (error) {
            console.error('Error saving score:', error);
            alert('Network error. Please try again.');
        }
    }

    saveDraft() {
        this.saveScore(true);
    }

    submitScore() {
        // Validate all fields are filled
        const criteria = ['legal-reasoning', 'citation-format', 'courtroom-etiquette', 'responsiveness', 'time-management'];
        for (const criterion of criteria) {
            const value = document.getElementById(criterion).value;
            if (!value || value < 1 || value > 5) {
                alert(`Please set a score for ${criterion.replace(/-/g, ' ')}`);
                return;
            }
        }
        
        if (confirm('Are you sure you want to submit this score? Submitted scores cannot be edited.')) {
            this.saveScore(false);
        }
    }

    // ================= UI HELPERS =================
    parseListInput(input) {
        if (!input || input.trim() === '') return [];
        return input.split(',').map(s => s.trim()).filter(s => s);
    }

    updateStatus(status) {
        const statusEl = document.getElementById('score-status');
        if (statusEl) {
            statusEl.innerHTML = `<span class="status-indicator ${status}">${status}</span>`;
        }
    }

    resetForm() {
        // Reset all sliders to 3
        const sliders = document.querySelectorAll('.score-slider');
        sliders.forEach(slider => {
            slider.value = 3;
            this.updateSliderValue(slider);
        });
        
        // Clear text inputs
        document.getElementById('written-feedback').value = '';
        document.getElementById('strengths').value = '';
        document.getElementById('areas-for-improvement').value = '';
        
        // Reset status
        this.updateStatus('draft');
        this.updatePreview();
    }

    renderScores(scores) {
        const container = document.getElementById('scores-container');
        if (!container) return;

        if (scores.length === 0) {
            container.innerHTML = '<p class="no-scores">No scores submitted yet</p>';
            return;
        }

        // Group by side
        const petitionerScores = scores.filter(s => s.team_side === 'petitioner' && s.is_submitted);
        const respondentScores = scores.filter(s => s.team_side === 'respondent' && s.is_submitted);

        let html = '';
        
        if (petitionerScores.length > 0) {
            const latest = petitionerScores[petitionerScores.length - 1];
            html += this.createScoreCardHtml(latest, 'petitioner');
        }
        
        if (respondentScores.length > 0) {
            const latest = respondentScores[respondentScores.length - 1];
            html += this.createScoreCardHtml(latest, 'respondent');
        }

        if (html === '') {
            html = '<p class="no-scores">No scores submitted yet</p>';
        }

        container.innerHTML = html;
    }

    createScoreCardHtml(score, side) {
        const sideLabel = side === 'petitioner' ? 'Petitioner' : 'Respondent';
        return `
            <div class="score-card ${side}">
                <h4>${sideLabel}</h4>
                <div class="score-breakdown">
                    <span>Legal: ${score.legal_reasoning}/5</span>
                    <span>Citation: ${score.citation_format}/5</span>
                    <span>Etiquette: ${score.courtroom_etiquette}/5</span>
                    <span>Responsive: ${score.responsiveness}/5</span>
                    <span>Time: ${score.time_management}/5</span>
                </div>
                <div class="total"><strong>Total: ${score.total_score.toFixed(1)}/5.0</strong></div>
            </div>
        `;
    }

    renderScoreCard(score) {
        const container = document.getElementById('scores-container');
        if (!container) return;

        // Remove "no scores" message if present
        const noScoresMsg = container.querySelector('.no-scores');
        if (noScoresMsg) {
            noScoresMsg.remove();
        }

        // Check if card already exists for this team
        const existingCard = container.querySelector(`.score-card.${score.team_side}`);
        if (existingCard) {
            existingCard.remove();
        }

        // Add new score card
        const cardHtml = this.createScoreCardHtml(score, score.team_side);
        container.insertAdjacentHTML('beforeend', cardHtml);
    }
}
