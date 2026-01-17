const EVALUATION_API = 'http://127.0.0.1:8000/api/practice/attempts';
const POLL_INTERVAL = 3000;
const MAX_POLL_ATTEMPTS = 20;

let evaluationPollTimer = null;
let pollAttemptCount = 0;
let currentAttemptId = null;
let currentQuestionId = null;
let currentEvaluation = null;
let allAttempts = [];

document.addEventListener('DOMContentLoaded', () => {
    const params = new URLSearchParams(window.location.search);
    currentAttemptId = params.get('attempt_id');
    currentQuestionId = params.get('question_id');
    
    if (!currentAttemptId) {
        showError('No attempt ID provided');
        return;
    }
    
    loadEvaluation();
});

async function loadEvaluation() {
    showState('loading');
    
    const result = await fetchEvaluation(currentAttemptId);
    
    if (!result.success) {
        showError(result.error);
        return;
    }
    
    const status = result.data.status;
    
    if (status === 'completed' || status === 'evaluated') {
        currentEvaluation = result.data.evaluation;
        await loadQuestionAndAttempts();
        renderResults();
    } else if (status === 'processing' || status === 'pending') {
        showState('pending');
        startPolling();
    } else if (status === 'failed') {
        showError(result.data.message || 'Evaluation failed');
    } else if (status === 'not_found') {
        await triggerAndPoll();
    }
}

async function triggerAndPoll() {
    showState('pending');
    
    const result = await triggerEvaluation(currentAttemptId);
    
    if (!result.success) {
        showError(result.error);
        return;
    }
    
    startPolling();
}

async function fetchEvaluation(attemptId) {
    try {
        const token = localStorage.getItem('access_token');
        if (!token) throw new Error('Not authenticated');
        
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
        
        return { success: true, data: await response.json() };
    } catch (error) {
        return { success: false, error: error.message };
    }
}

async function triggerEvaluation(attemptId) {
    try {
        const token = localStorage.getItem('access_token');
        if (!token) throw new Error('Not authenticated');
        
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
        
        return { success: true, data: await response.json() };
    } catch (error) {
        return { success: false, error: error.message };
    }
}

function startPolling() {
    stopPolling();
    pollAttemptCount = 0;
    
    evaluationPollTimer = setInterval(async () => {
        pollAttemptCount++;
        
        if (pollAttemptCount > MAX_POLL_ATTEMPTS) {
            stopPolling();
            showError('Evaluation is taking longer than expected. Please refresh.');
            return;
        }
        
        const result = await fetchEvaluation(currentAttemptId);
        
        if (!result.success) return;
        
        const status = result.data.status;
        
        if (status === 'completed' || status === 'evaluated') {
            stopPolling();
            currentEvaluation = result.data.evaluation;
            await loadQuestionAndAttempts();
            renderResults();
        } else if (status === 'failed') {
            stopPolling();
            showError(result.data.message);
        }
    }, POLL_INTERVAL);
}

function stopPolling() {
    if (evaluationPollTimer) {
        clearInterval(evaluationPollTimer);
        evaluationPollTimer = null;
    }
}

async function loadQuestionAndAttempts() {
    try {
        const token = localStorage.getItem('access_token');
        
        const attemptResponse = await fetch(`${EVALUATION_API.replace('/attempts', '')}/${currentAttemptId}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (attemptResponse.ok) {
            const attemptData = await attemptResponse.json();
            currentQuestionId = attemptData.practice_question_id;
        }
        
        if (currentQuestionId) {
            const attemptsResponse = await fetch(
                `http://127.0.0.1:8000/api/practice/questions/${currentQuestionId}/attempts`,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            
            if (attemptsResponse.ok) {
                allAttempts = await attemptsResponse.json();
            }
        }
    } catch (error) {
        console.error('Error loading question/attempts:', error);
    }
}

function showState(state) {
    document.getElementById('loadingState').classList.toggle('hidden', state !== 'loading');
    document.getElementById('pendingState').classList.toggle('hidden', state !== 'pending');
    document.getElementById('errorState').classList.toggle('hidden', state !== 'error');
    document.getElementById('resultsContainer').classList.toggle('hidden', state !== 'results');
}

function showError(message) {
    document.getElementById('errorMessage').textContent = message;
    showState('error');
}

function renderResults() {
    showState('results');
    
    if (!currentEvaluation) return;
    
    const eval_ = currentEvaluation;
    const rubric = eval_.rubric_breakdown || {};
    
    const maxMarks = rubric.max_marks || 10;
    const totalScore = eval_.score || 0;
    const percentage = (totalScore / maxMarks) * 100;
    
    document.getElementById('totalScore').textContent = totalScore.toFixed(1);
    document.getElementById('maxMarks').textContent = maxMarks;
    
    const circle = document.getElementById('scoreCircle');
    circle.setAttribute('stroke-dasharray', `${percentage}, 100`);
    
    if (percentage >= 80) {
        circle.style.stroke = '#4CAF50';
    } else if (percentage >= 50) {
        circle.style.stroke = '#FFC107';
    } else {
        circle.style.stroke = '#FF5722';
    }
    
    const confidence = eval_.confidence_score || 0;
    const confidenceBadge = document.getElementById('confidenceBadge');
    if (confidence >= 0.8) {
        confidenceBadge.textContent = 'High';
        confidenceBadge.className = 'confidence-badge high';
    } else if (confidence >= 0.5) {
        confidenceBadge.textContent = 'Medium';
        confidenceBadge.className = 'confidence-badge medium';
    } else {
        confidenceBadge.textContent = 'Low';
        confidenceBadge.className = 'confidence-badge low';
    }
    
    if (rubric.question_type) {
        document.getElementById('typeBadge').textContent = formatQuestionType(rubric.question_type);
    }
    document.getElementById('marksBadge').textContent = `${maxMarks} Marks`;
    
    renderComponents(rubric);
    renderStrengths(eval_.strengths || rubric.strengths || []);
    renderMissingPoints(rubric.missing_points || []);
    renderImprovements(eval_.improvements || rubric.improvement_suggestions || []);
    renderIdealStructure(rubric);
    renderAttemptsTimeline();
    renderComparison();
}

function renderComponents(rubric) {
    const container = document.getElementById('componentsList');
    const componentScores = rubric.component_scores || rubric.components || [];
    
    if (!componentScores.length) {
        container.innerHTML = '<p class="empty-state">No component breakdown available.</p>';
        return;
    }
    
    container.innerHTML = componentScores.map(comp => {
        const awarded = comp.awarded !== undefined ? comp.awarded : comp.marks;
        const max = comp.max !== undefined ? comp.max : comp.marks;
        const percentage = max > 0 ? (awarded / max) * 100 : 0;
        const feedback = comp.feedback || comp.description || '';
        
        let scoreClass = '';
        if (percentage >= 80) scoreClass = 'full';
        else if (percentage >= 50) scoreClass = 'partial';
        else scoreClass = 'low';
        
        return `
            <div class="component-item">
                <div class="component-header">
                    <span class="component-name">${comp.component || comp.name}</span>
                    <span class="component-score ${scoreClass}">${awarded} / ${max}</span>
                </div>
                <div class="component-bar">
                    <div class="component-fill" style="width: ${percentage}%"></div>
                </div>
                ${feedback ? `<p class="component-feedback">${feedback}</p>` : ''}
            </div>
        `;
    }).join('');
}

function renderStrengths(strengths) {
    const container = document.getElementById('strengthsList');
    
    if (!strengths.length) {
        container.innerHTML = '<li>No specific strengths identified.</li>';
        return;
    }
    
    container.innerHTML = strengths.map(s => `<li>${s}</li>`).join('');
}

function renderMissingPoints(missing) {
    const container = document.getElementById('missingPointsList');
    
    if (!missing.length) {
        container.innerHTML = '<li>All key points covered!</li>';
        return;
    }
    
    container.innerHTML = missing.map(m => `<li>${m}</li>`).join('');
}

function renderImprovements(improvements) {
    const container = document.getElementById('improvementsList');
    
    if (!improvements.length) {
        container.innerHTML = '<li>Continue practicing to maintain your performance.</li>';
        return;
    }
    
    container.innerHTML = improvements.map(i => `<li>${i}</li>`).join('');
}

function renderIdealStructure(rubric) {
    const container = document.getElementById('idealStructure');
    const components = rubric.components || rubric.component_scores || [];
    
    if (!components.length) {
        container.innerHTML = '<p class="empty-state">Follow the IRAC framework for best results.</p>';
        return;
    }
    
    container.innerHTML = components.map((comp, idx) => {
        const subPoints = comp.sub_points || [];
        const subPointsHtml = subPoints.length 
            ? `<div class="structure-subpoints">${subPoints.map(sp => `• ${sp.name}`).join('<br>')}</div>`
            : '';
        
        return `
            <div class="structure-item">
                <span class="structure-number">${idx + 1}</span>
                <div class="structure-content">
                    <span class="structure-heading">${comp.component || comp.name}</span>
                    ${subPointsHtml}
                </div>
            </div>
        `;
    }).join('');
}

function renderAttemptsTimeline() {
    const container = document.getElementById('attemptsTimeline');
    const noAttemptsMsg = document.getElementById('noAttemptsMessage');
    
    if (!allAttempts.length || allAttempts.length <= 1) {
        container.classList.add('hidden');
        noAttemptsMsg.classList.remove('hidden');
        return;
    }
    
    container.classList.remove('hidden');
    noAttemptsMsg.classList.add('hidden');
    
    const sortedAttempts = [...allAttempts].sort((a, b) => 
        new Date(b.created_at) - new Date(a.created_at)
    );
    
    container.innerHTML = sortedAttempts.map((attempt, idx) => {
        const attemptNum = sortedAttempts.length - idx;
        const isCurrent = attempt.id === parseInt(currentAttemptId);
        const date = new Date(attempt.created_at).toLocaleDateString('en-IN', {
            day: 'numeric',
            month: 'short',
            year: 'numeric'
        });
        
        let scoreClass = '';
        if (idx > 0 && attempt.score !== undefined) {
            const prevScore = sortedAttempts[idx - 1]?.score;
            if (prevScore !== undefined) {
                scoreClass = attempt.score > prevScore ? 'improved' : (attempt.score < prevScore ? 'declined' : '');
            }
        }
        
        const score = attempt.evaluation?.score ?? attempt.score ?? '-';
        
        return `
            <div class="attempt-item ${isCurrent ? 'current' : ''}" 
                 onclick="viewAttempt(${attempt.id})"
                 title="${isCurrent ? 'Currently viewing' : 'Click to view'}">
                <span class="attempt-number">${attemptNum}</span>
                <div class="attempt-details">
                    <span class="attempt-date">${date}</span>
                </div>
                <span class="attempt-score ${scoreClass}">${score}</span>
            </div>
        `;
    }).join('');
}

function renderComparison() {
    const section = document.getElementById('comparisonSection');
    const barsContainer = document.getElementById('comparisonBars');
    const summary = document.getElementById('comparisonSummary');
    
    if (!allAttempts.length || allAttempts.length < 2) {
        section.classList.add('hidden');
        return;
    }
    
    section.classList.remove('hidden');
    
    const sortedAttempts = [...allAttempts]
        .sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
        .slice(-5);
    
    const maxScore = Math.max(...sortedAttempts.map(a => a.evaluation?.score ?? a.score ?? 0), 1);
    
    barsContainer.innerHTML = sortedAttempts.map((attempt, idx) => {
        const score = attempt.evaluation?.score ?? attempt.score ?? 0;
        const heightPercent = (score / maxScore) * 100;
        
        return `
            <div class="chart-bar">
                <div class="bar-value">${score.toFixed(1)}</div>
                <div class="bar-fill" style="height: ${heightPercent}%"></div>
                <div class="bar-label">#${idx + 1}</div>
            </div>
        `;
    }).join('');
    
    const firstScore = sortedAttempts[0]?.evaluation?.score ?? sortedAttempts[0]?.score ?? 0;
    const lastScore = sortedAttempts[sortedAttempts.length - 1]?.evaluation?.score ?? 
                      sortedAttempts[sortedAttempts.length - 1]?.score ?? 0;
    const improvement = lastScore - firstScore;
    
    if (improvement > 0) {
        summary.textContent = `You've improved by ${improvement.toFixed(1)} marks since your first attempt!`;
    } else if (improvement < 0) {
        summary.textContent = `Your score decreased by ${Math.abs(improvement).toFixed(1)} marks. Review the feedback above.`;
    } else {
        summary.textContent = 'Your score is consistent across attempts.';
    }
}

function viewAttempt(attemptId) {
    if (attemptId === parseInt(currentAttemptId)) return;
    window.location.href = `evaluation-results.html?attempt_id=${attemptId}&question_id=${currentQuestionId}`;
}

function startReattempt() {
    if (currentQuestionId) {
        window.location.href = `practice-content.html?question_id=${currentQuestionId}&reattempt=true`;
    } else {
        showToast('Unable to start reattempt. Question not found.');
    }
}

function retryEvaluation() {
    loadEvaluation();
}

function goBack() {
    window.location.href = 'answer-practice.html';
}

function formatQuestionType(type) {
    const types = {
        'essay': 'Essay',
        'case_analysis': 'Case Analysis',
        'short_answer': 'Short Answer',
        'mcq': 'MCQ'
    };
    return types[type] || type;
}

function showToast(message) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 3000);
}
