if (!window.auth.requireAuth()) {
    window.location.href = './login.html';
}

const role = window.auth.getRole();
if (role !== 'student') {
    console.warn('Non-student trying to access student dashboard');
    window.auth.redirectToDashboard(role);
}

const navItems = document.querySelectorAll('.nav-item');
if (item.hasAttribute('data-action') && item.getAttribute('data-action') === 'start-studying') {
    e.preventDefault();
    window.location.href = 'start-studying.html';
    return;
}
navItems.forEach(item => {
    item.addEventListener('click', (e) => {
        if (!item.hasAttribute('data-logout')) {
            e.preventDefault();
            
            navItems.forEach(nav => nav.classList.remove('active'));
            item.classList.add('active');
            
            const page = item.getAttribute('data-page');
            console.log('Navigating to:', page);
        }
    });
});

function startStudying() {
    console.log('Starting study session...');
}

function openCaseSimplifier() {
    console.log('Opening Case Simplifier...');
}

function practiceAnswers() {
    console.log('Opening Answer Practice...');
}

function openNotes() {
    console.log('Opening Notes...');
}

function askAI() {
    const query = document.getElementById('aiQuery').value;
    if (query.trim()) {
        console.log('AI Query:', query);
        document.getElementById('aiQuery').value = '';
    }
}

function setQuery(element) {
    const query = element.textContent.trim().replace(/"/g, '');
    document.getElementById('aiQuery').value = query;
    document.getElementById('aiQuery').focus();
}

document.getElementById('aiQuery').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        askAI();
    }
});

function toggleCheck(item) {
    const checkbox = item.querySelector('.checkbox');
    checkbox.classList.toggle('checked');
    item.classList.toggle('completed');
}

function openItem(itemId) {
    console.log('Opening item:', itemId);
}

window.addEventListener('load', function() {
    const progressBars = document.querySelectorAll('.progress-fill');
    progressBars.forEach(bar => {
        const width = bar.style.width;
        bar.style.width = '0%';
        setTimeout(() => {
            bar.style.width = width;
        }, 100);
    });
});

try {
    const userData = window.auth.getCurrentUser();
    if (userData && userData.name) {
        document.getElementById('studentName').textContent = userData.name;
    }
} catch (e) {
    console.log('Using placeholder student name');
}
function handleStartStudying() {
    window.location.href = 'start-studying.html';
}

document.addEventListener('DOMContentLoaded', function() {
    const startStudyingButtons = document.querySelectorAll('[data-action="start-studying"]');
    
    startStudyingButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            handleStartStudying();
        });
    });
});