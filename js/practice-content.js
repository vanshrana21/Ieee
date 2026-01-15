/**
 * practice-content.js
 * Phase 4.4: Practice Question Submission & Attempts
 * Handles answer submission and attempt history display
 */

const API_BASE_URL = 'http://127.0.0.1:8000';

// ============================================================================
// STATE MANAGEMENT
// ============================================================================

let currentQuestion = null;
let currentAttempts = [];
let submissionInProgress = false;

// ============================================================================
// PRACTICE CONTENT FETCHING
// ============================================================================

/**
 * Fetch practice question details
 * @param {number} questionId - Question ID
 * @returns {Promise<Object>} Question data
 */
async function fetchPracticeQuestion(questionId) {
    try {
        const token = window.auth.getToken();
        if (!token) {
            throw new Error('Not authenticated');
        }

        const response = await fetch(`${API_BASE_URL}/api/practice/${questionId}/attempts`, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to fetch question');
        }

        const data = await response.json();
        return {
            success: true,
            data: data
        };

    } catch (error) {
        console.error('Error fetching practice question:', error);
        return {
            success: false,
            error: error.message || 'Network error'
        };
    }
}

/**
 * Submit practice attempt
 * @param {number} questionId - Question ID
 * @param {Object} attemptData - Submission data
 * @returns {Promise<Object>} Submission result
 */
async function submitPracticeAttempt(questionId, attemptData) {
    try {
        const token = window.auth.getToken();
        if (!token) {
            throw new Error('Not authenticated');
        }

        const response = await fetch(`${API_BASE_URL}/api/practice/${questionId}/attempt`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(attemptData)
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to submit attempt');
        }

        const data = await response.json();
        return {
            success: true,
            data: data
        };

    } catch (error) {
        console.error('Error submitting attempt:', error);
        return {
            success: false,
            error: error.message || 'Network error'
        };
    }
}

// ============================================================================
// RENDERING FUNCTIONS
// ============================================================================

/**
 * Render practice question page
 * @param {number} questionId - Question ID to display
 */
async function renderPracticeContent(questionId) {
    const container = document.getElementById('contentContainer');
    if (!container) {
        console.error('Content container not found');
        return;
    }

    // Show loading state
    container.innerHTML = `
        <div class="loading-state">
            <div class="loading-spinner"></div>
            <p>Loading question...</p>
        </div>
    `;

    // Fetch question and attempts
    const result = await fetchPracticeQuestion(questionId);

    if (!result.success) {
        showError(container, result.error);
        return;
    }

    currentQuestion = result.data.question;
    currentAttempts = result.data.attempts || [];

    // Render question UI
    renderQuestionUI(container);
}

/**
 * Render complete question UI
 */
function renderQuestionUI(container) {
    container.innerHTML = '';

    // Header
    const header = createQuestionHeader();
    container.appendChild(header);

    // Question content
    const questionCard = createQuestionCard();
    container.appendChild(questionCard);

    // Answer submission form
    const answerForm = createAnswerForm();
    container.appendChild(answerForm);

    // Attempt history
    if (currentAttempts.length > 0) {
        const historySection = createAttemptHistory();
        container.appendChild(historySection);
    }
}

/**
 * Create question header
 */
function createQuestionHeader() {
    const header = document.createElement('div');
    header.className = 'content-header';

    const difficultyColor = {
        'easy': '#10b981',
        'medium': '#f59e0b',
        'hard': '#ef4444'
    }[currentQuestion.difficulty] || '#64748b';

    header.innerHTML = `
        <button onclick="goBackToPractice()" class="back-button">
            ← Back to Practice
        </button>
        
        <div class="question-meta">
            <span class="question-type-badge">${formatQuestionType(currentQuestion.question_type)}</span>
            <span class="difficulty-badge" style="background: ${difficultyColor}20; color: ${difficultyColor}">
                ${currentQuestion.difficulty ? currentQuestion.difficulty.toUpperCase() : 'MEDIUM'}
            </span>
            <span class="marks-badge">${currentQuestion.marks} mark${currentQuestion.marks !== 1 ? 's' : ''}</span>
        </div>
    `;

    return header;
}

/**
 * Create question card
 */
function createQuestionCard() {
    const card = document.createElement('div');
    card.className = 'question-card';

    card.innerHTML = `
        <h2 class="question-title">Question</h2>
        <p class="question-text">${currentQuestion.question}</p>
    `;

    return card;
}

/**
 * Create answer submission form
 */
function createAnswerForm() {
    const form = document.createElement('div');
    form.className = 'answer-form';
    form.id = 'answerForm';

    if (currentQuestion.question_type === 'mcq') {
        // MCQ options
        form.innerHTML = `
            <h3 class="form-title">Your Answer</h3>
            <div class="mcq-options" id="mcqOptions">
                <label class="mcq-option">
                    <input type="radio" name="mcq_answer" value="A" />
                    <span class="option-label">A</span>
                    <span class="option-text">${currentQuestion.option_a || 'Option A'}</span>
                </label>
                <label class="mcq-option">
                    <input type="radio" name="mcq_answer" value="B" />
                    <span class="option-label">B</span>
                    <span class="option-text">${currentQuestion.option_b || 'Option B'}</span>
                </label>
                <label class="mcq-option">
                    <input type="radio" name="mcq_answer" value="C" />
                    <span class="option-label">C</span>
                    <span class="option-text">${currentQuestion.option_c || 'Option C'}</span>
                </label>
                <label class="mcq-option">
                    <input type="radio" name="mcq_answer" value="D" />
                    <span class="option-label">D</span>
                    <span class="option-text">${currentQuestion.option_d || 'Option D'}</span>
                </label>
            </div>
            <div class="form-actions">
                <button onclick="handleSubmitAnswer()" class="submit-button" id="submitButton">
                    Submit Answer
                </button>
            </div>
            <div id="feedbackMessage" class="feedback-message" style="display: none;"></div>
        `;
    } else {
        // Descriptive answer
        form.innerHTML = `
            <h3 class="form-title">Your Answer</h3>
            <textarea 
                id="answerTextarea" 
                class="answer-textarea" 
                placeholder="Write your answer here..."
                rows="8"
            ></textarea>
            <div class="form-actions">
                <button onclick="handleSubmitAnswer()" class="submit-button" id="submitButton">
                    Submit Answer
                </button>
            </div>
            <div id="feedbackMessage" class="feedback-message" style="display: none;"></div>
        `;
    }

    return form;
}

/**
 * Create attempt history section
 */
function createAttemptHistory() {
    const section = document.createElement('div');
    section.className = 'attempt-history';
    section.id = 'attemptHistory';

    let historyHTML = `
        <h3 class="history-title">
            Your Attempts (${currentAttempts.length})
        </h3>
        <div class="attempts-list">
    `;

    currentAttempts.forEach((attempt, index) => {
        const isCorrect = attempt.is_correct;
        const statusIcon = isCorrect === true ? '✓' : isCorrect === false ? '✗' : '⏳';
        const statusClass = isCorrect === true ? 'correct' : isCorrect === false ? 'incorrect' : 'pending';
        
        historyHTML += `
            <div class="attempt-item ${statusClass}">
                <div class="attempt-header">
                    <span class="attempt-number">Attempt #${attempt.attempt_number}</span>
                    <span class="attempt-status">${statusIcon}</span>
                </div>
                <div class="attempt-details">
                    <p class="attempt-answer">
                        <strong>Your answer:</strong> 
                        ${attempt.selected_option.length <= 100 ? 
                            attempt.selected_option : 
                            attempt.selected_option.substring(0, 100) + '...'
                        }
                    </p>
                    <div class="attempt-meta">
                        <span>${formatDateTime(attempt.attempted_at)}</span>
                        ${attempt.time_taken_seconds ? 
                            `<span>⏱️ ${formatTime(attempt.time_taken_seconds)}</span>` : ''
                        }
                    </div>
                </div>
            </div>
        `;
    });

    historyHTML += `</div>`;
    section.innerHTML = historyHTML;

    return section;
}

// ============================================================================
// SUBMISSION HANDLER
// ============================================================================

/**
 * Handle answer submission
 */
async function handleSubmitAnswer() {
    if (submissionInProgress) {
        return;
    }

    const submitButton = document.getElementById('submitButton');
    const feedbackMessage = document.getElementById('feedbackMessage');

    // Get answer based on question type
    let attemptData = {};

    if (currentQuestion.question_type === 'mcq') {
        const selectedOption = document.querySelector('input[name="mcq_answer"]:checked');
        
        if (!selectedOption) {
            showFeedback('Please select an answer', 'error');
            return;
        }

        attemptData.selected_option = selectedOption.value;
    } else {
        const answerTextarea = document.getElementById('answerTextarea');
        const answerText = answerTextarea ? answerTextarea.value.trim() : '';

        if (!answerText || answerText.length < 10) {
            showFeedback('Please write a meaningful answer (at least 10 characters)', 'error');
            return;
        }

        attemptData.answer_text = answerText;
    }

    // Disable submit button
    submissionInProgress = true;
    submitButton.disabled = true;
    submitButton.textContent = 'Submitting...';

    // Submit attempt
    const result = await submitPracticeAttempt(currentQuestion.id, attemptData);

    if (result.success) {
        // Show success feedback
        const response = result.data;
        const message = response.message || 'Answer submitted successfully';
        
        showFeedback(message, response.attempt.is_correct === true ? 'success' : 
                              response.attempt.is_correct === false ? 'error' : 'info');

        // Show explanation for MCQs
        if (currentQuestion.question_type === 'mcq' && response.question.explanation) {
            setTimeout(() => {
                showExplanation(response.question.explanation, response.question.correct_answer);
            }, 1500);
        }

        // Clear form
        clearAnswerForm();

        // Reload question to get updated attempts
        setTimeout(async () => {
            const refreshResult = await fetchPracticeQuestion(currentQuestion.id);
            if (refreshResult.success) {
                currentAttempts = refreshResult.data.attempts || [];
                updateAttemptHistory();
            }
        }, 2000);

    } else {
        showFeedback(result.error || 'Failed to submit answer', 'error');
    }

    // Re-enable submit button
    submissionInProgress = false;
    submitButton.disabled = false;
    submitButton.textContent = 'Submit Answer';
}

/**
 * Show feedback message
 */
function showFeedback(message, type) {
    const feedbackMessage = document.getElementById('feedbackMessage');
    if (!feedbackMessage) return;

    feedbackMessage.textContent = message;
    feedbackMessage.className = `feedback-message ${type}`;
    feedbackMessage.style.display = 'block';

    setTimeout(() => {
        feedbackMessage.style.display = 'none';
    }, 5000);
}

/**
 * Show explanation for MCQ
 */
function showExplanation(explanation, correctAnswer) {
    const feedbackMessage = document.getElementById('feedbackMessage');
    if (!feedbackMessage) return;

    feedbackMessage.innerHTML = `
        <strong>Correct Answer: ${correctAnswer}</strong><br/>
        ${explanation}
    `;
    feedbackMessage.className = 'feedback-message info';
    feedbackMessage.style.display = 'block';
}

/**
 * Clear answer form
 */
function clearAnswerForm() {
    if (currentQuestion.question_type === 'mcq') {
        const options = document.querySelectorAll('input[name="mcq_answer"]');
        options.forEach(option => option.checked = false);
    } else {
        const textarea = document.getElementById('answerTextarea');
        if (textarea) textarea.value = '';
    }
}

/**
 * Update attempt history section
 */
function updateAttemptHistory() {
    const container = document.getElementById('contentContainer');
    if (!container) return;

    // Remove old history
    const oldHistory = document.getElementById('attemptHistory');
    if (oldHistory) {
        oldHistory.remove();
    }

    // Add new history if there are attempts
    if (currentAttempts.length > 0) {
        const historySection = createAttemptHistory();
        container.appendChild(historySection);
    }
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Format question type for display
 */
function formatQuestionType(type) {
    const types = {
        'mcq': 'Multiple Choice',
        'short_answer': 'Short Answer',
        'essay': 'Essay',
        'case_analysis': 'Case Analysis'
    };
    return types[type] || type;
}

/**
 * Format datetime for display
 */
function formatDateTime(isoString) {
    const date = new Date(isoString);
    const now = new Date();
    const diff = now - date;
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (minutes < 1) return 'Just now';
    if (minutes < 60) return `${minutes} minute${minutes !== 1 ? 's' : ''} ago`;
    if (hours < 24) return `${hours} hour${hours !== 1 ? 's' : ''} ago`;
    if (days < 7) return `${days} day${days !== 1 ? 's' : ''} ago`;
    
    return date.toLocaleDateString('en-IN', { 
        day: 'numeric', 
        month: 'short', 
        year: 'numeric' 
    });
}

/**
 * Format time duration
 */
function formatTime(seconds) {
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}m ${remainingSeconds}s`;
}

/**
 * Show error state
 */
function showError(container, message) {
    container.innerHTML = `
        <div class="error-state">
            <div style="font-size: 64px; margin-bottom: 16px;">⚠️</div>
            <h2>Error</h2>
            <p>${message}</p>
            <button onclick="goBackToPractice()" class="primary-button">
                Back to Practice
            </button>
        </div>
    `;
}

/**
 * Navigate back to practice module
 */
function goBackToPractice() {
    window.history.back();
}

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Check if we're on the practice content page
    const contentContainer = document.getElementById('contentContainer');
    if (contentContainer) {
        // Get question ID from URL
        const urlParams = new URLSearchParams(window.location.search);
        const questionId = urlParams.get('id');

        if (questionId) {
            renderPracticeContent(parseInt(questionId));
        } else {
            showError(contentContainer, 'No question ID provided');
        }
    }
});

// ============================================================================
// GLOBAL EXPORTS
// ============================================================================

window.practiceContent = {
    renderPracticeContent,
    handleSubmitAnswer,
    goBackToPractice
};