/**
 * role-guard.js
 * Phase 2: Role Separation & Routing Sanity
 * 
 * PURPOSE:
 * - Enforce role-based access control on frontend
 * - Prevent students from accessing lawyer pages
 * - Prevent lawyers from accessing student pages
 * - Redirect mismatched users to their correct dashboard
 * 
 * RULES:
 * - A student should NEVER see lawyer UI
 * - A lawyer should NEVER see student UI
 * - Direct URL tampering must fail safely
 */

(function() {
    'use strict';

    const ROLE_KEY = 'user_role';
    const TOKEN_KEY = 'access_token';

    const STUDENT_PAGES = [
        'dashboard-student.html',
        'settings-student.html',
        'start-studying.html',
        'module-content.html',
        'practice-content.html',
        'answer-writing.html',
        'my-notes.html',
        'benchmark.html',
        'onboarding.html',
        'tutor.html'
    ];

    const LAWYER_PAGES = [
        'dashboard-lawyer.html',
        'dashboard.html',
        'settings-lawyer.html',
        'settings.html'
    ];

    const SHARED_PAGES = [
        'login.html',
        'signup.html',
        'case-simplifier.html',
        'index.html'
    ];

    const ROLE_DASHBOARDS = {
        student: '/html/dashboard-student.html',
        lawyer: '/html/dashboard-lawyer.html'
    };

    const ROLE_SETTINGS = {
        student: '/html/settings-student.html',
        lawyer: '/html/settings-lawyer.html'
    };

    function getToken() {
        try {
            return localStorage.getItem(TOKEN_KEY);
        } catch (e) {
            return null;
        }
    }

    function getUserRole() {
        try {
            return localStorage.getItem(ROLE_KEY);
        } catch (e) {
            return null;
        }
    }

    function isAuthenticated() {
        return !!getToken();
    }

    function getCurrentPage() {
        const path = window.location.pathname;
        const page = path.split('/').pop() || 'index.html';
        return page.toLowerCase();
    }

    function isStudentPage(page) {
        return STUDENT_PAGES.some(p => page.includes(p.toLowerCase()));
    }

    function isLawyerPage(page) {
        return LAWYER_PAGES.some(p => page.includes(p.toLowerCase()));
    }

    function isSharedPage(page) {
        return SHARED_PAGES.some(p => page.includes(p.toLowerCase()));
    }

    function isAuthPage(page) {
        return page.includes('login.html') || page.includes('signup.html');
    }

    function redirectTo(url) {
        if (window.location.pathname !== url) {
            window.location.href = url;
        }
    }

    function getDashboardForRole(role) {
        return ROLE_DASHBOARDS[role] || ROLE_DASHBOARDS.student;
    }

    function getSettingsForRole(role) {
        return ROLE_SETTINGS[role] || ROLE_SETTINGS.student;
    }

    function validateAccess() {
        const currentPage = getCurrentPage();
        const role = getUserRole();
        const authenticated = isAuthenticated();

        if (isAuthPage(currentPage)) {
            if (authenticated) {
                redirectTo(getDashboardForRole(role));
                return false;
            }
            return true;
        }

        if (!authenticated && !isSharedPage(currentPage)) {
            redirectTo('/html/login.html');
            return false;
        }

        if (!authenticated) {
            return true;
        }

        if (isSharedPage(currentPage)) {
            return true;
        }

        if (currentPage === 'settings.html') {
            redirectTo(getSettingsForRole(role));
            return false;
        }

        if (role === 'student' && isLawyerPage(currentPage)) {
            console.warn('[RoleGuard] Student attempted to access lawyer page:', currentPage);
            redirectTo(ROLE_DASHBOARDS.student);
            return false;
        }

        if (role === 'lawyer' && isStudentPage(currentPage)) {
            console.warn('[RoleGuard] Lawyer attempted to access student page:', currentPage);
            redirectTo(ROLE_DASHBOARDS.lawyer);
            return false;
        }

        return true;
    }

    function requireRole(allowedRole) {
        const role = getUserRole();
        
        if (!isAuthenticated()) {
            redirectTo('/html/login.html');
            return false;
        }

        if (role !== allowedRole) {
            console.warn(`[RoleGuard] Role mismatch: expected ${allowedRole}, got ${role}`);
            redirectTo(getDashboardForRole(role));
            return false;
        }

        return true;
    }

    function requireStudent() {
        return requireRole('student');
    }

    function requireLawyer() {
        return requireRole('lawyer');
    }

    function updateSidebarForRole() {
        const role = getUserRole();
        const sidebar = document.getElementById('sidebar');
        
        if (!sidebar) return;

        const settingsLink = sidebar.querySelector('a[href*="settings"]');
        if (settingsLink) {
            settingsLink.href = getSettingsForRole(role);
        }

        const dashboardLink = sidebar.querySelector('a[href*="dashboard"]');
        if (dashboardLink) {
            dashboardLink.href = getDashboardForRole(role);
        }

        if (role === 'student') {
            sidebar.querySelectorAll('[data-role="lawyer"]').forEach(el => {
                el.style.display = 'none';
            });
        } else if (role === 'lawyer') {
            sidebar.querySelectorAll('[data-role="student"]').forEach(el => {
                el.style.display = 'none';
            });
        }
    }

    function init() {
        const accessAllowed = validateAccess();
        
        if (accessAllowed) {
            updateSidebarForRole();
        }
        
        return accessAllowed;
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.JurisRoleGuard = {
        validateAccess,
        requireRole,
        requireStudent,
        requireLawyer,
        getUserRole,
        isAuthenticated,
        getDashboardForRole,
        getSettingsForRole,
        updateSidebarForRole,
        
        STUDENT_PAGES,
        LAWYER_PAGES,
        SHARED_PAGES
    };

})();
