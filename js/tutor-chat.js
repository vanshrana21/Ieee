/**
 * tutor-chat.js
 * Phase 10: Complete AI Tutor Chat Interface
 */

const API_BASE = 'http://127.0.0.1:8000';

class TutorChat {
    constructor() {
        this.sessionId = null;
        this.messagesContainer = document.getElementById('messagesContainer');
        this.userInput = document.getElementById('userInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.loadingIndicator = document.getElementById('loadingIndicator');
        this.errorMessage = document.getElementById('errorMessage');
        this.emptyState = document.getElementById('emptyState');
        
        this.init();
    }
    
    init() {
        // Event listeners
        this.sendBtn.addEventListener('click', () => this.sendMessage());
        this.userInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
        
        // Auto-resize textarea
        this.userInput.addEventListener('input', () => {
            this.userInput.style.height = 'auto';
            this.userInput.style.height = Math.min(this.userInput.scrollHeight, 120) + 'px';
        });
        
        // Focus input
        this.userInput.focus();
    }
    
    async sendMessage() {
        const userText = this.userInput.value.trim();
        
        if (!userText || userText.length < 2) {
            return;
        }
        
        // Hide empty state
        if (this.emptyState) {
            this.emptyState.style.display = 'none';
        }
        
        // Hide error
        this.hideError();
        
        // Render user message
        this.renderMessage('user', userText);
        
        // Clear input
        this.userInput.value = '';
        this.userInput.style.height = 'auto';
        
        // Disable send button
        this.sendBtn.disabled = true;
        this.loadingIndicator.classList.add('active');
        
        try {
            const token = window.auth.getToken();
            
            if (!token) {
                throw new Error('Not authenticated');
            }
            
            const response = await fetch(`${API_BASE}/api/tutor/chat`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    input: userText,
                    context: {
                        previous_turns: 3
                    }
                })
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.detail || 'Failed to get response');
            }
            
            // Store session ID
            if (data.session_id) {
                this.sessionId = data.session_id;
            }
            
            // Render assistant response
            this.renderMessage('assistant', data.content, data.provenance, data.confidence_score);
            
        } catch (error) {
            console.error('Chat error:', error);
            this.showError(error.message || 'Failed to send message. Please try again.');
        } finally {
            this.sendBtn.disabled = false;
            this.loadingIndicator.classList.remove('active');
            this.userInput.focus();
        }
    }
    
    renderMessage(role, content, provenance = [], confidenceScore = null) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;
        
        const bubbleDiv = document.createElement('div');
        bubbleDiv.className = 'message-bubble';
        bubbleDiv.textContent = content;
        
        messageDiv.appendChild(bubbleDiv);
        
        // Add metadata for assistant messages
        if (role === 'assistant') {
            const metaDiv = document.createElement('div');
            metaDiv.className = 'message-meta';
            
            // Confidence badge
            if (confidenceScore !== null) {
                const badge = document.createElement('span');
                badge.className = 'confidence-badge';
                
                if (confidenceScore >= 0.7) {
                    badge.classList.add('confidence-high');
                    badge.textContent = `✓ High confidence (${Math.round(confidenceScore * 100)}%)`;
                } else if (confidenceScore >= 0.4) {
                    badge.classList.add('confidence-medium');
                    badge.textContent = `⚠ Medium confidence (${Math.round(confidenceScore * 100)}%)`;
                } else {
                    badge.classList.add('confidence-low');
                    badge.textContent = `⚠ Low confidence (${Math.round(confidenceScore * 100)}%)`;
                }
                
                metaDiv.appendChild(badge);
            }
            
            messageDiv.appendChild(metaDiv);
            
            // Provenance
            if (provenance && provenance.length > 0) {
                const provenanceDiv = document.createElement('div');
                provenanceDiv.className = 'provenance';
                
                const title = document.createElement('div');
                title.className = 'provenance-title';
                title.textContent = '📚 Sources used:';
                provenanceDiv.appendChild(title);
                
                provenance.forEach(source => {
                    const item = document.createElement('div');
                    item.className = 'provenance-item';
                    item.innerHTML = `<strong>${this.escapeHtml(source.title || `${source.doc_type}:${source.doc_id}`)}</strong> (${Math.round(source.score * 100)}% match)`;
                    provenanceDiv.appendChild(item);
                });
                
                bubbleDiv.appendChild(provenanceDiv);
            }
        }
        
        this.messagesContainer.appendChild(messageDiv);
        
        // Scroll to bottom
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }
    
    showError(message) {
        this.errorMessage.textContent = message;
        this.errorMessage.classList.add('active');
        
        setTimeout(() => {
            this.hideError();
        }, 5000);
    }
    
    hideError() {
        this.errorMessage.classList.remove('active');
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize chat when DOM is ready
let tutorChat;
// ADD TO tutor-chat.js (at top of DOMContentLoaded)

document.addEventListener('DOMContentLoaded', () => {
    if (!window.auth.isAuthenticated()) {
        window.location.href = '/html/login.html';
        return;
    }
    
    tutorChat = new TutorChat();
    
    const initialQuery = sessionStorage.getItem('tutorInitialQuery');
    if (initialQuery) {
        sessionStorage.removeItem('tutorInitialQuery');
        tutorChat.userInput.value = initialQuery;
        setTimeout(() => {
            tutorChat.sendMessage();
        }, 500);
    }
    
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', (e) => {
            e.preventDefault();
            window.auth.logout();
        });
    }
});

document.addEventListener('DOMContentLoaded', () => {
    // Check authentication
    if (!window.auth.isAuthenticated()) {
        window.location.href = '/html/login.html';
        return;
    }
    
    tutorChat = new TutorChat();
    
    // Logout button
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', (e) => {
            e.preventDefault();
            window.auth.logout();
        });
    }
});

// Suggestion handler
function sendSuggestion(text) {
    if (tutorChat && tutorChat.userInput) {
        tutorChat.userInput.value = text;
        tutorChat.sendMessage();
    }
}
