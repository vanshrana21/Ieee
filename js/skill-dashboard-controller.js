/**
 * js/skill-dashboard-controller.js
 * Phase 5: Skill Dashboard Controller
 * Handles skill progress visualization with Chart.js
 */

class SkillDashboardController {
    constructor(userId) {
        this.userId = userId;
        this.baseUrl = 'http://localhost:8000/api';
        this.currentPeriod = 'last_30_days';
        this.charts = {};
        
        this.skillMapping = {
            'citation_accuracy': { cardId: 'card-citation', scoreId: 'score-citation', trendId: 'trend-citation', trendValId: 'trendval-citation', percentileId: 'percentile-citation', chartId: 'chart-citation' },
            'etiquette_compliance': { cardId: 'card-etiquette', scoreId: 'score-etiquette', trendId: 'trend-etiquette', trendValId: 'trendval-etiquette', percentileId: 'percentile-etiquette', chartId: 'chart-etiquette' },
            'legal_reasoning': { cardId: 'card-reasoning', scoreId: 'score-reasoning', trendId: 'trend-reasoning', trendValId: 'trendval-reasoning', percentileId: 'percentile-reasoning', chartId: 'chart-reasoning' },
            'doctrine_mastery': { cardId: 'card-doctrine', scoreId: 'score-doctrine', trendId: 'trend-doctrine', trendValId: 'trendval-doctrine', percentileId: 'percentile-doctrine', chartId: 'chart-doctrine' },
            'time_management': { cardId: 'card-time', scoreId: 'score-time', trendId: 'trend-time', trendValId: 'trendval-time', percentileId: 'percentile-time', chartId: 'chart-time' }
        };
        
        this.init();
    }

    init() {
        this.loadUserData();
        this.loadWeaknesses();
        this.loadBenchmarks();
    }

    getAuthToken() {
        return localStorage.getItem('access_token') || '';
    }

    setPeriod(period) {
        this.currentPeriod = period;
        document.querySelectorAll('.period-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelector(`[data-period="${period}"]`).classList.add('active');
        this.loadUserData();
    }

    async loadUserData() {
        const token = this.getAuthToken();
        if (!token) {
            console.error('No auth token found');
            return;
        }

        try {
            const response = await fetch(
                `${this.baseUrl}/analytics/skills/${this.userId}?period=${this.currentPeriod}`,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );

            if (response.ok) {
                const data = await response.json();
                this.renderSkills(data.skills);
                this.renderInsights(data.insights);
            } else {
                console.error('Failed to load skill data');
            }
        } catch (error) {
            console.error('Error loading skill data:', error);
        }
    }

    renderSkills(skills) {
        skills.forEach(skill => {
            const mapping = this.skillMapping[skill.skill_type];
            if (!mapping) return;

            // Update score
            const scoreEl = document.getElementById(mapping.scoreId);
            if (scoreEl) scoreEl.textContent = `${skill.current_score.toFixed(1)}/5.0`;

            // Update trend
            const trendEl = document.getElementById(mapping.trendId);
            const trendValEl = document.getElementById(mapping.trendValId);
            if (trendEl && trendValEl) {
                if (skill.improvement) {
                    const isPositive = skill.improvement.startsWith('+');
                    trendEl.textContent = isPositive ? '↑' : '↓';
                    trendEl.className = `trend-arrow ${isPositive ? 'up' : 'down'}`;
                    trendValEl.textContent = `${skill.improvement} this month`;
                } else {
                    trendEl.textContent = '→';
                    trendEl.className = 'trend-arrow';
                    trendValEl.textContent = 'No change';
                }
            }

            // Update percentile
            const percentileEl = document.getElementById(mapping.percentileId);
            if (percentileEl) percentileEl.textContent = `Top ${100 - skill.percentile}%`;

            // Update card color based on score
            const cardEl = document.getElementById(mapping.cardId);
            if (cardEl) {
                cardEl.classList.remove('low', 'medium', 'high');
                if (skill.current_score < 3) cardEl.classList.add('low');
                else if (skill.current_score < 4) cardEl.classList.add('medium');
                else cardEl.classList.add('high');
            }

            // Render chart
            this.renderSkillChart(mapping.chartId, skill.history);
        });
    }

    renderSkillChart(canvasId, history) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return;

        // Destroy existing chart
        if (this.charts[canvasId]) {
            this.charts[canvasId].destroy();
        }

        const labels = history.map(h => {
            const date = new Date(h.date);
            return `${date.getMonth() + 1}/${date.getDate()}`;
        });
        const data = history.map(h => h.score);

        this.charts[canvasId] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Score',
                    data: data,
                    borderColor: '#667eea',
                    backgroundColor: 'rgba(102, 126, 234, 0.1)',
                    tension: 0.4,
                    fill: true,
                    pointRadius: 4,
                    pointBackgroundColor: '#667eea'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    y: {
                        min: 0,
                        max: 5,
                        ticks: { stepSize: 1 }
                    },
                    x: {
                        grid: { display: false }
                    }
                }
            }
        });
    }

    renderInsights(insights) {
        const container = document.getElementById('insights-container');
        if (!container) return;

        if (insights.length === 0) {
            container.innerHTML = `
                <div class="insight-card">
                    <span class="insight-icon">💡</span>
                    <p>Start practicing to see personalized insights!</p>
                </div>
            `;
            return;
        }

        container.innerHTML = insights.map(insight => `
            <div class="insight-card">
                <span class="insight-icon">💡</span>
                <p>${insight}</p>
            </div>
        `).join('');
    }

    async loadWeaknesses() {
        const token = this.getAuthToken();
        try {
            const response = await fetch(
                `${this.baseUrl}/analytics/weaknesses/${this.userId}`,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );

            if (response.ok) {
                const data = await response.json();
                this.renderWeaknesses(data.weaknesses);
                this.renderStrengths(data.strengths);
            }
        } catch (error) {
            console.error('Error loading weaknesses:', error);
        }
    }

    renderWeaknesses(weaknesses) {
        const container = document.getElementById('weaknesses-container');
        if (!container) return;

        if (weaknesses.length === 0) {
            container.innerHTML = '<p class="loading-text">No major weaknesses detected. Keep up the good work!</p>';
            return;
        }

        container.innerHTML = weaknesses.map(w => `
            <div class="weakness-card">
                <h4>${w.skill_display}</h4>
                <div class="pattern-text">${w.pattern}</div>
                <div class="example-text">Example: "${w.example}"</div>
                <div class="remediation-text">💡 ${w.remediation}</div>
                <div class="frequency-badge">${w.frequency}</div>
            </div>
        `).join('');
    }

    renderStrengths(strengths) {
        const container = document.getElementById('strengths-container');
        if (!container) return;

        if (strengths.length === 0) {
            container.innerHTML = '<p class="loading-text">Practice more to build your strengths!</p>';
            return;
        }

        container.innerHTML = strengths.map(s => `
            <div class="strength-card">
                <h4>${s.skill_display}</h4>
                <div class="pattern-text">${s.pattern}</div>
                <div class="example-text">${s.note}</div>
                <div class="frequency-badge good">Top ${100 - s.percentile}% percentile</div>
            </div>
        `).join('');
    }

    async loadBenchmarks() {
        const token = this.getAuthToken();
        try {
            const response = await fetch(
                `${this.baseUrl}/analytics/benchmarks`,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );

            if (response.ok) {
                const data = await response.json();
                this.renderBenchmarks(data);
            }
        } catch (error) {
            console.error('Error loading benchmarks:', error);
        }
    }

    renderBenchmarks(benchmarks) {
        const ctx = document.getElementById('chart-benchmarks');
        if (!ctx || benchmarks.length === 0) return;

        const labels = benchmarks.map(b => b.skill_type.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase()));
        const userScores = benchmarks.map(b => b.mean_score); // In production, would be user's actual scores
        const p25 = benchmarks.map(b => b.percentile_25);
        const p50 = benchmarks.map(b => b.percentile_50);
        const p75 = benchmarks.map(b => b.percentile_75);

        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: '25th Percentile',
                        data: p25,
                        backgroundColor: 'rgba(244, 67, 54, 0.3)'
                    },
                    {
                        label: 'Median',
                        data: p50,
                        backgroundColor: 'rgba(255, 193, 7, 0.5)'
                    },
                    {
                        label: '75th Percentile',
                        data: p75,
                        backgroundColor: 'rgba(76, 175, 80, 0.5)'
                    },
                    {
                        label: 'Cohort Average',
                        data: userScores,
                        backgroundColor: 'rgba(102, 126, 234, 0.8)'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        min: 0,
                        max: 5,
                        title: { display: true, text: 'Score (0-5)' }
                    }
                }
            }
        });
    }
}
