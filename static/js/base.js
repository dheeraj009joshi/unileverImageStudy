/**
 * Unilever Image Study - Optimized Base JavaScript
 * Lightweight core functionality for maximum performance
 */

// ========================================
// Performance-Optimized Core
// ========================================

class UnileverApp {
    constructor() {
        this.isInitialized = false;
        this.init();
    }

    init() {
        if (this.isInitialized) return;
        
        // Only initialize essential features
        this.setupNavigation();
        this.setupFlashMessages();
        this.setupLoadingStates();
        this.applyRequiredIndicators();
        this.setupFormEnhancements();
        
        this.isInitialized = true;
    }

    setupNavigation() {
        // Mobile navigation toggle
        const navToggle = document.querySelector('.nav-toggle');
        const navMenu = document.querySelector('#nav-menu');
        
        if (navToggle && navMenu) {
            navToggle.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                
                // Toggle mobile menu
                navMenu.classList.toggle('is-open');
                navToggle.classList.toggle('is-open');
                
                // Update ARIA attributes
                const isExpanded = navMenu.classList.contains('is-open');
                navToggle.setAttribute('aria-expanded', isExpanded.toString());
                
                // Close user dropdown if open
                const userDropdown = document.querySelector('.user-dropdown');
                if (userDropdown) {
                    userDropdown.classList.remove('is-open');
                }
                
                console.log('Mobile menu toggled:', isExpanded);
            });
            
            // Close mobile menu when clicking outside
            document.addEventListener('click', (e) => {
                if (!navToggle.contains(e.target) && !navMenu.contains(e.target)) {
                    navMenu.classList.remove('is-open');
                    navToggle.classList.remove('is-open');
                    navToggle.setAttribute('aria-expanded', 'false');
                }
            });
        }

        // User menu dropdown
        const userMenu = document.querySelector('.user-menu-toggle');
        const userDropdown = document.querySelector('.user-dropdown');
        
        if (userMenu && userDropdown) {
            userMenu.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                
                // Close mobile menu if open
                if (navMenu && navMenu.classList.contains('is-open')) {
                    navMenu.classList.remove('is-open');
                    navToggle.classList.remove('is-open');
                    navToggle.setAttribute('aria-expanded', 'false');
                }
                
                // Toggle user dropdown
                userDropdown.classList.toggle('is-open');
                const isExpanded = userDropdown.classList.contains('is-open');
                userMenu.setAttribute('aria-expanded', isExpanded.toString());
                
                console.log('User dropdown toggled:', isExpanded);
            });

            // Close user dropdown on outside click
            document.addEventListener('click', (e) => {
                if (!userMenu.contains(e.target) && !userDropdown.contains(e.target)) {
                    userDropdown.classList.remove('is-open');
                    userMenu.setAttribute('aria-expanded', 'false');
                }
            });
        }
        
        // Close mobile menu on window resize
        window.addEventListener('resize', () => {
            if (window.innerWidth > 768) {
                if (navMenu) navMenu.classList.remove('is-open');
                if (navToggle) {
                    navToggle.classList.remove('is-open');
                    navToggle.setAttribute('aria-expanded', 'false');
                }
            }
        });
    }

    setupFlashMessages() {
        const flashMessages = document.querySelectorAll('.flash-message');
        
        flashMessages.forEach(message => {
            // Auto-hide after 5 seconds
            setTimeout(() => {
                message.style.opacity = '0';
                setTimeout(() => message.remove(), 300);
            }, 5000);

            // Close button
            const closeBtn = message.querySelector('.flash-close');
            if (closeBtn) {
                closeBtn.addEventListener('click', () => {
                    message.style.opacity = '0';
                    setTimeout(() => message.remove(), 300);
                });
            }
        });
    }

    setupLoadingStates() {
        // Show loading on form submission
        const forms = document.querySelectorAll('form[data-loading]');
        forms.forEach(form => {
            form.addEventListener('submit', () => {
                this.showLoading();
            });
        });

        // Hide loading on page load
        window.addEventListener('load', () => {
            this.hideLoading();
        });
    }

    showLoading(message = 'Loading...') {
        const overlay = document.getElementById('loading-overlay');
        if (!overlay) return;

        // Update message
        const textElement = overlay.querySelector('.loading-overlay-text');
        if (textElement) textElement.textContent = message || 'Loading...';

        // Start subtle fade-in
        overlay.style.opacity = '0';
        overlay.classList.add('is-visible');
        requestAnimationFrame(() => {
            overlay.style.transition = 'opacity 150ms ease-in';
            overlay.style.opacity = '1';
            overlay.setAttribute('aria-hidden', 'false');
        });
    }

    hideLoading() {
        const overlay = document.getElementById('loading-overlay');
        if (!overlay) return;
        overlay.style.transition = 'opacity 150ms ease-out';
        overlay.style.opacity = '0';
        setTimeout(() => {
            overlay.classList.remove('is-visible');
            overlay.setAttribute('aria-hidden', 'true');
        }, 150);
    }

    // Add visual required indicator to labels based on actual required fields
    applyRequiredIndicators() {
        // Handle standard form controls
        const requiredFields = document.querySelectorAll('input[required], select[required], textarea[required]');
        requiredFields.forEach(field => {
            let label = null;
            if (field.id) {
                label = document.querySelector(`label[for="${CSS.escape(field.id)}"]`);
            }
            // Fallback: look for a label within the same form-group
            if (!label) {
                const group = field.closest('.form-group, .field, .input-group');
                if (group) {
                    label = group.querySelector('label');
                }
            }
            if (label) {
                // Remove any hardcoded trailing '*'
                const trimmed = label.textContent.trim();
                if (trimmed.endsWith('*')) {
                    label.textContent = trimmed.slice(0, -1).trim();
                }
                if (label.classList.contains('study-form-label')) {
                    label.classList.add('study-form-label--required');
                } else {
                    label.classList.add('form-label--required');
                }
            }
        });

        // Handle grouped question blocks (e.g., classification)
        const questionBlocks = document.querySelectorAll('.question, .question-item, .form-group');
        questionBlocks.forEach(block => {
            const hasRequired = block.querySelector('input[required], select[required], textarea[required]') !== null;
            if (!hasRequired) return;
            const qLabel = block.querySelector('.question-label, label');
            if (qLabel) {
                const trimmed = qLabel.textContent.trim();
                if (trimmed.endsWith('*')) {
                    qLabel.textContent = trimmed.slice(0, -1).trim();
                }
                if (qLabel.classList.contains('study-form-label')) {
                    qLabel.classList.add('study-form-label--required');
                } else if (qLabel.classList.contains('form-label') || qLabel.classList.contains('question-label')) {
                    qLabel.classList.add('form-label--required');
                }
            }
        });
    }

    // Enhanced form handling
    setupFormEnhancements() {
        // Password toggle functionality
        const passwordToggles = document.querySelectorAll('.password-toggle');
        passwordToggles.forEach(toggle => {
            toggle.addEventListener('click', (e) => {
                e.preventDefault();
                const input = toggle.parentElement.querySelector('input[type="password"], input[type="text"]');
                const icon = toggle.querySelector('.toggle-icon');
                
                if (input.type === 'password') {
                    input.type = 'text';
                    icon.textContent = '🙈';
                } else {
                    input.type = 'password';
                    icon.textContent = '👁️';
                }
            });
        });

        // Form validation enhancement
        const forms = document.querySelectorAll('form[data-validate]');
        forms.forEach(form => {
            form.addEventListener('submit', (e) => {
                if (!this.validateForm(form)) {
                    e.preventDefault();
                }
            });
        });
    }

    validateForm(form) {
        let isValid = true;
        const requiredFields = form.querySelectorAll('[required]');
        
        requiredFields.forEach(field => {
            if (!field.value.trim()) {
                this.showFieldError(field, 'This field is required');
                isValid = false;
            } else {
                this.clearFieldError(field);
            }
        });

        return isValid;
    }

    showFieldError(field, message) {
        this.clearFieldError(field);
        field.classList.add('form-control--error');
        
        const errorDiv = document.createElement('div');
        errorDiv.className = 'form-error';
        errorDiv.textContent = message;
        field.parentNode.appendChild(errorDiv);
    }

    clearFieldError(field) {
        field.classList.remove('form-control--error');
        const errorDiv = field.parentNode.querySelector('.form-error');
        if (errorDiv) {
            errorDiv.remove();
        }
    }

    hideLoading() {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) {
            overlay.classList.remove('is-visible');
        }
    }
}

// ========================================
// Global API
// ========================================

window.Unilever = {
    app: null,
    
    init() {
        this.app = new UnileverApp();
        return this.app;
    },
    
    showLoading() {
        if (this.app) this.app.showLoading();
    },
    
    hideLoading() {
        if (this.app) this.app.hideLoading();
    }
};

// ========================================
// Auto-initialization
// ========================================

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        Unilever.init();
    });
} else {
    Unilever.init();
}
