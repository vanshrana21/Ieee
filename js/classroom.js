/**
 * Classroom Mode JavaScript
 * Handles session creation, joining, and real-time updates
 */

// Configuration
const TOKEN_KEY = 'access_token';

// State
let currentSession = null;
let currentUser = null;
let isTeacher = false;
let timerInterval = null;

// DOM Elements
const createSessionForm = document.getElementById('create-session-form');
const joinSessionForm = document.getElementById('join-session-form');
const sessionCodeInput = document.getElementById('session-code-input');
const createBtn = document.getElementById('create-session-btn');
const joinBtn = document.getElementById('join-session-btn');
const sessionInfo = document.getElementById('session-info');
const sessionCodeDisplay = document.getElementById('session-code');
const sessionStatus = document.getElementById('session-status');
const participantsList = document.getElementById('participants-list');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    console.log('[API] Request: Initialize classroom');
    
    // Check if user is logged in
    const token = localStorage.getItem(TOKEN_KEY);
    
    if (!token) {
        console.error('[API ERROR] No token found, redirecting to login');
        window.location.href = '/html/login.html';
        return;
    }
    
    // Get user info from localStorage
    const userInfo = localStorage.getItem('user_info');
    
    currentUser = JSON.parse(userInfo || '{}');
    
    isTeacher = currentUser.role === 'teacher' || currentUser.role === 'faculty';
    
    // Show appropriate form
    if (isTeacher) {
        console.log('[INIT] Showing teacher form');
        createSessionForm.style.display = 'block';
    } else {
        console.log('[INIT] Showing student form');
        joinSessionForm.style.display = 'block';
    }
});

// Create Session
async function createSession() {
    const topic = document.getElementById('session-topic').value.trim();
    const category = document.getElementById('session-category').value;
    const maxParticipants = parseInt(document.getElementById('max-participants').value) || 40;
    
    if (!topic) {
        alert('Please enter a session topic');
        return;
    }
    
    createBtn.disabled = true;
    createBtn.textContent = 'Creating...';
    
    try {
        const data = await window.apiRequest('/api/classroom/sessions', {
            method: 'POST',
            body: JSON.stringify({
                topic: topic,
                category: category,
                max_participants: maxParticipants,
                prep_time_minutes: 15,
                oral_time_minutes: 10,
                ai_judge_mode: 'hybrid'
            })
        });
        
        if (data) {
            currentSession = data;
            sessionCodeDisplay.textContent = data.session_code;
            sessionStatus.textContent = 'Session Created';
            sessionInfo.style.display = 'block';
            createSessionForm.style.display = 'none';
            
            // Start polling for updates
            pollSessionUpdates();
        }
    } catch (error) {
        // Show exact backend error message
        let errorMessage = 'Failed to create session';
        if (error.message) {
            errorMessage = error.message;
        }
        
        alert(errorMessage);
        console.error('[CREATE] Network error:', error);
        alert(`Network error: ${error.message}. Please check your connection and try again.`);
    } finally {
        createBtn.disabled = false;
        createBtn.textContent = 'Create Session';
    }
}

// Join Session
async function joinSession() {
    const sessionCode = sessionCodeInput.value.trim().toUpperCase();
    
    if (!sessionCode) {
        alert('Please enter a session code');
        return;
    }
    
    if (!sessionCode.match(/^JURIS-[A-Z0-9]{6}$/)) {
        alert('Invalid session code format. Expected: JURIS-XXXXXX');
        return;
    }
    
    joinBtn.disabled = true;
    joinBtn.textContent = 'Joining...';
    
    try {
        const data = await window.apiRequest('/api/classroom/sessions/join', {
            method: 'POST',
            body: JSON.stringify({ session_code: sessionCode })
        });
        
        if (data) {
            currentSession = data;
            sessionCodeDisplay.textContent = data.session_code;
            sessionStatus.textContent = 'Joined Session';
            sessionInfo.style.display = 'block';
            joinSessionForm.style.display = 'none';
            
            // Start polling for updates
            pollSessionUpdates();
        }
    } catch (error) {
        alert(error.message || 'Failed to join session');
    } finally {
        joinBtn.disabled = false;
        joinBtn.textContent = 'Join Session';
    }
}

// Poll for session updates
async function pollSessionUpdates() {
    if (!currentSession || !currentSession.id) return;
    
    try {
        const data = await window.apiRequest(`/api/classroom/sessions/${currentSession.id}`);
        
        if (data) {
            updateSessionUI(data);
        }
    } catch (error) {
        console.error('[API ERROR] Failed to poll session updates:', error);
    }
}

// Update session display
function updateSessionUI(session) {
    currentSession = session;
    sessionStatus.textContent = `Status: ${session.current_state}`;
    
    if (session.participants) {
        participantsList.innerHTML = session.participants.map(p => 
            `<li>${p.user_name || p.user_email} (${p.role})</li>`
        ).join('');
    }
    
    // Poll every 5 seconds
    setTimeout(pollSessionUpdates, 5000);
}

// Event Listeners
createBtn?.addEventListener('click', createSession);
joinBtn?.addEventListener('click', joinSession);

// Allow Enter key to submit
sessionCodeInput?.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') joinSession();
});

document.getElementById('session-topic')?.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') createSession();
});

// Debug functions
window.debugClassroom = {
    getSession: () => currentSession,
    getUser: () => currentUser,
    poll: pollSessionUpdates
};
