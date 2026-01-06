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