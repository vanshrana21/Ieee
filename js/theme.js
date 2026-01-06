/**
 * theme.js
 * Global theme manager - MUST load FIRST in <head> with blocking script
 * Prevents flash of unstyled content (FOUC)
 */

(function() {
  'use strict';
  
  const THEME_KEY = 'legalai_theme';
  
  /**
   * Apply theme immediately to prevent flash
   */
  function applyTheme(theme) {
    if (theme === 'dark') {
      document.documentElement.classList.add('dark-mode');
    } else {
      document.documentElement.classList.remove('dark-mode');
    }
  }
  
  /**
   * Get saved theme or default to light
   */
  function getSavedTheme() {
    try {
      return localStorage.getItem(THEME_KEY) || 'light';
    } catch {
      return 'light';
    }
  }
  
  /**
   * Save theme preference
   */
  function saveTheme(theme) {
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch (e) {
      console.warn('Could not save theme preference:', e);
    }
  }
  
  // Apply theme IMMEDIATELY on script load (before DOM ready)
  applyTheme(getSavedTheme());
  
  /**
   * Public API exposed to window
   */
  window.ThemeManager = {
    /**
     * Get current theme
     */
    getTheme: function() {
      return getSavedTheme();
    },
    
    /**
     * Set theme (light or dark)
     */
    setTheme: function(theme) {
      if (theme !== 'light' && theme !== 'dark') {
        console.error('Invalid theme:', theme);
        return;
      }
      saveTheme(theme);
      applyTheme(theme);
      
      // Dispatch custom event for components that need to react
      window.dispatchEvent(new CustomEvent('themechange', { 
        detail: { theme: theme } 
      }));
    },
    
    /**
     * Toggle between light and dark
     */
    toggleTheme: function() {
      const current = this.getTheme();
      const newTheme = current === 'dark' ? 'light' : 'dark';
      this.setTheme(newTheme);
      return newTheme;
    },
    
    /**
     * Check if dark mode is active
     */
    isDarkMode: function() {
      return this.getTheme() === 'dark';
    }
  };
  
  // Also expose legacy API for backward compatibility
  window.ThemeUtils = window.ThemeManager;
  
})();