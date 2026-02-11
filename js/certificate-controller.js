/**
 * js/certificate-controller.js
 * Phase 5: Certificate Generator Controller
 * Handles certificate generation, preview, download, and sharing
 */

class CertificateController {
    constructor() {
        this.baseUrl = 'http://localhost:8000/api';
        this.currentCertificate = null;
        this.competitions = [];
        this.teams = [];
        
        this.init();
    }

    init() {
        this.loadCompetitions();
        this.loadTeams();
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
                this.competitions = data.competitions || [];
                this.populateCompetitionSelect();
            }
        } catch (error) {
            console.error('Error loading competitions:', error);
        }
    }

    async loadTeams() {
        const token = this.getAuthToken();
        try {
            const response = await fetch(
                `${this.baseUrl}/teams/my-teams`,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            if (response.ok) {
                const data = await response.json();
                this.teams = data.teams || [];
                this.populateTeamSelect();
            }
        } catch (error) {
            console.error('Error loading teams:', error);
        }
    }

    populateCompetitionSelect() {
        const select = document.getElementById('competition-select');
        if (!select) return;

        // Clear existing options except first
        while (select.options.length > 1) {
            select.remove(1);
        }

        this.competitions.forEach(comp => {
            const option = document.createElement('option');
            option.value = comp.id;
            option.textContent = comp.title;
            select.appendChild(option);
        });
    }

    populateTeamSelect() {
        const select = document.getElementById('team-select');
        if (!select) return;

        while (select.options.length > 1) {
            select.remove(1);
        }

        this.teams.forEach(team => {
            const option = document.createElement('option');
            option.value = team.id;
            option.textContent = team.name;
            select.appendChild(option);
        });
    }

    async generateCertificate() {
        const competitionId = document.getElementById('competition-select')?.value;
        const teamId = document.getElementById('team-select')?.value;
        const finalRank = parseInt(document.getElementById('final-rank')?.value);
        const totalScore = parseFloat(document.getElementById('total-score')?.value);

        if (!competitionId || !teamId || !finalRank || isNaN(totalScore)) {
            this.showStatus('Please fill in all fields', 'error');
            return;
        }

        const token = this.getAuthToken();
        const payload = {
            competition_id: parseInt(competitionId),
            team_id: parseInt(teamId),
            final_rank: finalRank,
            total_score: totalScore
        };

        const btn = document.getElementById('generate-btn');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Generating...';
        }

        try {
            const response = await fetch(
                `${this.baseUrl}/analytics/certificates/generate`,
                {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(payload)
                }
            );

            if (response.ok) {
                const data = await response.json();
                this.currentCertificate = data;
                this.showPreview(data);
                this.showStatus('Certificate generated successfully!', 'success');
            } else {
                const error = await response.json();
                this.showStatus(error.detail || 'Failed to generate certificate', 'error');
            }
        } catch (error) {
            console.error('Error generating certificate:', error);
            this.showStatus('Network error. Please try again.', 'error');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Generate Certificate';
            }
        }
    }

    showPreview(certificate) {
        // Hide placeholder
        const placeholder = document.getElementById('pdf-placeholder');
        if (placeholder) placeholder.classList.add('hidden');

        // Show PDF in iframe
        const iframe = document.getElementById('pdf-preview');
        if (iframe) {
            iframe.src = `${this.baseUrl}/analytics/certificates/${certificate.certificate_code}/download`;
        }

        // Show QR section
        const qrSection = document.getElementById('qr-section');
        if (qrSection) qrSection.classList.remove('hidden');

        // Show QR image
        const qrImg = document.getElementById('qr-image');
        if (qrImg) {
            // In production, this would be the actual QR path
            qrImg.src = `https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=${encodeURIComponent(`https://juris.ai/verify/${certificate.certificate_code}`)}`;
        }

        // Show action buttons
        const actions = document.getElementById('action-buttons');
        if (actions) actions.classList.remove('hidden');
    }

    async downloadCertificate() {
        if (!this.currentCertificate) return;

        const token = this.getAuthToken();
        try {
            const response = await fetch(
                `${this.baseUrl}/analytics/certificates/${this.currentCertificate.certificate_code}/download`,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );

            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `NLSIU_Certificate_${this.currentCertificate.certificate_code}.pdf`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
                this.showStatus('Certificate downloaded!', 'success');
            } else {
                this.showStatus('Failed to download certificate', 'error');
            }
        } catch (error) {
            console.error('Error downloading:', error);
            this.showStatus('Download failed. Please try again.', 'error');
        }
    }

    shareToLinkedIn() {
        if (!this.currentCertificate) return;

        const text = `I earned ${this.currentCertificate.rank} place in ${this.currentCertificate.competition_title} at NLSIU with a score of ${this.currentCertificate.total_score}/5.0! 🏆⚖️`;
        const url = `https://juris.ai/verify/${this.currentCertificate.certificate_code}`;
        
        const linkedInUrl = `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(url)}&summary=${encodeURIComponent(text)}`;
        window.open(linkedInUrl, '_blank');
    }

    shareToWhatsApp() {
        if (!this.currentCertificate) return;

        const text = `I earned ${this.currentCertificate.rank} place in ${this.currentCertificate.competition_title} at NLSIU! 🏆⚖️\n\nVerify my certificate: https://juris.ai/verify/${this.currentCertificate.certificate_code}`;
        
        const whatsappUrl = `https://wa.me/?text=${encodeURIComponent(text)}`;
        window.open(whatsappUrl, '_blank');
    }

    showStatus(message, type) {
        const statusEl = document.getElementById('status-message');
        if (!statusEl) return;

        statusEl.textContent = message;
        statusEl.className = `status-message ${type}`;
        
        setTimeout(() => {
            statusEl.classList.add('hidden');
        }, 5000);
    }
}
