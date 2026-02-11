/**
 * Phase 4: Memorial Analysis Controller
 * 
 * Displays AI analysis results with scores, feedback, case citations,
 * and doctrine analysis.
 * 
 * Features:
 * - Score visualization with animated bars
 * - Strengths and improvements display
 * - Case citation verification
 * - Doctrine gap analysis
 * - Navigation between submissions
 */

class MemorialAnalysisController {
    /**
     * @param {number} memorialId - ID of the memorial analysis
     * @param {object} options - Configuration options
     */
    constructor(memorialId, options = {}) {
        this.memorialId = memorialId;
        this.competitionId = options.competitionId || 1;
        this.teamId = options.teamId || null;
        this.apiBaseUrl = options.apiBaseUrl || '/api';
        this.onBackToUpload = options.onBackToUpload || null;
        this.onViewAllSubmissions = options.onViewAllSubmissions || null;
        
        // State
        this.analysisData = null;
        this.isLoading = false;
        
        // DOM Element Cache
        this.elements = {};
        
        // Bind methods
        this.loadAnalysis = this.loadAnalysis.bind(this);
        this.renderAnalysis = this.renderAnalysis.bind(this);
    }
    
    /**
     * Initialize controller and load analysis data
     */
    initialize() {
        this.cacheElements();
        this.setupEventListeners();
        this.loadAnalysis();
    }
    
    /**
     * Cache DOM elements for performance
     */
    cacheElements() {
        // Header elements
        this.elements.teamName = document.getElementById('team-name');
        this.elements.analysisDate = document.getElementById('analysis-date');
        this.elements.downloadPdf = document.getElementById('download-pdf');
        
        // Score elements
        this.elements.overallScore = document.getElementById('overall-score');
        this.elements.scorePercentage = document.getElementById('score-percentage');
        this.elements.scoreCircle = document.getElementById('score-circle');
        
        // Score breakdown bars
        this.elements.iracBar = document.getElementById('irac-bar');
        this.elements.iracScore = document.getElementById('irac-score');
        this.elements.citationBar = document.getElementById('citation-bar');
        this.elements.citationScore = document.getElementById('citation-score');
        this.elements.reasoningBar = document.getElementById('reasoning-bar');
        this.elements.reasoningScore = document.getElementById('reasoning-score');
        
        // Lists
        this.elements.strengthsList = document.getElementById('strengths-list');
        this.elements.improvementsList = document.getElementById('improvements-list');
        this.elements.citationsList = document.getElementById('citations-list');
        this.elements.doctrinesGrid = document.getElementById('doctrines-grid');
        this.elements.recommendationsList = document.getElementById('recommendations-list');
        
        // Action buttons
        this.elements.backToUpload = document.getElementById('back-to-upload');
        this.elements.viewAllSubmissions = document.getElementById('view-all-submissions');
        this.elements.submitForCompetition = document.getElementById('submit-for-competition');
        
        // Container
        this.elements.container = document.getElementById('memorial-analysis-container');
    }
    
    /**
     * Setup event listeners
     */
    setupEventListeners() {
        if (this.elements.backToUpload) {
            this.elements.backToUpload.addEventListener('click', () => {
                if (this.onBackToUpload) {
                    this.onBackToUpload();
                } else {
                    window.location.href = 'memorial-upload.html';
                }
            });
        }
        
        if (this.elements.viewAllSubmissions) {
            this.elements.viewAllSubmissions.addEventListener('click', () => {
                if (this.onViewAllSubmissions) {
                    this.onViewAllSubmissions();
                }
            });
        }
        
        if (this.elements.submitForCompetition) {
            this.elements.submitForCompetition.addEventListener('click', () => {
                this.submitForCompetition();
            });
        }
        
        if (this.elements.downloadPdf) {
            this.elements.downloadPdf.addEventListener('click', (e) => {
                e.preventDefault();
                this.downloadMemorial();
            });
        }
    }
    
    /**
     * Load analysis data from API
     */
    async loadAnalysis() {
        this.isLoading = true;
        this.showLoading();
        
        try {
            const response = await fetch(
                `${this.apiBaseUrl}/competitions/${this.competitionId}/memorials/${this.memorialId}/analysis`,
                {
                    headers: {
                        'Authorization': `Bearer ${this.getAuthToken()}`
                    }
                }
            );
            
            if (!response.ok) {
                throw new Error('Failed to load analysis');
            }
            
            this.analysisData = await response.json();
            this.renderAnalysis();
            
        } catch (error) {
            console.error('Error loading analysis:', error);
            this.showError('Failed to load analysis. Please try again.');
        } finally {
            this.isLoading = false;
        }
    }
    
    /**
     * Show loading state
     */
    showLoading() {
        if (this.elements.container) {
            this.elements.container.classList.add('loading');
        }
    }
    
    /**
     * Show error state
     * @param {string} message 
     */
    showError(message) {
        if (this.elements.container) {
            this.elements.container.classList.remove('loading');
            this.elements.container.innerHTML = `
                <div class="analysis-error">
                    <div class="error-icon">❌</div>
                    <h3>Error Loading Analysis</h3>
                    <p>${message}</p>
                    <button class="btn primary" onclick="location.reload()">Retry</button>
                </div>
            `;
        }
    }
    
    /**
     * Render analysis data to UI
     */
    renderAnalysis() {
        if (!this.analysisData) return;
        
        const data = this.analysisData;
        
        // Update header
        this.updateHeader(data);
        
        // Update scores
        this.updateScores(data.scores);
        
        // Update feedback
        this.updateFeedback(data.feedback);
        
        // Update citations
        this.updateCitations(data.feedback?.case_citations || []);
        
        // Update doctrines
        this.updateDoctrines(data.feedback?.doctrine_gaps || []);
        
        // Update recommendations
        this.updateRecommendations(data.feedback?.recommendations || []);
        
        // Animate elements
        this.animateScoreBars();
    }
    
    /**
     * Update header information
     * @param {object} data 
     */
    updateHeader(data) {
        if (this.elements.teamName) {
            const side = data.team_side || 'petitioner';
            const teamLabel = side === 'petitioner' ? 'Petitioner' : 'Respondent';
            this.elements.teamName.textContent = `Team ${data.team_id || '1'} (${teamLabel})`;
        }
        
        if (this.elements.analysisDate && data.completed_at) {
            const date = new Date(data.completed_at);
            this.elements.analysisDate.innerHTML = `
                <span class="date-icon">📅</span>
                <span>Analyzed on ${date.toLocaleDateString('en-US', {
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric'
                })} at ${date.toLocaleTimeString('en-US', {
                    hour: '2-digit',
                    minute: '2-digit'
                })}</span>
            `;
        }
        
        if (this.elements.downloadPdf) {
            this.elements.downloadPdf.href = 
                `${this.apiBaseUrl}/competitions/${this.competitionId}/memorials/${this.memorialId}/download`;
        }
    }
    
    /**
     * Update score displays
     * @param {object} scores 
     */
    updateScores(scores) {
        if (!scores) return;
        
        // Overall score
        if (this.elements.overallScore) {
            this.elements.overallScore.textContent = scores.overall?.toFixed(1) || '0.0';
        }
        
        if (this.elements.scorePercentage) {
            this.elements.scorePercentage.textContent = `${scores.percentage || 0}%`;
        }
        
        // Update circle color based on score
        if (this.elements.scoreCircle) {
            const overall = scores.overall || 0;
            this.elements.scoreCircle.classList.remove('low', 'medium', 'high');
            if (overall < 3) {
                this.elements.scoreCircle.classList.add('low');
            } else if (overall < 4) {
                this.elements.scoreCircle.classList.add('medium');
            } else {
                this.elements.scoreCircle.classList.add('high');
            }
        }
        
        // Individual criteria
        if (this.elements.iracBar && this.elements.iracScore) {
            const irac = scores.irac_structure || 0;
            this.elements.iracBar.style.width = `${(irac / 5) * 100}%`;
            this.elements.iracScore.textContent = `${irac}/5`;
        }
        
        if (this.elements.citationBar && this.elements.citationScore) {
            const citation = scores.citation_format || 0;
            this.elements.citationBar.style.width = `${(citation / 5) * 100}%`;
            this.elements.citationScore.textContent = `${citation}/5`;
        }
        
        if (this.elements.reasoningBar && this.elements.reasoningScore) {
            const reasoning = scores.legal_reasoning || 0;
            this.elements.reasoningBar.style.width = `${(reasoning / 5) * 100}%`;
            this.elements.reasoningScore.textContent = `${reasoning}/5`;
        }
    }
    
    /**
     * Update feedback sections
     * @param {object} feedback 
     */
    updateFeedback(feedback) {
        if (!feedback) return;
        
        // Strengths
        if (this.elements.strengthsList && feedback.strengths) {
            this.elements.strengthsList.innerHTML = feedback.strengths.map(strength => `
                <div class="strength-item">
                    <div class="item-icon">✓</div>
                    <div class="item-content">
                        <strong>${strength}</strong>
                    </div>
                </div>
            `).join('');
        }
        
        // Improvements
        if (this.elements.improvementsList && feedback.improvements) {
            this.elements.improvementsList.innerHTML = feedback.improvements.map(imp => `
                <div class="improvement-item">
                    <div class="item-icon">!</div>
                    <div class="item-content">
                        <strong>${imp.issue || imp}</strong>
                        ${imp.suggestion ? `<p>${imp.suggestion}</p>` : ''}
                        ${imp.priority ? `<span class="priority-badge ${imp.priority}">${imp.priority}</span>` : ''}
                    </div>
                </div>
            `).join('');
        }
    }
    
    /**
     * Update case citations list
     * @param {Array} citations 
     */
    updateCitations(citations) {
        if (!this.elements.citationsList || !citations) return;
        
        this.elements.citationsList.innerHTML = citations.map(cite => {
            const statusClass = cite.status === 'verified' ? 'verified' : 
                               cite.status === 'mentioned_not_analyzed' ? 'warning' : 'info';
            const statusText = cite.status === 'verified' ? '✓ SCC' : 
                              cite.status === 'mentioned_not_analyzed' ? '⚠ Missing Analysis' : 'ℹ Mentioned';
            
            return `
                <div class="citation-item">
                    <div class="citation-badge ${statusClass}">${statusText}</div>
                    <div class="citation-content">
                        <div class="citation-name">${cite.name}</div>
                        <div class="citation-context">${cite.context}</div>
                        ${cite.usage_count ? `<div class="citation-usage">Used ${cite.usage_count} time${cite.usage_count > 1 ? 's' : ''}</div>` : ''}
                    </div>
                </div>
            `;
        }).join('');
    }
    
    /**
     * Update doctrine analysis grid
     * @param {Array} doctrines 
     */
    updateDoctrines(doctrines) {
        if (!this.elements.doctrinesGrid || !doctrines) return;
        
        const doctrineDisplayNames = {
            'proportionality': 'Proportionality Test',
            'basic_structure': 'Basic Structure',
            'irac': 'IRAC Structure',
            'article_21': 'Article 21 Analysis',
            'precedent_application': 'Precedent Application'
        };
        
        this.elements.doctrinesGrid.innerHTML = doctrines.map(doc => {
            const displayName = doctrineDisplayNames[doc.doctrine] || doc.doctrine;
            const statusClass = doc.status === 'present' ? 'present' : 
                               doc.status === 'strong' ? 'strong' : 'missing';
            const statusIcon = doc.status === 'present' ? '✅' : 
                              doc.status === 'strong' ? '⭐' : '❌';
            const statusText = doc.status === 'present' ? 'Present' : 
                              doc.status === 'strong' ? 'Strong' : 'Missing';
            
            return `
                <div class="doctrine-card ${statusClass}">
                    <div class="doctrine-icon">⚖️</div>
                    <div class="doctrine-name">${displayName}</div>
                    <div class="doctrine-status">
                        <span class="status-icon">${statusIcon}</span>
                        <span class="status-text">${statusText}</span>
                    </div>
                    <div class="doctrine-description">${doc.importance || doc.description || ''}</div>
                    ${doc.reference ? `<div class="doctrine-reference">Ref: ${doc.reference}</div>` : ''}
                </div>
            `;
        }).join('');
    }
    
    /**
     * Update recommendations list
     * @param {Array} recommendations 
     */
    updateRecommendations(recommendations) {
        if (!this.elements.recommendationsList || !recommendations) return;
        
        const typeIcons = {
            'additional_citation': '📖',
            'oral_argument': '🎯',
            'structure': '📋',
            'general': '💡'
        };
        
        this.elements.recommendationsList.innerHTML = recommendations.map(rec => {
            const icon = typeIcons[rec.type] || '💡';
            return `
                <div class="recommendation-item">
                    <div class="rec-icon">${icon}</div>
                    <div class="rec-content">
                        <strong>${rec.suggestion}</strong>
                        ${rec.priority ? `<span class="priority-badge ${rec.priority}">${rec.priority}</span>` : ''}
                    </div>
                </div>
            `;
        }).join('');
    }
    
    /**
     * Animate score bars on load
     */
    animateScoreBars() {
        setTimeout(() => {
            if (this.elements.iracBar) {
                this.elements.iracBar.style.transition = 'width 1s ease-out';
            }
            if (this.elements.citationBar) {
                this.elements.citationBar.style.transition = 'width 1s ease-out';
            }
            if (this.elements.reasoningBar) {
                this.elements.reasoningBar.style.transition = 'width 1s ease-out';
            }
        }, 100);
    }
    
    /**
     * Download memorial PDF
     */
    async downloadMemorial() {
        try {
            const response = await fetch(
                `${this.apiBaseUrl}/competitions/${this.competitionId}/memorials/${this.memorialId}/download`,
                {
                    headers: {
                        'Authorization': `Bearer ${this.getAuthToken()}`
                    }
                }
            );
            
            if (!response.ok) {
                throw new Error('Download failed');
            }
            
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `memorial_${this.memorialId}.pdf`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            
        } catch (error) {
            console.error('Download error:', error);
            alert('Failed to download memorial. Please try again.');
        }
    }
    
    /**
     * Submit memorial for competition
     */
    async submitForCompetition() {
        if (!confirm('Are you sure you want to submit this memorial for the competition? This action cannot be undone.')) {
            return;
        }
        
        try {
            const response = await fetch(
                `${this.apiBaseUrl}/competitions/${this.competitionId}/memorials/${this.memorialId}/submit`,
                {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${this.getAuthToken()}`,
                        'Content-Type': 'application/json'
                    }
                }
            );
            
            if (!response.ok) {
                throw new Error('Submission failed');
            }
            
            const result = await response.json();
            alert('Memorial submitted successfully for competition!');
            
            // Update UI
            if (this.elements.submitForCompetition) {
                this.elements.submitForCompetition.disabled = true;
                this.elements.submitForCompetition.textContent = '✓ Submitted';
            }
            
        } catch (error) {
            console.error('Submission error:', error);
            alert('Failed to submit memorial. Please try again.');
        }
    }
    
    /**
     * Get auth token from localStorage
     * @returns {string}
     */
    getAuthToken() {
        return localStorage.getItem('access_token') || '';
    }
    
    /**
     * Cleanup resources
     */
    cleanup() {
        // Cleanup if needed
    }
}

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MemorialAnalysisController;
}
