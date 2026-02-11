/**
 * Phase 2: Virtual Courtroom Infrastructure - Transcript Audio Recorder
 *
 * Records audio and sends to backend for transcription.
 * Handles chunked recording, WebSocket streaming, and transcript updates.
 */

class TranscriptRecorder {
    /**
     * Creates a new TranscriptRecorder instance.
     * @param {number} roundId - The round ID
     * @param {CourtroomState} stateManager - Phase 0 state manager instance
     */
    constructor(roundId, stateManager) {
        this.roundId = roundId;
        this.stateManager = stateManager;
        this.webSocketManager = null;

        // Recording state
        this.isRecording = false;
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.audioStream = null;
        this.recordingStartTime = null;
        this.chunkTimer = null;
        this.chunkInterval = 10000; // 10 seconds

        // Browser support check
        this.isSupported = this.checkBrowserSupport();

        // Bind methods
        this.initialize = this.initialize.bind(this);
        this.checkBrowserSupport = this.checkBrowserSupport.bind(this);
        this.startRecording = this.startRecording.bind(this);
        this.stopRecording = this.stopRecording.bind(this);
        this.handleChunk = this.handleChunk.bind(this);
        this.sendChunkToBackend = this.sendChunkToBackend.bind(this);
        this.handleTranscriptUpdate = this.handleTranscriptUpdate.bind(this);
        this.handleWebSocketMessage = this.handleWebSocketMessage.bind(this);
        this.getCurrentSpeaker = this.getCurrentSpeaker.bind(this);
        this.generateWaveform = this.generateWaveform.bind(this);
        this.cleanup = this.cleanup.bind(this);

        console.log(`[TranscriptRecorder] Initialized for round ${roundId}`);
    }

    /**
     * Initialize the recorder with WebSocket connection.
     * @param {WebSocketManager} webSocketManager - WebSocket manager instance
     */
    initialize(webSocketManager) {
        if (!this.isSupported) {
            console.warn('[TranscriptRecorder] Audio recording not supported in this browser');
            return;
        }

        this.webSocketManager = webSocketManager;

        // Subscribe to WebSocket transcript messages
        this.webSocketManager.onMessage('transcript_update', this.handleWebSocketMessage);
        this.webSocketManager.onMessage('recording_start', this.handleWebSocketMessage);
        this.webSocketManager.onMessage('recording_stop', this.handleWebSocketMessage);

        console.log('[TranscriptRecorder] Recorder initialized with WebSocket');
    }

    /**
     * Check browser support for MediaRecorder API.
     * @returns {boolean} True if supported
     */
    checkBrowserSupport() {
        return !!(navigator.mediaDevices && window.MediaRecorder);
    }

    /**
     * Start audio recording.
     * @returns {Promise<boolean>} Success status
     */
    async startRecording() {
        if (!this.isSupported) {
            console.error('[TranscriptRecorder] Recording not supported');
            this.showWarning('Audio recording is not supported in this browser');
            return false;
        }

        if (this.isRecording) {
            console.warn('[TranscriptRecorder] Already recording');
            return false;
        }

        try {
            // Request audio permission
            this.audioStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    sampleRate: 44100
                }
            });

            // Initialize MediaRecorder with appropriate MIME type
            const mimeType = this.getSupportedMimeType();
            this.mediaRecorder = new MediaRecorder(this.audioStream, {
                mimeType: mimeType,
                audioBitsPerSecond: 128000
            });

            // Handle data available
            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data && event.data.size > 0) {
                    this.audioChunks.push(event.data);
                }
            };

            // Handle recording stop
            this.mediaRecorder.onstop = async () => {
                console.log('[TranscriptRecorder] Recording stopped');
                await this.sendChunksToBackend();
            };

            // Handle errors
            this.mediaRecorder.onerror = (error) => {
                console.error('[TranscriptRecorder] MediaRecorder error:', error);
                this.stopRecording();
            };

            // Start recording
            this.mediaRecorder.start();
            this.isRecording = true;
            this.recordingStartTime = Date.now();
            this.audioChunks = [];

            // Start chunk timer for periodic uploads
            this.chunkTimer = setInterval(this.handleChunk, this.chunkInterval);

            // Update UI
            this.updateRecordingUI(true);

            // Broadcast via WebSocket
            this.webSocketManager?.sendMessage({
                event: 'recording_start',
                data: {
                    round_id: this.roundId,
                    timestamp: new Date().toISOString()
                }
            });

            console.log('[TranscriptRecorder] Recording started');
            return true;

        } catch (error) {
            console.error('[TranscriptRecorder] Failed to start recording:', error);
            this.showWarning(`Failed to start recording: ${error.message}`);
            return false;
        }
    }

    /**
     * Stop audio recording.
     * @returns {Promise<void>}
     */
    async stopRecording() {
        if (!this.isRecording) {
            return;
        }

        // Stop chunk timer
        if (this.chunkTimer) {
            clearInterval(this.chunkTimer);
            this.chunkTimer = null;
        }

        // Stop MediaRecorder
        if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
            this.mediaRecorder.stop();
        }

        // Stop audio stream
        if (this.audioStream) {
            this.audioStream.getTracks().forEach(track => track.stop());
            this.audioStream = null;
        }

        this.isRecording = false;

        // Update UI
        this.updateRecordingUI(false);

        // Broadcast via WebSocket
        this.webSocketManager?.sendMessage({
            event: 'recording_stop',
            data: {
                round_id: this.roundId,
                duration: Date.now() - this.recordingStartTime,
                timestamp: new Date().toISOString()
            }
        });

        console.log('[TranscriptRecorder] Recording stopped');
    }

    /**
     * Handle chunk timer - send current chunks to backend.
     */
    async handleChunk() {
        if (!this.isRecording || this.audioChunks.length === 0) {
            return;
        }

        // Create a copy of chunks and reset
        const chunksToSend = [...this.audioChunks];
        this.audioChunks = [];

        // Send to backend
        await this.sendChunkToBackend(chunksToSend, false);
    }

    /**
     * Send audio chunks to backend.
     * @param {Array<Blob>} chunks - Audio chunks
     * @param {boolean} isFinal - Whether this is the final batch
     * @returns {Promise<Object>} Upload result
     */
    async sendChunkToBackend(chunks, isFinal = false) {
        if (!chunks || chunks.length === 0) {
            return null;
        }

        // Combine chunks into single blob
        const combinedBlob = new Blob(chunks, { type: chunks[0].type });

        // Create form data
        const formData = new FormData();
        formData.append('audio', combinedBlob, `chunk-${Date.now()}.webm`);
        formData.append('round_id', this.roundId.toString());
        formData.append('speaker_role', this.getCurrentSpeaker());
        formData.append('timestamp', new Date().toISOString());
        formData.append('is_final', isFinal.toString());

        // Retry logic with exponential backoff
        const maxRetries = 3;
        let lastError = null;

        for (let attempt = 0; attempt < maxRetries; attempt++) {
            try {
                const token = localStorage.getItem('access_token') || '';
                const response = await fetch(
                    `/api/oral-rounds/${this.roundId}/audio/chunk`,
                    {
                        method: 'POST',
                        headers: {
                            'Authorization': `Bearer ${token}`
                        },
                        body: formData
                    }
                );

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }

                const result = await response.json();
                console.log('[TranscriptRecorder] Chunk uploaded:', result);

                // Handle transcript update if returned
                if (result.transcript) {
                    this.handleTranscriptUpdate({
                        segment_id: result.segment_id,
                        speaker_role: result.speaker_role || this.getCurrentSpeaker(),
                        text: result.transcript,
                        confidence: result.confidence || 0.95,
                        timestamp: new Date().toISOString()
                    });
                }

                return result;

            } catch (error) {
                lastError = error;
                console.warn(`[TranscriptRecorder] Upload attempt ${attempt + 1} failed:`, error);

                // Exponential backoff: 1s, 2s, 4s
                if (attempt < maxRetries - 1) {
                    await this.delay(1000 * Math.pow(2, attempt));
                }
            }
        }

        console.error('[TranscriptRecorder] All upload attempts failed:', lastError);
        throw lastError;
    }

    /**
     * Send all remaining chunks to backend (final upload).
     * @returns {Promise<void>}
     */
    async sendChunksToBackend() {
        if (this.audioChunks.length === 0) {
            return;
        }

        try {
            await this.sendChunkToBackend(this.audioChunks, true);
            this.audioChunks = [];
        } catch (error) {
            console.error('[TranscriptRecorder] Failed to send final chunks:', error);
        }
    }

    /**
     * Handle incoming transcript update from backend.
     * @param {Object} data - Transcript segment data
     */
    handleTranscriptUpdate(data) {
        // Create transcript segment
        const segment = {
            id: data.segment_id,
            speakerRole: data.speaker_role,
            text: data.text,
            timestamp: data.timestamp,
            confidence: data.confidence,
            isFinal: data.is_final || true
        };

        // Update state
        const currentTranscript = this.stateManager.state.transcript;
        this.stateManager.setState({
            transcript: [...currentTranscript, segment]
        });

        console.log('[TranscriptRecorder] Transcript updated:', segment);
    }

    /**
     * Handle incoming WebSocket messages.
     * @param {Object} message - WebSocket message
     */
    handleWebSocketMessage(message) {
        const { event, data } = message;

        console.log(`[TranscriptRecorder] Received WebSocket message: ${event}`);

        switch (event) {
            case 'transcript_update':
                this.handleTranscriptUpdate(data);
                break;
            case 'recording_start':
                // Sync recording state from other clients
                this.updateRecordingUI(true);
                break;
            case 'recording_stop':
                // Sync recording state from other clients
                this.updateRecordingUI(false);
                break;
            default:
                console.warn(`[TranscriptRecorder] Unknown event: ${event}`);
        }
    }

    /**
     * Get current speaker from state.
     * @returns {string} Speaker role
     */
    getCurrentSpeaker() {
        return this.stateManager.state.timer.currentSpeaker || 'unknown';
    }

    /**
     * Get supported MIME type for MediaRecorder.
     * @returns {string} MIME type
     */
    getSupportedMimeType() {
        const types = [
            'audio/webm;codecs=opus',
            'audio/webm',
            'audio/ogg;codecs=opus',
            'audio/ogg',
            'audio/mp4',
            'audio/wav'
        ];

        for (const type of types) {
            if (MediaRecorder.isTypeSupported(type)) {
                return type;
            }
        }

        return 'audio/webm';
    }

    /**
     * Update recording UI.
     * @param {boolean} isRecording - Recording state
     */
    updateRecordingUI(isRecording) {
        // Update recording indicator
        const indicator = document.getElementById('recording-indicator');
        if (indicator) {
            indicator.classList.toggle('recording', isRecording);
            indicator.setAttribute('aria-label', isRecording ? 'Recording in progress' : 'Not recording');
        }

        // Update waveform visualization
        const waveform = document.getElementById('waveform-canvas');
        if (waveform) {
            waveform.classList.toggle('active', isRecording);
        }

        // Update button
        const recordButton = document.getElementById('record-button');
        if (recordButton) {
            recordButton.textContent = isRecording ? '⏹ Stop Recording' : '⏺ Start Recording';
            recordButton.setAttribute('aria-pressed', isRecording);
        }
    }

    /**
     * Generate waveform visualization.
     * @param {AnalyserNode} analyser - Audio analyser node
     */
    generateWaveform(analyser) {
        const canvas = document.getElementById('waveform-canvas');
        if (!canvas || !analyser) return;

        const ctx = canvas.getContext('2d');
        const bufferLength = analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);

        const draw = () => {
            if (!this.isRecording) {
                // Clear canvas when not recording
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                return;
            }

            requestAnimationFrame(draw);

            analyser.getByteTimeDomainData(dataArray);

            ctx.fillStyle = '#0f3460';
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            ctx.lineWidth = 2;
            ctx.strokeStyle = '#4CAF50';
            ctx.beginPath();

            const sliceWidth = canvas.width / bufferLength;
            let x = 0;

            for (let i = 0; i < bufferLength; i++) {
                const v = dataArray[i] / 128.0;
                const y = (v * canvas.height) / 2;

                if (i === 0) {
                    ctx.moveTo(x, y);
                } else {
                    ctx.lineTo(x, y);
                }

                x += sliceWidth;
            }

            ctx.lineTo(canvas.width, canvas.height / 2);
            ctx.stroke();
        };

        draw();
    }

    /**
     * Show warning message.
     * @param {string} message - Warning message
     */
    showWarning(message) {
        const warningEl = document.getElementById('recording-warning');
        if (warningEl) {
            warningEl.textContent = message;
            warningEl.style.display = 'block';
            setTimeout(() => {
                warningEl.style.display = 'none';
            }, 5000);
        } else {
            alert(message);
        }
    }

    /**
     * Utility: Delay promise.
     * @param {number} ms - Milliseconds to delay
     * @returns {Promise<void>}
     */
    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * Get recording duration.
     * @returns {number} Duration in milliseconds
     */
    getRecordingDuration() {
        if (!this.isRecording || !this.recordingStartTime) {
            return 0;
        }
        return Date.now() - this.recordingStartTime;
    }

    /**
     * Format duration as MM:SS.
     * @returns {string} Formatted duration
     */
    getFormattedDuration() {
        const duration = this.getRecordingDuration();
        const seconds = Math.floor(duration / 1000);
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = seconds % 60;
        return `${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`;
    }

    /**
     * Check if recording is in progress.
     * @returns {boolean} Recording state
     */
    isCurrentlyRecording() {
        return this.isRecording;
    }

    /**
     * Check if recording is supported.
     * @returns {boolean} Support status
     */
    isRecordingSupported() {
        return this.isSupported;
    }

    /**
     * Cleanup resources.
     */
    cleanup() {
        this.stopRecording();

        if (this.webSocketManager) {
            this.webSocketManager.offMessage('transcript_update', this.handleWebSocketMessage);
            this.webSocketManager.offMessage('recording_start', this.handleWebSocketMessage);
            this.webSocketManager.offMessage('recording_stop', this.handleWebSocketMessage);
        }

        this.audioChunks = [];
        console.log('[TranscriptRecorder] Cleaned up');
    }
}

// Export for module use
if (typeof module !== 'undefined' && module.exports) {
    module.exports = TranscriptRecorder;
}
