/**
 * ai-judge-interface.js
 * Phase 3: AI Judge Interface Component
 * 
 * Mobile-first UI for AI Moot Court Practice
 * Manages 4 screens: Problem Selector → Argument Input → AI Feedback → Debrief
 */

class AIJudgeInterface {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.currentScreen = 'problems'; // problems, argument, feedback, debrief
        this.currentProblem = null;
        this.currentSide = null;
        this.currentTurn = 1;
        this.sessionData = null;
        this.turnsData = [];
        this.problems = [];
        
        this.init();
    }

    init() {
        this.render();
        this.loadProblems();
    }

    // Screen 1: Problem Selector
    async loadProblems() {
        const result = await aiMootApi.getValidationProblems();
        
        if (result.error) {
            this.showError(result.error);
            return;
        }

        this.problems = result;
        this.renderProblems();
    }

    renderProblems() {
        const problemCards = this.problems.map((p, index) => {
            const colors = ['#3b82f6', '#8b5cf6', '#f59e0b'];
            const color = colors[index % colors.length];
            
            return `
                <div class="ai-problem-card" style="border-left: 4px solid ${color};">
                    <h3>${p.title}</h3>
                    <p>${p.legal_issue}</p>
                    <div class="ai-problem-actions">
                        <button class="ai-btn ai-btn-primary" onclick="aiJudge.selectProblem(${p.id}, 'petitioner')">
                            Petitioner
                        </button>
                        <button class="ai-btn ai-btn-secondary" onclick="aiJudge.selectProblem(${p.id}, 'respondent')">
                            Respondent
                        </button>
                    </div>
                </div>
            `;
        }).join('');

        const html = `
            <div class="ai-screen ai-screen-problems">
                <div class="ai-header">
                    <h1>🏛️ AI Moot Court Practice</h1>
                    <p>Solo practice with AI Judge — no teammates needed</p>
                </div>
                <div class="ai-problems-list">
                    ${problemCards}
                </div>
            </div>
        `;

        this.updateContent(html);
    }

    async selectProblem(problemId, side) {
        this.currentProblem = problemId;
        this.currentSide = side;
        
        // Create session
        const problemType = `validation_${problemId}`;
        const result = await aiMootApi.createAISession(problemType, side, problemId);
        
        if (result.error) {
            this.showError(result.error);
            return;
        }

        this.sessionData = result;
        this.currentTurn = result.current_turn || 1;
        this.currentScreen = 'argument';
        this.renderArgument();
    }

    // Screen 2: Argument Input
    renderArgument() {
        const problem = this.problems.find(p => p.id === this.currentProblem);
        const roundNames = ['Opening Argument', 'Rebuttal', 'Sur-rebuttal'];
        const roundName = roundNames[this.currentTurn - 1] || `Round ${this.currentTurn}`;
        
        const html = `
            <div class="ai-screen ai-screen-argument">
                <div class="ai-header">
                    <h1>Round ${this.currentTurn} — ${roundName}</h1>
                    <p>${problem?.title || 'Moot Problem'}</p>
                    <span class="ai-side-badge ai-side-${this.currentSide}">${this.currentSide}</span>
                </div>
                
                <div class="ai-argument-form">
                    <textarea 
                        id="argumentInput"
                        class="ai-textarea"
                        placeholder="My Lord, I submit that..."
                        maxlength="250"
                        rows="5"
                    ></textarea>
                    
                    <div class="ai-helper-text">
                        <p>✅ Must say 'My Lord' at start</p>
                        <p>✅ Cite cases as (2017) 10 SCC 1</p>
                        <p>✅ Max 250 characters</p>
                    </div>
                    
                    <div class="ai-char-counter">
                        <span id="charCount">0</span>/250
                    </div>
                    
                    <button class="ai-btn ai-btn-primary ai-btn-large" onclick="aiJudge.submitArgument()">
                        Submit to Bench →
                    </button>
                </div>
                
                <div id="validationError" class="ai-validation-error" style="display: none;">
                    Argument must be at least 20 characters and contain "My Lord"
                </div>
            </div>
        `;

        this.updateContent(html);
        
        // Add character counter
        const textarea = document.getElementById('argumentInput');
        const charCount = document.getElementById('charCount');
        textarea.addEventListener('input', () => {
            charCount.textContent = textarea.value.length;
        });
    }

    validateArgument(argument) {
        if (argument.length < 20) {
            return false;
        }
        if (!argument.toLowerCase().includes('my lord')) {
            return false;
        }
        return true;
    }

    async submitArgument() {
        const textarea = document.getElementById('argumentInput');
        const argument = textarea.value.trim();
        
        if (!this.validateArgument(argument)) {
            document.getElementById('validationError').style.display = 'block';
            return;
        }
        
        document.getElementById('validationError').style.display = 'none';
        
        // Show loading
        this.showLoading('Submitting to Bench...');
        
        const result = await aiMootApi.submitArgument(this.sessionData.id, argument);
        
        this.hideLoading();
        
        if (result.error) {
            // Check if it's a network error or API not configured
            if (result.error.includes('Network') || result.error.includes('offline')) {
                this.showError('AI Judge offline. Using practice mode.');
                // Still show mock feedback
                this.showFeedback(result);
            } else {
                this.showError(result.error);
            }
            return;
        }

        // Store turn data
        this.turnsData.push({
            turn: this.currentTurn,
            argument: argument,
            feedback: result.feedback,
            scores: result.score_breakdown,
            missing_cases: result.missing_cases || []
        });

        this.showFeedback(result);
    }

    // Screen 3: AI Feedback
    showFeedback(result) {
        const scores = result.score_breakdown || {};
        const legalAccuracy = scores.legal_accuracy || 0;
        const citation = scores.citation || 0;
        const etiquette = scores.etiquette || 0;
        
        // Phase 4: Get behavior data from result
        const behaviorData = result.behavior_data || {};
        const etiquetteCheck = behaviorData.etiquette_check || {};
        const citationCheck = behaviorData.citation_check || {};
        const interruptionCheck = behaviorData.interruption_check || {};
        const proportionalityCheck = behaviorData.proportionality_check || {};
        const landmarkCheck = behaviorData.landmark_check || {};
        
        const renderStars = (count, highlightLow = false) => {
            const stars = [];
            for (let i = 0; i < 5; i++) {
                if (i < count) {
                    stars.push('⭐');
                } else if (highlightLow && i === count) {
                    stars.push('⚠️');
                } else {
                    stars.push('☆');
                }
            }
            return stars.join('');
        };
        
        // Phase 4: Render behavior badges
        const renderBehaviorBadges = () => {
            const badges = [];
            
            // Etiquette badge
            if (etiquetteCheck.has_etiquette) {
                badges.push(`<span class="badge etiquette-badge" title="You addressed the bench as 'My Lord'">✅ My Lord</span>`);
            } else {
                badges.push(`<span class="badge etiquette-badge missing" title="${etiquetteCheck.feedback || 'Address the bench as My Lord'}">❌ My Lord</span>`);
            }
            
            // Citation badge
            if (citationCheck.valid_citation && !citationCheck.wrong_format_cases?.length) {
                badges.push(`<span class="badge citation-badge" title="Correct SCC format used">✅ SCC Format</span>`);
            } else if (citationCheck.wrong_format_cases?.length) {
                badges.push(`<span class="badge citation-badge missing" title="${citationCheck.feedback || 'Use (2017) 10 SCC 1 format'}">❌ SCC Format</span>`);
            } else {
                badges.push(`<span class="badge citation-badge missing" title="Cite as (2017) 10 SCC 1, not 'Puttaswamy case'">❌ SCC Format</span>`);
            }
            
            // Landmark case badge
            if (landmarkCheck.cited_cases?.length) {
                const caseName = landmarkCheck.cited_cases[0].split(' ')[0];
                badges.push(`<span class="badge case-badge" title="Cited ${landmarkCheck.cited_cases[0]}">✅ ${caseName}</span>`);
            } else if (landmarkCheck.missing_cases?.length) {
                const caseName = landmarkCheck.missing_cases[0].split(' ')[0];
                badges.push(`<span class="badge case-badge missing" title="${landmarkCheck.feedback || 'Missing landmark case'}">❌ ${caseName}</span>`);
            }
            
            // Proportionality badge (only for constitutional law)
            if (proportionalityCheck.needs_proportionality) {
                if (proportionalityCheck.addressed) {
                    badges.push(`<span class="badge proportionality-badge" title="Addressed Puttaswamy proportionality test">✅ Proportionality</span>`);
                } else {
                    badges.push(`<span class="badge proportionality-badge missing" title="${proportionalityCheck.feedback || 'Address the four-prong proportionality test'}">❌ Proportionality</span>`);
                }
            }
            
            // Interruption badge
            if (interruptionCheck.should_interrupt) {
                badges.push(`<span class="badge interruption-badge" title="Judge interrupted after ${interruptionCheck.word_count} words">⚡ Interrupted</span>`);
            }
            
            return badges.join('');
        };
        
        // Phase 4: Render score items with hints
        const renderScoreItem = (label, value, hint, showHint) => {
            return `
                <div class="ai-score-item">
                    <span class="ai-score-label">${label}</span>
                    <span class="ai-score-stars">${renderStars(value, showHint)}</span>
                    ${showHint ? `<small class="score-hint">${hint}</small>` : ''}
                </div>
            `;
        };

        const isSessionComplete = this.currentTurn >= 3 || result.session_complete;
        const nextButtonText = isSessionComplete ? 'Session Complete →' : 'Reply to Judge →';
        const nextAction = isSessionComplete ? 'aiJudge.showDebrief()' : 'aiJudge.nextTurn()';

        const html = `
            <div class="ai-screen ai-screen-feedback">
                <div class="ai-judge-avatar">
                    👨‍⚖️ Justice Chandrachud
                </div>
                
                <!-- Phase 4: Behavior Badges -->
                <div class="behavior-badges">
                    ${renderBehaviorBadges()}
                </div>
                
                <div class="ai-feedback-box">
                    <p>${result.feedback || 'Counsel, proceed with your submission.'}</p>
                </div>
                
                <div class="ai-scores">
                    ${renderScoreItem('Legal Accuracy', legalAccuracy, '', false)}
                    ${renderScoreItem('Citation Format', citation, 'Use (2017) 10 SCC 1 format', citation < 3)}
                    ${renderScoreItem('Etiquette', etiquette, 'Say "My Lord" at start', !etiquetteCheck.has_etiquette)}
                </div>
                
                <button class="ai-btn ai-btn-primary ai-btn-large" onclick="${nextAction}">
                    ${nextButtonText}
                </button>
            </div>
        `;

        this.updateContent(html);
    }

    nextTurn() {
        this.currentTurn++;
        this.currentScreen = 'argument';
        this.renderArgument();
    }

    // Screen 4: Debrief
    showDebrief() {
        // Calculate improvement metrics
        const firstTurn = this.turnsData[0];
        const lastTurn = this.turnsData[this.turnsData.length - 1];
        
        const firstCitation = firstTurn?.scores?.citation || 0;
        const lastCitation = lastTurn?.scores?.citation || 0;
        const citationImprovement = lastCitation - firstCitation;
        
        const firstEtiquette = firstTurn?.scores?.etiquette || 0;
        const lastEtiquette = lastTurn?.scores?.etiquette || 0;
        
        // Collect missed cases across all turns
        const allMissedCases = new Set();
        this.turnsData.forEach(turn => {
            if (turn.missing_cases) {
                turn.missing_cases.forEach(c => allMissedCases.add(c));
            }
        });

        const html = `
            <div class="ai-screen ai-screen-debrief">
                <div class="ai-header">
                    <h1>Session Complete ✅</h1>
                    <p>Your AI Practice session summary</p>
                </div>
                
                <div class="ai-metrics">
                    <div class="ai-metric-card">
                        <h4>Citation Accuracy</h4>
                        <p class="ai-metric-value">
                            ${firstCitation}/5 → ${lastCitation}/5
                            ${citationImprovement > 0 ? `<span class="ai-improvement">↑${citationImprovement * 20}%</span>` : ''}
                        </p>
                    </div>
                    
                    <div class="ai-metric-card">
                        <h4>Etiquette Score</h4>
                        <p class="ai-metric-value">${firstEtiquette}/5 → ${lastEtiquette}/5</p>
                    </div>
                    
                    ${allMissedCases.size > 0 ? `
                    <div class="ai-metric-card ai-metric-warning">
                        <h4>Missed Cases</h4>
                        <p>${Array.from(allMissedCases).join(', ')}</p>
                    </div>
                    ` : ''}
                </div>
                
                <div class="ai-cta-buttons">
                    <button class="ai-btn ai-btn-primary ai-btn-large" onclick="aiJudge.restartSameProblem()">
                        Practice Again
                    </button>
                    <button class="ai-btn ai-btn-secondary" onclick="aiJudge.restartNewProblem()">
                        Try New Problem
                    </button>
                    <a href="./moot-court.html" class="ai-btn ai-btn-tertiary">
                        Join Real Competition →
                    </a>
                </div>
            </div>
        `;

        this.updateContent(html);
    }

    restartSameProblem() {
        this.currentTurn = 1;
        this.turnsData = [];
        this.selectProblem(this.currentProblem, this.currentSide);
    }

    restartNewProblem() {
        this.currentScreen = 'problems';
        this.currentProblem = null;
        this.currentSide = null;
        this.currentTurn = 1;
        this.sessionData = null;
        this.turnsData = [];
        this.renderProblems();
    }

    // Utility methods
    updateContent(html) {
        this.container.innerHTML = html;
    }

    showLoading(message = 'Loading...') {
        this.container.innerHTML = `
            <div class="ai-loading">
                <div class="ai-spinner"></div>
                <p>${message}</p>
            </div>
        `;
    }

    hideLoading() {
        // Loading screen is replaced by content
    }

    showError(message) {
        this.container.innerHTML = `
            <div class="ai-error">
                <p>⚠️ ${message}</p>
                <button class="ai-btn ai-btn-secondary" onclick="aiJudge.retry()">Retry</button>
            </div>
        `;
    }

    retry() {
        if (this.currentScreen === 'problems') {
            this.loadProblems();
        } else if (this.currentScreen === 'argument') {
            this.renderArgument();
        }
    }

    render() {
        // Initial render is handled by loadProblems
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('ai-judge-container');
    if (container) {
        window.aiJudge = new AIJudgeInterface('ai-judge-container');
    }
});
