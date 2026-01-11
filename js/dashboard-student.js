/**
 * dashboard-student.js
 * Student Dashboard Controller
 * Handles authentication, user greeting, and UI interactions
 */

// ============================================================================
// AUTHENTICATION & USER GREETING
// ============================================================================

(function initializeDashboard() {
    'use strict';
    
    /**
     * Verify authentication and redirect if needed
     * This runs BEFORE anything else
     */
    function checkAuthentication() {
        // Use auth.js requireAuth() method
        if (window.auth && typeof window.auth.requireAuth === 'function') {
            if (!window.auth.requireAuth()) {
                // User is not authenticated - requireAuth handles redirect
                return false;
            }
        } else {
            // Fallback: check token manually
            const token = localStorage.getItem('access_token');
            if (!token) {
                console.warn('No authentication token found. Redirecting to login...');
                window.location.href = './login.html';
                return false;
            }
        }
        return true;
    }
    
    /**
     * Load and display authenticated user's first name
     * Uses auth.js getUserFirstName() method
     */
    function loadUserGreeting() {
        const nameElement = document.getElementById('studentName');
        
        if (!nameElement) {
            console.error('Student name element (#studentName) not found');
            return;
        }
        
        // Get first name from auth.js
        let firstName = null;
        
        if (window.auth && typeof window.auth.getUserFirstName === 'function') {
            firstName = window.auth.getUserFirstName();
        }
        
        // Fallback: try getting full name and extract first name
        if (!firstName && window.auth && typeof window.auth.getUserName === 'function') {
            const fullName = window.auth.getUserName();
            if (fullName) {
                firstName = fullName.trim().split(' ')[0];
            }
        }
        
        // Display greeting
        if (firstName && firstName.trim().length > 0) {
            nameElement.textContent = `, ${firstName.trim()}`;
            nameElement.style.opacity = '0';
            
            // Smooth fade-in animation
            setTimeout(() => {
                nameElement.style.transition = 'opacity 0.3s ease-in';
                nameElement.style.opacity = '1';
            }, 50);
        } else {
            // No name available - leave blank
            nameElement.textContent = '';
            console.warn('User name not found in storage');
        }
    }
    
    /**
     * Initialize dashboard on page load
     */
    function init() {
        // Step 1: Verify authentication (redirects if not authenticated)
        if (!checkAuthentication()) {
            return; // Stop execution if not authenticated
        }
        
        // Step 2: Load user greeting
        loadUserGreeting();
    }
    
    // Run initialization
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
    
})();

// ============================================================================
// SIDEBAR TOGGLE FUNCTIONALITY
// ============================================================================

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const mainWrapper = document.getElementById('mainWrapper');
    const overlay = document.getElementById('sidebarOverlay');
    const hamburger = document.getElementById('hamburgerBtn');
    
    const isDesktop = window.innerWidth > 1024;
    
    if (isDesktop) {
        // Desktop: Toggle content shift
        mainWrapper.classList.toggle('shifted');
        sidebar.classList.toggle('open');
        hamburger.classList.toggle('active');
    } else {
        // Mobile: Toggle sidebar and overlay
        sidebar.classList.toggle('open');
        overlay.classList.toggle('active');
        hamburger.classList.toggle('active');
        
        // Prevent body scroll when sidebar is open
        if (sidebar.classList.contains('open')) {
            document.body.style.overflow = 'hidden';
        } else {
            document.body.style.overflow = '';
        }
    }
}

// Close sidebar when clicking overlay
document.addEventListener('DOMContentLoaded', () => {
    const overlay = document.getElementById('sidebarOverlay');
    if (overlay) {
        overlay.addEventListener('click', toggleSidebar);
    }
});

// Hamburger button click event
document.addEventListener('DOMContentLoaded', () => {
    const hamburger = document.getElementById('hamburgerBtn');
    if (hamburger) {
        hamburger.addEventListener('click', toggleSidebar);
    }
});

// Close sidebar on window resize if needed
let resizeTimer;
window.addEventListener('resize', function() {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function() {
        const sidebar = document.getElementById('sidebar');
        const mainWrapper = document.getElementById('mainWrapper');
        const overlay = document.getElementById('sidebarOverlay');
        const hamburger = document.getElementById('hamburgerBtn');
        const isDesktop = window.innerWidth > 1024;
        
        if (isDesktop) {
            // Reset mobile classes
            overlay.classList.remove('active');
            document.body.style.overflow = '';
        } else {
            // Reset desktop classes if sidebar is closed
            if (!sidebar.classList.contains('open')) {
                mainWrapper.classList.remove('shifted');
                hamburger.classList.remove('active');
            }
        }
    }, 250);
});

// Close sidebar on ESC key
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('sidebarOverlay');
        const hamburger = document.getElementById('hamburgerBtn');
        const mainWrapper = document.getElementById('mainWrapper');
        
        if (sidebar.classList.contains('open')) {
            sidebar.classList.remove('open');
            overlay.classList.remove('active');
            hamburger.classList.remove('active');
            mainWrapper.classList.remove('shifted');
            document.body.style.overflow = '';
        }
    }
});

// ============================================================================
// LOGOUT HANDLER
// ============================================================================

/**
 * Handle user logout using auth.js
 */
function handleLogout() {
    if (confirm('Are you sure you want to logout?')) {
        // Use auth.js logout method if available
        if (window.auth && typeof window.auth.logout === 'function') {
            window.auth.logout();
        } else {
            // Fallback: clear storage manually
            localStorage.clear();
            window.location.href = './login.html';
        }
    }
}

// ============================================================================
// PRIMARY ACTION CARD FUNCTIONS
// ============================================================================

function startStudying() {
    window.location.href = "start-studying.html";
}

function openCaseSimplifier() {
    window.location.href = "./case-simplifier.html";
}

function practiceAnswers() {
    window.location.href = "./answer-practice.html";
}

function openNotes() {
    window.location.href = "./my-notes.html";
}

// ============================================================================
// AI ASSISTANT FUNCTIONS
// ============================================================================

function askAI() {
    const query = document.getElementById('aiQuery').value;
    if (query.trim()) {
        console.log('AI Query:', query);
        alert('AI Query: ' + query + '\n\nThis would connect to an AI backend in production.');
        document.getElementById('aiQuery').value = '';
    }
}

function setQuery(element) {
    const query = element.textContent.trim().replace(/"/g, '');
    document.getElementById('aiQuery').value = query;
    document.getElementById('aiQuery').focus();
}

// Enter key support for AI input
document.addEventListener('DOMContentLoaded', () => {
    const aiQuery = document.getElementById('aiQuery');
    if (aiQuery) {
        aiQuery.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                askAI();
            }
        });
    }
});

// ============================================================================
// CHECKLIST TOGGLE FUNCTION
// ============================================================================

function toggleCheck(item) {
    const checkbox = item.querySelector('.checkbox');
    checkbox.classList.toggle('checked');
    item.classList.toggle('completed');
}

// ============================================================================
// RECENT ITEM CLICK HANDLER
// ============================================================================

function openItem(itemId) {
    console.log('Opening item:', itemId);
    alert('Opening: ' + itemId + '\n\nThis would navigate to the actual content in production.');
}

// ============================================================================
// PROGRESS BAR ANIMATION
// ============================================================================

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