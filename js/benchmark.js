/**
 * benchmark.js
 * Phase 8.3 & 8.4: Benchmark Visualization Engine with Normalization
 * 
 * DESIGN PRINCIPLES:
 * - Student should understand where they stand
 * - Student should understand WHY
 * - Student should know what to do next
 * - NO ranks, NO peer names, NO demotivation
 * 
 * Phase 8.4 additions:
 * - Display normalized percentile for fairness
 * - Show confidence indicator
 * - Display difficulty-adjusted feedback
 */

const SAFE_FEEDBACK_TEMPLATES = {
    ahead: "You are ahead of most peers in this subject.",
    aligned: "You are currently aligned with the cohort average.",
    needsAttention: "This subject needs attention to catch up with peers."
};

const OVERALL_MESSAGES = {
    top25: "You are performing better than most students in your semester. Keep up the excellent work!",
    middle50Above: "You are performing above average compared to your semester peers. Good progress!",
    middle50Below: "You are performing close to the average of your peers. Consistent practice will help you improve.",
    bottom25: "There is room for improvement. Focus on your weaker subjects to catch up with your peers."
};

const CONFIDENCE_LABELS = {
    high: "High confidence",
    medium: "Moderate confidence",
    low: "Low confidence"
};

let benchmarkData = null;

document.addEventListener('DOMContentLoaded', () => {
    initializePage();
    loadBenchmarkData();
});

function initializePage() {
    const menuToggle = document.getElementById('menuToggle');
    const sidebar = document.getElementById('sidebar');
    const sidebarOverlay = document.getElementById('sidebarOverlay');
    
    if (menuToggle) {
        menuToggle.addEventListener('click', () => {
            sidebar.classList.toggle('open');
            sidebarOverlay.classList.toggle('active');
        });
    }
    
    if (sidebarOverlay) {
        sidebarOverlay.addEventListener('click', () => {
            sidebar.classList.remove('open');
            sidebarOverlay.classList.remove('active');
        });
    }
    
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', (e) => {
            e.preventDefault();
            localStorage.removeItem('access_token');
            window.location.href = './login.html';
        });
    }
    
    const infoBtn = document.getElementById('overallInfoBtn');
    const tooltip = document.getElementById('overallTooltip');
    const tooltipClose = document.getElementById('tooltipClose');
    
    if (infoBtn && tooltip) {
        infoBtn.addEventListener('click', () => {
            tooltip.style.display = tooltip.style.display === 'none' ? 'block' : 'none';
        });
    }
    
    if (tooltipClose) {
        tooltipClose.addEventListener('click', () => {
            tooltip.style.display = 'none';
        });
    }
    
    document.addEventListener('click', (e) => {
        if (tooltip && !tooltip.contains(e.target) && e.target !== infoBtn) {
            tooltip.style.display = 'none';
        }
    });
    
    const user = JSON.parse(localStorage.getItem('user') || '{}');
    const avatarInitial = document.getElementById('avatarInitial');
    if (avatarInitial && user.name) {
        avatarInitial.textContent = user.name.charAt(0).toUpperCase();
    }
}

async function loadBenchmarkData() {
    showLoading();
    
    try {
        const data = await api.get('/api/benchmark/compare');
        benchmarkData = data;
        
        if (!data.success) {
            showError(data.error || 'Unable to load benchmark data');
            return;
        }
        
        if (data.eligibility && !data.eligibility.eligible) {
            showEligibilityState(data.eligibility);
            return;
        }
        
        renderBenchmark(data);
        
    } catch (error) {
        console.error('Benchmark load error:', error);
        showError(error.message || 'Unable to load benchmark data');
    }
}

function showLoading() {
    document.getElementById('loadingState').style.display = 'flex';
    document.getElementById('errorState').style.display = 'none';
    document.getElementById('eligibilityState').style.display = 'none';
    document.getElementById('benchmarkContainer').style.display = 'none';
}

function showError(message) {
    document.getElementById('loadingState').style.display = 'none';
    document.getElementById('errorState').style.display = 'flex';
    document.getElementById('eligibilityState').style.display = 'none';
    document.getElementById('benchmarkContainer').style.display = 'none';
    
    document.getElementById('errorMessage').textContent = message;
}

function showEligibilityState(eligibility) {
    document.getElementById('loadingState').style.display = 'none';
    document.getElementById('errorState').style.display = 'none';
    document.getElementById('eligibilityState').style.display = 'flex';
    document.getElementById('benchmarkContainer').style.display = 'none';
    
    const attemptsCompleted = eligibility.attempts_completed || 0;
    const attemptsRequired = eligibility.attempts_required || 3;
    const progress = Math.min((attemptsCompleted / attemptsRequired) * 100, 100);
    
    document.getElementById('eligibilityProgressFill').style.width = `${progress}%`;
    document.getElementById('eligibilityProgressText').textContent = `${attemptsCompleted} / ${attemptsRequired} attempts`;
    
    if (eligibility.reason) {
        document.getElementById('eligibilityMessage').textContent = 
            `Complete ${attemptsRequired - attemptsCompleted} more practice sessions to unlock your peer comparison.`;
    }
}

function renderBenchmark(data) {
    document.getElementById('loadingState').style.display = 'none';
    document.getElementById('errorState').style.display = 'none';
    document.getElementById('eligibilityState').style.display = 'none';
    document.getElementById('benchmarkContainer').style.display = 'block';
    
    renderCohortInfo(data.cohort);
    renderOverallStanding(data.overall, data.cohort);
    renderSubjectCards(data.subjects);
}

function renderCohortInfo(cohort) {
    if (!cohort) return;
    
    const description = `Compared with ${cohort.active_students || 0} active ${cohort.course || 'course'} students in Semester ${cohort.semester || '-'}`;
    document.getElementById('cohortDescription').textContent = description;
    
    if (cohort.small_cohort_warning) {
        const section = document.getElementById('cohortInfoSection');
        const notice = document.createElement('div');
        notice.className = 'small-cohort-notice';
        notice.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="8" x2="12" y2="12"/>
                <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <p>Your cohort has fewer students than usual. Percentiles may be less precise but will improve as more peers practice.</p>
        `;
        section.appendChild(notice);
    }
}

function renderOverallStanding(overall, cohort) {
    if (!overall) return;
    
    const normalized = overall.normalized || {};
    const percentile = normalized.percentile !== undefined ? normalized.percentile : overall.percentile;
    const band = overall.band;
    const confidence = normalized.confidence || 'high';
    
    const percentileNumber = document.getElementById('percentileNumber');
    const percentileFill = document.getElementById('percentileFill');
    const bandValue = document.getElementById('bandValue');
    const overallMessage = document.getElementById('overallMessage');
    
    if (percentile !== null && percentile !== undefined) {
        percentileNumber.textContent = percentile;
        
        const circumference = 2 * Math.PI * 45;
        const offset = circumference - (percentile / 100) * circumference;
        percentileFill.style.strokeDashoffset = offset;
        
        const bandClass = getBandClass(band);
        percentileFill.classList.add(bandClass);
        bandValue.classList.add(bandClass);
    } else {
        percentileNumber.textContent = '--';
        bandValue.classList.add('insufficient-data');
    }
    
    bandValue.textContent = band || 'Calculating...';
    
    const message = getOverallMessage(percentile, band);
    let messageHtml = `<p>${message}</p>`;
    
    if (confidence === 'low') {
        messageHtml += `<p class="confidence-note">Benchmark accuracy improves with more practice.</p>`;
    } else if (normalized.note) {
        messageHtml += `<p class="normalization-note">${normalized.note}</p>`;
    }
    
    overallMessage.innerHTML = messageHtml;
    
    if (overall.strongest_subject) {
        const strongestEl = document.getElementById('strongestSubject');
        strongestEl.querySelector('.sw-value').textContent = overall.strongest_subject.title;
    }
    
    if (overall.weakest_subject) {
        const weakestEl = document.getElementById('weakestSubject');
        weakestEl.querySelector('.sw-value').textContent = overall.weakest_subject.title;
    }
}

function getBandClass(band) {
    if (!band) return 'insufficient-data';
    
    const bandLower = band.toLowerCase();
    if (bandLower.includes('top')) return 'top-band';
    if (bandLower.includes('bottom')) return 'bottom-band';
    return 'middle-band';
}

function getOverallMessage(percentile, band) {
    if (percentile === null || percentile === undefined) {
        return "Complete more practice to see your standing among peers.";
    }
    
    if (percentile >= 75) {
        return OVERALL_MESSAGES.top25;
    } else if (percentile >= 50) {
        return OVERALL_MESSAGES.middle50Above;
    } else if (percentile >= 25) {
        return OVERALL_MESSAGES.middle50Below;
    } else {
        return OVERALL_MESSAGES.bottom25;
    }
}

function renderSubjectCards(subjects) {
    const grid = document.getElementById('subjectsBenchmarkGrid');
    grid.innerHTML = '';
    
    if (!subjects || subjects.length === 0) {
        grid.innerHTML = `
            <div class="empty-subjects">
                <div class="empty-subjects-icon">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                    </svg>
                </div>
                <h3>No Subjects to Compare</h3>
                <p>Start practicing subjects in your curriculum to see benchmark comparisons.</p>
            </div>
        `;
        return;
    }
    
    subjects.forEach((subject, index) => {
        const card = createSubjectCard(subject, index);
        grid.appendChild(card);
    });
}

function createSubjectCard(subject, index) {
    const card = document.createElement('div');
    card.className = 'subject-benchmark-card';
    
    const hasData = subject.student_mastery !== null && subject.student_mastery !== undefined;
    const hasPercentile = subject.percentile !== null && subject.percentile !== undefined;
    
    const normalized = subject.normalized || {};
    const difficulty = subject.difficulty || {};
    const normalizedPercentile = normalized.percentile;
    const displayPercentile = normalizedPercentile !== undefined ? normalizedPercentile : subject.percentile;
    const confidence = normalized.confidence || 'high';
    
    const bandClass = hasPercentile ? getBandClass(subject.band) : 'no-data';
    const percentileText = displayPercentile !== null && displayPercentile !== undefined ? `${displayPercentile}th` : 'N/A';
    
    const studentMastery = hasData ? subject.student_mastery : 0;
    const cohortAvg = subject.cohort_avg || 0;
    const diff = hasData ? (studentMastery - cohortAvg).toFixed(1) : null;
    const diffClass = diff > 0 ? 'positive' : (diff < 0 ? 'negative' : '');
    const diffText = diff !== null ? (diff > 0 ? `+${diff}%` : `${diff}%`) : '--';
    
    const feedback = getSubjectFeedback(subject);
    const feedbackClass = feedback.type;
    
    const explanation = generateExplanation(subject);
    
    const difficultyBadge = difficulty.is_harder ? 
        `<span class="difficulty-badge harder">Challenging subject</span>` : '';
    
    const confidenceBadge = confidence === 'low' ? 
        `<span class="confidence-badge low">More data needed</span>` : '';
    
    card.innerHTML = `
        <div class="subject-benchmark-header">
            <div>
                <h3 class="subject-benchmark-title">${subject.title}</h3>
                <span class="subject-benchmark-code">${subject.code || ''}</span>
                ${difficultyBadge}
            </div>
            <span class="subject-percentile-badge ${bandClass}">${percentileText}</span>
        </div>
        
        <div class="subject-comparison-bar">
            <div class="comparison-bar-container">
                <div class="comparison-bar-zones">
                    <div class="bar-zone weak">&lt;40%</div>
                    <div class="bar-zone average">40-70%</div>
                    <div class="bar-zone strong">&gt;70%</div>
                </div>
                ${hasData ? `
                    <div class="comparison-marker" style="left: ${Math.min(Math.max(cohortAvg, 2), 98)}%">
                        <div class="marker-dot cohort"></div>
                        <div class="marker-line cohort-line"></div>
                    </div>
                    <div class="comparison-marker" style="left: ${Math.min(Math.max(studentMastery, 2), 98)}%">
                        <div class="marker-dot student"></div>
                        <div class="marker-line"></div>
                        <span class="marker-label">${studentMastery.toFixed(0)}%</span>
                    </div>
                ` : ''}
            </div>
            <div class="comparison-legend">
                <div class="legend-item">
                    <span class="legend-dot student"></span>
                    <span>Your Score</span>
                </div>
                <div class="legend-item">
                    <span class="legend-dot cohort"></span>
                    <span>Cohort Avg (${cohortAvg.toFixed(0)}%)</span>
                </div>
            </div>
        </div>
        
        <div class="subject-stats">
            <div class="stat-item">
                <span class="stat-item-label">Your Mastery</span>
                <span class="stat-item-value">${hasData ? studentMastery.toFixed(1) + '%' : '--'}</span>
            </div>
            <div class="stat-item">
                <span class="stat-item-label">Cohort Avg</span>
                <span class="stat-item-value">${cohortAvg.toFixed(1)}%</span>
            </div>
            <div class="stat-item">
                <span class="stat-item-label">vs Peers</span>
                <span class="stat-item-value ${diffClass}">${diffText}</span>
            </div>
        </div>
        
        <div class="subject-feedback ${feedbackClass}">
            <p>${feedback.message}</p>
            ${confidenceBadge}
        </div>
        
        <div class="subject-explanation">
            <button class="explanation-toggle" data-subject="${index}">
                <span>Why this result?</span>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="6 9 12 15 18 9"/>
                </svg>
            </button>
            <div class="explanation-content" id="explanation-${index}">
                ${explanation}
            </div>
        </div>
    `;
    
    const toggleBtn = card.querySelector('.explanation-toggle');
    toggleBtn.addEventListener('click', () => {
        toggleBtn.classList.toggle('expanded');
        const content = card.querySelector(`#explanation-${index}`);
        content.classList.toggle('visible');
    });
    
    return card;
}

function getSubjectFeedback(subject) {
    const hasData = subject.student_mastery !== null && subject.student_mastery !== undefined;
    
    if (!hasData) {
        return {
            type: 'neutral',
            message: 'Complete practice in this subject to see how you compare with peers.'
        };
    }
    
    const percentile = subject.percentile;
    const studentMastery = subject.student_mastery;
    const cohortAvg = subject.cohort_avg || 0;
    
    if (percentile === null || percentile === undefined) {
        if (studentMastery > cohortAvg + 5) {
            return { type: 'positive', message: SAFE_FEEDBACK_TEMPLATES.ahead };
        } else if (studentMastery < cohortAvg - 5) {
            return { type: 'negative', message: SAFE_FEEDBACK_TEMPLATES.needsAttention };
        } else {
            return { type: 'neutral', message: SAFE_FEEDBACK_TEMPLATES.aligned };
        }
    }
    
    if (percentile >= 75) {
        return { type: 'positive', message: SAFE_FEEDBACK_TEMPLATES.ahead };
    } else if (percentile >= 25) {
        return { type: 'neutral', message: SAFE_FEEDBACK_TEMPLATES.aligned };
    } else {
        return { type: 'negative', message: SAFE_FEEDBACK_TEMPLATES.needsAttention };
    }
}

function generateExplanation(subject) {
    const hasData = subject.student_mastery !== null && subject.student_mastery !== undefined;
    const studentMastery = subject.student_mastery || 0;
    const cohortAvg = subject.cohort_avg || 0;
    const cohortSize = subject.cohort_size || 0;
    const percentile = subject.percentile;
    
    const normalized = subject.normalized || {};
    const difficulty = subject.difficulty || {};
    const normalizedPercentile = normalized.percentile;
    const confidence = normalized.confidence;
    
    if (!hasData) {
        return `
            <p>You haven't completed any practice in this subject yet. Once you do, we'll compare your mastery with ${cohortSize} peers in your cohort.</p>
        `;
    }
    
    let explanationParts = [];
    
    explanationParts.push(`Your mastery in this subject is <strong>${studentMastery.toFixed(1)}%</strong>, compared to the cohort average of <strong>${cohortAvg.toFixed(1)}%</strong>.`);
    
    if (percentile !== null && percentile !== undefined) {
        explanationParts.push(`This places you at the <strong>${percentile}th percentile</strong>, meaning you are performing better than ${percentile}% of your ${cohortSize} active peers.`);
    }
    
    if (difficulty.is_harder) {
        explanationParts.push(`This subject is generally considered more challenging.`);
    }
    
    if (normalizedPercentile !== undefined && normalizedPercentile !== percentile) {
        explanationParts.push(`Your standing is adjusted to ensure fairness across subjects with different difficulty levels.`);
    }
    
    const diff = studentMastery - cohortAvg;
    if (diff > 10) {
        explanationParts.push(`Your score is significantly above average. Your consistent practice is paying off.`);
    } else if (diff > 0) {
        explanationParts.push(`You are slightly above average. Keep practicing to maintain your edge.`);
    } else if (diff > -10) {
        explanationParts.push(`You are close to the average. Regular practice will help you move ahead.`);
    } else {
        explanationParts.push(`There is room for improvement. Focus on understanding core concepts and practice regularly.`);
    }
    
    if (confidence === 'low') {
        explanationParts.push(`<em>Note: Benchmark accuracy improves with more practice.</em>`);
    }
    
    return `<p>${explanationParts.join(' ')}</p>`;
}

window.loadBenchmarkData = loadBenchmarkData;
