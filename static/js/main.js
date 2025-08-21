/**
 * Main JavaScript file for UnileverImageStudy
 * Optimized for performance - only essential functionality
 */

// Auto-hide flash messages after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach(message => {
        setTimeout(() => {
            message.style.opacity = '0';
            setTimeout(() => message.remove(), 300);
        }, 5000);
    });
});

// Mobile navigation toggle (only if elements exist)
document.addEventListener('DOMContentLoaded', function() {
    const navToggle = document.querySelector('.nav-toggle');
    const navMenu = document.querySelector('.nav-menu');
    
    if (navToggle && navMenu) {
        navToggle.addEventListener('click', () => navMenu.classList.toggle('nav-menu-open'));
    }
});

// Essential form validation (only when needed)
function validateRequired(field) {
    const isValid = field.value.trim().length > 0;
    field.classList.toggle('form-error', !isValid);
    return isValid;
}

function validateEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    const isValid = emailRegex.test(email.value);
    email.classList.toggle('form-error', !isValid);
    return isValid;
}

// Lightweight utility functions
function formatDuration(seconds) {
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${(seconds % 60).toFixed(0)}s`;
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${minutes}m`;
}

function formatDateTime(dateString) {
    return new Date(dateString).toLocaleString();
}

// Optimized API helper
async function apiRequest(url, options = {}) {
    try {
        const response = await fetch(url, {
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                ...options.headers
            },
            ...options
        });
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    } catch (error) {
        console.error('API request failed:', error);
        throw error;
    }
}

// Simple confirmation dialog
function confirmAction(message, callback) {
    if (confirm(message)) callback();
}

// Loading state management
function setLoadingState(element, isLoading) {
    if (isLoading) {
        element.disabled = true;
        element.dataset.originalText = element.textContent;
        element.textContent = 'Loading...';
    } else {
        element.disabled = false;
        element.textContent = element.dataset.originalText || '';
    }
}

// Toast notification (lightweight)
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: var(--${type === 'success' ? 'success' : type === 'error' ? 'error' : 'primary'}-color);
        color: white;
        padding: 1rem;
        border-radius: 4px;
        z-index: 1000;
        animation: slideIn 0.3s ease;
    `;
    
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

// CSV export (only when needed)
function exportToCSV(data, filename) {
    const csv = data.map(row => Object.values(row).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
}

// Initialize only essential functionality
document.addEventListener('DOMContentLoaded', function() {
    // Add loading states to forms (only submit buttons)
    document.querySelectorAll('form button[type="submit"]').forEach(btn => {
        btn.addEventListener('submit', () => setLoadingState(btn, true));
    });
    
    // Add confirmation to delete buttons (only if they exist)
    document.querySelectorAll('[data-confirm]').forEach(button => {
        button.addEventListener('click', (e) => {
            if (!confirm(button.dataset.confirm)) e.preventDefault();
        });
    });
});

// Add CSS animation for toast
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
`;
document.head.appendChild(style);
