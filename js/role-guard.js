/**
 * role-guard.js
 * PHASE 1: Role & Permission Freeze - Frontend Role Guard
 * 
 * PURPOSE:
 * - Enforce role-based access control on frontend
 * - Prevent students from accessing teacher pages
 * - Prevent teachers from accessing student pages
 * - Redirect mismatched users to their correct dashboard
 * 
 * RULES:
 * - A student should NEVER see teacher UI
 * - A teacher should NEVER see student UI
 * - Direct URL tampering must fail safely
 * 
 * SUPPORTED ROLES: teacher, student (ONLY)
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

    const TEACHER_PAGES = [
        'faculty-dashboard.html',
        'faculty-project.html',
        'classroom-create-session.html',
        'classroom-control-panel.html',
        'institution-setup.html',
        'settings.html'
    ];

    const SHARED_PAGES = [
        'login.html',
        'signup.html',
        'case-simplifier.html',
        'index.html'
    ];

    const ROLE_DASHBOARDS = {
        teacher: '/html/faculty-dashboard.html',
        student: '/html/dashboard-student.html'
    };

    const ROLE_SETTINGS = {
        teacher: '/html/settings.html',
        student: '/html/settings-student.html'
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

    function isTeacherPage(page) {
        return TEACHER_PAGES.some(p => page.includes(p.toLowerCase()));
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

        if (role === 'student' && isTeacherPage(currentPage)) {
            console.warn('[RoleGuard] Student attempted to access teacher page:', currentPage);
            redirectTo(ROLE_DASHBOARDS.student);
            return false;
        }

        if (role === 'teacher' && isStudentPage(currentPage)) {
            console.warn('[RoleGuard] Teacher attempted to access student page:', currentPage);
            redirectTo(ROLE_DASHBOARDS.teacher);
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

    function requireTeacher() {
        return requireRole('teacher');
    }

    // DEPRECATED: Use requireTeacher instead
    function requireLawyer() {
        console.warn('[RoleGuard] requireLawyer() is deprecated. Use requireTeacher() instead.');
        return requireTeacher();
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
            sidebar.querySelectorAll('[data-role="teacher"]').forEach(el => {
                el.style.display = 'none';
            });
        } else if (role === 'teacher') {
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
        requireTeacher,
        getUserRole,
        isAuthenticated,
        getDashboardForRole,
        getSettingsForRole,
        updateSidebarForRole,
        
        STUDENT_PAGES,
        TEACHER_PAGES,
        SHARED_PAGES
    };

})();
