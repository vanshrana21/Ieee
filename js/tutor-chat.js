const TUTOR_API = 'http://127.0.0.1:8000/api/tutor/chat';

let currentSessionId = null;
let isLoading = false;

document.addEventListener('DOMContentLoaded', () => {
    checkAuth();
    loadContext();
    loadSuggestions();
    setupInputHandlers();
});

function checkAuth() {
    const token = localStorage.getItem('access_token');
    if (!token) {
        window.location.href = 'login.html';
    }
}

async function loadContext() {
    try {
        const token = localStorage.getItem('access_token');
        const response = await fetch(`${TUTOR_API}/context`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (!response.ok) throw new Error('Failed to load context');
        
        const context = await response.json();
        
        document.getElementById('contextCourse').textContent = context.course || 'Not Enrolled';
        document.getElementById('contextSemester').textContent = context.semester || '-';
        document.getElementById('contextAttempts').textContent = context.total_attempts || 0;
        
        document.getElementById('userCourse').textContent = context.course || '';
        document.getElementById('userSemester').textContent = context.semester ? `Semester ${context.semester}` : '';
        
        const weakTopicsContainer = document.getElementById('weakTopics');
        if (context.weak_topics && context.weak_topics.length > 0) {
            weakTopicsContainer.innerHTML = context.weak_topics.slice(0, 5).map(topic => `
                <div class="weak-topic-item">${formatTopicName(topic)}</div>
            `).join('');
        } else {
            weakTopicsContainer.innerHTML = '<p class="empty-state">No weak topics identified</p>';
        }
        
    } catch (error) {
        console.error('Error loading context:', error);
    }
}

async function loadSuggestions() {
    try {
        const token = localStorage.getItem('access_token');
        const response = await fetch(`${TUTOR_API}/suggested-queries`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (!response.ok) throw new Error('Failed to load suggestions');
        
        const data = await response.json();
        
        const container = document.getElementById('suggestionsList');
        if (data.suggestions && data.suggestions.length > 0) {
            container.innerHTML = data.suggestions.map(s => `
                <div class="suggestion-item" onclick="useSuggestion('${escapeHtml(s.query)}')">
                    <div class="suggestion-query">${escapeHtml(s.query)}</div>
                    <div class="suggestion-reason">${escapeHtml(s.reason)}</div>
                </div>
            `).join('');
        } else {
            container.innerHTML = '<p class="empty-state">No suggestions available</p>';
        }
        
    } catch (error) {
        console.error('Error loading suggestions:', error);
        document.getElementById('suggestionsList').innerHTML = '<p class="empty-state">Failed to load suggestions</p>';
    }
}

function setupInputHandlers() {
    const input = document.getElementById('chatInput');
    const charCount = document.getElementById('charCount');
    
    input.addEventListener('input', () => {
        charCount.textContent = input.value.length;
        
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 150) + 'px';
    });
    
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
}

function useSuggestion(query) {
    document.getElementById('chatInput').value = query;
    document.getElementById('charCount').textContent = query.length;
    document.getElementById('chatInput').focus();
}

async function sendMessage() {
    const input = document.getElementById('chatInput');
    const query = input.value.trim();
    
    if (!query || isLoading) return;
    
    isLoading = true;
    const sendBtn = document.getElementById('sendBtn');
    sendBtn.disabled = true;
    
    const welcomeMessage = document.querySelector('.welcome-message');
    if (welcomeMessage) {
        welcomeMessage.remove();
    }
    
    addMessage('user', query);
    input.value = '';
    document.getElementById('charCount').textContent = '0';
    input.style.height = 'auto';
    
    const typingId = showTypingIndicator();
    
    try {
        const token = localStorage.getItem('access_token');
        const response = await fetch(`${TUTOR_API}/ask`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                query: query,
                session_id: currentSessionId
            })
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to get response');
        }
        
        const data = await response.json();
        
        currentSessionId = data.session_id;
        
        hideTypingIndicator(typingId);
        
        addMessage('assistant', data.response, {
            intent: data.intent,
            topic: data.topic,
            mastery_level: data.mastery_level
        });
        
        updateInfoPanel(data);
        
    } catch (error) {
        hideTypingIndicator(typingId);
        addMessage('assistant', 'Sorry, I encountered an error. Please try again.', { error: true });
        showToast(error.message);
    } finally {
        isLoading = false;
        sendBtn.disabled = false;
    }
}

function addMessage(role, content, meta = {}) {
    const container = document.getElementById('chatMessages');
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    
    const avatarText = role === 'assistant' ? 'AI' : 'You';
    
    const formattedContent = role === 'assistant' ? formatMarkdown(content) : escapeHtml(content);
    
    messageDiv.innerHTML = `
        <div class="message-avatar">${avatarText}</div>
        <div class="message-content">${formattedContent}</div>
    `;
    
    if (role === 'assistant' && meta.intent) {
        const metaDiv = document.createElement('div');
        metaDiv.className = 'message-meta';
        metaDiv.innerHTML = `
            <span class="meta-badge">${formatIntent(meta.intent)}</span>
            ${meta.topic ? `<span class="meta-badge">${formatTopicName(meta.topic)}</span>` : ''}
        `;
        messageDiv.querySelector('.message-content').appendChild(metaDiv);
    }
    
    container.appendChild(messageDiv);
    container.scrollTop = container.scrollHeight;
}

function showTypingIndicator() {
    const container = document.getElementById('chatMessages');
    const typingDiv = document.createElement('div');
    typingDiv.className = 'message assistant';
    typingDiv.id = 'typing-indicator';
    
    typingDiv.innerHTML = `
        <div class="message-avatar">AI</div>
        <div class="typing-indicator">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
        </div>
    `;
    
    container.appendChild(typingDiv);
    container.scrollTop = container.scrollHeight;
    
    return 'typing-indicator';
}

function hideTypingIndicator(id) {
    const typing = document.getElementById(id);
    if (typing) {
        typing.remove();
    }
}

function updateInfoPanel(data) {
    const panel = document.getElementById('infoPanel');
    panel.classList.add('visible');
    
    document.getElementById('intentBadge').textContent = formatIntent(data.intent);
    document.getElementById('topicInfo').textContent = data.topic ? formatTopicName(data.topic) : 'General';
    
    const masteryBadge = document.getElementById('masteryBadge');
    masteryBadge.textContent = formatMastery(data.mastery_level);
    masteryBadge.className = `mastery-badge ${data.mastery_level}`;
    
    const suggestionsList = document.getElementById('responseSuggestions');
    if (data.suggestions && data.suggestions.length > 0) {
        suggestionsList.innerHTML = data.suggestions.map(s => `<li>${escapeHtml(s)}</li>`).join('');
        document.getElementById('suggestionsSection').style.display = 'block';
    } else {
        document.getElementById('suggestionsSection').style.display = 'none';
    }
    
    const relatedList = document.getElementById('relatedContent');
    if (data.related_content && data.related_content.length > 0) {
        relatedList.innerHTML = data.related_content.map(item => `
            <li onclick="navigateToContent('${item.type}', ${item.id})">${escapeHtml(item.title)}</li>
        `).join('');
        document.getElementById('relatedSection').style.display = 'block';
    } else {
        document.getElementById('relatedSection').style.display = 'none';
    }
}

function closeInfoPanel() {
    document.getElementById('infoPanel').classList.remove('visible');
}

function startNewChat() {
    currentSessionId = null;
    
    const container = document.getElementById('chatMessages');
    container.innerHTML = `
        <div class="welcome-message">
            <div class="welcome-icon">
                <span>AI</span>
            </div>
            <h3>Welcome to your AI Law Tutor</h3>
            <p>Ask questions about your syllabus topics. I will provide exam-oriented explanations based on your course and semester.</p>
            <div class="welcome-rules">
                <div class="rule">
                    <span class="rule-icon">+</span>
                    <span>Explain concepts, cases, and legal principles</span>
                </div>
                <div class="rule">
                    <span class="rule-icon">+</span>
                    <span>Clarify doubts and compare legal terms</span>
                </div>
                <div class="rule">
                    <span class="rule-icon">+</span>
                    <span>Guide you on answer writing structure</span>
                </div>
                <div class="rule negative">
                    <span class="rule-icon">-</span>
                    <span>No legal advice for personal situations</span>
                </div>
                <div class="rule negative">
                    <span class="rule-icon">-</span>
                    <span>No topics outside your syllabus</span>
                </div>
            </div>
        </div>
    `;
    
    closeInfoPanel();
    showToast('Started new chat session');
}

function navigateToContent(type, id) {
    if (type === 'learn') {
        window.location.href = `learn-content.html?id=${id}`;
    } else if (type === 'case') {
        window.location.href = `case-content.html?id=${id}`;
    }
}

function formatMarkdown(text) {
    if (!text) return '';
    
    text = text.replace(/^### (.*$)/gm, '<h3>$1</h3>');
    text = text.replace(/^## (.*$)/gm, '<h2>$1</h2>');
    text = text.replace(/^# (.*$)/gm, '<h1>$1</h1>');
    
    text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/\*(.*?)\*/g, '<em>$1</em>');
    
    text = text.replace(/`(.*?)`/g, '<code>$1</code>');
    
    text = text.replace(/^> (.*$)/gm, '<blockquote>$1</blockquote>');
    
    text = text.replace(/^\* (.*$)/gm, '<li>$1</li>');
    text = text.replace(/^- (.*$)/gm, '<li>$1</li>');
    text = text.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
    
    text = text.replace(/^\d+\. (.*$)/gm, '<li>$1</li>');
    
    const tableRegex = /\|(.+)\|\n\|[-:| ]+\|\n((?:\|.+\|\n?)+)/g;
    text = text.replace(tableRegex, (match, header, rows) => {
        const headers = header.split('|').filter(h => h.trim()).map(h => `<th>${h.trim()}</th>`).join('');
        const bodyRows = rows.trim().split('\n').map(row => {
            const cells = row.split('|').filter(c => c.trim()).map(c => `<td>${c.trim()}</td>`).join('');
            return `<tr>${cells}</tr>`;
        }).join('');
        return `<table><thead><tr>${headers}</tr></thead><tbody>${bodyRows}</tbody></table>`;
    });
    
    text = text.replace(/\n\n/g, '</p><p>');
    text = text.replace(/\n/g, '<br>');
    
    if (!text.startsWith('<')) {
        text = '<p>' + text + '</p>';
    }
    
    return text;
}

function formatIntent(intent) {
    const intents = {
        'explain_concept': 'Explanation',
        'clarify_doubt': 'Clarification',
        'writing_guidance': 'Writing Guide',
        'revision_help': 'Revision',
        'general_question': 'General',
        'out_of_scope': 'Out of Scope'
    };
    return intents[intent] || intent;
}

function formatMastery(level) {
    const levels = {
        'weak': 'Weak',
        'average': 'Average',
        'strong': 'Strong',
        'unknown': 'Unknown'
    };
    return levels[level] || level;
}

function formatTopicName(topic) {
    if (!topic) return '';
    return topic.replace(/-/g, ' ').replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

function escapeHtml(text) {
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
