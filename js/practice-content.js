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
    loadSubjects(); // Load subjects BEFORE attaching listeners
    setupEventListeners();
    setupSidebarToggle();
    await loadUserInfo();
    checkURLParams();
}

function setupEventListeners() {
    const subjectSelect = document.querySelectorAll("select")[0];
    const moduleSelect  = document.querySelectorAll("select")[1];

    console.log("Subject select bound:", subjectSelect);
    console.log("Module select bound:", moduleSelect);

    if (subjectSelect) {
        subjectSelect.addEventListener("change", () => {
            console.log("Subject changed:", subjectSelect.value);
            populatePracticeModules(subjectSelect.value);
        });
    }
    
    if (moduleSelect) {
        moduleSelect.addEventListener('change', handleModuleChange);
    }

    const startPracticeBtn = document.querySelector('#startPracticeBtn');
    if (startPracticeBtn) {
        startPracticeBtn.addEventListener('click', startPractice);
    }
    
    const submitAnswerBtn = document.querySelector('#submitAnswerBtn');
    if (submitAnswerBtn) {
        submitAnswerBtn.addEventListener('click', submitAnswer);
    }
    
    const nextQuestionBtn = document.querySelector('#nextQuestionBtn');
    if (nextQuestionBtn) {
        nextQuestionBtn.addEventListener('click', nextQuestion);
    }

    document.querySelectorAll('.option-btn').forEach(btn => {
        btn.addEventListener('click', () => selectOption(btn.dataset.option));
    });

    const textAnswer = document.querySelector('#textAnswer');
    if (textAnswer) {
        textAnswer.addEventListener('input', function() {
            const submitBtn = document.querySelector('#submitAnswerBtn');
            if (submitBtn) submitBtn.disabled = !this.value.trim();
        });
    }

    const logoutBtn = document.querySelector('#logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', logout);
    }
}

function setupSidebarToggle() {
    const menuToggle = document.querySelector('#menuToggle');
    const sidebar = document.querySelector('#sidebar');
    const overlay = document.querySelector('#sidebarOverlay');

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
            const userNameEl = document.querySelector('#userName');
            if (userNameEl) userNameEl.textContent = response.full_name || response.email.split('@')[0];
        }
    } catch (err) {
        console.error('Failed to load user info:', err);
    }
}

function loadSubjects() {
    const select = document.querySelectorAll("select")[0];
    if (!select) return;

    // Clear and populate
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
    console.log("Subject changed:", subjectId);
    populatePracticeModules(subjectId);
}

function populatePracticeModules(subjectId) {
    const moduleSelect = document.querySelectorAll("select")[1];
    const startBtn = document.querySelector('#startPracticeBtn');

    if (!moduleSelect) return;

    // MANDATORY: Clear moduleSelect.innerHTML
    moduleSelect.innerHTML = '<option value="">-- Select Practice Module --</option>';
    
    if (!subjectId) {
        moduleSelect.disabled = true;
        if (startBtn) startBtn.disabled = true;
        state.modules = [];
        return;
    }

    const subject = state.subjects.find(s => s.id === subjectId);
    if (!subject) return;

    state.modules = subject.modules;
    
    // MANDATORY: Appends <option> elements
    subject.modules.forEach(moduleName => {
        const option = document.createElement('option');
        option.value = moduleName;
        option.textContent = moduleName;
        moduleSelect.appendChild(option);
    });

    // MANDATORY: Sets moduleSelect.disabled = false
    moduleSelect.disabled = false;
    console.log("Modules loaded for:", subjectId);
}

function handleModuleChange(e) {
    const moduleName = e.target.value;
    const startBtn = document.querySelector('#startPracticeBtn');
    if (startBtn) startBtn.disabled = !moduleName;
    state.currentModuleId = moduleName;
    state.currentModuleTitle = moduleName;
}

function checkURLParams() {
    const params = new URLSearchParams(window.location.search);
    const subjectId = params.get('subject_id');
    const moduleName = params.get('module_name');

    if (subjectId) {
        const subjectSelect = document.querySelectorAll("select")[0];
        if (subjectSelect) {
            subjectSelect.value = subjectId;
            populatePracticeModules(subjectId);
            
            if (moduleName) {
                const moduleSelect = document.querySelectorAll("select")[1];
                if (moduleSelect) {
                    moduleSelect.value = moduleName;
                    handleModuleChange({ target: { value: moduleName } });
                }
            }
        }
    }
}

async function startPractice() {
    const subjectSelect = document.querySelectorAll("select")[0];
    if (!subjectSelect) return;
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
    document.querySelector('#moduleSelectionSection').classList.add('hidden');
    document.querySelector('#emptyStateSection').classList.add('hidden');
    document.querySelector('#quizCompleteSection').classList.add('hidden');
    document.querySelector('#quizSection').classList.remove('hidden');
}

function showEmptyState() {
    document.querySelector('#moduleSelectionSection').classList.add('hidden');
    document.querySelector('#quizSection').classList.add('hidden');
    document.querySelector('#quizCompleteSection').classList.add('hidden');
    document.querySelector('#emptyStateSection').classList.remove('hidden');
}

function goToModuleSelection() {
    stopTimer();
    document.querySelector('#quizSection').classList.add('hidden');
    document.querySelector('#emptyStateSection').classList.add('hidden');
    document.querySelector('#quizCompleteSection').classList.add('hidden');
    document.querySelector('#moduleSelectionSection').classList.remove('hidden');
}

function renderQuestion() {
    const question = state.questions[state.currentQuestionIndex];
    if (!question) return;

    document.querySelector('#moduleTitle').textContent = state.currentModuleTitle;
    document.querySelector('#questionCounter').textContent = 
        `Q${state.currentQuestionIndex + 1} / Q${state.questions.length}`;

    const diffBadge = document.querySelector('#difficultyBadge');
    diffBadge.textContent = question.difficulty.charAt(0).toUpperCase() + question.difficulty.slice(1);
    diffBadge.className = `difficulty-badge ${question.difficulty}`;

    document.querySelector('#topicTag').textContent = question.topic_tag || 'General';
    document.querySelector('#questionText').textContent = question.question;

    const isMCQ = question.type === 'mcq';
    document.querySelector('#mcqOptions').classList.toggle('hidden', !isMCQ);
    document.querySelector('#textAnswerContainer').classList.toggle('hidden', isMCQ);

    if (isMCQ && question.options) {
        const letters = ['A', 'B', 'C', 'D'];
        question.options.forEach((opt, i) => {
            const optionEl = document.querySelector(`#option${letters[i]}`);
            if (optionEl) optionEl.textContent = opt;
        });

        document.querySelectorAll('.option-btn').forEach(btn => {
            btn.classList.remove('selected', 'correct', 'incorrect');
            btn.disabled = false;
        });
    } else {
        const textAnswer = document.querySelector('#textAnswer');
        if (textAnswer) textAnswer.value = '';
    }

    state.selectedAnswer = null;
    const submitBtn = document.querySelector('#submitAnswerBtn');
    if (submitBtn) submitBtn.disabled = true;
    document.querySelector('#feedbackPanel').classList.add('hidden');
}

function selectOption(option) {
    state.selectedAnswer = option;

    document.querySelectorAll('.option-btn').forEach(btn => {
        btn.classList.remove('selected');
        if (btn.dataset.option === option) {
            btn.classList.add('selected');
        }
    });

    const submitBtn = document.querySelector('#submitAnswerBtn');
    if (submitBtn) submitBtn.disabled = false;
}

async function submitAnswer() {
    const question = state.questions[state.currentQuestionIndex];
    if (!question) return;

    const isMCQ = question.type === 'mcq';
    let answer = '';
    if (isMCQ) {
        answer = state.selectedAnswer;
    } else {
        const textAnswerEl = document.querySelector('#textAnswer');
        answer = textAnswerEl ? textAnswerEl.value.trim() : '';
    }

    if (!answer) {
        showToast('Please provide an answer');
        return;
    }

    const submitBtn = document.querySelector('#submitAnswerBtn');
    if (submitBtn) submitBtn.disabled = true;
    document.querySelectorAll('.option-btn').forEach(btn => btn.disabled = true);

    try {
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
        if (submitBtn) submitBtn.disabled = false;
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

    const feedbackPanel = document.querySelector('#feedbackPanel');
    const feedbackIcon = document.querySelector('#feedbackIcon');
    const feedbackStatus = document.querySelector('#feedbackStatus');

    if (feedbackIcon) feedbackIcon.textContent = isCorrect ? '✔' : '❌';
    if (feedbackStatus) {
        feedbackStatus.textContent = isCorrect ? 'Correct!' : 'Incorrect';
        feedbackStatus.className = `feedback-status ${isCorrect ? 'correct' : 'incorrect'}`;
    }

    const correctAnsTxt = document.querySelector('#correctAnswerText');
    if (correctAnsTxt) correctAnsTxt.textContent = correctAnswer || 'N/A';
    
    const explanationTxt = document.querySelector('#explanationText');
    if (explanationTxt) explanationTxt.textContent = explanation || 'No explanation provided.';

    const masteryUpdate = document.querySelector('#masteryUpdate');
    const masteryTxt = document.querySelector('#masteryText');
    if (response.mastery_update && masteryTxt) {
        masteryTxt.textContent = 
            `Subject mastery: ${response.mastery_update.subject_mastery_percent}% (${response.mastery_update.strength_label})`;
        masteryUpdate.classList.remove('hidden');
    } else if (masteryUpdate) {
        masteryUpdate.classList.add('hidden');
    }

    if (feedbackPanel) feedbackPanel.classList.remove('hidden');

    const isLast = state.currentQuestionIndex >= state.questions.length - 1;
    const nextBtn = document.querySelector('#nextQuestionBtn');
    if (nextBtn) nextBtn.textContent = isLast ? 'Finish Quiz' : 'Next Question';
}

function showTextFeedback(response) {
    const feedbackPanel = document.querySelector('#feedbackPanel');
    const feedbackIcon = document.querySelector('#feedbackIcon');
    const feedbackStatus = document.querySelector('#feedbackStatus');

    if (feedbackIcon) feedbackIcon.textContent = '📝';
    if (feedbackStatus) {
        feedbackStatus.textContent = 'Answer Saved';
        feedbackStatus.className = 'feedback-status pending';
    }

    const correctAnsSection = document.querySelector('#correctAnswerSection');
    if (correctAnsSection) {
        correctAnsSection.innerHTML = 
            '<strong>Status:</strong><span>Answer saved. Evaluation pending.</span>';
    }
    
    const explanationSection = document.querySelector('#explanationSection');
    if (explanationSection) explanationSection.classList.add('hidden');
    
    const masteryUpdate = document.querySelector('#masteryUpdate');
    if (masteryUpdate) masteryUpdate.classList.add('hidden');

    if (feedbackPanel) feedbackPanel.classList.remove('hidden');

    const isLast = state.currentQuestionIndex >= state.questions.length - 1;
    const nextBtn = document.querySelector('#nextQuestionBtn');
    if (nextBtn) nextBtn.textContent = isLast ? 'Finish Quiz' : 'Next Question';
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

    document.querySelector('#quizSection').classList.add('hidden');
    document.querySelector('#quizCompleteSection').classList.remove('hidden');

    const correctCountEl = document.querySelector('#correctCount');
    if (correctCountEl) correctCountEl.textContent = state.results.correct;
    
    const totalCountEl = document.querySelector('#totalCount');
    if (totalCountEl) totalCountEl.textContent = state.results.total;

    const accuracyPercentEl = document.querySelector('#accuracyPercent');
    if (accuracyPercentEl) {
        const accuracy = state.results.total > 0 
            ? Math.round((state.results.correct / state.results.total) * 100) 
            : 0;
        accuracyPercentEl.textContent = `${accuracy}%`;
    }
}

function retryQuiz() {
    state.currentQuestionIndex = 0;
    state.selectedAnswer = null;
    state.results = { correct: 0, total: 0 };
    state.timerSeconds = 0;

    document.querySelector('#quizCompleteSection').classList.add('hidden');
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
    const timerDisplay = document.querySelector('#timerDisplay');
    if (timerDisplay) {
        timerDisplay.textContent = 
            `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
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
    if (!response.ok) {
        if (response.status === 401) {
            localStorage.removeItem('access_token');
            window.location.href = '/html/login.html';
        }
        throw new Error('API request failed');
    }
    return await response.json();
}

function showToast(message, type = 'info') {
    if (window.JurisErrorHandler) {
        window.JurisErrorHandler.showToast(message, type === 'error' ? 'error' : 'info');
        return;
    }
    const toast = document.querySelector('#toast');
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
