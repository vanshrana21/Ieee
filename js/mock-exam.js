const MOCK_EXAM_API = 'http://127.0.0.1:8000/api/mock-exam';

let examState = {
    sessionId: null,
    sections: [],
    allQuestions: [],
    currentQuestionIndex: 0,
    remainingSeconds: 0,
    timerInterval: null,
    autoSaveTimeout: null,
    questionStartTime: null,
    fiveMinuteWarningShown: false,
    localAnswers: {}
};

document.addEventListener('DOMContentLoaded', () => {
    checkAuth();
    checkActiveSession();
});

function checkAuth() {
    const token = localStorage.getItem('access_token');
    if (!token) {
        window.location.href = 'login.html';
    }
}

async function checkActiveSession() {
    try {
        const token = localStorage.getItem('access_token');
        const response = await fetch(`${MOCK_EXAM_API}/active`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (!response.ok) return;
        
        const data = await response.json();
        
        if (data.active_session && data.active_session.session) {
            const confirmed = confirm('You have an exam in progress. Continue?');
            if (confirmed) {
                restoreSession(data.active_session);
            }
        }
    } catch (error) {
        console.error('Error checking active session:', error);
    }
}

async function startExam() {
    const examType = document.getElementById('examTypeSelect').value;
    const btn = document.getElementById('btnStartExam');
    
    btn.disabled = true;
    btn.textContent = 'Starting Exam...';
    
    try {
        const token = localStorage.getItem('access_token');
        const response = await fetch(`${MOCK_EXAM_API}/start`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ exam_type: examType })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to start exam');
        }
        
        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        restoreSession(data);
        
    } catch (error) {
        console.error('Error starting exam:', error);
        showToast(error.message || 'Failed to start exam');
        btn.disabled = false;
        btn.textContent = 'Start Exam';
    }
}

function restoreSession(data) {
    examState.sessionId = data.session.id;
    examState.sections = data.sections || [];
    examState.remainingSeconds = data.timer.remaining_seconds;
    
    examState.allQuestions = [];
    let globalIndex = 0;
    
    for (const section of examState.sections) {
        for (const question of section.questions) {
            examState.allQuestions.push({
                ...question,
                sectionLabel: section.section,
                globalIndex: globalIndex++
            });
            
            if (question.user_answer) {
                examState.localAnswers[question.answer_id] = question.user_answer;
            }
        }
    }
    
    document.getElementById('examInstructions').classList.add('hidden');
    document.getElementById('examContainer').classList.remove('hidden');
    
    document.getElementById('subjectName').textContent = data.session.subject_name || 'General';
    document.getElementById('totalCount').textContent = data.progress.total;
    
    renderQuestionPalette();
    loadQuestion(0);
    startTimer();
    updateProgress(data.progress);
    
    saveToLocalStorage();
}

function renderQuestionPalette() {
    const container = document.getElementById('sectionsContainer');
    container.innerHTML = '';
    
    let questionNum = 0;
    
    for (const section of examState.sections) {
        const sectionDiv = document.createElement('div');
        sectionDiv.className = 'section-group';
        
        const title = document.createElement('div');
        title.className = 'section-title';
        title.textContent = `Section ${section.section} (${section.marks_per_question} marks each)`;
        sectionDiv.appendChild(title);
        
        const buttonsDiv = document.createElement('div');
        buttonsDiv.className = 'question-buttons';
        
        for (let i = 0; i < section.questions.length; i++) {
            const q = section.questions[i];
            const btn = document.createElement('button');
            btn.className = 'q-btn';
            btn.textContent = questionNum + 1;
            btn.dataset.index = questionNum;
            btn.onclick = () => loadQuestion(parseInt(btn.dataset.index));
            
            updateButtonState(btn, q);
            buttonsDiv.appendChild(btn);
            questionNum++;
        }
        
        sectionDiv.appendChild(buttonsDiv);
        container.appendChild(sectionDiv);
    }
}

function updateButtonState(btn, question) {
    btn.classList.remove('answered', 'flagged', 'current');
    
    const index = parseInt(btn.dataset.index);
    if (index === examState.currentQuestionIndex) {
        btn.classList.add('current');
    }
    
    if (question.is_flagged) {
        btn.classList.add('flagged');
    } else if (question.is_attempted || examState.localAnswers[question.answer_id]) {
        btn.classList.add('answered');
    }
}

function loadQuestion(index) {
    if (index < 0 || index >= examState.allQuestions.length) return;
    
    saveCurrentAnswer();
    
    examState.currentQuestionIndex = index;
    examState.questionStartTime = Date.now();
    
    const question = examState.allQuestions[index];
    
    document.getElementById('currentSection').textContent = `Section ${question.sectionLabel}`;
    document.getElementById('currentQuestionNumber').textContent = `Question ${index + 1}`;
    document.getElementById('currentMarks').textContent = `${question.marks} marks`;
    document.getElementById('questionText').textContent = question.question_text;
    
    const guidelines = document.getElementById('questionGuidelines');
    if (question.question && question.question.guidelines) {
        guidelines.innerHTML = `<h4>Guidelines</h4><p>${escapeHtml(question.question.guidelines)}</p>`;
        guidelines.style.display = 'block';
    } else {
        guidelines.style.display = 'none';
    }
    
    const textarea = document.getElementById('answerTextarea');
    textarea.value = examState.localAnswers[question.answer_id] || '';
    updateWordCount();
    
    const flagBtn = document.getElementById('btnFlag');
    if (question.is_flagged) {
        flagBtn.classList.add('flagged');
    } else {
        flagBtn.classList.remove('flagged');
    }
    
    document.getElementById('btnPrev').disabled = index === 0;
    document.getElementById('btnNext').disabled = index === examState.allQuestions.length - 1;
    
    updatePaletteHighlight();
}

function updatePaletteHighlight() {
    const buttons = document.querySelectorAll('.q-btn');
    buttons.forEach((btn, i) => {
        const q = examState.allQuestions[i];
        updateButtonState(btn, q);
    });
}

function navigateQuestion(direction) {
    const newIndex = examState.currentQuestionIndex + direction;
    if (newIndex >= 0 && newIndex < examState.allQuestions.length) {
        loadQuestion(newIndex);
    }
}

function handleAnswerInput() {
    updateWordCount();
    showSavingIndicator();
    
    const question = examState.allQuestions[examState.currentQuestionIndex];
    const textarea = document.getElementById('answerTextarea');
    examState.localAnswers[question.answer_id] = textarea.value;
    
    clearTimeout(examState.autoSaveTimeout);
    examState.autoSaveTimeout = setTimeout(() => {
        saveCurrentAnswer();
    }, 2000);
    
    saveToLocalStorage();
}

function updateWordCount() {
    const textarea = document.getElementById('answerTextarea');
    const text = textarea.value.trim();
    const words = text ? text.split(/\s+/).length : 0;
    document.getElementById('wordCount').textContent = words;
}

function showSavingIndicator() {
    const indicator = document.getElementById('autoSaveIndicator');
    indicator.textContent = 'Saving...';
    indicator.className = 'auto-save-indicator saving';
}

function showSavedIndicator() {
    const indicator = document.getElementById('autoSaveIndicator');
    indicator.textContent = 'Auto-saved';
    indicator.className = 'auto-save-indicator saved';
}

async function saveCurrentAnswer() {
    const question = examState.allQuestions[examState.currentQuestionIndex];
    if (!question) return;
    
    const answerText = examState.localAnswers[question.answer_id] || '';
    const timeSpent = Math.floor((Date.now() - examState.questionStartTime) / 1000);
    
    try {
        const token = localStorage.getItem('access_token');
        const response = await fetch(`${MOCK_EXAM_API}/session/${examState.sessionId}/answer`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                answer_id: question.answer_id,
                answer_text: answerText,
                time_spent_seconds: timeSpent
            })
        });
        
        if (response.ok) {
            const data = await response.json();
            question.is_attempted = data.is_attempted;
            updatePaletteHighlight();
            showSavedIndicator();
            updateAttemptedCount();
        }
    } catch (error) {
        console.error('Error saving answer:', error);
    }
}

async function toggleFlag() {
    const question = examState.allQuestions[examState.currentQuestionIndex];
    
    try {
        const token = localStorage.getItem('access_token');
        const response = await fetch(`${MOCK_EXAM_API}/session/${examState.sessionId}/flag`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ answer_id: question.answer_id })
        });
        
        if (response.ok) {
            const data = await response.json();
            question.is_flagged = data.is_flagged;
            
            const flagBtn = document.getElementById('btnFlag');
            if (question.is_flagged) {
                flagBtn.classList.add('flagged');
            } else {
                flagBtn.classList.remove('flagged');
            }
            
            updatePaletteHighlight();
        }
    } catch (error) {
        console.error('Error toggling flag:', error);
    }
}

function startTimer() {
    if (examState.timerInterval) {
        clearInterval(examState.timerInterval);
    }
    
    updateTimerDisplay();
    
    examState.timerInterval = setInterval(() => {
        examState.remainingSeconds--;
        updateTimerDisplay();
        
        if (examState.remainingSeconds <= 300 && !examState.fiveMinuteWarningShown) {
            showTimeWarning();
            examState.fiveMinuteWarningShown = true;
        }
        
        if (examState.remainingSeconds <= 0) {
            clearInterval(examState.timerInterval);
            autoSubmitExam();
        }
    }, 1000);
}

function updateTimerDisplay() {
    const hours = Math.floor(examState.remainingSeconds / 3600);
    const minutes = Math.floor((examState.remainingSeconds % 3600) / 60);
    const seconds = examState.remainingSeconds % 60;
    
    const display = `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
    document.getElementById('timerDisplay').textContent = display;
    
    const container = document.getElementById('timerContainer');
    if (examState.remainingSeconds <= 300) {
        container.classList.add('warning');
    } else {
        container.classList.remove('warning');
    }
}

function pad(num) {
    return num.toString().padStart(2, '0');
}

function showTimeWarning() {
    document.getElementById('warningTimeLeft').textContent = '5 minutes';
    document.getElementById('timeWarningModal').classList.remove('hidden');
}

function closeTimeWarning() {
    document.getElementById('timeWarningModal').classList.add('hidden');
}

function updateProgress(progress) {
    document.getElementById('attemptedCount').textContent = progress.attempted;
}

function updateAttemptedCount() {
    const attempted = examState.allQuestions.filter(q => 
        q.is_attempted || examState.localAnswers[q.answer_id]
    ).length;
    document.getElementById('attemptedCount').textContent = attempted;
}

function confirmSubmit() {
    saveCurrentAnswer();
    
    const attempted = examState.allQuestions.filter(q => 
        q.is_attempted || examState.localAnswers[q.answer_id]
    ).length;
    const flagged = examState.allQuestions.filter(q => q.is_flagged).length;
    
    document.getElementById('summaryAttempted').textContent = `${attempted}/${examState.allQuestions.length}`;
    document.getElementById('summaryFlagged').textContent = flagged;
    document.getElementById('summaryTimeRemaining').textContent = document.getElementById('timerDisplay').textContent;
    
    document.getElementById('submitModal').classList.remove('hidden');
}

function closeSubmitModal() {
    document.getElementById('submitModal').classList.add('hidden');
}

async function submitExam() {
    closeSubmitModal();
    
    try {
        const token = localStorage.getItem('access_token');
        const response = await fetch(`${MOCK_EXAM_API}/session/${examState.sessionId}/submit`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (!response.ok) {
            throw new Error('Failed to submit exam');
        }
        
        const summary = await response.json();
        showCompletionScreen(summary, 'completed');
        
    } catch (error) {
        console.error('Error submitting exam:', error);
        showToast('Failed to submit exam. Please try again.');
    }
}

async function autoSubmitExam() {
    showToast('Time expired! Auto-submitting exam...');
    
    try {
        const token = localStorage.getItem('access_token');
        const response = await fetch(`${MOCK_EXAM_API}/session/${examState.sessionId}/submit`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        const summary = await response.json();
        showCompletionScreen(summary, 'auto_submitted');
        
    } catch (error) {
        console.error('Error auto-submitting exam:', error);
        showCompletionScreen({
            questions_attempted: examState.allQuestions.filter(q => q.is_attempted).length,
            total_questions: examState.allQuestions.length,
            time_taken_seconds: examState.allQuestions.reduce((sum, q) => sum + (q.time_spent_seconds || 0), 0)
        }, 'auto_submitted');
    }
}

function showCompletionScreen(summary, status) {
    clearInterval(examState.timerInterval);
    clearLocalStorage();
    
    document.getElementById('examContainer').classList.add('hidden');
    document.getElementById('completionScreen').classList.remove('hidden');
    
    if (status === 'auto_submitted') {
        document.getElementById('completionStatus').textContent = 'Your exam was auto-submitted due to time expiry.';
    }
    
    document.getElementById('finalAttempted').textContent = summary.questions_attempted || 0;
    document.getElementById('finalTotal').textContent = summary.total_questions || examState.allQuestions.length;
    
    const timeTaken = summary.time_taken_seconds || 0;
    const minutes = Math.floor(timeTaken / 60);
    const seconds = timeTaken % 60;
    document.getElementById('finalTime').textContent = `${minutes}m ${seconds}s`;
}

function saveToLocalStorage() {
    const data = {
        sessionId: examState.sessionId,
        localAnswers: examState.localAnswers,
        currentIndex: examState.currentQuestionIndex
    };
    localStorage.setItem('exam_state', JSON.stringify(data));
}

function clearLocalStorage() {
    localStorage.removeItem('exam_state');
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showToast(message) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 3000);
}

window.addEventListener('beforeunload', (e) => {
    if (examState.sessionId && examState.remainingSeconds > 0) {
        saveCurrentAnswer();
        e.preventDefault();
        e.returnValue = '';
    }
});
