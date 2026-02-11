/**
 * js/ai-coach-controller.js
 * Phase 4: AI Coach Controller
 * Real-time hint generation during arguments
 */

class AICoachController {
    constructor(roundId, teamId) {
        this.roundId = roundId;
        this.teamId = teamId;
        this.baseUrl = 'http://localhost:8000/api';
        this.enabled = true;
        this.dismissTime = 10000; // 10 seconds
        this.currentHint = null;
        this.dismissTimer = null;
        this.hintCooldown = false;

        // Hint templates for client-side detection
        this.hintTemplates = [
            {
                pattern: /Puttaswamy|privacy|article 21/i,
                type: 'citation',
                text: 'Cite Puttaswamy as (2017) 10 SCC 1',
                priority: 8
            },
            {
                pattern: /Navtej|section 377|decriminalization/i,
                type: 'citation',
                text: 'Cite Navtej as (2018) 10 SCC 1',
                priority: 8
            },
            {
                pattern: /Vishaka|sexual harassment|workplace/i,
                type: 'citation',
                text: 'Cite Vishaka as (1997) 6 SCC 241',
                priority: 7
            },
            {
                pattern: /^[^my lord]*$/i,
                type: 'etiquette',
                text: "Start with 'My Lord' or 'My Lords'",
                priority: 9
            },
            {
                pattern: /proportionality|reasonable restriction| Article 19/i,
                type: 'doctrine',
                text: 'Apply proportionality test (Puttaswamy para 184)',
                priority: 6
            },
            {
                pattern: /Kesavananda|basic structure/i,
                type: 'citation',
                text: 'Cite Kesavananda as (1973) 4 SCC 225',
                priority: 7
            },
            {
                pattern: /(?!.*\(\d{4}\)\s*\d+\s*SCC).*case|.*precedent/i,
                type: 'structure',
                text: 'Use IRAC: Issue-Rule-Application-Conclusion',
                priority: 5
            },
            {
                pattern: /as held in|relied upon|following/i,
                type: 'structure',
                text: 'Good precedent usage! Continue with application.',
                priority: 4
            }
        ];

        this.init();
    }

    init() {
        this.startMonitoring();
        this.loadActiveHints();
    }

    getAuthToken() {
        return localStorage.getItem('access_token') || '';
    }

    // Monitor text input for hint triggers
    startMonitoring() {
        // Listen for text input in argument textarea
        document.addEventListener('input', (e) => {
            if (!this.enabled || this.hintCooldown) return;
            if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') {
                this.analyzeText(e.target.value);
            }
        });
    }

    analyzeText(text) {
        if (text.length < 20) return; // Need minimum text

        // Check against hint templates
        for (const template of this.hintTemplates.sort((a, b) => b.priority - a.priority)) {
            if (template.pattern.test(text)) {
                // Check if this hint was recently shown
                if (!this.wasRecentlyShown(template.text)) {
                    this.showHint(template.type, template.text, this.getTriggerKeyword(text, template.pattern));
                    this.hintCooldown = true;
                    setTimeout(() => this.hintCooldown = false, 5000); // 5s cooldown between hints
                    return; // Show only one hint at a time
                }
            }
        }
    }

    getTriggerKeyword(text, pattern) {
        const match = text.match(pattern);
        return match ? match[0] : null;
    }

    wasRecentlyShown(hintText) {
        // Check localStorage for recently shown hints
        const recentHints = JSON.parse(localStorage.getItem('recentHints') || '[]');
        const now = Date.now();
        const fiveMinutesAgo = now - 5 * 60 * 1000;

        // Clean old hints
        const validHints = recentHints.filter(h => h.timestamp > fiveMinutesAgo);

        // Check if this hint is in recent list
        const isRecent = validHints.some(h => h.text === hintText);

        // Update storage
        localStorage.setItem('recentHints', JSON.stringify(validHints));

        return isRecent;
    }

    async showHint(type, text, triggerKeyword = null) {
        // Create hint in backend
        const token = this.getAuthToken();
        try {
            const response = await fetch(
                `${this.baseUrl}/oral-rounds/${this.roundId}/ai-coach/hints?hint_type=${type}&hint_text=${encodeURIComponent(text)}&trigger_keyword=${encodeURIComponent(triggerKeyword || '')}`,
                {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` }
                }
            );

            if (response.ok) {
                const hint = await response.json();
                this.currentHint = hint;
                this.renderHint(hint);

                // Add to recent hints
                const recentHints = JSON.parse(localStorage.getItem('recentHints') || '[]');
                recentHints.push({ text: text, timestamp: Date.now() });
                localStorage.setItem('recentHints', JSON.stringify(recentHints));
            }
        } catch (error) {
            console.error('Error creating hint:', error);
        }
    }

    renderHint(hint) {
        const bar = document.getElementById('ai-coach-bar');
        const typeEl = document.getElementById('hint-type');
        const textEl = document.getElementById('hint-text');
        const progressEl = document.getElementById('timer-progress');

        if (!bar || !typeEl || !textEl) return;

        // Set content
        typeEl.textContent = hint.hint_type.toUpperCase();
        textEl.textContent = hint.hint_text;

        // Show bar
        bar.classList.remove('hidden');

        // Animate timer
        const duration = this.dismissTime;
        let elapsed = 0;

        if (this.dismissTimer) {
            clearInterval(this.dismissTimer);
        }

        this.dismissTimer = setInterval(() => {
            elapsed += 100;
            const remaining = duration - elapsed;
            const percentage = (remaining / duration) * 100;

            if (progressEl) {
                progressEl.style.strokeDashoffset = 100 - percentage;
            }

            if (remaining <= 0) {
                this.dismissHint();
            }
        }, 100);
    }

    async dismissHint() {
        const bar = document.getElementById('ai-coach-bar');
        if (bar) {
            bar.classList.add('hidden');
        }

        if (this.dismissTimer) {
            clearInterval(this.dismissTimer);
            this.dismissTimer = null;
        }

        // Mark as dismissed in backend
        if (this.currentHint) {
            const token = this.getAuthToken();
            try {
                await fetch(
                    `${this.baseUrl}/oral-rounds/${this.roundId}/ai-coach/hints/${this.currentHint.id}/dismiss`,
                    {
                        method: 'POST',
                        headers: { 'Authorization': `Bearer ${token}` }
                    }
                );
            } catch (error) {
                console.error('Error dismissing hint:', error);
            }
        }

        this.currentHint = null;
    }

    async loadActiveHints() {
        const token = this.getAuthToken();
        try {
            const response = await fetch(
                `${this.baseUrl}/oral-rounds/${this.roundId}/ai-coach/hints`,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );

            if (response.ok) {
                const hints = await response.json();
                // Show most recent undismissed hint
                const activeHint = hints.find(h => !h.is_dismissed);
                if (activeHint) {
                    this.currentHint = activeHint;
                    this.renderHint(activeHint);
                }
            }
        } catch (error) {
            console.error('Error loading hints:', error);
        }
    }

    toggleEnabled() {
        const checkbox = document.getElementById('coach-enabled');
        this.enabled = checkbox.checked;

        if (!this.enabled && this.currentHint) {
            this.dismissHint();
        }
    }

    updateDismissTime() {
        const slider = document.getElementById('dismiss-time');
        const display = document.getElementById('dismiss-time-display');
        const seconds = parseInt(slider.value);
        this.dismissTime = seconds * 1000;
        display.textContent = `${seconds}s`;
    }

    // Check which hint types are enabled
    getEnabledHintTypes() {
        const types = [];
        if (document.getElementById('hint-citation')?.checked) types.push('citation');
        if (document.getElementById('hint-etiquette')?.checked) types.push('etiquette');
        if (document.getElementById('hint-doctrine')?.checked) types.push('doctrine');
        if (document.getElementById('hint-structure')?.checked) types.push('structure');
        return types;
    }
}
