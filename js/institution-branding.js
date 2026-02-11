/**
 * js/institution-branding.js
 * Phase 6: Dynamic institution branding controller
 * Fetches and applies institution branding to all pages
 */

class InstitutionBranding {
    constructor() {
        this.baseUrl = 'http://localhost:8000/api';
        this.branding = null;
        this.cacheKey = 'institution_branding';
        this.cacheExpiry = 3600000; // 1 hour
        
        this.init();
    }

    init() {
        // Auto-detect institution and apply branding
        const institutionCode = this.detectInstitutionFromURL();
        if (institutionCode) {
            this.fetchAndApplyBranding(institutionCode);
        }
    }

    detectInstitutionFromURL() {
        // Check subdomain (e.g., nlsiu.juris.ai)
        const hostname = window.location.hostname;
        const subdomainMatch = hostname.match(/^([a-z0-9-]+)\.juris\.ai$/i);
        if (subdomainMatch) {
            return subdomainMatch[1].toLowerCase();
        }
        
        // Check query param (e.g., ?institution=nlsiu)
        const urlParams = new URLSearchParams(window.location.search);
        const institution = urlParams.get('institution');
        if (institution) {
            return institution.toLowerCase();
        }
        
        // Check localStorage for previously viewed institution
        const cached = localStorage.getItem(this.cacheKey);
        if (cached) {
            try {
                const data = JSON.parse(cached);
                if (data.code) {
                    return data.code.toLowerCase();
                }
            } catch (e) {
                console.error('Error parsing cached branding:', e);
            }
        }
        
        return null;
    }

    async fetchBranding(institutionCode) {
        // Check cache first
        const cached = this.getCachedBranding(institutionCode);
        if (cached) {
            return cached;
        }
        
        try {
            const response = await fetch(
                `${this.baseUrl}/institutions/${institutionCode}/branding`
            );
            
            if (response.ok) {
                const data = await response.json();
                this.cacheBranding(institutionCode, data);
                return data;
            }
        } catch (error) {
            console.error('Error fetching institution branding:', error);
        }
        
        return null;
    }

    getCachedBranding(institutionCode) {
        try {
            const cached = localStorage.getItem(`${this.cacheKey}_${institutionCode}`);
            if (cached) {
                const data = JSON.parse(cached);
                if (data.timestamp && (Date.now() - data.timestamp) < this.cacheExpiry) {
                    return data.branding;
                }
            }
        } catch (e) {
            console.error('Error reading cached branding:', e);
        }
        return null;
    }

    cacheBranding(institutionCode, branding) {
        try {
            const data = {
                branding: branding,
                timestamp: Date.now()
            };
            localStorage.setItem(`${this.cacheKey}_${institutionCode}`, JSON.stringify(data));
            localStorage.setItem(this.cacheKey, JSON.stringify({ code: institutionCode }));
        } catch (e) {
            console.error('Error caching branding:', e);
        }
    }

    async fetchAndApplyBranding(institutionCode) {
        const branding = await this.fetchBranding(institutionCode);
        if (branding) {
            this.applyBranding(branding);
        }
        return branding;
    }

    applyBranding(branding) {
        this.branding = branding;
        
        // Set CSS variables
        const root = document.documentElement;
        root.style.setProperty('--institution-primary', branding.primary_color || '#8B0000');
        root.style.setProperty('--institution-secondary', branding.secondary_color || '#D4AF37');
        root.style.setProperty('--institution-accent', branding.accent_color || '#2C3E50');
        
        // Calculate text colors for contrast
        root.style.setProperty('--institution-text-on-primary', '#D4AF37');
        root.style.setProperty('--institution-text-on-secondary', '#8B0000');
        
        // Update page title
        if (branding.name) {
            document.title = document.title.replace('Juris AI', branding.name);
        }
        
        // Update logo if element exists
        const logoElements = document.querySelectorAll('[id="institution-logo"], .institution-logo');
        logoElements.forEach(el => {
            if (branding.logo_url) {
                el.src = branding.logo_url;
                el.style.display = 'block';
            }
        });
        
        // Update navbar title
        const nameElements = document.querySelectorAll('[id="institution-name"], .institution-name');
        nameElements.forEach(el => {
            if (branding.name) {
                el.textContent = branding.name;
            }
        });
        
        // Dispatch event for other components
        window.dispatchEvent(new CustomEvent('institutionBrandingApplied', {
            detail: branding
        }));
        
        console.log('Institution branding applied:', branding.name);
    }

    getCurrentBranding() {
        return this.branding;
    }

    clearCache() {
        // Clear all branding cache
        Object.keys(localStorage).forEach(key => {
            if (key.startsWith(this.cacheKey)) {
                localStorage.removeItem(key);
            }
        });
    }

    /**
     * Helper to detect institution from email domain
     */
    static detectFromEmail(email) {
        if (!email || !email.includes('@')) {
            return null;
        }
        
        const domain = email.split('@')[1].toLowerCase();
        
        // Common institution domain mappings
        const domainMappings = {
            'nlsiu.ac.in': 'nlsiu',
            'nluo.ac.in': 'nluo',
            'nludelhi.ac.in': 'nlud',
            'nujs.edu': 'nujs',
            'nlujodhpur.ac.in': 'nluj',
            'nalsar.ac.in': 'nalsar',
            'nluguwahati.ac.in': 'nlug',
            'nliu.ac.in': 'nliu'
        };
        
        return domainMappings[domain] || null;
    }
}

// Auto-initialize on page load
if (typeof window !== 'undefined') {
    window.institutionBranding = new InstitutionBranding();
}
