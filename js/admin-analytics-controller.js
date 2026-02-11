/**
 * js/admin-analytics-controller.js
 * Phase 5: Admin Analytics Controller
 * Handles competition analytics visualization and export
 */

class AdminAnalyticsController {
    constructor() {
        this.baseUrl = 'http://localhost:8000/api';
        this.currentCompetitionId = null;
        this.analyticsData = null;
        this.charts = {};
        
        this.init();
    }

    init() {
        this.loadCompetitions();
    }

    getAuthToken() {
        return localStorage.getItem('access_token') || '';
    }

    async loadCompetitions() {
        const token = this.getAuthToken();
        try {
            const response = await fetch(
                `${this.baseUrl}/competitions`,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            if (response.ok) {
                const data = await response.json();
                this.populateCompetitionSelect(data.competitions || []);
            }
        } catch (error) {
            console.error('Error loading competitions:', error);
        }
    }

    populateCompetitionSelect(competitions) {
        const select = document.getElementById('competition-select');
        if (!select) return;

        competitions.forEach(comp => {
            const option = document.createElement('option');
            option.value = comp.id;
            option.textContent = comp.title;
            select.appendChild(option);
        });
    }

    async loadCompetitionData() {
        const select = document.getElementById('competition-select');
        if (!select || !select.value) return;

        this.currentCompetitionId = select.value;
        const token = this.getAuthToken();

        try {
            const response = await fetch(
                `${this.baseUrl}/analytics/admin/competition/${this.currentCompetitionId}`,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );

            if (response.ok) {
                const data = await response.json();
                this.analyticsData = data;
                this.renderOverview(data);
                this.renderCharts(data);
                this.renderCases(data.top_cited_cases);
            } else if (response.status === 403) {
                alert('Admin access required');
            } else {
                console.error('Failed to load analytics');
            }
        } catch (error) {
            console.error('Error loading competition analytics:', error);
        }
    }

    renderOverview(data) {
        // Update stat cards
        const participationEl = document.getElementById('participation-rate');
        const completionEl = document.getElementById('completion-rate');
        const citationEl = document.getElementById('avg-citation');
        const participantsEl = document.getElementById('total-participants');

        if (participationEl) participationEl.textContent = data.participation_rate;
        if (completionEl) completionEl.textContent = data.completion_rate;
        if (citationEl) citationEl.textContent = data.avg_citation_score.toFixed(1);
        if (participantsEl) participantsEl.textContent = '42'; // Would come from API
    }

    renderCharts(data) {
        // Criteria chart
        const criteriaCtx = document.getElementById('chart-criteria');
        if (criteriaCtx) {
            if (this.charts.criteria) this.charts.criteria.destroy();
            
            const criteria = data.avg_scores_by_criteria;
            this.charts.criteria = new Chart(criteriaCtx, {
                type: 'radar',
                data: {
                    labels: Object.keys(criteria).map(k => k.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())),
                    datasets: [{
                        label: 'Average Score',
                        data: Object.values(criteria),
                        backgroundColor: 'rgba(102, 126, 234, 0.2)',
                        borderColor: '#667eea',
                        pointBackgroundColor: '#667eea',
                        pointBorderColor: '#fff',
                        pointHoverBackgroundColor: '#fff',
                        pointHoverBorderColor: '#667eea'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        r: {
                            min: 0,
                            max: 5,
                            ticks: {
                                stepSize: 1
                            }
                        }
                    }
                }
            });
        }

        // Doctrine mastery chart
        const doctrineCtx = document.getElementById('chart-doctrine');
        if (doctrineCtx) {
            if (this.charts.doctrine) this.charts.doctrine.destroy();
            
            const doctrines = data.doctrine_mastery;
            const labels = Object.keys(doctrines).map(k => k.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()));
            const values = Object.values(doctrines).map(v => parseInt(v));

            this.charts.doctrine = new Chart(doctrineCtx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Mastery %',
                        data: values,
                        backgroundColor: [
                            'rgba(102, 126, 234, 0.8)',
                            'rgba(118, 75, 162, 0.8)',
                            'rgba(212, 175, 55, 0.8)',
                            'rgba(139, 0, 0, 0.8)'
                        ],
                        borderColor: [
                            '#667eea',
                            '#764ba2',
                            '#D4AF37',
                            '#8B0000'
                        ],
                        borderWidth: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            min: 0,
                            max: 100,
                            title: {
                                display: true,
                                text: 'Mastery Percentage'
                            }
                        }
                    }
                }
            });
        }
    }

    renderCases(cases) {
        const container = document.getElementById('cases-container');
        if (!container || !cases) return;

        const maxCount = Math.max(...cases.map(c => c.count));

        container.innerHTML = cases.map(c => {
            const percentage = (c.count / maxCount) * 100;
            return `
                <div class="case-item">
                    <div class="case-name">${c.case}</div>
                    <div class="case-bar-container">
                        <div class="case-bar" style="width: ${percentage}%"></div>
                    </div>
                    <div class="case-count">${c.count} citations</div>
                </div>
            `;
        }).join('');
    }

    exportCSV() {
        if (!this.analyticsData) {
            alert('Please select a competition first');
            return;
        }

        const data = this.analyticsData;
        
        // Build CSV content
        let csv = 'Competition Analytics Report\n';
        csv += `Competition ID,${data.competition_id}\n`;
        csv += `Participation Rate,${data.participation_rate}\n`;
        csv += `Completion Rate,${data.completion_rate}\n`;
        csv += `Average Citation Score,${data.avg_citation_score}\n\n`;

        csv += 'Score by Criteria\n';
        csv += 'Criteria,Average Score\n';
        Object.entries(data.avg_scores_by_criteria).forEach(([key, value]) => {
            csv += `${key},${value}\n`;
        });

        csv += '\nDoctrine Mastery\n';
        csv += 'Doctrine,Mastery Level\n';
        Object.entries(data.doctrine_mastery).forEach(([key, value]) => {
            csv += `${key},${value}\n`;
        });

        csv += '\nTop Cited Cases\n';
        csv += 'Case,Citation Count\n';
        data.top_cited_cases.forEach(c => {
            csv += `"${c.case}",${c.count}\n`;
        });

        // Download
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `competition_${data.competition_id}_analytics.csv`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
    }
}
