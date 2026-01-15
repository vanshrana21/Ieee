/**
 * evaluation-ui.js
 * Phase 5: AI Evaluation & Feedback UI Integration
 * 
 * Minimal frontend extension for practice-content.js
 * Handles evaluation triggering, polling, and display
 */

const EVALUATION_API = 'http://127.0.0.1:8000/api/practice/attempts';
const POLL_INTERVAL = 3000; // Poll every 3 seconds
const MAX_POLL_ATTEMPTS = 20; // Max 60 seconds of polling

let evaluationPollTimer = null;
let pollAttemptCount = 0;

/**
 * Trigger AI evaluation for an attempt
 * @param {number} attemptId - Attempt ID
 * @returns {Promise<Object>} Evaluation trigger result
 */
async function triggerEvaluation(attemptId) {
    try {
        const token = window.auth.getToken();
        if (!token) {
            throw new Error('Not authenticated');
        }

        const response = await fetch(`${EVALUATION_API}/${attemptId}/evaluate`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to trigger evaluation');
        }

        const data = await response.json();
        return {
            success: true,
            data: data
        };

    } catch (error) {
        console.error('Error triggering evaluation:', error);
        return {
            success: false,
            error: error.message || 'Network error'
        };
    }
}

/**
 * Fetch evaluation status/results
 * @param {number} attemptId - Attempt ID
 * @returns {Promise<Object>} Evaluation data
 */
async function fetchEvaluation(attemptId) {
    try {
        const token = window.auth.getToken();
        if (!token) {
            throw new Error('Not authenticated');
        }

        const response = await fetch(`${EVALUATION_API}/${attemptId}/evaluation`, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to fetch evaluation');
        }

        const data = await response.json();
        return {
            success: true,
            data: data
        };

    } catch (error) {
        console.error('Error fetching evaluation:', error);
        return {
            success: false,
            error: error.message || 'Network error'
        };
    }
}

/**
 * Start polling for evaluation completion
 * @param {number} attemptId - Attempt ID
 */
function startEvaluationPolling(attemptId) {
    // Clear any existing poll timer
    stopEvaluationPolling();
    
    pollAttemptCount = 0;
    
    evaluationPollTimer = setInterval(async () => {
        pollAttemptCount++;
        
        // Stop polling after max attempts
        if (pollAttemptCount > MAX_POLL_ATTEMPTS) {
            stopEvaluationPolling();
            showEvaluationTimeout();
            return;
        }
        
        // Fetch evaluation status
        const result = await fetchEvaluation(attemptId);
        
        if (!result.success) {
            console.error('Polling error:', result.error);
            return;
        }
        
        const status = result.data.status;
        
        if (status === 'completed') {
            // Evaluation complete - display results
            stopEvaluationPolling();
            displayEvaluationResults(result.data.evaluation);
        } else if (status === 'failed') {
            // Evaluation failed
            stopEvaluationPolling();
            showEvaluationError(result.data.message);
        }
        // Otherwise keep polling (pending/processing)
        
    }, POLL_INTERVAL);
}

/**
 * Stop evaluation polling
 */
function stopEvaluationPolling() {
    if (evaluationPollTimer) {
        clearInterval(evaluationPollTimer);
        evaluationPollTimer = null;
    }
}

/**
 * Display evaluation results in UI
 * @param {Object} evaluation - Evaluation data
 */
function displayEvaluationResults(evaluation) {
    // Remove pending message
    const pendingCard = document.getElementById('evaluationPending');
    if (pendingCard) {
        pendingCard.remove();
    }
    
    // Create evaluation card
    const evaluationCard = createEvaluationCard(evaluation);
    
    // Insert after answer form
    const answerForm = document.getElementById('answerForm');
    if (answerForm) {
        answerForm.after(evaluationCard);
    } else {
        // Fallback: append to container
        const container = document.getElementById('contentContainer');
        if (container) {
            container.appendChild(evaluationCard);
        }
    }
}

/**
 * Create evaluation results card
 * @param {Object} evaluation - Evaluation data
 * @returns {HTMLElement} Evaluation card element
 */
function createEvaluationCard(evaluation) {
    const card = document.createElement('div');
    card.className = 'evaluation-card';
    card.id = 'evaluationResults';
    
    let html = `
        <div class="evaluation-header">
            <h3 class="evaluation-title">✨ AI Evaluation</h3>
    `;
    
    // Score badge (if available)
    if (evaluation.score !== null && evaluation.score !== undefined) {
        html += `
            <div class="evaluation-score">
                <span class="score-value">${evaluation.score}</span>
                <span class="score-label">/ ${currentQuestion.marks}</span>
            </div>
        `;
    }
    
    html += `</div>`;
    
    // Feedback text
    if (evaluation.feedback_text) {
        html += `
            <div class="evaluation-section">
                <h4 class="section-title">📝 Overall Feedback</h4>
                <p class="feedback-text">${evaluation.feedback_text}</p>
            </div>
        `;
    }
    
    // Strengths
    if (evaluation.strengths && evaluation.strengths.length > 0) {
        html += `
            <div class="evaluation-section">
                <h4 class="section-title">💪 Strengths</h4>
                <ul class="feedback-list strengths-list">
        `;
        evaluation.strengths.forEach(strength => {
            html += `<li>✓ ${strength}</li>`;
        });
        html += `</ul></div>`;
    }
    
    // Improvements
    if (evaluation.improvements && evaluation.improvements.length > 0) {
        html += `
            <div class="evaluation-section">
                <h4 class="section-title">🎯 Areas for Improvement</h4>
                <ul class="feedback-list improvements-list">
        `;
        evaluation.improvements.forEach(improvement => {
            html += `<li>→ ${improvement}</li>`;
        });
        html += `</ul></div>`;
    }
    
    // Rubric breakdown (if available)
    if (evaluation.rubric_breakdown) {
        html += `
            <div class="evaluation-section">
                <h4 class="section-title">📊 Detailed Breakdown</h4>
                <div class="rubric-breakdown">
        `;
        
        for (const [criterion, score] of Object.entries(evaluation.rubric_breakdown)) {
            const criterionLabel = criterion.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
            html += `
                <div class="rubric-item">
                    <span class="rubric-label">${criterionLabel}</span>
                    <span class="rubric-score">${score}/10</span>
                </div>
            `;
        }
        
        html += `</div></div>`;
    }
    
    // Confidence indicator
    if (evaluation.confidence_score) {
        const confidencePercent = Math.round(evaluation.confidence_score * 100);
        html += `
            <div class="evaluation-footer">
                <span class="confidence-label">AI Confidence: ${confidencePercent}%</span>
            </div>
        `;
    }
    
    card.innerHTML = html;
    return card;
}

/**
 * Show evaluation pending message
 */
function showEvaluationPending() {
    const pendingCard = document.createElement('div');
    pendingCard.className = 'evaluation-pending';
    pendingCard.id = 'evaluationPending';
    
    pendingCard.innerHTML = `
        <div class="pending-content">
            <div class="pending-spinner"></div>
            <h4>🤖 AI is evaluating your answer...</h4>
            <p>This may take 10-30 seconds. Results will appear automatically.</p>
        </div>
    `;
    
    // Insert after answer form
    const answerForm = document.getElementById('answerForm');
    if (answerForm) {
        answerForm.after(pendingCard);
    }
}

/**
 * Show evaluation timeout message
 */
function showEvaluationTimeout() {
    const pendingCard = document.getElementById('evaluationPending');
    if (pendingCard) {
        pendingCard.innerHTML = `
            <div class="pending-content">
                <h4>⏱️ Evaluation is taking longer than expected</h4>
                <p>Please refresh the page in a few moments to see your results.</p>
                <button onclick="window.location.reload()" class="refresh-button">
                    Refresh Page
                </button>
            </div>
        `;
    }
}

/**
 * Show evaluation error
 * @param {string} message - Error message
 */
function showEvaluationError(message) {
    const pendingCard = document.getElementById('evaluationPending');
    if (pendingCard) {
        pendingCard.innerHTML = `
            <div class="pending-content error">
                <h4>❌ Evaluation Failed</h4>
                <p>${message || 'An error occurred during evaluation.'}</p>
                <p>You can try again or contact support if the issue persists.</p>
            </div>
        `;
    }
}

/**
 * Handle answer submission with automatic evaluation
 * This extends the existing handleSubmitAnswer function
 */
async function handleSubmitAnswerWithEvaluation() {
    // Call original submission handler
    const submitResult = await window.practiceContent.handleSubmitAnswer();
    
    if (!submitResult || !submitResult.success) {
        return; // Submission failed, don't trigger evaluation
    }
    
    const attemptId = submitResult.attemptId;
    
    // Check if this is a descriptive question (MCQs don't need AI evaluation)
    const questionType = currentQuestion.question_type;
    
    if (questionType === 'mcq') {
        // MCQs already have feedback, skip AI evaluation
        return;
    }
    
    // Show pending message
    showEvaluationPending();
    
    // Trigger evaluation
    const triggerResult = await triggerEvaluation(attemptId);
    
    if (!triggerResult.success) {
        showEvaluationError(triggerResult.error);
        return;
    }
    
    // Start polling for results
    startEvaluationPolling(attemptId);
}

/**
 * Check for existing evaluation on page load
 * @param {number} attemptId - Attempt ID
 */
async function checkExistingEvaluation(attemptId) {
    const result = await fetchEvaluation(attemptId);
    
    if (!result.success) {
        return; // No evaluation or error
    }
    
    const status = result.data.status;
    
    if (status === 'completed') {
        // Display existing evaluation
        displayEvaluationResults(result.data.evaluation);
    } else if (status === 'processing' || status === 'pending') {
        // Evaluation in progress - start polling
        showEvaluationPending();
        startEvaluationPolling(attemptId);
    } else if (status === 'failed') {
        // Show error
        showEvaluationError(result.data.message);
    }
    // status === 'not_found' - no evaluation exists, do nothing
}

// ============================================================================
// INTEGRATION WITH EXISTING PRACTICE-CONTENT.JS
// ============================================================================

/**
 * Initialize evaluation UI on page load
 * Call this after practice question is loaded
 */
function initializeEvaluationUI() {
    // Override submit button if descriptive question
    if (currentQuestion && currentQuestion.question_type !== 'mcq') {
        const submitButton = document.getElementById('submitButton');
        if (submitButton) {
            // Remove old event listener and add new one
            submitButton.onclick = null;
            submitButton.addEventListener('click', handleSubmitAnswerWithEvaluation);
        }
    }
    
    // Check for existing evaluations in attempt history
    if (currentAttempts && currentAttempts.length > 0) {
        // Check most recent attempt
        const latestAttempt = currentAttempts[0];
        if (latestAttempt && latestAttempt.id) {
            checkExistingEvaluation(latestAttempt.id);
        }
    }
}

// ============================================================================
// CSS STYLES (ADD TO PRACTICE-CONTENT.CSS)
// ============================================================================
/*
.evaluation-card {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border-radius: 12px;
    padding: 32px;
    margin: 24px 0;
    box-shadow: 0 8px 24px rgba(102, 126, 234, 0.3);
}

.evaluation-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
}

.evaluation-title {
    font-size: 22px;
    font-weight: 700;
    margin: 0;
}

.evaluation-score {
    background: rgba(255, 255, 255, 0.2);
    padding: 12px 20px;
    border-radius: 8px;
    backdrop-filter: blur(10px);
}

.score-value {
    font-size: 28px;
    font-weight: 700;
}

.score-label {
    font-size: 16px;
    opacity: 0.9;
}

.evaluation-section {
    background: rgba(255, 255, 255, 0.1);
    border-radius: 8px;
    padding: 20px;
    margin-bottom: 16px;
    backdrop-filter: blur(10px);
}

.section-title {
    font-size: 16px;
    font-weight: 600;
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
}

.feedback-text {
    line-height: 1.8;
    font-size: 15px;
    margin: 0;
}

.feedback-list {
    list-style: none;
    padding: 0;
    margin: 0;
}

.feedback-list li {
    padding: 8px 0;
    line-height: 1.6;
    font-size: 15px;
}

.rubric-breakdown {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 12px;
}

.rubric-item {
    display: flex;
    justify-content: space-between;
    padding: 12px;
    background: rgba(255, 255, 255, 0.15);
    border-radius: 6px;
}

.rubric-label {
    font-size: 14px;
}

.rubric-score {
    font-weight: 700;
}

.evaluation-footer {
    text-align: center;
    padding-top: 16px;
    opacity: 0.8;
    font-size: 13px;
}

.evaluation-pending {
    background: white;
    border: 2px dashed #cbd5e1;
    border-radius: 12px;
    padding: 32px;
    margin: 24px 0;
    text-align: center;
}

.pending-content h4 {
    font-size: 18px;
    color: #0f172a;
    margin-bottom: 8px;
}

.pending-content p {
    color: #64748b;
    font-size: 14px;
}

.pending-spinner {
    width: 40px;
    height: 40px;
    border: 4px solid #e2e8f0;
    border-top-color: #667eea;
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin: 0 auto 16px;
}

@keyframes spin {
    to { transform: rotate(360deg); }
}

.refresh-button {
    background: #1A3D6D;
    color: white;
    border: none;
    padding: 10px 24px;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    margin-top: 16px;
}

.refresh-button:hover {
    background: #0C2B4E;
}
*/

// ============================================================================
// GLOBAL EXPORTS
// ============================================================================

window.evaluationUI = {
    triggerEvaluation,
    fetchEvaluation,
    checkExistingEvaluation,
    initializeEvaluationUI,
    displayEvaluationResults
};