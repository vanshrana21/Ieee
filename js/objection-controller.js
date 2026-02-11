/**
 * js/objection-controller.js
 * Phase 3.3: Objection Mechanics Controller
 * Handles raising, displaying, and ruling on objections
 */

class ObjectionController {
    constructor(roundId) {
        this.roundId = roundId;
        this.selectedType = null;
        this.baseUrl = 'http://localhost:8000/api';
        this.isJudge = false;
        
        this.init();
    }

    init() {
        this.checkUserRole();
        this.loadObjections();
        this.startPolling();
    }

    // ================= AUTH & ROLE CHECK =================
    checkUserRole() {
        const token = this.getAuthToken();
        if (token) {
            try {
                const payload = JSON.parse(atob(token.split('.')[1]));
                this.isJudge = ['JUDGE', 'FACULTY', 'ADMIN', 'SUPER_ADMIN'].includes(payload.role);
                
                if (this.isJudge) {
                    document.getElementById('judge-ruling-panel')?.classList.remove('hidden');
                }
            } catch (e) {
                console.error('Error decoding token:', e);
            }
        }
    }

    getAuthToken() {
        return localStorage.getItem('access_token') || '';
    }

    // ================= MODAL CONTROL =================
    openModal() {
        const modal = document.getElementById('objection-modal');
        modal.classList.add('show');
        this.resetModal();
    }

    closeModal() {
        const modal = document.getElementById('objection-modal');
        modal.classList.remove('show');
    }

    resetModal() {
        this.selectedType = null;
        document.querySelectorAll('.obj-btn').forEach(btn => btn.classList.remove('selected'));
        document.getElementById('target-speaker').value = '';
        document.getElementById('objection-context').value = '';
        document.getElementById('raise-objection-btn').disabled = true;
    }

    // ================= OBJECTION TYPE SELECTION =================
    selectType(type) {
        this.selectedType = type;
        document.querySelectorAll('.obj-btn').forEach(btn => btn.classList.remove('selected'));
        document.querySelector(`[data-type="${type}"]`)?.classList.add('selected');
        document.getElementById('raise-objection-btn').disabled = false;
    }

    // ================= API CALLS =================
    async loadObjections() {
        try {
            const token = this.getAuthToken();
            const response = await fetch(`${this.baseUrl}/oral-rounds/${this.roundId}/objections`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });

            if (response.ok) {
                const objections = await response.json();
                this.renderObjections(objections);
                if (this.isJudge) {
                    this.renderPendingObjections(objections);
                }
            }
        } catch (error) {
            console.error('Failed to load objections:', error);
        }
    }

    async raiseObjection() {
        if (!this.selectedType) {
            alert('Please select an objection type');
            return;
        }

        const token = this.getAuthToken();
        if (!token) {
            alert('Please log in to raise objections');
            return;
        }

        const payload = {
            objection_type: this.selectedType,
            target_speaker_id: null, // Simplified - would resolve from selection
            target_statement: document.getElementById('objection-context').value,
            round_stage: 'arguments',
            transcript_context: null
        };

        try {
            const response = await fetch(`${this.baseUrl}/oral-rounds/${this.roundId}/objections`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });

            if (response.ok) {
                const result = await response.json();
                alert('Objection raised!');
                this.closeModal();
                this.loadObjections();
                this.addToTranscript(result);
            } else {
                const error = await response.json();
                alert(`Error: ${error.detail || 'Failed to raise objection'}`);
            }
        } catch (error) {
            console.error('Error raising objection:', error);
            alert('Network error. Please try again.');
        }
    }

    async raiseEmergencyObjection() {
        this.selectedType = 'relevance';
        await this.raiseObjection();
    }

    async ruleOnObjection(objectionId, ruling) {
        const token = this.getAuthToken();
        if (!token) return;

        const payload = {
            ruling: ruling,
            reason: null
        };

        try {
            const response = await fetch(
                `${this.baseUrl}/oral-rounds/${this.roundId}/objections/${objectionId}/rule`,
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
                this.loadObjections();
            } else {
                const error = await response.json();
                alert(`Error: ${error.detail || 'Failed to rule on objection'}`);
            }
        } catch (error) {
            console.error('Error ruling on objection:', error);
        }
    }

    async withdrawObjection(objectionId) {
        const token = this.getAuthToken();
        if (!token) return;

        try {
            const response = await fetch(
                `${this.baseUrl}/oral-rounds/${this.roundId}/objections/${objectionId}/withdraw`,
                {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` }
                }
            );

            if (response.ok) {
                this.loadObjections();
            } else {
                const error = await response.json();
                alert(`Error: ${error.detail || 'Failed to withdraw objection'}`);
            }
        } catch (error) {
            console.error('Error withdrawing objection:', error);
        }
    }

    // ================= RENDERING =================
    renderObjections(objections) {
        const container = document.getElementById('objections-list');
        if (!container) return;

        if (objections.length === 0) {
            container.innerHTML = '<p class="no-objections">No objections raised</p>';
            return;
        }

        container.innerHTML = objections.map(obj => this.createObjectionHTML(obj)).join('');
    }

    renderPendingObjections(objections) {
        const container = document.getElementById('pending-objections');
        const panel = document.getElementById('judge-ruling-panel');
        if (!container || !panel) return;

        const pending = objections.filter(o => o.status === 'raised' || o.status === 'pending');

        if (pending.length === 0) {
            panel.classList.add('hidden');
            container.innerHTML = '<p class="no-pending">No pending objections</p>';
            return;
        }

        panel.classList.remove('hidden');
        container.innerHTML = pending.map(obj => this.createPendingHTML(obj)).join('');
    }

    createObjectionHTML(obj) {
        const statusClass = obj.status.toLowerCase();
        return `
            <div class="objection-item ${statusClass}">
                <div class="objection-type">${this.formatType(obj.objection_type)}</div>
                <span class="objection-status ${statusClass}">${obj.status}</span>
                <div class="objection-meta">
                    Raised by ${obj.raised_by_name} • ${this.formatTime(obj.raised_at)}
                    ${obj.ruled_by_name ? `<br>Ruled by ${obj.ruled_by_name}` : ''}
                </div>
            </div>
        `;
    }

    createPendingHTML(obj) {
        return `
            <div class="pending-objection">
                <div class="obj-type">${this.formatType(obj.objection_type)}</div>
                <div class="obj-raised-by">Raised by ${obj.raised_by_name}</div>
                <div class="ruling-buttons">
                    <button class="btn sustain" onclick="objectionController.ruleOnObjection(${obj.id}, 'sustain')">
                        ✅ SUSTAIN
                    </button>
                    <button class="btn overrule" onclick="objectionController.ruleOnObjection(${obj.id}, 'overrule')">
                        ❌ OVERRULE
                    </button>
                </div>
            </div>
        `;
    }

    // ================= HELPERS =================
    formatType(type) {
        return type.replace(/_/g, ' ').toUpperCase();
    }

    formatTime(isoString) {
        if (!isoString) return '';
        const date = new Date(isoString);
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    addToTranscript(objection) {
        // Would integrate with transcript controller
        console.log('Objection added to transcript:', objection);
    }

    startPolling() {
        // Poll for new objections every 3 seconds
        setInterval(() => this.loadObjections(), 3000);
    }
}
