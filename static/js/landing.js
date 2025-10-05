/**
 * Unilever Image Study - Landing Page JavaScript
 * Interactive features and animations
 */

// ========================================
// Landing Page Initialization
// ========================================

function initializePage() {
    console.log('Initializing landing page...');
    
    // Initialize animations
    initializeAnimations();
    
    // Initialize interactive elements
    initializeInteractiveElements();
    
    // Initialize scroll effects
    initializeScrollEffects();
    
    // Initialize floating cards
    initializeFloatingCards();
}

// ========================================
// Animation System
// ========================================

function initializeAnimations() {
    // Intersection Observer for fade-in animations
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };
    
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('animate-in');
            }
        });
    }, observerOptions);
    
    // Observe elements for animation
    const animateElements = document.querySelectorAll('.feature-card, .step-item, .testimonial-card');
    animateElements.forEach(el => {
        observer.observe(el);
        el.classList.add('animate-ready');
    });
}

// ========================================
// Interactive Elements
// ========================================

function initializeInteractiveElements() {
    // Feature card interactions
    initializeFeatureCards();
    
    // Step interactions
    initializeSteps();
    
    // Testimonial interactions
    initializeTestimonials();
    
    // CTA button interactions
    initializeCTAButtons();
}

function initializeFeatureCards() {
    const featureCards = document.querySelectorAll('.feature-card');
    
    featureCards.forEach(card => {
        // Add hover effects
        card.addEventListener('mouseenter', () => {
            card.classList.add('is-hovered');
        });
        
        card.addEventListener('mouseleave', () => {
            card.classList.remove('is-hovered');
        });
        
        // Add click effect
        card.addEventListener('click', () => {
            card.classList.add('is-clicked');
            setTimeout(() => {
                card.classList.remove('is-clicked');
            }, 200);
        });
    });
}

function initializeSteps() {
    const steps = document.querySelectorAll('.step-item');
    
    steps.forEach((step, index) => {
        // Add progress indicator
        const progressBar = document.createElement('div');
        progressBar.className = 'step-progress';
        progressBar.style.width = '0%';
        step.appendChild(progressBar);
        
        // Animate progress on scroll
        const stepObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    setTimeout(() => {
                        progressBar.style.width = '100%';
                    }, index * 200);
                }
            });
        }, { threshold: 0.5 });
        
        stepObserver.observe(step);
    });
}

function initializeTestimonials() {
    const testimonialCards = document.querySelectorAll('.testimonial-card');
    
    testimonialCards.forEach(card => {
        // Add quote animation
        const quote = card.querySelector('.testimonial-text');
        if (quote) {
            quote.addEventListener('mouseenter', () => {
                quote.style.transform = 'scale(1.02)';
            });
            
            quote.addEventListener('mouseleave', () => {
                quote.style.transform = 'scale(1)';
            });
        }
        
        // Add author hover effect
        const author = card.querySelector('.testimonial-author');
        if (author) {
            author.addEventListener('mouseenter', () => {
                author.style.transform = 'translateX(10px)';
            });
            
            author.addEventListener('mouseleave', () => {
                author.style.transform = 'translateX(0)';
            });
        }
    });
}

function initializeCTAButtons() {
    const ctaButtons = document.querySelectorAll('.cta-section .btn');
    
    ctaButtons.forEach(button => {
        // Add pulse animation on hover
        button.addEventListener('mouseenter', () => {
            button.classList.add('pulse');
        });
        
        button.addEventListener('mouseleave', () => {
            button.classList.remove('pulse');
        });
        
        // Add click ripple effect
        button.addEventListener('click', (e) => {
            createRippleEffect(e, button);
        });
    });
}

// ========================================
// Scroll Effects
// ========================================

function initializeScrollEffects() {
    // Parallax effect for hero section
    initializeParallax();
    
    // Sticky navigation effect
    initializeStickyNav();
    
    // Progress indicators
    initializeProgressIndicators();
}

function initializeParallax() {
    const heroSection = document.querySelector('.hero-section');
    if (!heroSection) return;
    
    window.addEventListener('scroll', () => {
        const scrolled = window.pageYOffset;
        const rate = scrolled * -0.5;
        
        // Apply parallax to background
        heroSection.style.transform = `translateY(${rate}px)`;
        
        // Adjust floating cards based on scroll
        const floatingCards = document.querySelectorAll('.floating-card');
        floatingCards.forEach((card, index) => {
            const cardRate = rate * (0.3 + index * 0.1);
            card.style.transform = `translateY(${cardRate}px)`;
        });
    });
}

function initializeStickyNav() {
    const header = document.querySelector('.app-header');
    if (!header) return;
    
    let lastScroll = 0;
    
    window.addEventListener('scroll', () => {
        const currentScroll = window.pageYOffset;
        
        if (currentScroll > 100) {
            header.classList.add('is-sticky');
        } else {
            header.classList.remove('is-sticky');
        }
        
        // Hide/show header on scroll
        if (currentScroll > lastScroll && currentScroll > 200) {
            header.classList.add('is-hidden');
        } else {
            header.classList.remove('is-hidden');
        }
        
        lastScroll = currentScroll;
    });
}

function initializeProgressIndicators() {
    // Create scroll progress bar
    const progressBar = document.createElement('div');
    progressBar.className = 'scroll-progress';
    document.body.appendChild(progressBar);
    
    window.addEventListener('scroll', () => {
        const scrolled = window.pageYOffset;
        const maxHeight = document.documentElement.scrollHeight - window.innerHeight;
        const progress = (scrolled / maxHeight) * 100;
        
        progressBar.style.width = `${progress}%`;
    });
}

// ========================================
// Floating Cards Animation
// ========================================

function initializeFloatingCards() {
    const floatingCards = document.querySelectorAll('.floating-card');
    
    floatingCards.forEach((card, index) => {
        // Add staggered animation delay
        card.style.animationDelay = `${index * 2}s`;
        
        // Add interactive hover effects
        card.addEventListener('mouseenter', () => {
            card.style.animationPlayState = 'paused';
            card.style.transform = 'scale(1.1) rotate(2deg)';
        });
        
        card.addEventListener('mouseleave', () => {
            card.style.animationPlayState = 'running';
            card.style.transform = 'scale(1) rotate(0deg)';
        });
        
        // Add click interaction
        card.addEventListener('click', () => {
            card.classList.add('is-clicked');
            setTimeout(() => {
                card.classList.remove('is-clicked');
            }, 300);
        });
    });
}

// ========================================
// Utility Functions
// ========================================

function createRippleEffect(event, element) {
    const ripple = document.createElement('span');
    const rect = element.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height);
    const x = event.clientX - rect.left - size / 2;
    const y = event.clientY - rect.top - size / 2;
    
    ripple.style.width = ripple.style.height = size + 'px';
    ripple.style.left = x + 'px';
    ripple.style.top = y + 'px';
    ripple.classList.add('ripple');
    
    element.appendChild(ripple);
    
    setTimeout(() => {
        ripple.remove();
    }, 600);
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function throttle(func, limit) {
    let inThrottle;
    return function() {
        const args = arguments;
        const context = this;
        if (!inThrottle) {
            func.apply(context, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// ========================================
// Performance Optimizations
// ========================================

// Throttle scroll events for better performance
const throttledScrollHandler = throttle(() => {
    // Update scroll-based effects
    updateScrollEffects();
}, 16); // ~60fps

window.addEventListener('scroll', throttledScrollHandler);

function updateScrollEffects() {
    // Update any scroll-based animations here
    const scrolled = window.pageYOffset;
    
    // Update progress indicators
    updateProgressIndicators(scrolled);
    
    // Update parallax effects
    updateParallaxEffects(scrolled);
}

function updateProgressIndicators(scrolled) {
    const progressBar = document.querySelector('.scroll-progress');
    if (progressBar) {
        const maxHeight = document.documentElement.scrollHeight - window.innerHeight;
        const progress = (scrolled / maxHeight) * 100;
        progressBar.style.width = `${progress}%`;
    }
}

function updateParallaxEffects(scrolled) {
    const heroSection = document.querySelector('.hero-section');
    if (heroSection) {
        const rate = scrolled * -0.5;
        heroSection.style.transform = `translateY(${rate}px)`;
    }
}

// ========================================
// Accessibility Enhancements
// ========================================

function initializeAccessibility() {
    // Add keyboard navigation for interactive elements
    initializeKeyboardNavigation();
    
    // Add focus indicators
    initializeFocusIndicators();
    
    // Add ARIA labels
    initializeARIALabels();
}

function initializeKeyboardNavigation() {
    const interactiveElements = document.querySelectorAll('.feature-card, .testimonial-card, .floating-card');
    
    interactiveElements.forEach(element => {
        element.setAttribute('tabindex', '0');
        element.setAttribute('role', 'button');
        
        element.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                element.click();
            }
        });
    });
}

function initializeFocusIndicators() {
    const focusableElements = document.querySelectorAll('a, button, [tabindex]');
    
    focusableElements.forEach(element => {
        element.addEventListener('focus', () => {
            element.classList.add('is-focused');
        });
        
        element.addEventListener('blur', () => {
            element.classList.remove('is-focused');
        });
    });
}

function initializeARIALabels() {
    // Add descriptive labels for screen readers
    const floatingCards = document.querySelectorAll('.floating-card');
    floatingCards.forEach((card, index) => {
        const title = card.querySelector('h3')?.textContent || 'Feature';
        card.setAttribute('aria-label', `${title} - Click to learn more`);
    });
    
    // Add progress information
    const steps = document.querySelectorAll('.step-item');
    steps.forEach((step, index) => {
        const title = step.querySelector('.step-title')?.textContent || 'Step';
        step.setAttribute('aria-label', `${title} - Step ${index + 1} of ${steps.length}`);
    });
}

// ========================================
// Event Listeners
// ========================================

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    initializePage();
    initializeAccessibility();
});

// Handle window resize
window.addEventListener('resize', debounce(() => {
    // Recalculate any layout-dependent values
    updateLayoutValues();
}, 250));

function updateLayoutValues() {
    // Update any layout-dependent calculations here
    const heroSection = document.querySelector('.hero-section');
    if (heroSection) {
        // Recalculate hero section dimensions if needed
        const height = window.innerHeight;
        heroSection.style.minHeight = `${height}px`;
    }
}

// ========================================
// Export for Global Use
// ========================================

// Make functions available globally if needed
window.UnileverLanding = {
    initializePage,
    initializeAnimations,
    initializeInteractiveElements,
    initializeScrollEffects,
    initializeFloatingCards
};

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        initializePage,
        initializeAnimations,
        initializeInteractiveElements,
        initializeScrollEffects,
        initializeFloatingCards
    };
}
