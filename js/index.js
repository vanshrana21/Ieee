/**
 * ============================================
 * CINEMATIC 3D SCROLL ANIMATION SYSTEM
 * ============================================
 * Professional scroll-driven 3D transformations
 * with layered parallax and depth effects
 */

document.addEventListener('DOMContentLoaded', () => {
  
  // Register GSAP plugins
  gsap.registerPlugin(ScrollTrigger);

  console.log('🎬 3D Animation System Initialized');

  // ============================================
  // NAVBAR - Subtle fade in
  // ============================================
  
  gsap.from('.navbar', {
    y: -20,
    opacity: 0,
    duration: 1,
    ease: 'power3.out'
  });

  // Navbar scroll shadow
  ScrollTrigger.create({
    start: 'top -10',
    end: 99999,
    toggleClass: {
      targets: '.navbar',
      className: 'navbar-scrolled'
    }
  });

  // ============================================
  // HERO TEXT - Staggered entrance
  // ============================================
  
  const heroTextTimeline = gsap.timeline({
    defaults: { ease: 'power3.out' }
  });

  heroTextTimeline
    .from('.hero-title', {
      y: 60,
      opacity: 0,
      duration: 1.2,
      delay: 0.3
    })
    .from('.hero-subtitle', {
      y: 40,
      opacity: 0,
      duration: 1
    }, '-=0.7')
    .from('.hero-actions', {
      y: 30,
      opacity: 0,
      duration: 0.9
    }, '-=0.6')
    .from('.hero-trust', {
      y: 20,
      opacity: 0,
      duration: 0.8
    }, '-=0.5');

  // ============================================
  // 3D DOCUMENT STACK - CINEMATIC ENTRANCE
  // ============================================
  
  // Initial entrance animation
  gsap.from('.document-stack', {
    scale: 0.8,
    opacity: 0,
    rotateX: 30,
    rotateY: 30,
    duration: 1.5,
    delay: 0.5,
    ease: 'power3.out'
  });

  // Stagger the document layers
  gsap.from('.doc-layer', {
    z: -200,
    opacity: 0,
    duration: 1.2,
    stagger: 0.15,
    delay: 0.8,
    ease: 'power3.out'
  });

  // Animate floating accents
  gsap.from('.floating-accent', {
    scale: 0,
    opacity: 0,
    duration: 1.5,
    stagger: 0.2,
    delay: 1,
    ease: 'back.out(1.5)'
  });

  // ============================================
  // 3D SCROLL-DRIVEN ROTATION & DEPTH
  // ============================================
  
  gsap.to('.document-stack', {
    rotateX: -10,
    rotateY: 10,
    z: 100,
    scrollTrigger: {
      trigger: '.hero',
      start: 'top top',
      end: 'bottom top',
      scrub: 1.5,
      // markers: true // Uncomment for debugging
    }
  });

  // ============================================
  // LAYERED PARALLAX - Each layer moves differently
  // ============================================
  
  gsap.to('.layer-back', {
    z: -180,
    x: -30,
    y: 20,
    rotateY: -5,
    scrollTrigger: {
      trigger: '.hero',
      start: 'top top',
      end: 'bottom top',
      scrub: 2
    }
  });

  gsap.to('.layer-middle', {
    z: -90,
    x: 15,
    y: -10,
    scrollTrigger: {
      trigger: '.hero',
      start: 'top top',
      end: 'bottom top',
      scrub: 1.8
    }
  });

  gsap.to('.layer-front', {
    z: 50,
    x: -10,
    y: -15,
    rotateY: 3,
    scrollTrigger: {
      trigger: '.hero',
      start: 'top top',
      end: 'bottom top',
      scrub: 1.5
    }
  });

  // ============================================
  // FLOATING ACCENTS - Scroll parallax
  // ============================================
  
  gsap.to('.accent-1', {
    y: 100,
    x: -50,
    scale: 1.5,
    opacity: 0,
    scrollTrigger: {
      trigger: '.hero',
      start: 'top top',
      end: 'bottom top',
      scrub: 1
    }
  });

  gsap.to('.accent-2', {
    y: -80,
    x: 40,
    scale: 0.8,
    opacity: 0,
    scrollTrigger: {
      trigger: '.hero',
      start: 'top top',
      end: 'bottom top',
      scrub: 1.2
    }
  });

  gsap.to('.accent-3', {
    y: 60,
    x: 30,
    scale: 1.3,
    opacity: 0,
    scrollTrigger: {
      trigger: '.hero',
      start: 'top top',
      end: 'bottom top',
      scrub: 0.8
    }
  });

  // ============================================
  // HERO TEXT - Parallax scroll
  // ============================================
  
  gsap.to('.hero-content', {
    y: -80,
    opacity: 0.3,
    scrollTrigger: {
      trigger: '.hero',
      start: 'top top',
      end: 'bottom top',
      scrub: 1.5
    }
  });

  // ============================================
  // DOCUMENT STACK BREAKUP - Transition to features
  // ============================================
  
  gsap.to('.document-stack', {
    scale: 0.7,
    opacity: 0,
    rotateX: -30,
    rotateY: 30,
    z: -200,
    scrollTrigger: {
      trigger: '.hero',
      start: 'center top',
      end: 'bottom top',
      scrub: 2
    }
  });

  // ============================================
  // FEATURES SECTION - Depth entrance
  // ============================================
  
  // Section header
  gsap.fromTo('.features .section-header',
    {
      y: 60,
      opacity: 0
    },
    {
      y: 0,
      opacity: 1,
      duration: 1.2,
      ease: 'power3.out',
      scrollTrigger: {
        trigger: '#features',
        start: 'top 75%',
        toggleActions: 'play none none none'
      }
    }
  );

  // Feature cards - 3D depth entrance
  gsap.fromTo('.feature-card',
    {
      y: 80,
      z: -100,
      opacity: 0,
      rotateX: 10
    },
    {
      y: 0,
      z: 0,
      opacity: 1,
      rotateX: 0,
      duration: 1,
      stagger: 0.2,
      ease: 'power3.out',
      scrollTrigger: {
        trigger: '#features',
        start: 'top 70%',
        toggleActions: 'play none none none'
      }
    }
  );

  // Feature icons - Scale pop
  gsap.fromTo('.feature-icon',
    {
      scale: 0.5,
      opacity: 0,
      rotateY: 90
    },
    {
      scale: 1,
      opacity: 1,
      rotateY: 0,
      duration: 0.8,
      stagger: 0.2,
      delay: 0.3,
      ease: 'back.out(2)',
      scrollTrigger: {
        trigger: '#features',
        start: 'top 70%',
        toggleActions: 'play none none none'
      }
    }
  );

  // ============================================
  // HOW IT WORKS - Step animations
  // ============================================
  
  gsap.from('.how-it-works .section-header', {
    y: 50,
    opacity: 0,
    duration: 1,
    ease: 'power3.out',
    scrollTrigger: {
      trigger: '.how-it-works',
      start: 'top 75%',
      toggleActions: 'play none none none'
    }
  });

  gsap.utils.toArray('.step').forEach((step, i) => {
    // Step container
    gsap.from(step, {
      x: i % 2 === 0 ? -60 : 60,
      opacity: 0,
      duration: 1,
      ease: 'power3.out',
      scrollTrigger: {
        trigger: step,
        start: 'top 80%',
        toggleActions: 'play none none none'
      }
    });

    // Step number - 3D pop
    gsap.from(step.querySelector('.step-number'), {
      scale: 0.3,
      opacity: 0,
      rotateY: 180,
      duration: 0.9,
      ease: 'back.out(2)',
      scrollTrigger: {
        trigger: step,
        start: 'top 80%',
        toggleActions: 'play none none none'
      }
    });

    // Step content
    gsap.from(step.querySelector('.step-content'), {
      y: 40,
      opacity: 0,
      duration: 1,
      delay: 0.2,
      ease: 'power3.out',
      scrollTrigger: {
        trigger: step,
        start: 'top 80%',
        toggleActions: 'play none none none'
      }
    });
  });

  // ============================================
  // CTA SECTION - Depth entrance
  // ============================================
  
  gsap.from('.cta-content', {
    y: 60,
    z: -80,
    opacity: 0,
    scale: 0.95,
    duration: 1.2,
    ease: 'power3.out',
    scrollTrigger: {
      trigger: '.cta',
      start: 'top 75%',
      toggleActions: 'play none none none'
    }
  });

  gsap.from('.cta-title', {
    y: 40,
    opacity: 0,
    duration: 1,
    delay: 0.2,
    ease: 'power3.out',
    scrollTrigger: {
      trigger: '.cta',
      start: 'top 75%',
      toggleActions: 'play none none none'
    }
  });

  gsap.from('.cta-subtitle', {
    y: 30,
    opacity: 0,
    duration: 0.9,
    delay: 0.3,
    ease: 'power3.out',
    scrollTrigger: {
      trigger: '.cta',
      start: 'top 75%',
      toggleActions: 'play none none none'
    }
  });

  gsap.from('.cta-actions', {
    y: 25,
    opacity: 0,
    scale: 0.95,
    duration: 0.8,
    delay: 0.4,
    ease: 'back.out(1.5)',
    scrollTrigger: {
      trigger: '.cta',
      start: 'top 75%',
      toggleActions: 'play none none none'
    }
  });

  // ============================================
  // FOOTER
  // ============================================
  
  gsap.from('.footer-content', {
    y: 50,
    opacity: 0,
    duration: 1,
    ease: 'power3.out',
    scrollTrigger: {
      trigger: '.footer',
      start: 'top 85%',
      toggleActions: 'play none none none'
    }
  });

  gsap.from('.footer-section', {
    y: 30,
    opacity: 0,
    duration: 0.8,
    stagger: 0.1,
    ease: 'power3.out',
    scrollTrigger: {
      trigger: '.footer-content',
      start: 'top 85%',
      toggleActions: 'play none none none'
    }
  });

  // ============================================
  // BUTTON MICRO-INTERACTIONS
  // ============================================
  
  const buttons = document.querySelectorAll('.btn');
  
  buttons.forEach(button => {
    button.addEventListener('mouseenter', () => {
      gsap.to(button, {
        scale: 1.05,
        y: -2,
        duration: 0.3,
        ease: 'power2.out'
      });
    });

    button.addEventListener('mouseleave', () => {
      gsap.to(button, {
        scale: 1,
        y: 0,
        duration: 0.3,
        ease: 'power2.out'
      });
    });
  });

  // ============================================
  // SMOOTH ANCHOR SCROLLING
  // ============================================
  
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
      const href = this.getAttribute('href');
      
      if (href === '#' || !href) return;
      
      const target = document.querySelector(href);
      if (target) {
        e.preventDefault();
        
        gsap.to(window, {
          duration: 1.5,
          scrollTo: {
            y: target,
            offsetY: 90
          },
          ease: 'power3.inOut'
        });
      }
    });
  });

  // ============================================
  // ACCESSIBILITY - Reduced motion support
  // ============================================
  
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    gsap.globalTimeline.timeScale(0.01);
    ScrollTrigger.refresh();
    console.log('⚠️ Reduced motion enabled');
  }

  // ============================================
  // PERFORMANCE - Refresh on resize
  // ============================================
  
  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      ScrollTrigger.refresh();
    }, 250);
  });

  // ============================================
  // DEBUG INFO
  // ============================================
  
  console.log('✨ 3D Document Stack:', document.querySelector('.document-stack'));
  console.log('📊 Feature cards found:', document.querySelectorAll('.feature-card').length);
  console.log('🎯 ScrollTriggers active:', ScrollTrigger.getAll().length);
  console.log('🎬 All animations loaded successfully');
});
/* ============================================
   3D HERO SCROLL ANIMATION - VANILLA JS
   ============================================
   PASTE THIS INTO: js/index.js or js/main.js
   (at the bottom of your existing JS, or in a new <script> tag)
   ============================================ */

(function() {
    'use strict';
    
    // Wait for DOM to be ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init3DAnimation);
    } else {
        init3DAnimation();
    }
    
    function init3DAnimation() {
        const hero3DScene = document.querySelector('.hero-3d-scene');
        const floatingDocs = document.querySelectorAll('.floating-doc');
        const floatingIcons = document.querySelectorAll('.floating-icon');
        const accentOrbs = document.querySelectorAll('.accent-orb');
        const heroSection = document.querySelector('.hero');
        
        if (!hero3DScene || !heroSection) {
            console.log('3D Hero elements not found');
            return;
        }
        
        console.log('✨ 3D Hero Animation Initialized');
        
        // ============================================
        // SCROLL-BASED ANIMATION
        // ============================================
        
        let ticking = false;
        
        function updateAnimation() {
            const scrollY = window.scrollY;
            const heroHeight = heroSection.offsetHeight;
            const scrollProgress = Math.min(scrollY / heroHeight, 1);
            
            // Calculate rotation based on scroll
            const rotateX = 10 - (scrollProgress * 30); // 10deg → -20deg
            const rotateY = -10 + (scrollProgress * 25); // -10deg → 15deg
            const translateZ = scrollProgress * -150; // Move back in Z-axis
            const scale = 1 - (scrollProgress * 0.2); // Slightly shrink
            
            // Apply to main scene
            hero3DScene.style.transform = `
                rotateX(${rotateX}deg) 
                rotateY(${rotateY}deg) 
                translateZ(${translateZ}px)
                scale(${scale})
            `;
            
            // Animate individual documents with parallax
            floatingDocs.forEach((doc, index) => {
                const speed = 1 + (index * 0.3); // Different speeds for depth
                const docRotateY = (index - 1) * 8; // Spread rotation
                const docTranslateZ = -100 * index - (scrollProgress * 80 * speed);
                const docOpacity = 1 - (scrollProgress * 0.6 * speed);
                
                doc.style.transform = `
                    translate(-50%, -50%) 
                    translateZ(${docTranslateZ}px) 
                    rotateY(${docRotateY + (scrollProgress * 15)}deg)
                    rotateX(${scrollProgress * -10}deg)
                `;
                doc.style.opacity = Math.max(docOpacity, 0.2);
            });
            
            // Animate floating icons
            floatingIcons.forEach((icon, index) => {
                const iconSpeed = 1.5 + (index * 0.4);
                const iconTranslateY = scrollProgress * -100 * iconSpeed;
                const iconRotate = scrollProgress * (360 / 3) * (index + 1);
                const iconOpacity = 1 - (scrollProgress * 1.2);
                
                icon.style.transform = `
                    translateY(${iconTranslateY}px) 
                    translateZ(${80 + (index * 20)}px)
                    rotate(${iconRotate}deg)
                    scale(${1 - scrollProgress * 0.3})
                `;
                icon.style.opacity = Math.max(iconOpacity, 0);
            });
            
            // Fade out accent orbs
            accentOrbs.forEach((orb, index) => {
                const orbOpacity = 0.3 - (scrollProgress * 0.5);
                orb.style.opacity = Math.max(orbOpacity, 0);
            });
            
            ticking = false;
        }
        
        function requestAnimationTick() {
            if (!ticking) {
                window.requestAnimationFrame(updateAnimation);
                ticking = true;
            }
        }
        
        // Listen to scroll with throttling
        window.addEventListener('scroll', requestAnimationTick, { passive: true });
        
        // Initial update
        updateAnimation();
        
        // ============================================
        // MOUSE PARALLAX EFFECT (OPTIONAL)
        // ============================================
        
        let mouseX = 0;
        let mouseY = 0;
        let targetX = 0;
        let targetY = 0;
        
        function updateMouseParallax() {
            // Smooth interpolation
            targetX += (mouseX - targetX) * 0.05;
            targetY += (mouseY - targetY) * 0.05;
            
            const rotateYMouse = targetX * 0.01; // Max ±10deg
            const rotateXMouse = -targetY * 0.01; // Max ±10deg
            
            // Apply subtle mouse movement (only when not scrolling much)
            if (window.scrollY < 100) {
                hero3DScene.style.transform = `
                    rotateX(${10 + rotateXMouse}deg) 
                    rotateY(${-10 + rotateYMouse}deg)
                `;
            }
            
            requestAnimationFrame(updateMouseParallax);
        }
        
        function handleMouseMove(e) {
            const centerX = window.innerWidth / 2;
            const centerY = window.innerHeight / 2;
            
            mouseX = e.clientX - centerX;
            mouseY = e.clientY - centerY;
        }
        
        // Only enable mouse parallax on desktop
        if (window.innerWidth > 768) {
            window.addEventListener('mousemove', handleMouseMove, { passive: true });
            requestAnimationFrame(updateMouseParallax);
        }
        
        // ============================================
        // ENTRANCE ANIMATION
        // ============================================
        
        function playEntranceAnimation() {
            // Fade in and scale up the scene
            hero3DScene.style.opacity = '0';
            hero3DScene.style.transform = 'rotateX(30deg) rotateY(-30deg) scale(0.8)';
            
            setTimeout(() => {
                hero3DScene.style.transition = 'all 1.5s cubic-bezier(0.4, 0, 0.2, 1)';
                hero3DScene.style.opacity = '1';
                hero3DScene.style.transform = 'rotateX(10deg) rotateY(-10deg) scale(1)';
            }, 100);
            
            // Stagger documents
            floatingDocs.forEach((doc, index) => {
                doc.style.opacity = '0';
                doc.style.transform = 'translate(-50%, -50%) translateZ(-300px)';
                
                setTimeout(() => {
                    doc.style.transition = `all 1.2s cubic-bezier(0.4, 0, 0.2, 1) ${index * 0.15}s`;
                    doc.style.opacity = index === 0 ? '1' : (index === 1 ? '0.85' : '0.7');
                    
                    const baseTransform = index === 0 
                        ? 'translate(-50%, -50%) translateZ(0px)'
                        : index === 1
                        ? 'translate(-50%, -50%) translateZ(-100px) rotateY(-8deg)'
                        : 'translate(-50%, -50%) translateZ(-180px) rotateY(8deg)';
                    
                    doc.style.transform = baseTransform;
                }, 200);
            });
            
            // Fade in icons
            floatingIcons.forEach((icon, index) => {
                icon.style.opacity = '0';
                icon.style.transform = 'scale(0)';
                
                setTimeout(() => {
                    icon.style.transition = `all 0.8s cubic-bezier(0.68, -0.55, 0.265, 1.55) ${0.6 + index * 0.2}s`;
                    icon.style.opacity = '1';
                    icon.style.transform = 'scale(1)';
                }, 100);
            });
        }
        
        // Play entrance after a short delay
        setTimeout(playEntranceAnimation, 300);
        
        // ============================================
        // INTERSECTION OBSERVER FOR FEATURE CARDS
        // ============================================
        
        const featureCards = document.querySelectorAll('.feature-card');
        
        if (featureCards.length > 0) {
            const observerOptions = {
                root: null,
                threshold: 0.15,
                rootMargin: '0px'
            };
            
            const observer = new IntersectionObserver((entries) => {
                entries.forEach((entry, index) => {
                    if (entry.isIntersecting) {
                        setTimeout(() => {
                            entry.target.style.opacity = '1';
                            entry.target.style.transform = 'translateY(0) translateZ(0)';
                        }, index * 100);
                        observer.unobserve(entry.target);
                    }
                });
            }, observerOptions);
            
            featureCards.forEach((card) => {
                card.style.opacity = '0';
                card.style.transform = 'translateY(60px) translateZ(-50px)';
                card.style.transition = 'all 0.8s cubic-bezier(0.4, 0, 0.2, 1)';
                observer.observe(card);
            });
        }
        
        // ============================================
        // CLEANUP
        // ============================================
        
        window.addEventListener('beforeunload', () => {
            window.removeEventListener('scroll', requestAnimationTick);
            window.removeEventListener('mousemove', handleMouseMove);
        });
        
        console.log('✅ 3D Hero fully loaded');
    }
    
})();


