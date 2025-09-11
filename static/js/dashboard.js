/**
 * Mindsurve - Dashboard JavaScript
 * Interactive features for dashboard
 */

// ========================================
// Dashboard Initialization
// ========================================

function initializePage() {
    console.log('Initializing dashboard...');
    
    // Initialize dashboard components
    initializeDashboardComponents();
    
    // Initialize interactive features
    initializeInteractiveFeatures();
    
    // Initialize real-time updates
    initializeRealTimeUpdates();
    
    // Initialize charts and analytics
    initializeCharts();
}

// ========================================
// Dashboard Components
// ========================================

function initializeDashboardComponents() {
    // Initialize stat cards
    initializeStatCards();
    
    // Initialize study cards
    initializeStudyCards();
    
    // Initialize action cards
    initializeActionCards();
    
    // Initialize activity timeline
    initializeActivityTimeline();
}

function initializeStatCards() {
    const statCards = document.querySelectorAll('.stat-card');
    
    statCards.forEach((card, index) => {
        // Add staggered animation
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        
        setTimeout(() => {
            card.style.transition = 'all 0.6s ease';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 100);
        
        // Add hover effects
        card.addEventListener('mouseenter', () => {
            card.classList.add('is-hovered');
        });
        
        card.addEventListener('mouseleave', () => {
            card.classList.remove('is-hovered');
        });
    });
}

function initializeStudyCards() {
    const studyCards = document.querySelectorAll('.study-card');
    
    studyCards.forEach(card => {
        // Add click effects
        card.addEventListener('click', (e) => {
            // Don't trigger if clicking on buttons or links
            if (e.target.closest('a, button')) return;
            
            const studyLink = card.querySelector('.study-title a');
            if (studyLink) {
                studyLink.click();
            }
        });
        
        // Add hover effects
        card.addEventListener('mouseenter', () => {
            card.classList.add('is-hovered');
        });
        
        card.addEventListener('mouseleave', () => {
            card.classList.remove('is-hovered');
        });
        
        // Add keyboard navigation
        card.setAttribute('tabindex', '0');
        card.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                card.click();
            }
        });
    });
}

function initializeActionCards() {
    const actionCards = document.querySelectorAll('.action-card');
    
    actionCards.forEach(card => {
        // Add ripple effect on click
        card.addEventListener('click', (e) => {
            createRippleEffect(e, card);
        });
        
        // Add hover animations
        card.addEventListener('mouseenter', () => {
            const icon = card.querySelector('.action-icon');
            if (icon) {
                icon.style.transform = 'scale(1.1) rotate(5deg)';
            }
        });
        
        card.addEventListener('mouseleave', () => {
            const icon = card.querySelector('.action-icon');
            if (icon) {
                icon.style.transform = 'scale(1) rotate(0deg)';
            }
        });
    });
}

function initializeActivityTimeline() {
    const activityItems = document.querySelectorAll('.activity-item');
    
    activityItems.forEach((item, index) => {
        // Add staggered animation
        item.style.opacity = '0';
        item.style.transform = 'translateX(-20px)';
        
        setTimeout(() => {
            item.style.transition = 'all 0.5s ease';
            item.style.opacity = '1';
            item.style.transform = 'translateX(0)';
        }, index * 150);
    });
}

// ========================================
// Interactive Features
// ========================================

function initializeInteractiveFeatures() {
    // Initialize copy functionality
    initializeCopyFeatures();
    
    // Initialize delete confirmations
    initializeDeleteConfirmations();
    
    // Initialize search and filtering
    initializeSearchAndFilter();
    
    // Initialize sorting
    initializeSorting();
}

function initializeCopyFeatures() {
    const copyButtons = document.querySelectorAll('[onclick*="copyStudyLink"]');
    
    copyButtons.forEach(button => {
        // Add visual feedback
        button.addEventListener('click', () => {
            button.classList.add('is-copying');
            setTimeout(() => {
                button.classList.remove('is-copying');
            }, 1000);
        });
    });
}

function initializeDeleteConfirmations() {
    const deleteButtons = document.querySelectorAll('[onclick*="deleteDraftStudy"]');
    
    deleteButtons.forEach(button => {
        // Add loading states
        button.addEventListener('click', () => {
            button.classList.add('is-loading');
        });
    });
}

function initializeSearchAndFilter() {
    // Add search functionality if search input exists
    const searchInput = document.querySelector('.search-input');
    if (searchInput) {
        searchInput.addEventListener('input', debounce(handleSearch, 300));
    }
    
    // Add filter functionality
    const filterButtons = document.querySelectorAll('.filter-button');
    filterButtons.forEach(button => {
        button.addEventListener('click', () => {
            handleFilter(button.dataset.filter);
        });
    });
}

function initializeSorting() {
    const sortButtons = document.querySelectorAll('.sort-button');
    sortButtons.forEach(button => {
        button.addEventListener('click', () => {
            handleSort(button.dataset.sort);
        });
    });
}

// ========================================
// Real-time Updates
// ========================================

function initializeRealTimeUpdates() {
    // Set up periodic refresh for active studies
    if (document.querySelector('.active-studies-section')) {
        setInterval(refreshActiveStudies, 55000); // Refresh every 30 seconds
    }
    
    // Set up activity feed updates
    if (document.querySelector('.activity-timeline')) {
        setInterval(refreshActivityFeed, 60000); // Refresh every minute
    }
}

function refreshActiveStudies() {
    // Fetch updated study data
    fetch('/dashboard/api/active-studies')
        .then(response => response.json())
        .then(data => {
            updateStudyCards(data.studies);
        })
        .catch(error => {
            console.error('Failed to refresh active studies:', error);
        });
}

function refreshActivityFeed() {
    // Fetch updated activity data
    fetch('/dashboard/api/recent-activity')
        .then(response => response.json())
        .then(data => {
            updateActivityFeed(data.activities);
        })
        .catch(error => {
            console.error('Failed to refresh activity feed:', error);
        });
}

function updateStudyCards(studies) {
    studies.forEach(study => {
        const card = document.querySelector(`[data-study-id="${study._id}"]`);
        if (card) {
            // Update response counts
            const totalResponses = card.querySelector('.stat-value');
            if (totalResponses) {
                totalResponses.textContent = study.total_responses || 0;
            }
            
            // Update completion counts
            const completedResponses = card.querySelectorAll('.stat-value')[1];
            if (completedResponses) {
                completedResponses.textContent = study.completed_responses || 0;
            }
        }
    });
}

function updateActivityFeed(activities) {
    const timeline = document.querySelector('.activity-timeline');
    if (!timeline) return;
    
    // Add new activities to the top
    activities.forEach(activity => {
        const activityItem = createActivityItem(activity);
        timeline.insertBefore(activityItem, timeline.firstChild);
        
        // Animate in
        setTimeout(() => {
            activityItem.style.opacity = '1';
            activityItem.style.transform = 'translateX(0)';
        }, 100);
    });
    
    // Remove old activities if too many
    const items = timeline.querySelectorAll('.activity-item');
    if (items.length > 20) {
        for (let i = 20; i < items.length; i++) {
            items[i].remove();
        }
    }
}

function createActivityItem(activity) {
    const item = document.createElement('div');
    item.className = 'activity-item';
    item.style.opacity = '0';
    item.style.transform = 'translateX(-20px)';
    item.style.transition = 'all 0.5s ease';
    
    const icon = getActivityIcon(activity.type);
    const description = activity.description;
    const timestamp = formatTimestamp(activity.timestamp);
    
    item.innerHTML = `
        <div class="activity-icon">
            <span class="icon">${icon}</span>
        </div>
        <div class="activity-content">
            <p class="activity-text">${description}</p>
            <span class="activity-time">${timestamp}</span>
        </div>
    `;
    
    return item;
}

function getActivityIcon(type) {
    const icons = {
        'study_created': '➕',
        'response_received': '📊',
        'study_completed': '✅',
        'study_paused': '⏸️',
        'study_resumed': '▶️',
        'default': '📝'
    };
    
    return icons[type] || icons.default;
}

function formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now - date;
    
    if (diff < 60000) return 'Just now';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    
    return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// ========================================
// Charts and Analytics
// ========================================

function initializeCharts() {
    // Initialize response rate chart if canvas exists
    const responseChart = document.getElementById('response-chart');
    if (responseChart) {
        initializeResponseChart(responseChart);
    }
    
    // Initialize completion time chart if canvas exists
    const timeChart = document.getElementById('time-chart');
    if (timeChart) {
        initializeTimeChart(timeChart);
    }
}

function initializeResponseChart(canvas) {
    // This would integrate with a charting library like Chart.js
    // For now, we'll create a simple visualization
    const ctx = canvas.getContext('2d');
    const data = getResponseData();
    
    // Create a simple bar chart
    createSimpleBarChart(ctx, data, {
        width: canvas.width,
        height: canvas.height,
        colors: ['#3b82f6', '#10b981', '#f59e0b', '#ef4444']
    });
}

function initializeTimeChart(canvas) {
    // Initialize completion time visualization
    const ctx = canvas.getContext('2d');
    const data = getTimeData();
    
    // Create a simple line chart
    createSimpleLineChart(ctx, data, {
        width: canvas.width,
        height: canvas.height,
        color: '#3b82f6'
    });
}

function getResponseData() {
    // Mock data - replace with actual API call
    return {
        labels: ['Total', 'Completed', 'In Progress', 'Abandoned'],
        values: [150, 120, 20, 10]
    };
}

function getTimeData() {
    // Mock data - replace with actual API call
    return {
        labels: ['Task 1', 'Task 2', 'Task 3', 'Task 4', 'Task 5'],
        values: [45, 32, 28, 38, 42]
    };
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
    
    ripple.style.cssText = `
        position: absolute;
        width: ${size}px;
        height: ${size}px;
        left: ${x}px;
        top: ${y}px;
        background: rgba(59, 130, 246, 0.3);
        border-radius: 50%;
        transform: scale(0);
        animation: ripple 0.6s linear;
        pointer-events: none;
    `;
    
    element.style.position = 'relative';
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
// Event Handlers
// ========================================

function handleSearch(event) {
    const query = event.target.value.toLowerCase();
    const studyCards = document.querySelectorAll('.study-card');
    
    studyCards.forEach(card => {
        const title = card.querySelector('.study-title').textContent.toLowerCase();
        const type = card.querySelector('.meta-item').textContent.toLowerCase();
        
        if (title.includes(query) || type.includes(query)) {
            card.style.display = 'block';
            card.style.animation = 'fadeIn 0.3s ease';
        } else {
            card.style.display = 'none';
        }
    });
}

function handleFilter(filter) {
    const studyCards = document.querySelectorAll('.study-card');
    
    studyCards.forEach(card => {
        if (filter === 'all' || card.classList.contains(`study-card--${filter}`)) {
            card.style.display = 'block';
            card.style.animation = 'fadeIn 0.3s ease';
        } else {
            card.style.display = 'none';
        }
    });
    
    // Update active filter button
    document.querySelectorAll('.filter-button').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');
}

function handleSort(sortBy) {
    const studiesGrid = document.querySelector('.studies-grid');
    const studyCards = Array.from(studiesGrid.querySelectorAll('.study-card'));
    
    studyCards.sort((a, b) => {
        let aValue, bValue;
        
        switch (sortBy) {
            case 'title':
                aValue = a.querySelector('.study-title').textContent;
                bValue = b.querySelector('.study-title').textContent;
                return aValue.localeCompare(bValue);
            
            case 'date':
                aValue = new Date(a.querySelector('.meta-item').textContent);
                bValue = new Date(b.querySelector('.meta-item').textContent);
                return bValue - aValue;
            
            case 'responses':
                aValue = parseInt(a.querySelector('.stat-value').textContent) || 0;
                bValue = parseInt(b.querySelector('.stat-value').textContent) || 0;
                return bValue - aValue;
            
            default:
                return 0;
        }
    });
    
    // Reorder cards
    studyCards.forEach(card => {
        studiesGrid.appendChild(card);
    });
    
    // Update active sort button
    document.querySelectorAll('.sort-button').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');
}

// ========================================
// Simple Chart Functions
// ========================================

function createSimpleBarChart(ctx, data, options) {
    const { width, height, colors } = options;
    const barWidth = width / data.labels.length * 0.8;
    const barSpacing = width / data.labels.length * 0.2;
    const maxValue = Math.max(...data.values);
    
    // Clear canvas
    ctx.clearRect(0, 0, width, height);
    
    // Draw bars
    data.values.forEach((value, index) => {
        const barHeight = (value / maxValue) * height * 0.8;
        const x = index * (barWidth + barSpacing) + barSpacing / 2;
        const y = height - barHeight - 20;
        
        // Draw bar
        ctx.fillStyle = colors[index % colors.length];
        ctx.fillRect(x, y, barWidth, barHeight);
        
        // Draw label
        ctx.fillStyle = '#374151';
        ctx.font = '12px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(data.labels[index], x + barWidth / 2, height - 5);
        
        // Draw value
        ctx.fillText(value.toString(), x + barWidth / 2, y - 5);
    });
}

function createSimpleLineChart(ctx, data, options) {
    const { width, height, color } = options;
    const maxValue = Math.max(...data.values);
    const pointSpacing = width / (data.labels.length - 1);
    
    // Clear canvas
    ctx.clearRect(0, 0, width, height);
    
    // Draw line
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.beginPath();
    
    data.values.forEach((value, index) => {
        const x = index * pointSpacing;
        const y = height - (value / maxValue) * height * 0.8 - 20;
        
        if (index === 0) {
            ctx.moveTo(x, y);
        } else {
            ctx.lineTo(x, y);
        }
    });
    
    ctx.stroke();
    
    // Draw points
    ctx.fillStyle = color;
    data.values.forEach((value, index) => {
        const x = index * pointSpacing;
        const y = height - (value / maxValue) * height * 0.8 - 20;
        
        ctx.beginPath();
        ctx.arc(x, y, 4, 0, 2 * Math.PI);
        ctx.fill();
    });
    
    // Draw labels
    ctx.fillStyle = '#374151';
    ctx.font = '12px sans-serif';
    ctx.textAlign = 'center';
    data.labels.forEach((label, index) => {
        const x = index * pointSpacing;
        ctx.fillText(label, x, height - 5);
    });
}

// ========================================
// Export for Global Use
// ========================================

// Make functions available globally
window.MindsurveDashboard = {
    initializePage,
    initializeDashboardComponents,
    initializeInteractiveFeatures,
    initializeRealTimeUpdates,
    initializeCharts,
    refreshActiveStudies,
    refreshActivityFeed,
    handleSearch,
    handleFilter,
    handleSort
};

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        initializePage,
        initializeDashboardComponents,
        initializeInteractiveFeatures,
        initializeRealTimeUpdates,
        initializeCharts
    };
}
