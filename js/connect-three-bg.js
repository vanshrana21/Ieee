/**
 * Connect Three Canvas Animation
 * A Codrops/Tympanus-inspired network animation for login backgrounds
 * Vanilla JavaScript + Canvas (no external dependencies)
 * 
 * Enhanced version with dense particles, high connection density,
 * and smooth parallax mouse interaction
 */

(function () {
    'use strict';

    // Configuration - Enhanced for rich, dense visuals
    const CONFIG = {
        particleCount: 180,              // 2x+ particle count for density
        maxDistance: 180,                // Increased link distance for more connections
        particleRadius: { min: 1, max: 2.5 },  // Smaller, cleaner particles
        lineWidth: 0.8,
        speed: { min: 0.08, max: 0.25 }, // Slower, calmer movement
        lineOpacity: 0.25,               // Increased line opacity for visibility
        colors: {
            particles: 'rgba(160, 200, 255, 0.8)',   // Soft blue particles
            lines: 'rgba(120, 170, 255, BASE_OPACITY)',  // Template for line color
            background: '#0a1628'         // Dark navy background
        },
        mouse: {
            radius: 200,                  // Larger interaction radius
            attractStrength: 0.015,       // Gentle attraction
            parallaxStrength: 0.02        // Subtle parallax effect
        },
        parallax: {
            enabled: true,
            smoothing: 0.08,              // Smooth easing for parallax
            maxOffset: 30                 // Maximum parallax offset
        }
    };

    class Particle {
        constructor(canvas, index, totalParticles) {
            this.canvas = canvas;
            this.index = index;
            this.totalParticles = totalParticles;
            // Vary depth for parallax effect (0.3 to 1.0)
            this.depth = 0.3 + Math.random() * 0.7;
            this.reset();
        }

        reset() {
            this.x = Math.random() * this.canvas.width;
            this.y = Math.random() * this.canvas.height;
            this.baseX = this.x;
            this.baseY = this.y;
            this.radius = CONFIG.particleRadius.min +
                Math.random() * (CONFIG.particleRadius.max - CONFIG.particleRadius.min);

            // Slower speeds for calmer animation
            const speedRange = CONFIG.speed.max - CONFIG.speed.min;
            this.speedX = (Math.random() - 0.5) * speedRange * 2 +
                (Math.random() > 0.5 ? CONFIG.speed.min : -CONFIG.speed.min);
            this.speedY = (Math.random() - 0.5) * speedRange * 2 +
                (Math.random() > 0.5 ? CONFIG.speed.min : -CONFIG.speed.min);

            this.opacity = 0.4 + Math.random() * 0.5;

            // Slight pulse effect
            this.pulseSpeed = 0.01 + Math.random() * 0.02;
            this.pulseOffset = Math.random() * Math.PI * 2;
        }

        update(mouseX, mouseY, hasMouseInteraction, parallaxOffsetX, parallaxOffsetY, time) {
            // Move particle
            this.baseX += this.speedX;
            this.baseY += this.speedY;

            // Wrap around edges smoothly
            if (this.baseX < -10) this.baseX = this.canvas.width + 10;
            if (this.baseX > this.canvas.width + 10) this.baseX = -10;
            if (this.baseY < -10) this.baseY = this.canvas.height + 10;
            if (this.baseY > this.canvas.height + 10) this.baseY = -10;

            // Apply parallax offset based on particle depth
            this.x = this.baseX + (parallaxOffsetX * this.depth);
            this.y = this.baseY + (parallaxOffsetY * this.depth);

            // Gentle mouse attraction effect
            if (hasMouseInteraction) {
                const dx = mouseX - this.x;
                const dy = mouseY - this.y;
                const distance = Math.sqrt(dx * dx + dy * dy);

                if (distance < CONFIG.mouse.radius && distance > 0) {
                    const force = (1 - distance / CONFIG.mouse.radius) * CONFIG.mouse.attractStrength;
                    this.x += dx * force;
                    this.y += dy * force;
                }
            }

            // Subtle pulse effect on opacity
            this.currentOpacity = this.opacity + Math.sin(time * this.pulseSpeed + this.pulseOffset) * 0.1;
        }

        draw(ctx) {
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(160, 200, 255, ${this.currentOpacity.toFixed(2)})`;
            ctx.fill();
        }
    }

    class ConnectThreeAnimation {
        constructor(containerId) {
            this.container = document.getElementById(containerId);
            if (!this.container) {
                console.warn(`Container #${containerId} not found`);
                return;
            }

            this.canvas = document.createElement('canvas');
            this.ctx = this.canvas.getContext('2d');
            this.particles = [];
            this.mouseX = 0;
            this.mouseY = 0;
            this.targetMouseX = 0;
            this.targetMouseY = 0;
            this.hasMouseInteraction = false;
            this.isRunning = true;
            this.animationId = null;
            this.time = 0;

            // Parallax state
            this.parallaxX = 0;
            this.parallaxY = 0;
            this.targetParallaxX = 0;
            this.targetParallaxY = 0;

            this.init();
        }

        init() {
            // Set canvas styles
            this.canvas.style.position = 'absolute';
            this.canvas.style.top = '0';
            this.canvas.style.left = '0';
            this.canvas.style.width = '100%';
            this.canvas.style.height = '100%';
            this.canvas.style.pointerEvents = 'none';

            this.container.appendChild(this.canvas);
            this.resize();
            this.createParticles();
            this.bindEvents();
            this.animate();
        }

        resize() {
            const rect = this.container.getBoundingClientRect();
            const dpr = Math.min(window.devicePixelRatio || 1, 2); // Cap at 2x for performance

            this.canvas.width = rect.width * dpr;
            this.canvas.height = rect.height * dpr;

            this.ctx.scale(dpr, dpr);
            this.canvas.style.width = rect.width + 'px';
            this.canvas.style.height = rect.height + 'px';

            this.width = rect.width;
            this.height = rect.height;
            this.centerX = rect.width / 2;
            this.centerY = rect.height / 2;

            // Update particle canvas reference
            this.particles.forEach(p => {
                p.canvas = { width: rect.width, height: rect.height };
            });
        }

        createParticles() {
            this.particles = [];
            const rect = this.container.getBoundingClientRect();
            const fakeCanvas = { width: rect.width, height: rect.height };

            // Scale particle count based on screen size for consistent density
            const area = rect.width * rect.height;
            const baseArea = 1920 * 1080;
            const scaledCount = Math.floor(CONFIG.particleCount * Math.sqrt(area / baseArea));
            const particleCount = Math.max(100, Math.min(250, scaledCount));

            for (let i = 0; i < particleCount; i++) {
                this.particles.push(new Particle(fakeCanvas, i, particleCount));
            }
        }

        bindEvents() {
            // Resize handler with debounce
            let resizeTimeout;
            window.addEventListener('resize', () => {
                clearTimeout(resizeTimeout);
                resizeTimeout = setTimeout(() => {
                    this.resize();
                    this.createParticles();
                }, 150);
            });

            // Mouse interaction with smooth tracking
            window.addEventListener('mousemove', (e) => {
                const rect = this.container.getBoundingClientRect();
                this.targetMouseX = e.clientX - rect.left;
                this.targetMouseY = e.clientY - rect.top;
                this.hasMouseInteraction = true;

                // Calculate parallax target based on mouse position relative to center
                if (CONFIG.parallax.enabled) {
                    this.targetParallaxX = (this.targetMouseX - this.centerX) / this.centerX * CONFIG.parallax.maxOffset;
                    this.targetParallaxY = (this.targetMouseY - this.centerY) / this.centerY * CONFIG.parallax.maxOffset;
                }
            });

            window.addEventListener('mouseleave', () => {
                this.hasMouseInteraction = false;
                // Slowly return parallax to center
                this.targetParallaxX = 0;
                this.targetParallaxY = 0;
            });

            // Visibility change - pause when tab is not visible
            document.addEventListener('visibilitychange', () => {
                if (document.hidden) {
                    this.pause();
                } else {
                    this.resume();
                }
            });
        }

        drawConnections() {
            const particles = this.particles;
            const len = particles.length;
            const maxDist = CONFIG.maxDistance;
            const maxDistSq = maxDist * maxDist;

            // Batch line drawing for performance
            this.ctx.lineWidth = CONFIG.lineWidth;

            for (let i = 0; i < len; i++) {
                const p1 = particles[i];

                for (let j = i + 1; j < len; j++) {
                    const p2 = particles[j];
                    const dx = p1.x - p2.x;
                    const dy = p1.y - p2.y;
                    const distSq = dx * dx + dy * dy;

                    if (distSq < maxDistSq) {
                        const distance = Math.sqrt(distSq);
                        const opacity = (1 - distance / maxDist) * CONFIG.lineOpacity;

                        this.ctx.beginPath();
                        this.ctx.moveTo(p1.x, p1.y);
                        this.ctx.lineTo(p2.x, p2.y);
                        this.ctx.strokeStyle = `rgba(120, 170, 255, ${opacity.toFixed(3)})`;
                        this.ctx.stroke();
                    }
                }
            }
        }

        // Draw special connections near mouse for enhanced interactivity
        drawMouseConnections() {
            if (!this.hasMouseInteraction) return;

            const mouseRadius = CONFIG.mouse.radius * 1.2;
            const nearbyParticles = this.particles.filter(p => {
                const dx = p.x - this.mouseX;
                const dy = p.y - this.mouseY;
                return Math.sqrt(dx * dx + dy * dy) < mouseRadius;
            });

            // Draw brighter connections between nearby particles
            this.ctx.lineWidth = CONFIG.lineWidth * 1.2;
            for (let i = 0; i < nearbyParticles.length; i++) {
                for (let j = i + 1; j < nearbyParticles.length; j++) {
                    const p1 = nearbyParticles[i];
                    const p2 = nearbyParticles[j];
                    const dx = p1.x - p2.x;
                    const dy = p1.y - p2.y;
                    const distance = Math.sqrt(dx * dx + dy * dy);

                    if (distance < CONFIG.maxDistance * 0.7) {
                        const opacity = (1 - distance / (CONFIG.maxDistance * 0.7)) * 0.35;

                        this.ctx.beginPath();
                        this.ctx.moveTo(p1.x, p1.y);
                        this.ctx.lineTo(p2.x, p2.y);
                        this.ctx.strokeStyle = `rgba(180, 210, 255, ${opacity.toFixed(3)})`;
                        this.ctx.stroke();
                    }
                }
            }
        }

        animate() {
            if (!this.isRunning) return;

            this.time += 1;

            // Smooth mouse position interpolation
            this.mouseX += (this.targetMouseX - this.mouseX) * 0.1;
            this.mouseY += (this.targetMouseY - this.mouseY) * 0.1;

            // Smooth parallax interpolation
            this.parallaxX += (this.targetParallaxX - this.parallaxX) * CONFIG.parallax.smoothing;
            this.parallaxY += (this.targetParallaxY - this.parallaxY) * CONFIG.parallax.smoothing;

            // Clear canvas with background
            this.ctx.fillStyle = CONFIG.colors.background;
            this.ctx.fillRect(0, 0, this.width, this.height);

            // Update and draw particles
            this.particles.forEach(particle => {
                particle.update(
                    this.mouseX,
                    this.mouseY,
                    this.hasMouseInteraction,
                    this.parallaxX,
                    this.parallaxY,
                    this.time
                );
                particle.draw(this.ctx);
            });

            // Draw all connections
            this.drawConnections();

            // Draw enhanced mouse-area connections
            this.drawMouseConnections();

            this.animationId = requestAnimationFrame(() => this.animate());
        }

        pause() {
            this.isRunning = false;
            if (this.animationId) {
                cancelAnimationFrame(this.animationId);
                this.animationId = null;
            }
        }

        resume() {
            if (!this.isRunning) {
                this.isRunning = true;
                this.animate();
            }
        }

        destroy() {
            this.pause();
            if (this.canvas && this.canvas.parentNode) {
                this.canvas.parentNode.removeChild(this.canvas);
            }
        }
    }

    // Initialize when DOM is ready
    function init() {
        if (document.getElementById('bg-animation')) {
            window.connectThreeAnimation = new ConnectThreeAnimation('bg-animation');
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Expose to global scope for manual initialization
    window.ConnectThreeAnimation = ConnectThreeAnimation;
})();
