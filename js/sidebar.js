/**
 * sidebar.js
 * Phase 1: Navigation Shell - Collapsible Sidebar Controller
 * 
 * Features:
 * - Collapsible sidebar (expanded/collapsed)
 * - State persistence via localStorage
 * - Responsive behavior (mobile overlay, desktop collapse)
 * - Smooth transitions
 * - Keyboard accessibility
 */

(function() {
    'use strict';

    const STORAGE_KEY = 'juris_sidebar_collapsed';
    const MOBILE_BREAKPOINT = 1024;

    let sidebar = null;
    let overlay = null;
    let menuToggle = null;
    let mainContent = null;
    let isCollapsed = false;
    let isMobile = false;

    function init() {
        sidebar = document.getElementById('sidebar');
        overlay = document.getElementById('sidebarOverlay');
        menuToggle = document.getElementById('menuToggle');
        mainContent = document.querySelector('.main-content');

        if (!sidebar) {
            console.warn('[Sidebar] Sidebar element not found');
            return;
        }

        isMobile = window.innerWidth < MOBILE_BREAKPOINT;
        
        if (!isMobile) {
            isCollapsed = loadState();
        } else {
            isCollapsed = true;
        }
        
        applyState(false);
        bindEvents();
        updateActiveNavItem();
    }

    function loadState() {
        try {
            const saved = localStorage.getItem(STORAGE_KEY);
            return saved === 'true';
        } catch (e) {
            return false;
        }
    }

    function saveState(collapsed) {
        try {
            localStorage.setItem(STORAGE_KEY, collapsed.toString());
        } catch (e) {
        }
    }

    function applyState(animate = true) {
        if (!sidebar) return;

        if (!animate) {
            sidebar.style.transition = 'none';
            if (mainContent) mainContent.style.transition = 'none';
        }

        if (isMobile) {
            sidebar.classList.remove('collapsed');
            document.body.classList.remove('sidebar-collapsed');
            
            if (isCollapsed) {
                sidebar.classList.remove('open');
                if (overlay) overlay.classList.remove('active');
                document.body.style.overflow = '';
            } else {
                sidebar.classList.add('open');
                if (overlay) overlay.classList.add('active');
                document.body.style.overflow = 'hidden';
            }
        } else {
            sidebar.classList.remove('open');
            if (overlay) overlay.classList.remove('active');
            document.body.style.overflow = '';
            
            if (isCollapsed) {
                sidebar.classList.add('collapsed');
                document.body.classList.add('sidebar-collapsed');
            } else {
                sidebar.classList.remove('collapsed');
                document.body.classList.remove('sidebar-collapsed');
            }
        }

        if (!animate) {
            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    sidebar.style.transition = '';
                    if (mainContent) mainContent.style.transition = '';
                });
            });
        }
    }

    function toggle() {
        isCollapsed = !isCollapsed;
        
        if (!isMobile) {
            saveState(isCollapsed);
        }
        
        applyState(true);
    }

    function open() {
        if (isCollapsed) {
            isCollapsed = false;
            if (!isMobile) saveState(isCollapsed);
            applyState(true);
        }
    }

    function close() {
        if (!isCollapsed) {
            isCollapsed = true;
            if (!isMobile) saveState(isCollapsed);
            applyState(true);
        }
    }

    function bindEvents() {
        if (menuToggle) {
            menuToggle.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                toggle();
            });
        }

        if (overlay) {
            overlay.addEventListener('click', function() {
                if (isMobile && !isCollapsed) {
                    close();
                }
            });
        }

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && isMobile && !isCollapsed) {
                close();
            }
        });

        let resizeTimeout;
        window.addEventListener('resize', function() {
            clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(function() {
                const wasMobile = isMobile;
                isMobile = window.innerWidth < MOBILE_BREAKPOINT;
                
                if (wasMobile !== isMobile) {
                    if (isMobile) {
                        isCollapsed = true;
                    } else {
                        isCollapsed = loadState();
                    }
                    applyState(false);
                }
            }, 100);
        });

        const navItems = sidebar.querySelectorAll('.nav-item');
        navItems.forEach(function(item) {
            item.addEventListener('click', function() {
                if (isMobile) {
                    close();
                }
            });
        });
    }

    function updateActiveNavItem() {
        if (!sidebar) return;

        const currentPath = window.location.pathname;
        const currentPage = currentPath.split('/').pop() || 'index.html';
        
        const navItems = sidebar.querySelectorAll('.nav-item');
        navItems.forEach(function(item) {
            const href = item.getAttribute('href');
            if (!href) return;
            
            const linkPage = href.split('/').pop();
            
            item.classList.remove('active');
            
            if (linkPage === currentPage || 
                (currentPage === '' && linkPage === 'index.html') ||
                (currentPage === 'dashboard-student.html' && linkPage === 'dashboard-student.html')) {
                item.classList.add('active');
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.JurisSidebar = {
        toggle: toggle,
        open: open,
        close: close,
        isCollapsed: function() { return isCollapsed; },
        isMobile: function() { return isMobile; }
    };

})();
