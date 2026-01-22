/**
 * Practice Content - Phase 3.3 + Phase 9.4 Robustness
 * Semester 1 ONLY - Demo Standard
 */

const API_BASE_URL = 'http://127.0.0.1:8000';

// Semester 1 Fixed Curriculum Data
const SEM1_CURRICULUM = [
    {
        id: 'eng_1',
        title: 'General and Legal English',
        modules: [
            'Vocabulary & Legal Terminology',
            'Grammar & Sentence Correction',
            'Comprehension Passages',
            'Legal Writing (Short Notes / Paragraphs)',
            'Essay Writing (10–15 marks)',
            'Precis Writing'
        ]
    },
    {
        id: 'pol_1',
        title: 'Fundamental Principles of Political Science',
        modules: [
            'Political Theory Concepts (State, Sovereignty, Power)',
            'Thinkers-Based Questions (Plato, Aristotle, Hobbes, Locke, Rousseau)',
            'Short Answer Practice (2–5 marks)',
            'Long Answer Practice (10–15 marks)',
            'Conceptual MCQs'
        ]
    },
    {
        id: 'soc_1',
        title: 'Sociology–I (Legal Sociology)',
        modules: [
            'Law and Society (Basics)',
            'Social Institutions & Law',
            'Law as an Instrument of Social Change',
            'Short Notes Practice',
            'Case-Based Sociological Questions',
            'Conceptual MCQs'
        ]
    },
    {
        id: 'his_1',
        title: 'Indian History – Part I',
        modules: [
            'Ancient Indian History',
            'Medieval Indian History',
            'Society, Culture & Administration',
            'Short Answer Practice',
            'Long Answer Practice',
            'Timeline & Assertion-Based MCQs'
        ]
    }
];

// Deterministic Mock Questions for Demo
const MOCK_QUESTIONS = {
    'eng_1': {
        'Vocabulary & Legal Terminology': [
            {
                id: 'q1',
                type: 'mcq',
                difficulty: 'medium',
                topic_tag: 'Legal Terms',
                question: 'What does the legal term "Amicus Curiae" literally translate to?',
                options: ['Friend of the court', 'Enemy of the state', 'Legal representative', 'Presiding officer'],
                correct_answer: 'A',
                explanation: 'Amicus Curiae is a Latin phrase meaning "friend of the court". It refers to someone who is not a party to a case but offers information that bears on the case.'
            }
        ],
        'Grammar & Sentence Correction': [
            {
                id: 'q2',
                type: 'mcq',
                difficulty: 'easy',
                topic_tag: 'Grammar',
                question: 'Identify the grammatically correct sentence:',
                options: [
                    'The judge has gave his verdict.',
                    'The judge has given his verdict.',
                    'The judge have given his verdict.',
                    'The judge had give his verdict.'
                ],
                correct_answer: 'B',
                explanation: 'The present perfect tense requires "has" (for singular) + past participle (given).'
            }
        ]
    },
    'pol_1': {
        'Political Theory Concepts (State, Sovereignty, Power)': [
            {
                id: 'q3',
                type: 'mcq',
                difficulty: 'medium',
                topic_tag: 'Sovereignty',
                question: 'According to Austin, what is the essential characteristic of sovereignty?',
                options: ['Indivisibility', 'Popular will', 'Divine right', 'Moral authority'],
                correct_answer: 'A',
                explanation: 'John Austin characterized sovereignty as absolute, perpetual, and indivisible.'
            }
        ],
        'Thinkers-Based Questions (Plato, Aristotle, Hobbes, Locke, Rousseau)': [
            {
                id: 'q4',
                type: 'mcq',
                difficulty: 'hard',
                topic_tag: 'Thinkers',
                question: 'Who is the author of the work "Leviathan"?',
                options: ['John Locke', 'Thomas Hobbes', 'Jean-Jacques Rousseau', 'Niccolò Machiavelli'],
                correct_answer: 'B',
                explanation: 'Thomas Hobbes published "Leviathan" in 1651, outlining his social contract theory.'
            }
        ]
    },
    'soc_1': {
        'Law and Society (Basics)': [
            {
                id: 'q5',
                type: 'mcq',
                difficulty: 'medium',
                topic_tag: 'Sociology',
                question: 'Who coined the term "Sociology"?',
                options: ['Max Weber', 'Karl Marx', 'Auguste Comte', 'Emile Durkheim'],
                correct_answer: 'C',
                explanation: 'Auguste Comte is often called the "Father of Sociology" for coining the term in 1838.'
            }
        ]
    },
    'his_1': {
        'Ancient Indian History': [
            {
                id: 'q6',
                type: 'mcq',
                difficulty: 'easy',
                topic_tag: 'Indus Valley',
                question: 'Which was the major port city of the Indus Valley Civilization?',
                options: ['Harappa', 'Mohenjo-daro', 'Lothal', 'Kalibangan'],
                correct_answer: 'C',
                explanation: 'Lothal was a prominent port city of the Indus Valley Civilization, located in modern-day Gujarat.'
            }
        ]
    }
};

let state = {
    subjects: SEM1_CURRICULUM,
    modules: [],
    questions: [],
    currentQuestionIndex: 0,
    selectedAnswer: null,
    currentModuleId: null,
    currentModuleTitle: '',
    timerSeconds: 0,
    timerInterval: null,
    isLoading: false,
    results: {
        correct: 0,
        total: 0
    }
};

document.addEventListener('DOMContentLoaded', function() {
    initializePage();
});

async function initializePage() {
    if (window.JurisSessionManager && !window.JurisSessionManager.checkAuth()) {
        window.JurisSessionManager.requireAuth();
        return;
    }

    setupEventListeners();
    setupSidebarToggle();
    await loadUserInfo();
    loadSubjects(); // Synchronous for demo
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

function loadSubjects() {
    const select = document.getElementById('subjectSelect');
    select.innerHTML = '<option value="">-- Select Subject --</option>';

    state.subjects.forEach(subject => {
        const option = document.createElement('option');
        option.value = subject.id;
        option.textContent = subject.title;
        select.appendChild(option);
    });
}

function handleSubjectChange(e) {
    const subjectId = e.target.value;
    const moduleSelect = document.getElementById('moduleSelect');
    const startBtn = document.getElementById('startPracticeBtn');

    moduleSelect.innerHTML = '<option value="">-- Select Practice Module --</option>';
    moduleSelect.disabled = true;
    startBtn.disabled = true;
    state.modules = [];

    if (!subjectId) return;

    const subject = state.subjects.find(s => s.id === subjectId);
    if (!subject) return;

    state.modules = subject.modules;
    moduleSelect.disabled = false;

    subject.modules.forEach(moduleName => {
        const option = document.createElement('option');
        option.value = moduleName;
        option.textContent = moduleName;
        moduleSelect.appendChild(option);
    });
}

function handleModuleChange(e) {
    const moduleName = e.target.value;
    document.getElementById('startPracticeBtn').disabled = !moduleName;
    state.currentModuleId = moduleName;
    state.currentModuleTitle = moduleName;
}

function checkURLParams() {
    const params = new URLSearchParams(window.location.search);
    const subjectId = params.get('subject_id');
    const moduleName = params.get('module_name');

    if (subjectId) {
        document.getElementById('subjectSelect').value = subjectId;
        handleSubjectChange({ target: { value: subjectId } });
        
        if (moduleName) {
            document.getElementById('moduleSelect').value = moduleName;
            handleModuleChange({ target: { value: moduleName } });
        }
    }
}

async function startPractice() {
    const subjectSelect = document.getElementById('subjectSelect');
    const subjectId = subjectSelect.value;
    const moduleName = state.currentModuleId;

    if (!subjectId || !moduleName) {
        showToast('Please select both subject and module');
        return;
    }

    try {
        showToast('Starting Practice Session...');
        
        // Use Mock Data if available, otherwise fallback to "Coming Soon" or generic
        let questions = [];
        if (MOCK_QUESTIONS[subjectId] && MOCK_QUESTIONS[subjectId][moduleName]) {
            questions = MOCK_QUESTIONS[subjectId][moduleName];
        } else {
            // Generic mock questions for other modules
            questions = [
                {
                    id: 'gen_q1',
                    type: 'mcq',
                    difficulty: 'medium',
                    topic_tag: 'Practice',
                    question: `Practice question for ${moduleName} in ${subjectSelect.options[subjectSelect.selectedIndex].text}.`,
                    options: ['Option A', 'Option B', 'Option C', 'Option D'],
                    correct_answer: 'A',
                    explanation: 'Detailed explanation for the correct answer.'
                }
            ];
        }

        state.questions = questions;
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
        showToast('Error starting practice.');
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
        // FOR DEMO: Evaluate locally to ensure reliability
        const isCorrect = isMCQ ? (answer === question.correct_answer) : true;
        
        const mockResponse = {
            attempt: {
                is_correct: isCorrect,
                selected_option: answer
            },
            question: {
                correct_answer: question.correct_answer,
                explanation: question.explanation
            },
            mastery_update: {
                subject_mastery_percent: 75,
                strength_label: 'Strong'
            }
        };

        state.results.total++;

        if (isMCQ) {
            showMCQFeedback(mockResponse, answer);
        } else {
            showTextFeedback(mockResponse);
        }

    } catch (err) {
        console.error('Failed to submit answer:', err);
        showToast('Error submitting answer.');
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
            if (window.JurisErrorHandler) {
                window.JurisErrorHandler.handleAuthError();
            } else {
                localStorage.removeItem('access_token');
                window.location.href = '/html/login.html';
            }
        }
        throw new Error(data.detail || 'API request failed');
    }

    return data;
}

function showToast(message, type = 'info') {
    if (window.JurisErrorHandler) {
        window.JurisErrorHandler.showToast(message, type === 'error' ? 'error' : 'info');
        return;
    }
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
