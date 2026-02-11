/**
 * js/transcript-controller.js
 * Phase 3.3 + Speech-to-Text: Transcript Controller with Audio Recording
 * Handles transcript display, audio chunking, Whisper transcription, and export
 */

class TranscriptController {
    constructor(roundId) {
        this.roundId = roundId;
        this.entries = [];
        this.baseUrl = 'http://localhost:8000/api';
        this.isJudge = false;
        
        // Audio recording state
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.chunkIndex = 0;
        this.isRecording = false;
        this.currentSpeaker = 'petitioner';
        this.chunkInterval = null;
        this.pendingChunks = new Map();
        
        this.init();
    }

    init() {
        this.checkUserRole();
        this.loadTranscript();
        this.startPolling();
        this.setupAudioRecording();
    }

    // ================= AUDIO RECORDING (NEW) =================

    setupAudioRecording() {
        // Check browser support
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            console.warn('MediaRecorder not supported in this browser');
            this.showManualEntryFallback();
            return;
        }
        
        // Setup UI event listeners
        const startBtn = document.getElementById('btn-start-recording');
        const stopBtn = document.getElementById('btn-stop-recording');
        
        if (startBtn) {
            startBtn.addEventListener('click', () => this.startRecording());
        }
        if (stopBtn) {
            stopBtn.addEventListener('click', () => this.stopRecording());
        }
    }

    async startRecording() {
        try {
            // Get microphone access
            const stream = await navigator.mediaDevices.getUserMedia({ 
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    sampleRate: 16000
                } 
            });
            
            // Create MediaRecorder with 10-second timeslice
            this.mediaRecorder = new MediaRecorder(stream, {
                mimeType: 'audio/webm;codecs=opus'
            });
            
            this.audioChunks = [];
            this.chunkIndex = 0;
            this.isRecording = true;
            
            // Handle data available (every 10 seconds)
            this.mediaRecorder.ondataavailable = async (event) => {
                if (event.data.size > 0) {
                    await this.processAudioChunk(event.data);
                }
            };
            
            // Start recording with 10-second chunks
            this.mediaRecorder.start(10000);
            
            // Update UI
            this.updateRecordingUI(true);
            this.startWaveformVisualization(stream);
            
            console.log('Recording started (10s chunks)');
            
        } catch (error) {
            console.error('Error starting recording:', error);
            alert('Could not access microphone. Please check permissions or use manual entry.');
            this.showManualEntryFallback();
        }
    }

    stopRecording() {
        if (this.mediaRecorder && this.isRecording) {
            this.mediaRecorder.stop();
            this.isRecording = false;
            
            // Stop all tracks
            this.mediaRecorder.stream.getTracks().forEach(track => track.stop());
            
            // Update UI
            this.updateRecordingUI(false);
            this.stopWaveformVisualization();
            
            console.log('Recording stopped');
        }
    }

    async processAudioChunk(blob) {
        const chunkId = `chunk-${Date.now()}-${this.chunkIndex}`;
        this.chunkIndex++;
        
        // Track pending chunk
        this.pendingChunks.set(chunkId, {
            status: 'uploading',
            speakerRole: this.currentSpeaker,
            chunkIndex: this.chunkIndex
        });
        
        // Update UI
        this.updateChunkProgress(chunkId, 'uploading');
        
        try {
            // Create form data
            const formData = new FormData();
            formData.append('audio', blob, `chunk-${this.chunkIndex}.webm`);
            formData.append('speaker_role', this.currentSpeaker);
            formData.append('chunk_index', this.chunkIndex);
            
            // Upload chunk
            const token = this.getAuthToken();
            const response = await fetch(
                `${this.baseUrl}/oral-rounds/${this.roundId}/audio/chunk`,
                {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`
                    },
                    body: formData
                }
            );
            
            if (response.ok) {
                const result = await response.json();
                
                // Update tracking
                this.pendingChunks.set(chunkId, {
                    ...this.pendingChunks.get(chunkId),
                    serverChunkId: result.chunk_id,
                    status: 'processing'
                });
                
                this.updateChunkProgress(chunkId, 'processing', result.chunk_id);
                
                // Start polling for transcription
                this.pollChunkTranscription(result.chunk_id);
                
            } else {
                const error = await response.json();
                console.error('Chunk upload failed:', error);
                this.pendingChunks.set(chunkId, { status: 'failed', error: error.detail });
                this.updateChunkProgress(chunkId, 'failed');
            }
            
        } catch (error) {
            console.error('Error uploading chunk:', error);
            this.pendingChunks.set(chunkId, { status: 'failed', error: error.message });
            this.updateChunkProgress(chunkId, 'failed');
        }
    }

    async pollChunkTranscription(chunkId) {
        const maxAttempts = 30; // 30 seconds max
        let attempts = 0;
        
        const poll = async () => {
            if (attempts >= maxAttempts) {
                console.warn(`Transcription timeout for chunk ${chunkId}`);
                this.showTranscriptionFallback(chunkId);
                return;
            }
            
            try {
                const token = this.getAuthToken();
                const response = await fetch(
                    `${this.baseUrl}/oral-rounds/${this.roundId}/audio/chunk/${chunkId}/status`,
                    {
                        headers: { 'Authorization': `Bearer ${token}` }
                    }
                );
                
                if (response.ok) {
                    const status = await response.json();
                    
                    if (status.status === 'completed') {
                        // Add transcript entry
                        this.addTranscriptEntry({
                            id: `whisper-${chunkId}`,
                            content: status.transcript_text,
                            speaker_name: status.speaker_role.toUpperCase(),
                            speaker_role: status.speaker_role,
                            team_side: status.speaker_role,
                            entry_type: 'statement',
                            timestamp: new Date().toISOString(),
                            source: 'whisper',
                            confidence: status.confidence
                        });
                        
                        this.updateChunkProgress(chunkId, 'completed');
                        return;
                        
                    } else if (status.status === 'failed') {
                        console.error(`Transcription failed for chunk ${chunkId}:`, status.error);
                        this.showTranscriptionFallback(chunkId);
                        this.updateChunkProgress(chunkId, 'failed');
                        return;
                    }
                }
                
                // Continue polling
                attempts++;
                setTimeout(poll, 1000);
                
            } catch (error) {
                console.error('Error polling chunk status:', error);
                attempts++;
                setTimeout(poll, 1000);
            }
        };
        
        poll();
    }

    showTranscriptionFallback(chunkId) {
        const fallbackDiv = document.createElement('div');
        fallbackDiv.className = 'transcription-fallback';
        fallbackDiv.innerHTML = `
            <div class="fallback-notice">
                <span>⚠️</span> Audio chunk not transcribed. 
                <button onclick="this.closest('.transcription-fallback').querySelector('.fallback-entry').classList.toggle('hidden')">
                    Add manually
                </button>
            </div>
            <div class="fallback-entry hidden">
                <textarea placeholder="Enter transcript text..."></textarea>
                <button onclick="transcriptController.submitManualEntry(this)">Submit</button>
            </div>
        `;
        
        const container = document.getElementById('transcript-content');
        if (container) {
            container.appendChild(fallbackDiv);
            container.scrollTop = container.scrollHeight;
        }
    }

    submitManualEntry(button) {
        const textarea = button.previousElementSibling;
        const content = textarea.value.trim();
        
        if (content) {
            this.addTranscriptEntry({
                content: content,
                speaker_name: this.currentSpeaker.toUpperCase(),
                speaker_role: this.currentSpeaker,
                entry_type: 'statement',
                timestamp: new Date().toISOString(),
                source: 'manual'
            });
            
            button.closest('.transcription-fallback').remove();
        }
    }

    startWaveformVisualization(stream) {
        const canvas = document.getElementById('waveform-canvas');
        if (!canvas) return;
        
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const analyser = audioContext.createAnalyser();
        const microphone = audioContext.createMediaStreamSource(stream);
        
        microphone.connect(analyser);
        analyser.fftSize = 256;
        
        const bufferLength = analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);
        const ctx = canvas.getContext('2d');
        
        const draw = () => {
            if (!this.isRecording) return;
            
            requestAnimationFrame(draw);
            
            analyser.getByteFrequencyData(dataArray);
            
            ctx.fillStyle = '#1a1a2e';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            
            const barWidth = (canvas.width / bufferLength) * 2.5;
            let barHeight;
            let x = 0;
            
            for (let i = 0; i < bufferLength; i++) {
                barHeight = dataArray[i] / 2;
                const r = barHeight + 25 * (i / bufferLength);
                const g = 250 * (i / bufferLength);
                const b = 50;
                
                ctx.fillStyle = `rgb(${r},${g},${b})`;
                ctx.fillRect(x, canvas.height - barHeight, barWidth, barHeight);
                
                x += barWidth + 1;
            }
        };
        
        this.waveformAnimation = draw;
        draw();
    }

    stopWaveformVisualization() {
        const canvas = document.getElementById('waveform-canvas');
        if (canvas) {
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        }
        this.waveformAnimation = null;
    }

    updateRecordingUI(isRecording) {
        const startBtn = document.getElementById('btn-start-recording');
        const stopBtn = document.getElementById('btn-stop-recording');
        const statusEl = document.getElementById('recording-status');
        
        if (isRecording) {
            startBtn?.classList.add('hidden');
            stopBtn?.classList.remove('hidden');
            if (statusEl) {
                statusEl.textContent = '🔴 Recording...';
                statusEl.classList.add('recording');
            }
        } else {
            startBtn?.classList.remove('hidden');
            stopBtn?.classList.add('hidden');
            if (statusEl) {
                statusEl.textContent = '⏹ Stopped';
                statusEl.classList.remove('recording');
            }
        }
    }

    updateChunkProgress(chunkId, status, serverChunkId = null) {
        const progressContainer = document.getElementById('chunk-progress');
        if (!progressContainer) return;
        
        let indicator = document.getElementById(`chunk-${chunkId}`);
        if (!indicator) {
            indicator = document.createElement('div');
            indicator.id = `chunk-${chunkId}`;
            indicator.className = 'chunk-indicator';
            progressContainer.appendChild(indicator);
        }
        
        indicator.className = `chunk-indicator ${status}`;
        indicator.title = serverChunkId || chunkId;
        
        if (status === 'completed') {
            indicator.innerHTML = '✓';
        } else if (status === 'failed') {
            indicator.innerHTML = '✗';
        } else if (status === 'processing') {
            indicator.innerHTML = '⏳';
        } else {
            indicator.innerHTML = '↑';
        }
    }

    showManualEntryFallback() {
        const fallbackPanel = document.getElementById('manual-entry-panel');
        if (fallbackPanel) {
            fallbackPanel.classList.remove('hidden');
        }
    }

    setSpeakerRole(role) {
        this.currentSpeaker = role;
        
        document.querySelectorAll('.speaker-btn').forEach(btn => {
            btn.classList.remove('active');
            if (btn.dataset.role === role) {
                btn.classList.add('active');
            }
        });
        
        console.log(`Speaker role set to: ${role}`);
    }

    // ================= ORIGINAL TRANSCRIPT METHODS =================

    checkUserRole() {
        const token = this.getAuthToken();
        if (token) {
            try {
                const payload = JSON.parse(atob(token.split('.')[1]));
                this.isJudge = ['JUDGE', 'FACULTY', 'ADMIN', 'SUPER_ADMIN'].includes(payload.role);
                
                if (this.isJudge) {
                    document.getElementById('add-entry-panel')?.classList.remove('hidden');
                    document.getElementById('finalize-transcript-btn')?.classList.remove('hidden');
                }
            } catch (e) {
                console.error('Error decoding token:', e);
            }
        }
    }

    getAuthToken() {
        return localStorage.getItem('access_token') || '';
    }

    openModal() {
        const modal = document.getElementById('transcript-modal');
        modal?.classList.add('show');
        this.loadTranscript();
    }

    closeModal() {
        const modal = document.getElementById('transcript-modal');
        modal?.classList.remove('show');
    }

    async loadTranscript() {
        try {
            const token = this.getAuthToken();
            
            // Load both manual entries and live transcript segments
            const [entriesResponse, liveResponse] = await Promise.all([
                fetch(`${this.baseUrl}/oral-rounds/${this.roundId}/transcripts`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                }),
                fetch(`${this.baseUrl}/oral-rounds/${this.roundId}/transcripts/live`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                })
            ]);
            
            let allEntries = [];
            
            if (entriesResponse.ok) {
                const manualEntries = await entriesResponse.json();
                allEntries = allEntries.concat(manualEntries);
            }
            
            if (liveResponse.ok) {
                const liveData = await liveResponse.json();
                const liveEntries = liveData.segments.map(seg => ({
                    id: `live-${seg.chunk_id}`,
                    content: seg.text,
                    speaker_name: seg.speaker_role.toUpperCase(),
                    speaker_role: seg.speaker_role,
                    team_side: seg.speaker_role,
                    entry_type: 'statement',
                    timestamp: seg.timestamp,
                    source: 'whisper',
                    confidence: seg.confidence
                }));
                allEntries = allEntries.concat(liveEntries);
            }
            
            // Sort by timestamp
            allEntries.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
            
            this.entries = allEntries;
            this.renderTranscript(allEntries);
            this.renderPreview(allEntries.slice(-5));
            this.updateStats(allEntries);
            
        } catch (error) {
            console.error('Error loading transcript:', error);
        }
    }

    addTranscriptEntry(entry) {
        this.entries.push(entry);
        this.renderTranscript(this.entries);
        this.renderPreview(this.entries.slice(-5));
        this.updateStats(this.entries);
    }

    async addEntry() {
        const speaker = document.getElementById('entry-speaker').value;
        const type = document.getElementById('entry-type').value;
        const content = document.getElementById('entry-content').value;

        if (!content.trim()) {
            alert('Please enter transcript content');
            return;
        }

        const token = this.getAuthToken();
        const payload = {
            content: content,
            entry_type: type,
            round_stage: 'arguments',
            team_side: speaker.includes('petitioner') ? 'petitioner' : 
                      speaker.includes('respondent') ? 'respondent' : null,
            speaker_role: speaker,
            source: 'manual_entry'
        };

        try {
            const response = await fetch(`${this.baseUrl}/oral-rounds/${this.roundId}/transcripts`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });

            if (response.ok) {
                document.getElementById('entry-content').value = '';
                this.loadTranscript();
            } else {
                const error = await response.json();
                alert(`Error: ${error.detail || 'Failed to add entry'}`);
            }
        } catch (error) {
            console.error('Error adding entry:', error);
            alert('Network error. Please try again.');
        }
    }

    async finalizeTranscript() {
        if (!this.isJudge) {
            alert('Only judges can finalize transcripts');
            return;
        }
        
        if (!confirm('Are you sure you want to finalize this transcript? This will complete all audio processing.')) {
            return;
        }
        
        try {
            const token = this.getAuthToken();
            const response = await fetch(
                `${this.baseUrl}/oral-rounds/${this.roundId}/transcripts/finalize`,
                {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    }
                }
            );
            
            if (response.ok) {
                const result = await response.json();
                alert(`Transcript finalized! ${result.word_count} words from ${result.completed_chunks} audio chunks.`);
                this.loadTranscript();
            } else {
                const error = await response.json();
                alert(`Error: ${error.detail || 'Failed to finalize transcript'}`);
            }
        } catch (error) {
            console.error('Error finalizing transcript:', error);
            alert('Network error. Please try again.');
        }
    }

    async exportTranscript() {
        const token = this.getAuthToken();
        
        try {
            const response = await fetch(
                `${this.baseUrl}/oral-rounds/${this.roundId}/transcripts/export`,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );

            if (response.ok) {
                const data = await response.json();
                this.downloadTranscript(data);
            } else {
                alert('Failed to export transcript');
            }
        } catch (error) {
            console.error('Error exporting transcript:', error);
        }
    }

    renderTranscript(entries) {
        const container = document.getElementById('transcript-content');
        if (!container) return;

        if (entries.length === 0) {
            container.innerHTML = '<div class="transcript-loading"><p>No transcript entries yet. Start recording to capture speech.</p></div>';
            return;
        }

        container.innerHTML = entries.map(entry => this.createEntryHTML(entry)).join('');
        
        container.scrollTop = container.scrollHeight;
    }

    createEntryHTML(entry) {
        const time = this.formatTime(entry.timestamp);
        const sideClass = entry.team_side || (entry.speaker_role === 'judge' ? 'judge' : '');
        const typeClass = entry.entry_type === 'objection' ? 'objection' : 
                         entry.entry_type === 'ruling' ? 'ruling' : '';
        
        let confidenceBadge = '';
        if (entry.source === 'whisper' && entry.confidence !== undefined) {
            const confidenceClass = entry.confidence > 0.9 ? 'high' : 
                                   entry.confidence > 0.7 ? 'medium' : 'low';
            confidenceBadge = `<span class="confidence-badge ${confidenceClass}" title="Transcription confidence: ${(entry.confidence * 100).toFixed(1)}%">🎙️</span>`;
        }
        
        let content = entry.content;
        if (entry.entry_type === 'objection') {
            content = `OBJECTION: ${content}`;
        } else if (entry.entry_type === 'ruling') {
            content = `RULING: ${content}`;
        }

        return `
            <div class="transcript-entry ${sideClass} ${typeClass}" data-source="${entry.source || 'manual'}">
                <div class="entry-meta">
                    <div class="entry-time">${time}</div>
                    <div class="entry-speaker ${sideClass}">${entry.speaker_name}</div>
                    ${confidenceBadge}
                    ${entry.entry_type !== 'statement' ? `<span class="entry-type-badge">${entry.entry_type}</span>` : ''}
                </div>
                <div class="entry-content ${typeClass}-text">${this.escapeHtml(content)}</div>
            </div>
        `;
    }

    renderPreview(entries) {
        const container = document.getElementById('transcript-preview');
        if (!container) return;

        if (entries.length === 0) {
            container.innerHTML = '<div class="preview-empty"><p>No transcript entries yet</p></div>';
            return;
        }

        container.innerHTML = entries.map(entry => this.createPreviewHTML(entry)).join('');
    }

    createPreviewHTML(entry) {
        const shortContent = entry.content.length > 50 ? 
            entry.content.substring(0, 50) + '...' : entry.content;
        
        return `
            <div class="preview-entry">
                <span class="speaker">${entry.speaker_name}:</span>
                <span class="text">${this.escapeHtml(shortContent)}</span>
            </div>
        `;
    }

    updateStats(entries) {
        const countEl = document.getElementById('entry-count');
        const updatedEl = document.getElementById('last-updated');
        
        if (countEl) {
            countEl.textContent = `${entries.length} entries`;
        }
        if (updatedEl) {
            updatedEl.textContent = `Updated: ${new Date().toLocaleTimeString()}`;
        }
    }

    applyFilter() {
        const typeFilter = document.getElementById('filter-type').value;
        const sideFilter = document.getElementById('filter-side').value;
        
        let filtered = this.entries;
        
        if (typeFilter) {
            filtered = filtered.filter(e => e.entry_type === typeFilter);
        }
        
        if (sideFilter) {
            filtered = filtered.filter(e => e.team_side === sideFilter);
        }
        
        this.renderTranscript(filtered);
    }

    downloadTranscript(data) {
        let content = `COURTROOM TRANSCRIPT\n`;
        content += `Round ID: ${this.roundId}\n`;
        content += `Generated: ${new Date().toLocaleString()}\n`;
        content += `Total Entries: ${data.total_entries || this.entries.length}\n`;
        content += `========================================\n\n`;

        this.entries.forEach(entry => {
            const time = this.formatTime(entry.timestamp);
            const source = entry.source === 'whisper' ? ' [AUTO]' : '';
            content += `[${time}] ${entry.speaker_name}${source}: ${entry.content}\n\n`;
        });

        const blob = new Blob([content], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `transcript_round_${this.roundId}_${Date.now()}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    formatTime(isoString) {
        if (!isoString) return '';
        const date = new Date(isoString);
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    startPolling() {
        // Poll for new entries every 3 seconds
        setInterval(() => this.loadTranscript(), 3000);
    }
}
