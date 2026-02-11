/**
 * js/ai-judge-controller.js
 * Phase 4: AI Judge Controller
 * Handles AI evaluation submissions and feedback display
 */

class AIJudgeController {
    constructor(roundId, teamId) {
        this.roundId = roundId;
        this.teamId = teamId;
        this.selectedSide = null;
        this.currentEvaluation = null;
        this.baseUrl = 'http://localhost:8000/api';
        this.isJudge = false;
        
        this.init();
    }

    init() {
        this.checkUserRole();
        this.initEventListeners();
        this.loadEvaluations();
    }

    checkUserRole() {
        const token = this.getAuthToken();
        if (token) {
            try {
                const payload = JSON.parse(atob(token.split('.')[1]));
                this.isJudge = ['JUDGE', 'FACULTY', 'ADMIN', 'SUPER_ADMIN'].includes(payload.role);
                
                if (this.isJudge) {
                    document.getElementById('judge-actions')?.classList.remove('hidden');
                }
            } catch (e) {
                console.error('Error decoding token:', e);
            }
        }
    }

    getAuthToken() {
        return localStorage.getItem('access_token') || '';
    }

    initEventListeners() {
        const textarea = document.getElementById('ai-argument-input');
        if (textarea) {
            textarea.addEventListener('input', (e) => {
                document.getElementById('char-count').textContent = e.target.value.length;
                this.updateSubmitButton();
            });
        }
    }

    toggleMinimize() {
        const panel = document.getElementById('ai-judge-panel');
        panel.classList.toggle('minimized');
    }

    selectSide(side) {
        this.selectedSide = side;
        document.querySelectorAll('.side-btn').forEach(btn => btn.classList.remove('active'));
        document.getElementById(`btn-ai-${side}`).classList.add('active');
        this.updateSubmitButton();
    }

    updateSubmitButton() {
        const textarea = document.getElementById('ai-argument-input');
        const btn = document.getElementById('btn-ai-evaluate');
        const hasText = textarea.value.trim().length > 10;
        const hasSide = this.selectedSide !== null;
        btn.disabled = !(hasText && hasSide);
    }

    async submitArgument() {
        const argumentText = document.getElementById('ai-argument-input').value.trim();
        if (!argumentText || !this.selectedSide) return;

        const token = this.getAuthToken();
        if (!token) {
            alert('Please log in to submit arguments');
            return;
        }

        const payload = {
            team_id: this.teamId,
            team_side: this.selectedSide,
            argument_text: argumentText
        };

        try {
            const response = await fetch(`${this.baseUrl}/oral-rounds/${this.roundId}/ai-judge/evaluate`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });

            if (response.ok) {
                const result = await response.json();
                this.currentEvaluation = result;
                this.displayFeedback(result);
                this.loadEvaluations();
            } else {
                const error = await response.json();
                alert(`Error: ${error.detail || 'Failed to evaluate'}`);
            }
        } catch (error) {
            console.error('Error submitting argument:', error);
            alert('Network error. Please try again.');
        }
    }

    displayFeedback(evaluation) {
        const feedbackDisplay = document.getElementById('ai-feedback-display');
        feedbackDisplay.classList.remove('hidden');

        // Timestamp
        document.getElementById('feedback-timestamp').textContent = new Date().toLocaleTimeString();

        // Behavior badges
        const behavior = evaluation.ai_behavior_data || {};
        this.updateBadge('my-lord', behavior.has_my_lord);
        this.updateBadge('scc', behavior.valid_scc_citation);
        this.updateBadge('cites', behavior.cites_case_properly);
        this.updateBadge('precedent', behavior.uses_precedent);

        // Scores
        const scores = evaluation.ai_scores || {};
        this.updateScore('legal', scores.legal_accuracy || 0);
        this.updateScore('citation', scores.citation || 0);
        this.updateScore('etiquette', scores.etiquette || 0);
        this.updateScore('structure', scores.structure || 0);
        this.updateScore('persuasive', scores.persuasiveness || 0);

        // Feedback text
        document.getElementById('ai-feedback-text').textContent = evaluation.ai_feedback;

        // Extract next question from feedback
        const nextQuestionMatch = evaluation.ai_feedback.match(/Next question[:\s]*(.+?)(?:\.|$)/i);
        const nextQuestion = nextQuestionMatch ? nextQuestionMatch[1].trim() : 'Prepare for bench questions on cited precedents.';
        document.getElementById('ai-next-question').textContent = nextQuestion;

        // Show judge actions if user is judge
        if (this.isJudge) {
            document.getElementById('judge-actions').classList.remove('hidden');
        }
    }

    updateBadge(badgeId, isPositive) {
        const statusEl = document.getElementById(`status-${badgeId}`);
        if (statusEl) {
            statusEl.textContent = isPositive ? '✓' : '✗';
            statusEl.className = `badge-status ${isPositive ? 'positive' : 'negative'}`;
        }
    }

    updateScore(scoreType, value) {
        const bar = document.getElementById(`bar-${scoreType}`);
        const scoreValue = document.getElementById(`score-${scoreType}`);
        
        if (bar && scoreValue) {
            const percentage = (value / 5) * 100;
            bar.style.width = `${percentage}%`;
            bar.className = `score-bar ${value >= 4 ? 'high' : value >= 3 ? 'medium' : 'low'}`;
            scoreValue.textContent = `${value}/5`;
        }
    }

    async loadEvaluations() {
        const token = this.getAuthToken();
        try {
            const response = await fetch(
                `${this.baseUrl}/oral-rounds/${this.roundId}/ai-judge/evaluations`,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );

            if (response.ok) {
                const evaluations = await response.json();
                this.renderHistory(evaluations);
            }
        } catch (error) {
            console.error('Error loading evaluations:', error);
        }
    }

    renderHistory(evaluations) {
        const container = document.getElementById('eval-history');
        if (!container || evaluations.length === 0) return;

        const recent = evaluations.slice(0, 5);
        container.innerHTML = recent.map(evaluation => {
            const scores = evaluation.ai_scores || {};
            const avgScore = Object.values(scores).reduce((a, b) => a + b, 0) / Object.values(scores).length || 0;
            
            return `
                <div class="history-item">
                    <span class="side ${evaluation.team_side}">${evaluation.team_side}</span>
                    <span class="score">${avgScore.toFixed(1)}/5</span>
                    ${evaluation.is_official ? '<span class="official-badge">Official</span>' : ''}
                </div>
            `;
        }).join('');
    }

    async markOfficial() {
        if (!this.currentEvaluation) return;
        if (!this.isJudge) {
            alert('Only judges can mark scores as official');
            return;
        }

        const token = this.getAuthToken();
        try {
            const response = await fetch(
                `${this.baseUrl}/oral-rounds/${this.roundId}/ai-judge/evaluations/${this.currentEvaluation.id}/mark-official`,
                {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` }
                }
            );

            if (response.ok) {
                alert('AI score marked as official!');
                this.loadEvaluations();
            } else {
                const error = await response.json();
                alert(`Error: ${error.detail || 'Failed to mark official'}`);
            }
        } catch (error) {
            console.error('Error marking official:', error);
        }
    }
}
