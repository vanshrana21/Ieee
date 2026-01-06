// storage.js
window.Storage = {
  getSavedCases() {
    try {
      const saved = localStorage.getItem('saved_cases');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  },

  addSavedCase(caseItem) {
    const saved = this.getSavedCases();
    if (!saved.some(c => c.id === caseItem.id)) {
      saved.push(caseItem);
      localStorage.setItem('saved_cases', JSON.stringify(saved));
    }
  },

  removeSavedCase(caseId) {
    const saved = this.getSavedCases().filter(c => c.id !== caseId);
    localStorage.setItem('saved_cases', JSON.stringify(saved));
  },

  getSearchHistory() {
    try {
      return JSON.parse(localStorage.getItem('search_history')) || [];
    } catch {
      return [];
    }
  },

  isDemoMode() {
    return localStorage.getItem('user_mode') === 'demo';
  }
};
