/**
 * storage-service.js
 * Centralized localStorage management for LegalAI Research
 * Handles all browser storage operations with error handling
 */

const STORAGE_KEYS = {
    ACCESS_TOKEN: 'legalai_access_token',
    USER_ROLE: 'legalai_user_role',
    USER_NAME: 'legalai_user_name',
    USER_EMAIL: 'legalai_user_email'
};

const StorageService = {
    /**
     * Set item in localStorage with error handling
     */
    setItem(key, value) {
        try {
            if (value === null || value === undefined) {
                console.warn(`Attempted to store null/undefined for key: ${key}`);
                return false;
            }
            localStorage.setItem(key, value);
            return true;
        } catch (error) {
            console.error(`Failed to store ${key}:`, error);
            return false;
        }
    },

    /**
     * Get item from localStorage with error handling
     */
    getItem(key) {
        try {
            return localStorage.getItem(key);
        } catch (error) {
            console.error(`Failed to retrieve ${key}:`, error);
            return null;
        }
    },

    /**
     * Remove item from localStorage
     */
    removeItem(key) {
        try {
            localStorage.removeItem(key);
            return true;
        } catch (error) {
            console.error(`Failed to remove ${key}:`, error);
            return false;
        }
    },

    /**
     * Clear all auth-related data
     */
    clearAuthData() {
        try {
            Object.values(STORAGE_KEYS).forEach(key => {
                localStorage.removeItem(key);
            });
            return true;
        } catch (error) {
            console.error('Failed to clear auth data:', error);
            return false;
        }
    },

    /**
     * Store user profile data
     */
    setUserProfile(name, email, role) {
        const results = {
            name: this.setItem(STORAGE_KEYS.USER_NAME, name?.trim() || ''),
            email: this.setItem(STORAGE_KEYS.USER_EMAIL, email?.trim() || ''),
            role: this.setItem(STORAGE_KEYS.USER_ROLE, role?.trim() || '')
        };
        return results.name && results.email && results.role;
    },

    /**
     * Get user profile data
     */
    getUserProfile() {
        return {
            name: this.getItem(STORAGE_KEYS.USER_NAME),
            email: this.getItem(STORAGE_KEYS.USER_EMAIL),
            role: this.getItem(STORAGE_KEYS.USER_ROLE)
        };
    },

    /**
     * Get user's first name (for greetings)
     */
    getUserFirstName() {
        const fullName = this.getItem(STORAGE_KEYS.USER_NAME);
        if (!fullName) return null;
        
        // Extract first name (before first space)
        const firstName = fullName.trim().split(' ')[0];
        return firstName || null;
    }
};

// Make available globally
window.StorageService = StorageService;
window.STORAGE_KEYS = STORAGE_KEYS;