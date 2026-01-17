/**
 * Practice Content - Phase 3.3
 * Module-Aware Practice Mode for Indian Law Students
 */

const API_BASE_URL = 'http://127.0.0.1:8000';

let state = {
    subjects: [],
    modules: [],
    questions: [],
    currentQuestionIndex: 0,
    selectedAnswer: null,
    currentModuleId: null,
    currentModuleTitle: '',
    timerSeconds: 0,
    timerInterval: null,
    results: {
        correct: 0,
        total: 0
    }
};

document.addEventListener('DOMContentLoaded', function() {
    initializePage();
});

async function initializePage() {
    setupEventListeners();
    setupSidebarToggle();
    await loadUserInfo();
    await loadSubjects();
    checkURLParams();
}

function setupEventListeners() {
    document.getElementById('subjectSelect').addEventListener('change', handleSubjectChange);
    document.getElementById('moduleSelect').addEventListener('change', handleModuleChange);
    document.getElementById('startPracticeBtn').addEventListener('click', startPractice);
    document.getElementById('submitAnswerBtn').addEventListener('click', submitAnswer);
    document.getElementById('nextQuestionBtn').addEventListener('click', nextQuestion);

    document.querySelectorAll('.option-btn').forEach(btn => {
        btn.addEventListener('click', () => selectOption(btn.dataset.option));
    });

    document.getElementById('textAnswer').addEventListener('input', function() {
        document.getElementById('submitAnswerBtn').disabled = !this.value.trim();
    });

    document.getElementById('logoutBtn').addEventListener('click', logout);
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

async function loadSubjects() {
    try {
        const response = await apiRequest('/api/curriculum/my-subjects');
        state.subjects = response.subjects || [];

        const select = document.getElementById('subjectSelect');
        select.innerHTML = '<option value="">-- Select Subject --</option>';

        state.subjects.forEach(subject => {
            const option = document.createElement('option');
            option.value = subject.id;
            option.textContent = subject.title;
            select.appendChild(option);
        });
    } catch (err) {
        console.error('Failed to load subjects:', err);
        showToast('Failed to load subjects. Please try again.');
    }
}

async function handleSubjectChange(e) {
    const subjectId = e.target.value;
    const moduleSelect = document.getElementById('moduleSelect');
    const startBtn = document.getElementById('startPracticeBtn');

    moduleSelect.innerHTML = '<option value="">-- Select Module --</option>';
    moduleSelect.disabled = true;
    startBtn.disabled = true;
    state.modules = [];

    if (!subjectId) return;

    try {
        const response = await apiRequest(`/api/content/subjects/${subjectId}/modules`);
        const modules = response.modules || [];

        const practiceModules = modules.filter(m => m.module_type === 'practice' && m.status === 'active');

        if (practiceModules.length === 0) {
            moduleSelect.innerHTML = '<option value="">No practice modules available</option>';
            return;
        }

        state.modules = practiceModules;
        moduleSelect.disabled = false;

        practiceModules.forEach(module => {
            const option = document.createElement('option');
            option.value = module.id;
            option.textContent = module.title;
            moduleSelect.appendChild(option);
        });
    } catch (err) {
        console.error('Failed to load modules:', err);
        showToast('Failed to load modules');
    }
}

function handleModuleChange(e) {
    const moduleId = e.target.value;
    document.getElementById('startPracticeBtn').disabled = !moduleId;
    state.currentModuleId = moduleId;

    const selectedModule = state.modules.find(m => m.id == moduleId);
    state.currentModuleTitle = selectedModule ? selectedModule.title : 'Practice';
}

function checkURLParams() {
    const params = new URLSearchParams(window.location.search);
    const moduleId = params.get('module_id');
    const subjectId = params.get('subject_id');

    if (moduleId) {
        state.currentModuleId = moduleId;
        if (subjectId) {
            document.getElementById('subjectSelect').value = subjectId;
            handleSubjectChange({ target: { value: subjectId } }).then(() => {
                document.getElementById('moduleSelect').value = moduleId;
                handleModuleChange({ target: { value: moduleId } });
            });
        }
    }
}

async function startPractice() {
    if (!state.currentModuleId) {
        showToast('Please select a module first');
        return;
    }

    try {
        showToast('Loading questions...');
        const response = await apiRequest(`/api/practice/module/${state.currentModuleId}`);

        state.questions = response.questions || [];
        state.currentModuleTitle = response.module?.title || 'Practice';
        state.currentQuestionIndex = 0;
        state.selectedAnswer = null;
        state.results = { correct: 0, total: 0 };

        if (state.questions.length === 0) {
            showEmptyState();
            return;
        }

        showQuizSection();
        renderQuestion();
        startTimer();

    } catch (err) {
        console.error('Failed to start practice:', err);
        showToast('Failed to load questions. Please try again.');
    }
}

function showQuizSection() {
    document.getElementById('moduleSelectionSection').classList.add('hidden');
    document.getElementById('emptyStateSection').classList.add('hidden');
    document.getElementById('quizCompleteSection').classList.add('hidden');
    document.getElementById('quizSection').classList.remove('hidden');
}

function showEmptyState() {
    document.getElementById('moduleSelectionSection').classList.add('hidden');
    document.getElementById('quizSection').classList.add('hidden');
    document.getElementById('quizCompleteSection').classList.add('hidden');
    document.getElementById('emptyStateSection').classList.remove('hidden');
}

function goToModuleSelection() {
    stopTimer();
    document.getElementById('quizSection').classList.add('hidden');
    document.getElementById('emptyStateSection').classList.add('hidden');
    document.getElementById('quizCompleteSection').classList.add('hidden');
    document.getElementById('moduleSelectionSection').classList.remove('hidden');
}

function renderQuestion() {
    const question = state.questions[state.currentQuestionIndex];
    if (!question) return;

    document.getElementById('moduleTitle').textContent = state.currentModuleTitle;
    document.getElementById('questionCounter').textContent = 
        `Q${state.currentQuestionIndex + 1} / Q${state.questions.length}`;

    const diffBadge = document.getElementById('difficultyBadge');
    diffBadge.textContent = question.difficulty.charAt(0).toUpperCase() + question.difficulty.slice(1);
    diffBadge.className = `difficulty-badge ${question.difficulty}`;

    document.getElementById('topicTag').textContent = question.topic_tag || 'General';
    document.getElementById('questionText').textContent = question.question;

    const isMCQ = question.type === 'mcq';
    document.getElementById('mcqOptions').classList.toggle('hidden', !isMCQ);
    document.getElementById('textAnswerContainer').classList.toggle('hidden', isMCQ);

    if (isMCQ && question.options) {
        const letters = ['A', 'B', 'C', 'D'];
        question.options.forEach((opt, i) => {
            const optionEl = document.getElementById(`option${letters[i]}`);
            if (optionEl) optionEl.textContent = opt;
        });

        document.querySelectorAll('.option-btn').forEach(btn => {
            btn.classList.remove('selected', 'correct', 'incorrect');
            btn.disabled = false;
        });
    } else {
        document.getElementById('textAnswer').value = '';
    }

    state.selectedAnswer = null;
    document.getElementById('submitAnswerBtn').disabled = true;
    document.getElementById('feedbackPanel').classList.add('hidden');
}

function selectOption(option) {
    state.selectedAnswer = option;

    document.querySelectorAll('.option-btn').forEach(btn => {
        btn.classList.remove('selected');
        if (btn.dataset.option === option) {
            btn.classList.add('selected');
        }
    });

    document.getElementById('submitAnswerBtn').disabled = false;
}

async function submitAnswer() {
    const question = state.questions[state.currentQuestionIndex];
    if (!question) return;

    const isMCQ = question.type === 'mcq';
    let answer = isMCQ ? state.selectedAnswer : document.getElementById('textAnswer').value.trim();

    if (!answer) {
        showToast('Please provide an answer');
        return;
    }

    document.getElementById('submitAnswerBtn').disabled = true;
    document.querySelectorAll('.option-btn').forEach(btn => btn.disabled = true);

    try {
        const response = await apiRequest(`/api/content/practice/${question.id}/attempt`, 'POST', {
            selected_option: answer,
            time_taken_seconds: state.timerSeconds
        });

        state.results.total++;

        if (isMCQ) {
            showMCQFeedback(response, answer);
        } else {
            showTextFeedback(response);
        }

    } catch (err) {
        console.error('Failed to submit answer:', err);
        showToast('Failed to submit answer. Please try again.');
        document.getElementById('submitAnswerBtn').disabled = false;
        document.querySelectorAll('.option-btn').forEach(btn => btn.disabled = false);
    }
}

function showMCQFeedback(response, userAnswer) {
    const isCorrect = response.attempt?.is_correct;
    const correctAnswer = response.question?.correct_answer;
    const explanation = response.question?.explanation;

    if (isCorrect) {
        state.results.correct++;
    }

    document.querySelectorAll('.option-btn').forEach(btn => {
        if (btn.dataset.option === correctAnswer) {
            btn.classList.add('correct');
        } else if (btn.dataset.option === userAnswer && !isCorrect) {
            btn.classList.add('incorrect');
        }
    });

    const feedbackPanel = document.getElementById('feedbackPanel');
    const feedbackIcon = document.getElementById('feedbackIcon');
    const feedbackStatus = document.getElementById('feedbackStatus');

    feedbackIcon.textContent = isCorrect ? '✔' : '❌';
    feedbackStatus.textContent = isCorrect ? 'Correct!' : 'Incorrect';
    feedbackStatus.className = `feedback-status ${isCorrect ? 'correct' : 'incorrect'}`;

    document.getElementById('correctAnswerText').textContent = correctAnswer || 'N/A';
    document.getElementById('explanationText').textContent = explanation || 'No explanation provided.';

    if (response.mastery_update) {
        document.getElementById('masteryText').textContent = 
            `Subject mastery: ${response.mastery_update.subject_mastery_percent}% (${response.mastery_update.strength_label})`;
        document.getElementById('masteryUpdate').classList.remove('hidden');
    } else {
        document.getElementById('masteryUpdate').classList.add('hidden');
    }

    feedbackPanel.classList.remove('hidden');

    const isLast = state.currentQuestionIndex >= state.questions.length - 1;
    document.getElementById('nextQuestionBtn').textContent = isLast ? 'Finish Quiz' : 'Next Question';
}

function showTextFeedback(response) {
    const feedbackPanel = document.getElementById('feedbackPanel');
    const feedbackIcon = document.getElementById('feedbackIcon');
    const feedbackStatus = document.getElementById('feedbackStatus');

    feedbackIcon.textContent = '📝';
    feedbackStatus.textContent = 'Answer Saved';
    feedbackStatus.className = 'feedback-status pending';

    document.getElementById('correctAnswerSection').innerHTML = 
        '<strong>Status:</strong><span>Answer saved. Evaluation pending.</span>';
    document.getElementById('explanationSection').classList.add('hidden');
    document.getElementById('masteryUpdate').classList.add('hidden');

    feedbackPanel.classList.remove('hidden');

    const isLast = state.currentQuestionIndex >= state.questions.length - 1;
    document.getElementById('nextQuestionBtn').textContent = isLast ? 'Finish Quiz' : 'Next Question';
}

function nextQuestion() {
    if (state.currentQuestionIndex >= state.questions.length - 1) {
        showQuizComplete();
        return;
    }

    state.currentQuestionIndex++;
    state.selectedAnswer = null;
    renderQuestion();
}

function showQuizComplete() {
    stopTimer();

    document.getElementById('quizSection').classList.add('hidden');
    document.getElementById('quizCompleteSection').classList.remove('hidden');

    document.getElementById('correctCount').textContent = state.results.correct;
    document.getElementById('totalCount').textContent = state.results.total;

    const accuracy = state.results.total > 0 
        ? Math.round((state.results.correct / state.results.total) * 100) 
        : 0;
    document.getElementById('accuracyPercent').textContent = `${accuracy}%`;
}

function retryQuiz() {
    state.currentQuestionIndex = 0;
    state.selectedAnswer = null;
    state.results = { correct: 0, total: 0 };
    state.timerSeconds = 0;

    document.getElementById('quizCompleteSection').classList.add('hidden');
    showQuizSection();
    renderQuestion();
    startTimer();
}

function startTimer() {
    state.timerSeconds = 0;
    updateTimerDisplay();

    if (state.timerInterval) clearInterval(state.timerInterval);

    state.timerInterval = setInterval(() => {
        state.timerSeconds++;
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
    const minutes = Math.floor(state.timerSeconds / 60);
    const seconds = state.timerSeconds % 60;
    document.getElementById('timerDisplay').textContent = 
        `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
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

window.goToModuleSelection = goToModuleSelection;
window.retryQuiz = retryQuiz;
