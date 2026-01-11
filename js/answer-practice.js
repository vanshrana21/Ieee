// Questions Database
const questionsDatabase = {
    constitutional: {
        5: [
            {
                question: "Explain the concept of 'Procedure Established by Law' under Article 21.",
                hint: "Discuss Maneka Gandhi case and how it expanded Article 21",
                time: "8 mins",
                words: "~150 words",
                examTips: {
                    evaluation: [
                        "Clear definition of the concept",
                        "Reference to Maneka Gandhi v. Union of India",
                        "Comparison with 'due process of law'",
                        "Conclusion on current interpretation"
                    ],
                    mistakes: [
                        "Confusing with Article 14 or 19",
                        "Not mentioning the landmark case",
                        "Lack of structure (intro-body-conclusion)"
                    ],
                    fullMarks: [
                        "Start with Article 21's text",
                        "Cite Maneka Gandhi case and its impact",
                        "Mention 'just, fair, and reasonable' principle",
                        "End with significance"
                    ]
                },
                modelAnswer: `<strong>7. Not Expressly Declared Void:</strong>
The agreement must not fall under Sections 26-30 (wagering agreements, restraint of trade, etc.).

<strong>8. Certainty (Section 29):</strong>
Terms must be certain and not vague. Agreements with uncertain terms are void.

<strong>9. Possibility of Performance (Section 56):</strong>
Performance must be legally and physically possible.

<strong>10. Legal Formalities:</strong>
Some contracts require writing, registration, or attestation (e.g., sale of immovable property).

<strong>Conclusion:</strong> All these essentials must be present simultaneously for an agreement to be a valid, enforceable contract. Absence of any element affects the contract's validity - it may be void, voidable, or unenforceable.`
            }
        ],
        20: []
    }
};

// Timer variables
let timerInterval;
let seconds = 0;

// Current state
let currentQuestion = null;
let currentAnswer = '';

// Navigation
function goBackToDashboard() {
    window.location.href = 'dashboard-student.html';
}

// Load question
function loadQuestion() {
    const subject = document.getElementById('subjectSelect').value;
    const marks = document.getElementById('marksSelect').value;
    
    if (!subject) {
        showToast('⚠️ Please select a subject');
        return;
    }
    
    if (!marks) {
        showToast('⚠️ Please select question type');
        return;
    }
    
    const questions = questionsDatabase[subject][marks];
    
    if (!questions || questions.length === 0) {
        showToast('📭 No questions available for this selection');
        return;
    }
    
    // Pick random question
    const randomIndex = Math.floor(Math.random() * questions.length);
    currentQuestion = {
        ...questions[randomIndex],
        subject: subject,
        marks: parseInt(marks)
    };
    
    displayQuestion();
    showToast('✅ Question loaded successfully!');
}

// Display question
function displayQuestion() {
    // Show question card
    document.getElementById('questionCard').classList.remove('hidden');
    document.getElementById('writingSection').classList.remove('hidden');
    document.getElementById('examTipsCard').classList.remove('hidden');
    
    // Hide feedback and model answer
    document.getElementById('feedbackSection').classList.add('hidden');
    document.getElementById('modelAnswerSection').classList.add('hidden');
    
    // Populate question details
    const subjectNames = {
        constitutional: 'Constitutional Law',
        criminal: 'Criminal Law',
        contract: 'Contract Law'
    };
    
    document.getElementById('questionSubject').textContent = subjectNames[currentQuestion.subject];
    document.getElementById('questionMarks').textContent = currentQuestion.marks + ' Marks';
    document.getElementById('suggestedTime').textContent = currentQuestion.time;
    document.getElementById('wordLimit').textContent = currentQuestion.words;
    document.getElementById('questionContent').textContent = currentQuestion.question;
    document.getElementById('questionHint').textContent = currentQuestion.hint;
    
    // Populate exam tips
    const tips = currentQuestion.examTips;
    document.getElementById('evaluationPoints').innerHTML = tips.evaluation.map(point => `<li>${point}</li>`).join('');
    document.getElementById('commonMistakes').innerHTML = tips.mistakes.map(mistake => `<li>${mistake}</li>`).join('');
    document.getElementById('fullMarksStrategy').innerHTML = tips.fullMarks.map(strategy => `<li>${strategy}</li>`).join('');
    
    // Clear previous answer
    document.getElementById('answerTextarea').value = '';
    document.getElementById('wordCount').textContent = '0';
    
    // Reset and start timer
    resetTimer();
    startTimer();
    
    // Scroll to question
    document.getElementById('questionCard').scrollIntoView({ behavior: 'smooth' });
}

// Word counter
document.addEventListener('DOMContentLoaded', function() {
    const textarea = document.getElementById('answerTextarea');
    if (textarea) {
        textarea.addEventListener('input', function() {
            const text = this.value.trim();
            const words = text === '' ? 0 : text.split(/\s+/).length;
            document.getElementById('wordCount').textContent = words;
            currentAnswer = this.value;
        });
    }
    
    loadProgress();
});

// Timer functions
function startTimer() {
    timerInterval = setInterval(() => {
        seconds++;
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        document.getElementById('timerDisplay').textContent = 
            `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }, 1000);
}

function resetTimer() {
    clearInterval(timerInterval);
    seconds = 0;
    document.getElementById('timerDisplay').textContent = '00:00';
}

function stopTimer() {
    clearInterval(timerInterval);
}

// Clear answer
function clearAnswer() {
    if (confirm('Are you sure you want to clear your answer?')) {
        document.getElementById('answerTextarea').value = '';
        document.getElementById('wordCount').textContent = '0';
        currentAnswer = '';
        showToast('🗑️ Answer cleared');
    }
}

// Submit answer
function submitAnswer() {
    const answer = document.getElementById('answerTextarea').value.trim();
    
    if (!answer) {
        showToast('⚠️ Please write an answer before submitting');
        return;
    }
    
    if (!currentQuestion) {
        showToast('⚠️ No question loaded');
        return;
    }
    
    stopTimer();
    
    // Generate feedback
    generateFeedback(answer);
    
    // Show feedback and model answer sections
    document.getElementById('feedbackSection').classList.remove('hidden');
    document.getElementById('modelAnswerSection').classList.remove('hidden');
    
    // Populate model answer
    document.getElementById('modelAnswerText').innerHTML = currentQuestion.modelAnswer;
    
    // Scroll to feedback
    document.getElementById('feedbackSection').scrollIntoView({ behavior: 'smooth' });
    
    showToast('✅ Answer submitted! Review your feedback below.');
}

// Generate feedback (dummy AI-like feedback)
function generateFeedback(answer) {
    const wordCount = answer.split(/\s+/).length;
    const hasIntro = answer.toLowerCase().includes('introduction') || answer.toLowerCase().match(/^.{0,100}(define|meaning|concept)/i);
    const hasConclusion = answer.toLowerCase().includes('conclusion') || answer.match(/in conclusion|to conclude|thus|therefore/i);
    const hasCases = answer.match(/v\.|vs\.|versus/i) || answer.match(/\(\d{4}\)/);
    
    // Structure feedback
    let structureScore = 3;
    let structureText = '<ul>';
    if (hasIntro) {
        structureScore++;
        structureText += '<li>✅ Good introduction present</li>';
    } else {
        structureText += '<li>⚠️ Introduction could be clearer</li>';
    }
    if (hasConclusion) {
        structureScore++;
        structureText += '<li>✅ Proper conclusion included</li>';
    } else {
        structureText += '<li>⚠️ Add a stronger conclusion</li>';
    }
    structureText += '<li>💡 Ensure clear paragraph breaks for better presentation</li></ul>';
    
    // Legal accuracy
    let accuracyScore = 4;
    let accuracyText = '<ul><li>✅ Relevant legal provisions mentioned</li>';
    accuracyText += '<li>✅ Concepts explained adequately</li>';
    accuracyText += '<li>💡 Could include more specific section references</li></ul>';
    
    // Case law usage
    let caseLawScore = hasCases ? 4 : 2;
    let caseLawText = '<ul>';
    if (hasCases) {
        caseLawText += '<li>✅ Landmark cases cited</li>';
        caseLawText += '<li>✅ Case law integration is good</li>';
    } else {
        caseLawText += '<li>⚠️ No case law citations found</li>';
        caseLawText += '<li>💡 Include at least 2-3 relevant cases</li>';
    }
    caseLawText += '</ul>';
    
    // Language
    let languageScore = 4;
    let languageText = '<ul>';
    languageText += '<li>✅ Language is clear and formal</li>';
    if (wordCount >= 100) {
        languageText += '<li>✅ Adequate length maintained</li>';
    } else {
        languageText += '<li>⚠️ Answer seems brief, elaborate more</li>';
    }
    languageText += '<li>💡 Use legal terminology appropriately</li></ul>';
    
    // Overall score
    const overallScore = ((structureScore + accuracyScore + caseLawScore + languageScore) / 20 * currentQuestion.marks).toFixed(1);
    
    // Update feedback UI
    document.getElementById('structureScore').textContent = `${structureScore}/5`;
    document.getElementById('structureFeedback').innerHTML = structureText;
    
    document.getElementById('accuracyScore').textContent = `${accuracyScore}/5`;
    document.getElementById('accuracyFeedback').innerHTML = accuracyText;
    
    document.getElementById('caseLawScore').textContent = `${caseLawScore}/5`;
    document.getElementById('caseLawFeedback').innerHTML = caseLawText;
    
    document.getElementById('languageScore').textContent = `${languageScore}/5`;
    document.getElementById('languageFeedback').innerHTML = languageText;
    
    document.getElementById('overallScore').textContent = overallScore;
    document.getElementById('maxMarks').textContent = currentQuestion.marks;
    
    // Score message
    const percentage = (overallScore / currentQuestion.marks) * 100;
    let scoreMessage = '';
    if (percentage >= 80) {
        scoreMessage = 'Excellent work! You have a strong grasp of the topic. Keep it up!';
    } else if (percentage >= 60) {
        scoreMessage = 'Good effort! Review the model answer to refine your technique.';
    } else {
        scoreMessage = 'Keep practicing! Focus on structure and include more case laws.';
    }
    document.getElementById('scoreMessage').textContent = scoreMessage;
}

// Toggle model answer
function toggleModelAnswer() {
    const content = document.getElementById('modelAnswerContent');
    const toggleText = document.getElementById('toggleText');
    
    if (content.classList.contains('hidden')) {
        content.classList.remove('hidden');
        toggleText.textContent = 'Hide Model Answer';
    } else {
        content.classList.add('hidden');
        toggleText.textContent = 'Show Model Answer';
    }
}

// Copy model answer
function copyModelAnswer() {
    const modelText = document.getElementById('modelAnswerText').innerText;
    
    const textarea = document.createElement('textarea');
    textarea.value = modelText;
    document.body.appendChild(textarea);
    textarea.select();
    
    try {
        document.execCommand('copy');
        showToast('📋 Model answer copied to clipboard!');
    } catch (err) {
        showToast('❌ Failed to copy');
    }
    
    document.body.removeChild(textarea);
}

// Save attempt
function saveAttempt() {
    if (!currentQuestion || !currentAnswer) {
        showToast('⚠️ No attempt to save');
        return;
    }
    
    let attempts = JSON.parse(localStorage.getItem('answerAttempts') || '[]');
    
    const attempt = {
        subject: currentQuestion.subject,
        question: currentQuestion.question,
        marks: currentQuestion.marks,
        answer: currentAnswer,
        score: document.getElementById('overallScore').textContent,
        timeTaken: document.getElementById('timerDisplay').textContent,
        date: new Date().toLocaleDateString()
    };
    
    attempts.unshift(attempt);
    
    // Keep last 20 attempts
    if (attempts.length > 20) {
        attempts = attempts.slice(0, 20);
    }
    
    localStorage.setItem('answerAttempts', JSON.stringify(attempts));
    
    showToast('💾 Attempt saved successfully!');
    loadProgress();
}

// Load progress
function loadProgress() {
    const attempts = JSON.parse(localStorage.getItem('answerAttempts') || '[]');
    
    document.getElementById('totalAttempts').textContent = attempts.length;
    
    if (attempts.length > 0) {
        // Calculate average score
        const totalScore = attempts.reduce((sum, attempt) => {
            const score = parseFloat(attempt.score);
            return sum + (isNaN(score) ? 0 : score);
        }, 0);
        const avgScore = (totalScore / attempts.length).toFixed(1);
        document.getElementById('averageScore').textContent = avgScore;
        
        // Show recent attempts
        const recentHTML = attempts.slice(0, 5).map(attempt => {
            const subjectNames = {
                constitutional: 'Constitutional Law',
                criminal: 'Criminal Law',
                contract: 'Contract Law'
            };
            return `
                <div class="attempt-item">
                    <div class="attempt-subject">${subjectNames[attempt.subject]} (${attempt.marks} marks)</div>
                    <div class="attempt-meta">Score: ${attempt.score} • ${attempt.date}</div>
                </div>
            `;
        }).join('');
        
        document.getElementById('recentAttemptsList').innerHTML = recentHTML;
    } else {
        document.getElementById('averageScore').textContent = '-';
        document.getElementById('improvementTrend').textContent = '- -';
    }
}

// Retry question
function retryQuestion() {
    document.getElementById('answerTextarea').value = '';
    document.getElementById('wordCount').textContent = '0';
    currentAnswer = '';
    
    document.getElementById('feedbackSection').classList.add('hidden');
    document.getElementById('modelAnswerSection').classList.add('hidden');
    document.getElementById('modelAnswerContent').classList.add('hidden');
    document.getElementById('toggleText').textContent = 'Show Model Answer';
    
    resetTimer();
    startTimer();
    
    document.getElementById('writingSection').scrollIntoView({ behavior: 'smooth' });
    showToast('🔄 Try again! Write a better answer.');
}

// Load new question
function loadNewQuestion() {
    loadQuestion();
}

// Quick actions
function addToNotes() {
    showToast('📝 Added to your notes!');
}

function viewAllAttempts() {
    showToast('📊 All attempts view coming soon!');
}

function resetProgress() {
    if (confirm('Are you sure you want to reset all your progress? This cannot be undone.')) {
        localStorage.removeItem('answerAttempts');
        loadProgress();
        showToast('🔄 Progress reset successfully');
    }
}

// Toast notification
function showToast(message) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.classList.add('show');
    
    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}
