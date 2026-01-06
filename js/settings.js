/**
 * settings.js
 * Settings page controller with theme management
 */

/* =========================
   THEME TOGGLE MANAGER
========================= */
const ThemeToggle = {
  init() {
    const themeToggle = document.getElementById('theme-toggle');
    const themeStatusText = document.getElementById('theme-status-text');
    const themeIcon = document.querySelector('.settings-theme-status .theme-icon');
    
    if (!themeToggle || !themeStatusText) {
      console.warn('Theme toggle elements not found');
      return;
    }

    // Set initial state from ThemeManager
    const currentTheme = window.ThemeManager.getTheme();
    themeToggle.checked = (currentTheme === 'dark');
    this.updateUI(themeStatusText, themeIcon, currentTheme);

    // Handle toggle change
    themeToggle.addEventListener('change', (e) => {
      const newTheme = e.target.checked ? 'dark' : 'light';
      window.ThemeManager.setTheme(newTheme);
      this.updateUI(themeStatusText, themeIcon, newTheme);
      this.showNotification(`Switched to ${newTheme} mode`);
    });
  },

  updateUI(statusElement, iconElement, theme) {
    // Update status text
    statusElement.textContent = theme === 'dark' ? 'Dark Mode' : 'Light Mode';
    
    // Update icon (sun for light, moon for dark)
    if (iconElement) {
      if (theme === 'dark') {
        iconElement.innerHTML = `
          <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>
        `;
      } else {
        iconElement.innerHTML = `
          <circle cx="12" cy="12" r="5"/>
          <line x1="12" y1="1" x2="12" y2="3"/>
          <line x1="12" y1="21" x2="12" y2="23"/>
          <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
          <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
          <line x1="1" y1="12" x2="3" y2="12"/>
          <line x1="21" y1="12" x2="23" y2="12"/>
          <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
          <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
        `;
      }
    }
  },

  showNotification(message) {
    const notification = document.createElement('div');
    notification.style.cssText = `
      position: fixed;
      top: 80px;
      right: 20px;
      background-color: var(--color-primary);
      color: var(--color-text-inverse);
      padding: 1rem 1.5rem;
      border-radius: 8px;
      box-shadow: var(--shadow-lg);
      z-index: 10000;
      font-size: 0.875rem;
      font-weight: 500;
      animation: slideIn 0.3s ease-out;
    `;
    notification.textContent = message;
    
    // Add animation
    const style = document.createElement('style');
    style.textContent = `
      @keyframes slideIn {
        from {
          transform: translateX(400px);
          opacity: 0;
        }
        to {
          transform: translateX(0);
          opacity: 1;
        }
      }
    `;
    document.head.appendChild(style);
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
      notification.style.transition = 'opacity 0.3s ease-out, transform 0.3s ease-out';
      notification.style.opacity = '0';
      notification.style.transform = 'translateX(400px)';
      setTimeout(() => {
        notification.remove();
        style.remove();
      }, 300);
    }, 3000);
  }
};

/* =========================
   LANGUAGE MANAGER
========================= */
const LanguageManager = {
  LANGUAGE_KEY: 'user_language',

  init() {
    const languageSelect = document.getElementById('language-select');
    
    if (!languageSelect) return;

    // Load saved language
    const savedLanguage = this.getLanguage();
    languageSelect.value = savedLanguage;

    // Handle language change
    languageSelect.addEventListener('change', (e) => {
      const newLanguage = e.target.value;
      this.setLanguage(newLanguage);
      this.showNotification(`Language changed to ${this.getLanguageName(newLanguage)}`);
    });
  },

  getLanguage() {
    return localStorage.getItem(this.LANGUAGE_KEY) || 'en';
  },

  setLanguage(language) {
    localStorage.setItem(this.LANGUAGE_KEY, language);
  },

  getLanguageName(code) {
    const names = {
      'en': 'English',
      'hi': 'हिन्दी (Hindi)'
    };
    return names[code] || code;
  },

  showNotification(message) {
    const notification = document.createElement('div');
    notification.style.cssText = `
      position: fixed;
      top: 80px;
      right: 20px;
      background-color: var(--color-primary);
      color: white;
      padding: 1rem 1.5rem;
      border-radius: 8px;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
      z-index: 10000;
      font-size: 0.875rem;
      font-weight: 500;
    `;
    notification.textContent = message;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
      notification.style.transition = 'opacity 0.3s ease-out';
      notification.style.opacity = '0';
      setTimeout(() => notification.remove(), 300);
    }, 3000);
  }
};

/* =========================
   2FA MANAGER
========================= */
const TwoFactorManager = {
  TWO_FA_KEY: 'user_2fa_enabled',

  init() {
    const twoFAToggle = document.getElementById('2fa-toggle');
    
    if (!twoFAToggle) return;

    // Load saved 2FA status
    const saved2FA = this.get2FAStatus();
    twoFAToggle.checked = saved2FA;

    // Handle toggle change
    twoFAToggle.addEventListener('change', (e) => {
      const enabled = e.target.checked;
      this.set2FAStatus(enabled);
      
      const message = enabled ? '2FA enabled (UI demo only)' : '2FA disabled';
      this.showNotification(message);
    });
  },

  get2FAStatus() {
    return localStorage.getItem(this.TWO_FA_KEY) === 'true';
  },

  set2FAStatus(enabled) {
    localStorage.setItem(this.TWO_FA_KEY, enabled.toString());
  },

  showNotification(message) {
    const notification = document.createElement('div');
    notification.style.cssText = `
      position: fixed;
      top: 80px;
      right: 20px;
      background-color: var(--color-accent);
      color: var(--color-primary-dark);
      padding: 1rem 1.5rem;
      border-radius: 8px;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
      z-index: 10000;
      font-size: 0.875rem;
      font-weight: 600;
    `;
    notification.textContent = message;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
      notification.style.transition = 'opacity 0.3s ease-out';
      notification.style.opacity = '0';
      setTimeout(() => notification.remove(), 300);
    }, 3000);
  }
};

/* =========================
   LOGOUT MANAGER
========================= */
const LogoutManager = {
  init() {
    const logoutBtn = document.getElementById('logout-btn');

    if (logoutBtn) {
      logoutBtn.addEventListener('click', (e) => {
        e.preventDefault();
        this.handleLogout();
      });
    }
  },

  handleLogout() {
    const confirmed = confirm('Are you sure you want to logout?');
    
    if (confirmed) {
      // Clear user data but preserve theme preference
      const currentTheme = window.ThemeUtils.getTheme();
      
      // Clear other localStorage items
      localStorage.removeItem('saved_cases');
      localStorage.removeItem('search_history');
      localStorage.removeItem('user_mode');
      localStorage.removeItem('user_2fa_enabled');
      localStorage.removeItem('user_language');
      
      // Keep theme
      window.ThemeUtils.setTheme(currentTheme);
      
      // Show logout message
      this.showLogoutMessage();
      
      // Redirect after brief delay
      setTimeout(() => {
        window.location.href = 'login.html';
      }, 1000);
    }
  },

  showLogoutMessage() {
    const notification = document.createElement('div');
    notification.style.cssText = `
      position: fixed;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      background-color: white;
      color: var(--color-primary);
      padding: 2rem 3rem;
      border-radius: 12px;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
      z-index: 10000;
      font-size: 1rem;
      font-weight: 600;
      text-align: center;
    `;
    notification.textContent = 'Logging out...';
    
    document.body.appendChild(notification);
  }
};

/* =========================
   SIDEBAR TOGGLE
========================= */

const SidebarManager = {
  init() {
    const toggle = document.querySelector('.sidebar-toggle');
    const sidebar = document.querySelector('.dashboard-sidebar');
    const layout = document.querySelector('.dashboard-layout');

    if (!toggle || !sidebar || !layout) return;

    const applyState = (collapsed) => {
      sidebar.style.width = collapsed ? '0' : '280px';
      sidebar.style.overflow = collapsed ? 'hidden' : '';
      layout.classList.toggle('sidebar-collapsed', collapsed);
      localStorage.setItem('sidebar-collapsed', collapsed);
    };

    const saved = localStorage.getItem('sidebar-collapsed') === 'true';
    applyState(saved);

    toggle.addEventListener('click', () => {
      const isCollapsed = sidebar.style.width === '0px';
      applyState(!isCollapsed);
    });
  }
};

/* =========================
   INITIALIZE ALL
========================= */
document.addEventListener('DOMContentLoaded', () => {
  console.log('Settings page initializing...');
  
  // Initialize all managers
  ThemeToggle.init();
  LanguageManager.init();
  TwoFactorManager.init();
  LogoutManager.init();
  SidebarManager.init();
  
  console.log('Settings page initialized successfully');
});