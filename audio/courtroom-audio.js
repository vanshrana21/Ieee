/**
 * Phase 2: Virtual Courtroom Infrastructure - Audio Manager
 *
 * Manages audio cues for timer events using Web Audio API.
 * Fallback to HTML5 Audio for older browsers.
 */

class CourtroomAudio {
    /**
     * Creates a new CourtroomAudio instance.
     */
    constructor() {
        this.audioContext = null;
        this.audioBuffers = {};
        this.isMuted = false;
        this.volume = 0.7;
        this.isInitialized = false;
        this.fallbackMode = false;

        // Audio file paths
        this.audioFiles = {
            start: '/audio/start.mp3',
            pause: '/audio/pause.mp3',
            resume: '/audio/resume.mp3',
            reset: '/audio/reset.mp3',
            warning: '/audio/warning.mp3',
            urgent: '/audio/urgent.mp3',
            gavel: '/audio/gavel.mp3',
            sustained: '/audio/sustained.mp3',
            overruled: '/audio/overruled.mp3',
            objection: '/audio/objection.mp3'
        };

        // Bind methods
        this.initialize = this.initialize.bind(this);
        this.checkBrowserSupport = this.checkBrowserSupport.bind(this);
        this.preloadAudio = this.preloadAudio.bind(this);
        this.loadAudioFile = this.loadAudioFile.bind(this);
        this.generateTone = this.generateTone.bind(this);
        this.play = this.play.bind(this);
        this.playFromBuffer = this.playFromBuffer.bind(this);
        this.setVolume = this.setVolume.bind(this);
        this.toggleMute = this.toggleMute.bind(this);
        this.cleanup = this.cleanup.bind(this);

        console.log('[CourtroomAudio] Audio manager created');
    }

    /**
     * Initialize the audio manager.
     */
    async initialize() {
        if (this.isInitialized) {
            return;
        }

        // Check browser support
        if (!this.checkBrowserSupport()) {
            console.warn('[CourtroomAudio] Web Audio API not supported, using fallback');
            this.fallbackMode = true;
            this.isInitialized = true;
            return;
        }

        // Create audio context
        try {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            
            // Resume audio context if suspended (browser autoplay policy)
            if (this.audioContext.state === 'suspended') {
                await this.audioContext.resume();
            }
        } catch (error) {
            console.error('[CourtroomAudio] Failed to create AudioContext:', error);
            this.fallbackMode = true;
            this.isInitialized = true;
            return;
        }

        // Preload audio files
        await this.preloadAudio();

        this.isInitialized = true;
        console.log('[CourtroomAudio] Audio manager initialized');
    }

    /**
     * Check browser support for Web Audio API.
     * @returns {boolean} True if supported
     */
    checkBrowserSupport() {
        return !!(window.AudioContext || window.webkitAudioContext);
    }

    /**
     * Preload all audio files.
     */
    async preloadAudio() {
        const loadPromises = Object.entries(this.audioFiles).map(async ([key, path]) => {
            try {
                const buffer = await this.loadAudioFile(path);
                this.audioBuffers[key] = buffer;
                console.log(`[CourtroomAudio] Loaded: ${key}`);
            } catch (error) {
                console.warn(`[CourtroomAudio] Failed to load ${key}, using generated tone`);
                this.audioBuffers[key] = null;
            }
        });

        await Promise.all(loadPromises);
    }

    /**
     * Load an audio file from path.
     * @param {string} path - Audio file path
     * @returns {Promise<AudioBuffer>} Audio buffer
     */
    async loadAudioFile(path) {
        try {
            const response = await fetch(path);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const arrayBuffer = await response.arrayBuffer();
            return await this.audioContext.decodeAudioData(arrayBuffer);
        } catch (error) {
            throw new Error(`Failed to load audio: ${error.message}`);
        }
    }

    /**
     * Generate a tone for fallback when audio file unavailable.
     * @param {number} frequency - Tone frequency in Hz
     * @param {number} duration - Duration in seconds
     * @param {string} type - Oscillator type
     * @returns {AudioBuffer} Generated audio buffer
     */
    generateTone(frequency = 440, duration = 0.5, type = 'sine') {
        if (!this.audioContext) {
            return null;
        }

        const sampleRate = this.audioContext.sampleRate;
        const frameCount = sampleRate * duration;
        const buffer = this.audioContext.createBuffer(1, frameCount, sampleRate);
        const data = buffer.getChannelData(0);

        for (let i = 0; i < frameCount; i++) {
            data[i] = Math.sin(2 * Math.PI * frequency * i / sampleRate);
            // Apply simple envelope
            if (i < sampleRate * 0.01) {
                data[i] *= i / (sampleRate * 0.01);
            } else if (i > frameCount - sampleRate * 0.01) {
                data[i] *= (frameCount - i) / (sampleRate * 0.01);
            }
        }

        return buffer;
    }

    /**
     * Play an audio cue.
     * @param {string} cue - Audio cue name
     */
    async play(cue) {
        if (this.isMuted) {
            console.log(`[CourtroomAudio] Muted, skipping: ${cue}`);
            return;
        }

        // Initialize if not already
        if (!this.isInitialized) {
            await this.initialize();
        }

        // Fallback mode: use alert for critical cues
        if (this.fallbackMode) {
            if (cue === 'gavel' || cue === 'urgent') {
                // Visual fallback
                console.log(`[CourtroomAudio] FALLBACK - ${cue.toUpperCase()} AUDIO CUE`);
            }
            return;
        }

        // Resume audio context if needed (browser autoplay policy)
        if (this.audioContext.state === 'suspended') {
            await this.audioContext.resume();
        }

        const buffer = this.audioBuffers[cue];

        if (buffer) {
            // Play preloaded buffer
            this.playFromBuffer(buffer);
        } else {
            // Generate and play fallback tone
            const generatedBuffer = this.getFallbackTone(cue);
            if (generatedBuffer) {
                this.playFromBuffer(generatedBuffer);
            }
        }

        console.log(`[CourtroomAudio] Playing: ${cue}`);
    }

    /**
     * Play audio from buffer.
     * @param {AudioBuffer} buffer - Audio buffer to play
     */
    playFromBuffer(buffer) {
        if (!this.audioContext) return;

        const source = this.audioContext.createBufferSource();
        source.buffer = buffer;

        const gainNode = this.audioContext.createGain();
        gainNode.gain.value = this.volume;

        source.connect(gainNode);
        gainNode.connect(this.audioContext.destination);

        source.start(0);
    }

    /**
     * Get fallback tone for a cue.
     * @param {string} cue - Audio cue name
     * @returns {AudioBuffer|null} Generated buffer
     */
    getFallbackTone(cue) {
        const tones = {
            start: { frequency: 880, duration: 0.1, type: 'sine' },
            pause: { frequency: 440, duration: 0.2, type: 'sine' },
            resume: { frequency: 660, duration: 0.15, type: 'sine' },
            reset: { frequency: 330, duration: 0.3, type: 'sine' },
            warning: { frequency: 800, duration: 2.0, type: 'square' },
            urgent: { frequency: 1000, duration: 3.0, type: 'sawtooth' },
            gavel: { frequency: 200, duration: 1.0, type: 'square' },
            sustained: { frequency: 600, duration: 0.5, type: 'sine' },
            overruled: { frequency: 300, duration: 0.5, type: 'sawtooth' },
            objection: { frequency: 750, duration: 0.4, type: 'square' }
        };

        const config = tones[cue];
        if (!config) return null;

        return this.generateTone(config.frequency, config.duration, config.type);
    }

    /**
     * Set volume level.
     * @param {number} vol - Volume level 0.0-1.0
     */
    setVolume(vol) {
        this.volume = Math.max(0, Math.min(1, vol));
        console.log(`[CourtroomAudio] Volume set to: ${this.volume}`);
    }

    /**
     * Toggle mute state.
     * @returns {boolean} New mute state
     */
    toggleMute() {
        this.isMuted = !this.isMuted;
        console.log(`[CourtroomAudio] Muted: ${this.isMuted}`);
        return this.isMuted;
    }

    /**
     * Get mute state.
     * @returns {boolean} Current mute state
     */
    getMuteState() {
        return this.isMuted;
    }

    /**
     * Check if audio is initialized.
     * @returns {boolean} Initialization state
     */
    isReady() {
        return this.isInitialized;
    }

    /**
     * Check if using fallback mode.
     * @returns {boolean} Fallback mode state
     */
    isInFallbackMode() {
        return this.fallbackMode;
    }

    /**
     * Cleanup resources.
     */
    cleanup() {
        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }
        this.audioBuffers = {};
        this.isInitialized = false;
        console.log('[CourtroomAudio] Audio manager cleaned up');
    }
}

// Create global instance
window.courtroomAudio = new CourtroomAudio();

// Export for module use
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CourtroomAudio;
}
