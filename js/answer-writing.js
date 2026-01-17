/**
 * Answer Writing Practice - Phase 3.5
 * Long-form exam answer practice for Indian law students
 */

const API_BASE_URL = 'http://127.0.0.1:8000';

let state = {
    moduleId: null,
    questions: [],
    currentQuestion: null,
    timerInterval: null,
    startTime: null,
    elapsedSeconds: 0
};

document.addEventListener('DOMContentLoaded', function() {
    initializePage();
});

async function initializePage() {
    setupEventListeners();
    setupSidebarToggle();
    await loadUserInfo();
    
    const params = new URLSearchParams(window.location.search);
    state.moduleId = params.get('module_id');
    
    if (!state.moduleId) {
        showEmptyState();
        return;
    }
    
    await loadQuestions();
}

function setupEventListeners() {
    document.getElementById('logoutBtn').addEventListener('click', logout);
    document.getElementById('backToQuestionsBtn').addEventListener('click', showQuestionSelection);
    document.getElementById('submitAnswerBtn').addEventListener('click', submitAnswer);
    document.getElementById('tryAnotherBtn').addEventListener('click', showQuestionSelection);
    document.getElementById('viewAttemptsBtn').addEventListener('click', showPastAttempts);
    
    document.getElementById('answerTextarea').addEventListener('input', updateWordCount);
}

function setupSidebarToggle() {
    const menuToggle = document.getElementById('menuToggle');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');

    if (menuToggle && sidebar) {
        menuToggle.addEventListener('click', () => {
            sidebar.classList.toggle('open');
            overlay.classList.toggle('show');
        });
    }

    if (overlay) {
        overlay.addEventListener('click', () => {
            sidebar.classList.remove('open');
            overlay.classList.remove('show');
        });
    }
}

async function loadUserInfo() {
    try {
        const response = await apiRequest('/api/users/me');
        if (response && response.email) {
            document.getElementById('userName').textContent = response.full_name || response.email.split('@')[0];
        }
    } catch (err) {
        console.error('Failed to load user info:', err);
    }
}

async function loadQuestions() {
    showLoading();
    
    try {
        const response = await apiRequest(`/api/practice/answer-writing/${state.moduleId}`);
        
        if (!response.questions || response.questions.length === 0) {
            showEmptyState();
            return;
        }
        
        state.questions = response.questions;
        
        document.getElementById('moduleTitle').textContent = response.module.title;
        document.getElementById('questionCount').textContent = `${response.total_count} question${response.total_count !== 1 ? 's' : ''} available`;
        
        renderQuestionsGrid();
        showQuestionSelection();
        
    } catch (err) {
        console.error('Failed to load questions:', err);
        showEmptyState();
    }
}

function renderQuestionsGrid() {
    const grid = document.getElementById('questionsGrid');
    
    grid.innerHTML = state.questions.map(q => {
        const marksClass = q.marks <= 5 ? 'marks-5' : q.marks <= 10 ? 'marks-10' : 'marks-15';
        
        return `
            <div class="question-card" onclick="selectQuestion(${q.id})">
                <div class="question-card-header">
                    <span class="marks-badge ${marksClass}">${q.marks} Marks</span>
                    ${q.topic_tag ? `<span class="topic-tag">${escapeHtml(q.topic_tag)}</span>` : ''}
                </div>
                <div class="question-card-text">${escapeHtml(q.question)}</div>
                <div class="question-card-footer">
                    <span class="attempt-count">Click to practice</span>
                    <span class="start-btn">Start Writing →</span>
                </div>
            </div>
        `;
    }).join('');
}

function selectQuestion(questionId) {
    const question = state.questions.find(q => q.id === questionId);
    if (!question) return;
    
    state.currentQuestion = question;
    
    const marksClass = question.marks <= 5 ? 'marks-5' : question.marks <= 10 ? 'marks-10' : 'marks-15';
    document.getElementById('marksBadge').textContent = `${question.marks} Marks`;
    document.getElementById('marksBadge').className = `marks-badge ${marksClass}`;
    
    document.getElementById('topicTag').textContent = question.topic_tag || 'General';
    document.getElementById('topicTag').style.display = question.topic_tag ? 'inline' : 'none';
    
    document.getElementById('questionText').textContent = question.question;
    
    const guidelinesList = document.getElementById('guidelinesList');
    const guidelinesSection = document.getElementById('guidelinesSection');
    
    if (question.guidelines && question.guidelines.length > 0) {
        guidelinesList.innerHTML = question.guidelines.map(g => `<li>${escapeHtml(g)}</li>`).join('');
        guidelinesSection.style.display = 'block';
    } else {
        guidelinesSection.style.display = 'none';
    }
    
    const wordLimit = question.marks <= 5 ? 250 : question.marks <= 10 ? 500 : 750;
    document.getElementById('wordLimit').textContent = `(Suggested: ~${wordLimit} words)`;
    
    document.getElementById('answerTextarea').value = '';
    document.getElementById('wordCount').textContent = '0';
    
    document.getElementById('submissionSuccess').classList.add('hidden');
    document.getElementById('pastAttemptsSection').classList.add('hidden');
    document.querySelector('.question-panel').style.display = 'block';
    document.querySelector('.editor-panel').style.display = 'block';
    
    startTimer();
    showAnswerInterface();
    
    document.getElementById('answerTextarea').focus();
}

function showQuestionSelection() {
    stopTimer();
    hideAll();
    document.getElementById('questionSelection').classList.remove('hidden');
}

function showAnswerInterface() {
    hideAll();
    document.getElementById('answerInterface').classList.remove('hidden');
}

function showEmptyState() {
    hideAll();
    document.getElementById('emptyState').classList.remove('hidden');
}

function showLoading() {
    hideAll();
    document.getElementById('loadingState').style.display = 'flex';
}

function hideAll() {
    document.getElementById('loadingState').style.display = 'none';
    document.getElementById('emptyState').classList.add('hidden');
    document.getElementById('questionSelection').classList.add('hidden');
    document.getElementById('answerInterface').classList.add('hidden');
}

function updateWordCount() {
    const text = document.getElementById('answerTextarea').value;
    const words = text.trim() ? text.trim().split(/\s+/).length : 0;
    document.getElementById('wordCount').textContent = words;
}

function startTimer() {
    stopTimer();
    state.startTime = Date.now();
    state.elapsedSeconds = 0;
    
    updateTimerDisplay();
    state.timerInterval = setInterval(() => {
        state.elapsedSeconds = Math.floor((Date.now() - state.startTime) / 1000);
        updateTimerDisplay();
    }, 1000);
}

function stopTimer() {
    if (state.timerInterval) {
        clearInterval(state.timerInterval);
        state.timerInterval = null;
    }
}

function updateTimerDisplay() {
    const minutes = Math.floor(state.elapsedSeconds / 60);
    const seconds = state.elapsedSeconds % 60;
    document.getElementById('timerValue').textContent = 
        `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
}

async function submitAnswer() {
    const answerText = document.getElementById('answerTextarea').value.trim();
    
    if (!answerText) {
        showToast('Please write your answer before submitting');
        return;
    }
    
    if (answerText.length < 10) {
        showToast('Answer must be at least 10 characters');
        return;
    }
    
    stopTimer();
    const timeTakenMinutes = Math.ceil(state.elapsedSeconds / 60);
    
    const submitBtn = document.getElementById('submitAnswerBtn');
    submitBtn.disabled = true;
    submitBtn.innerHTML = 'Submitting...';
    
    try {
        const response = await apiRequest(`/api/practice/answer/${state.currentQuestion.id}/submit`, 'POST', {
            answer_text: answerText,
            time_taken_minutes: timeTakenMinutes
        });
        
        document.querySelector('.question-panel').style.display = 'none';
        document.querySelector('.editor-panel').style.display = 'none';
        document.getElementById('submissionSuccess').classList.remove('hidden');
        
        showToast('Answer submitted successfully!');
        
    } catch (err) {
        console.error('Failed to submit answer:', err);
        showToast('Failed to submit answer. Please try again.');
        startTimer();
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = `
            Submit Answer
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="22" y1="2" x2="11" y2="13"/>
                <polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
        `;
    }
}

async function showPastAttempts() {
    if (!state.currentQuestion) return;
    
    document.getElementById('submissionSuccess').classList.add('hidden');
    document.getElementById('pastAttemptsSection').classList.remove('hidden');
    
    try {
        const response = await apiRequest(`/api/practice/answer/${state.currentQuestion.id}/attempts`);
        
        const attemptsList = document.getElementById('attemptsList');
        const noAttempts = document.getElementById('noAttempts');
        
        if (!response.attempts || response.attempts.length === 0) {
            attemptsList.innerHTML = '';
            noAttempts.classList.remove('hidden');
            return;
        }
        
        noAttempts.classList.add('hidden');
        
        attemptsList.innerHTML = response.attempts.map(attempt => {
            const date = new Date(attempt.attempted_at);
            const formattedDate = date.toLocaleDateString('en-IN', {
                day: 'numeric',
                month: 'short',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
            
            const statusClass = attempt.evaluation?.status === 'completed' ? 'completed' : 'pending';
            const statusText = attempt.evaluation?.status === 'completed' ? 'Reviewed' : 'Pending';
            
            let feedbackHtml = '';
            if (attempt.evaluation?.status === 'completed' && attempt.evaluation?.feedback_text) {
                feedbackHtml = `
                    <div class="feedback-section">
                        <h5>Feedback</h5>
                        <p class="feedback-text">${escapeHtml(attempt.evaluation.feedback_text)}</p>
                        ${attempt.evaluation.strengths?.length || attempt.evaluation.improvements?.length ? `
                            <div class="feedback-lists">
                                ${attempt.evaluation.strengths?.length ? `
                                    <div class="feedback-list strengths">
                                        <h6>Strengths</h6>
                                        <ul>${attempt.evaluation.strengths.map(s => `<li>${escapeHtml(s)}</li>`).join('')}</ul>
                                    </div>
                                ` : ''}
                                ${attempt.evaluation.improvements?.length ? `
                                    <div class="feedback-list improvements">
                                        <h6>Areas for Improvement</h6>
                                        <ul>${attempt.evaluation.improvements.map(i => `<li>${escapeHtml(i)}</li>`).join('')}</ul>
                                    </div>
                                ` : ''}
                            </div>
                        ` : ''}
                    </div>
                `;
            }
            
            return `
                <div class="attempt-card">
                    <div class="attempt-card-header">
                        <span class="attempt-number">Attempt #${attempt.attempt_number}</span>
                        <span class="attempt-date">${formattedDate}</span>
                    </div>
                    <div class="attempt-preview">"${escapeHtml(attempt.answer_preview)}"</div>
                    <div class="attempt-footer">
                        <span class="evaluation-status ${statusClass}">${statusText}</span>
                        ${attempt.time_taken_minutes ? `<span class="time-taken">${attempt.time_taken_minutes} min</span>` : ''}
                    </div>
                    ${feedbackHtml}
                </div>
            `;
        }).join('');
        
    } catch (err) {
        console.error('Failed to load attempts:', err);
        showToast('Failed to load past attempts');
    }
}

async function apiRequest(endpoint, method = 'GET', body = null) {
    const token = localStorage.getItem('access_token');
    const headers = {
        'Content-Type': 'application/json'
    };

    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const config = {
        method,
        headers
    };

    if (body) {
        config.body = JSON.stringify(body);
    }

    const response = await fetch(`${API_BASE_URL}${endpoint}`, config);
    const data = await response.json();

    if (!response.ok) {
        if (response.status === 401) {
            localStorage.removeItem('access_token');
            window.location.href = '/html/login.html';
        }
        throw new Error(data.detail || 'API request failed');
    }

    return data;
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showToast(message) {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 3000);
}

function logout() {
    localStorage.removeItem('access_token');
    window.location.href = '/html/login.html';
}

window.selectQuestion = selectQuestion;
