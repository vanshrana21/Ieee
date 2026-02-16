const PLANNER_API = 'http://127.0.0.1:8000/api/study-planner';

let currentPlan = null;
let selectedItem = null;

document.addEventListener('DOMContentLoaded', () => {
    checkAuth();
    loadPlan();
    loadNextItem();
});

function checkAuth() {
    const token = localStorage.getItem('access_token');
    if (!token) {
        window.location.href = 'login.html';
    }
}

async function loadPlan() {
    const planType = document.getElementById('planType').value;
    const planDays = document.getElementById('planDays');
    
    planDays.innerHTML = `
        <div class="loading-state">
            <div class="spinner"></div>
            <p>Generating your personalized study plan...</p>
        </div>
    `;
    
    try {
        const endpoint = planType === 'daily' ? '/daily' : '/weekly';
        const data = await apiRequest(`${PLANNER_API}${endpoint}`);
        
        if (data) {
            currentPlan = data;
            renderPlan(currentPlan);
            updateStats(currentPlan);
            renderRecommendations(currentPlan.recommendations);
        }
    } catch (error) {
        console.error('Error loading plan:', error);
        planDays.innerHTML = `
            <div class="empty-state">
                <h3>Unable to generate plan</h3>
                <p>Start practicing some topics to get personalized recommendations.</p>
            </div>
        `;
    }
}

async function loadNextItem() {
    const container = document.getElementById('nextItemContent');
    
    try {
        const item = await apiRequest(`${PLANNER_API}/next`);
        
        if (item) {
            renderNextItem(item);
        } else {
            container.innerHTML = `
                <div class="empty-state">
                    <h3>No items available</h3>
                    <p>Start learning to get recommendations.</p>
                </div>
            `;
        }
    } catch (error) {
        console.error('[API ERROR] Failed to load next item:', error);
        container.innerHTML = `
            <div class="empty-state">
                <h3>No items available</h3>
                <p>Start learning to get recommendations.</p>
            </div>
        `;
    }
}

function renderPlan(plan) {
    const container = document.getElementById('planDays');
    
    if (!plan.days || plan.days.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <h3>No study plan available</h3>
                <p>${plan.summary?.message || 'Start exploring subjects to get personalized recommendations.'}</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = plan.days.map(day => `
        <div class="day-card">
            <div class="day-header">
                <div class="day-info">
                    <h3>${day.day_label}</h3>
                    <span class="day-date">${formatDate(day.date)}</span>
                </div>
                <div class="day-meta">
                    <div class="day-meta-item">
                        <div class="day-meta-value">${day.items.length}</div>
                        <div class="day-meta-label">Items</div>
                    </div>
                    <div class="day-meta-item">
                        <div class="day-meta-value">${day.total_time_minutes}</div>
                        <div class="day-meta-label">Minutes</div>
                    </div>
                </div>
            </div>
            <div class="day-items">
                ${day.items.map(item => renderStudyItem(item)).join('')}
            </div>
        </div>
    `).join('');
}

function renderStudyItem(item) {
    const iconSvg = getActivityIcon(item.activity_type);
    const itemJson = encodeURIComponent(JSON.stringify(item));
    
    return `
        <div class="study-item" onclick="openItemModal('${itemJson}')">
            <div class="item-activity-icon ${item.activity_type}">
                ${iconSvg}
            </div>
            <div class="item-content">
                <div class="item-header">
                    <span class="item-title">${escapeHtml(item.content_title)}</span>
                    <span class="item-priority ${item.priority_level.toLowerCase()}">${item.priority_level}</span>
                </div>
                <div class="item-subject">${escapeHtml(item.subject_name)} ${item.topic_tag ? '- ' + formatTopicName(item.topic_tag) : ''}</div>
                <div class="item-why">${escapeHtml(item.why)}</div>
            </div>
            <div class="item-time">
                <div class="item-time-value">${item.estimated_time_minutes}</div>
                <div class="item-time-unit">min</div>
            </div>
        </div>
    `;
}

function renderNextItem(item) {
    const container = document.getElementById('nextItemContent');
    
    container.innerHTML = `
        <div class="next-item-card">
            <span class="next-item-badge ${item.activity}">${item.activity}</span>
            <div class="next-item-title">${escapeHtml(item.content_title)}</div>
            <div class="next-item-subject">${escapeHtml(item.subject)} ${item.topic ? '- ' + formatTopicName(item.topic) : ''}</div>
            <div class="next-item-why">${escapeHtml(item.why)}</div>
            <div class="next-item-focus">${escapeHtml(item.focus)}</div>
            <button class="btn-start-now" onclick="startNextItem(${item.content_id}, '${item.activity}', ${item.module_id})">
                Start Now (${item.estimated_time_minutes} min)
            </button>
        </div>
    `;
}

function updateStats(plan) {
    const summary = plan.summary || {};
    
    document.getElementById('totalItems').textContent = summary.total_items || 0;
    document.getElementById('totalTime').textContent = summary.total_time_minutes || 0;
    document.getElementById('weakTopics').textContent = summary.weak_topics_covered || summary.weak_topics_total || 0;
    document.getElementById('subjectsCovered').textContent = summary.subjects_covered || 0;
}

function renderRecommendations(recommendations) {
    const container = document.getElementById('recommendationsList');
    
    if (!recommendations || recommendations.length === 0) {
        document.getElementById('recommendationsBar').style.display = 'none';
        return;
    }
    
    container.innerHTML = recommendations.map(rec => `
        <span class="recommendation-item">${escapeHtml(rec)}</span>
    `).join('');
}

function changePlanType() {
    loadPlan();
}

async function regeneratePlan() {
    const planType = document.getElementById('planType').value;
    const planDays = document.getElementById('planDays');
    
    planDays.innerHTML = `
        <div class="loading-state">
            <div class="spinner"></div>
            <p>Regenerating your study plan...</p>
        </div>
    `;
    
    try {
        const data = await apiRequest(`${PLANNER_API}/regenerate?plan_type=${planType}`, {
            method: 'POST'
        });
        
        if (data) {
            currentPlan = data;
            renderPlan(currentPlan);
            updateStats(currentPlan);
            renderRecommendations(currentPlan.recommendations);
            showToast('Study plan regenerated');
        }
    } catch (error) {
        console.error('[API ERROR] Failed to regenerate plan:', error);
        showToast('Failed to regenerate plan');
        loadPlan();
    }
}

function openItemModal(itemJson) {
    const item = JSON.parse(decodeURIComponent(itemJson));
    selectedItem = item;
    
    document.getElementById('modalActivityBadge').textContent = item.activity_type;
    document.getElementById('modalActivityBadge').className = `modal-activity-badge ${item.activity_type}`;
    document.getElementById('modalPriorityBadge').textContent = item.priority_level;
    document.getElementById('modalPriorityBadge').className = `modal-priority-badge ${item.priority_level.toLowerCase()}`;
    
    document.getElementById('modalTitle').textContent = item.content_title;
    document.getElementById('modalSubject').textContent = `${item.subject_name} ${item.topic_tag ? '- ' + formatTopicName(item.topic_tag) : ''}`;
    
    document.getElementById('modalWhy').textContent = item.why;
    document.getElementById('modalFocus').textContent = item.focus;
    document.getElementById('modalSuccess').textContent = item.success_criteria;
    
    document.getElementById('modalTime').textContent = `${item.estimated_time_minutes} minutes`;
    document.getElementById('modalMastery').textContent = item.mastery_percent !== null ? `${item.mastery_percent.toFixed(0)}%` : 'Unknown';
    document.getElementById('modalLastPractice').textContent = item.days_since_practice !== null ? 
        (item.days_since_practice === 0 ? 'Today' : `${item.days_since_practice} days ago`) : 'Never';
    
    document.getElementById('itemModal').classList.add('visible');
}

function closeModal() {
    document.getElementById('itemModal').classList.remove('visible');
    selectedItem = null;
}

function startStudying() {
    if (!selectedItem) return;
    
    const activity = selectedItem.activity_type;
    const contentId = selectedItem.content_id;
    const moduleId = selectedItem.module_id;
    
    navigateToContent(activity, contentId, moduleId);
    closeModal();
}

function startNextItem(contentId, activity, moduleId) {
    navigateToContent(activity, contentId, moduleId);
}

function navigateToContent(activity, contentId, moduleId) {
    if (activity === 'learn' || activity === 'revision') {
        if (contentId) {
            window.location.href = `learn-content.html?id=${contentId}`;
        } else if (moduleId) {
            window.location.href = `module-content.html?id=${moduleId}`;
        }
    } else if (activity === 'case') {
        if (contentId) {
            window.location.href = `case-content.html?id=${contentId}`;
        } else if (moduleId) {
            window.location.href = `module-cases.html?id=${moduleId}`;
        }
    } else if (activity === 'practice') {
        if (contentId) {
            window.location.href = `answer-practice.html?question=${contentId}`;
        } else if (moduleId) {
            window.location.href = `practice.html?module=${moduleId}`;
        }
    }
    
    if (!contentId && !moduleId) {
        showToast('Opening practice section...');
        window.location.href = 'answer-practice.html';
    }
}

function getActivityIcon(activity) {
    const icons = {
        learn: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 19.5A2.5 2.5 0 016.5 17H20"/>
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/>
        </svg>`,
        case: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/>
            <path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3"/>
            <line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>`,
        practice: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/>
            <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/>
        </svg>`,
        revision: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="23 4 23 10 17 10"/>
            <polyline points="1 20 1 14 7 14"/>
            <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
        </svg>`,
    };
    return icons[activity] || icons.learn;
}

function formatDate(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    const options = { weekday: 'short', month: 'short', day: 'numeric' };
    return date.toLocaleDateString('en-US', options);
}

function formatTopicName(topic) {
    if (!topic) return '';
    return topic.replace(/-/g, ' ').replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
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

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeModal();
    }
});
