/**
 * TaskTimer Class - Handles task timing and element interaction tracking
 * Pure JavaScript implementation with no external dependencies
 */
class TaskTimer {
    constructor(studyId, taskId, shareToken) {
        this.studyId = studyId;
        this.taskId = taskId;
        this.shareToken = shareToken;
        this.taskStartTime = null;
        this.elementTimers = new Map();
        this.elementInteractions = new Map();
        this.isTracking = false;
        this.visibilityChangeHandler = this.handleVisibilityChange.bind(this);
        this.pageUnloadHandler = this.handlePageUnload.bind(this);
        
        this.init();
    }
    
    init() {
        // Set up visibility change tracking
        document.addEventListener('visibilitychange', this.visibilityChangeHandler);
        window.addEventListener('beforeunload', this.pageUnloadHandler);
        
        // Initialize element interaction tracking
        this.setupElementTracking();
        
        console.log('TaskTimer initialized for task:', this.taskId);
    }
    
    setupElementTracking() {
        // Find all study elements on the page
        const elements = document.querySelectorAll('[data-element-id]');
        
        elements.forEach(element => {
            const elementId = element.dataset.elementId;
            this.elementTimers.set(elementId, {
                startTime: null,
                totalViewTime: 0,
                hoverCount: 0,
                clickCount: 0,
                firstViewTime: null,
                lastViewTime: null
            });
            
            // Track element visibility
            this.setupIntersectionObserver(element, elementId);
            
            // Track hover events
            element.addEventListener('mouseenter', () => this.trackElementInteraction(elementId, 'hover'));
            element.addEventListener('mouseleave', () => this.trackElementInteraction(elementId, 'hover_end'));
            
            // Track click events
            element.addEventListener('click', () => this.trackElementInteraction(elementId, 'click'));
        });
    }
    
    setupIntersectionObserver(element, elementId) {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    this.startElementView(elementId);
                } else {
                    this.endElementView(elementId);
                }
            });
        }, {
            threshold: 0.1, // Element is considered visible when 10% is in view
            rootMargin: '0px'
        });
        
        observer.observe(element);
    }
    
    startTask() {
        if (this.isTracking) {
            console.warn('Task already started');
            return;
        }
        
        this.taskStartTime = new Date();
        this.isTracking = true;
        
        // Send task start to backend
        this.sendTaskStart();
        
        console.log('Task started at:', this.taskStartTime);
    }
    
    startElementView(elementId) {
        if (!this.isTracking) return;
        
        const elementData = this.elementTimers.get(elementId);
        if (elementData && !elementData.startTime) {
            elementData.startTime = new Date();
            if (!elementData.firstViewTime) {
                elementData.firstViewTime = new Date();
            }
            elementData.lastViewTime = new Date();
        }
    }
    
    endElementView(elementId) {
        if (!this.isTracking) return;
        
        const elementData = this.elementTimers.get(elementId);
        if (elementData && elementData.startTime) {
            const viewDuration = (new Date() - elementData.startTime) / 1000;
            elementData.totalViewTime += viewDuration;
            elementData.startTime = null;
            elementData.lastViewTime = new Date();
        }
    }
    
    trackElementInteraction(elementId, interactionType) {
        if (!this.isTracking) return;
        
        const elementData = this.elementTimers.get(elementId);
        if (!elementData) return;
        
        switch (interactionType) {
            case 'hover':
                elementData.hoverCount++;
                break;
            case 'click':
                elementData.clickCount++;
                break;
            case 'hover_end':
                // Hover end is handled by mouseleave, no increment needed
                break;
        }
        
        // Send interaction to backend
        this.sendInteractionTracking(elementId, interactionType);
    }
    
    async sendTaskStart() {
        try {
            const response = await fetch(`/study/${this.shareToken}/task/${this.getCurrentTaskIndex()}/start`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    task_id: this.taskId,
                    start_time: this.taskStartTime.toISOString()
                })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            console.log('Task start recorded:', data);
            
        } catch (error) {
            console.error('Error recording task start:', error);
        }
    }
    
    async sendInteractionTracking(elementId, interactionType) {
        try {
            const elementData = this.elementTimers.get(elementId);
            if (!elementData) return;
            
            const response = await fetch(`/study/${this.shareToken}/tracking`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    type: interactionType,
                    element_id: elementId,
                    duration: elementData.totalViewTime
                })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
        } catch (error) {
            console.error('Error tracking interaction:', error);
        }
    }
    
    async completeTask(rating) {
        if (!this.isTracking) {
            console.warn('Task not started');
            return;
        }
        
        const taskEndTime = new Date();
        const taskDuration = (taskEndTime - this.taskStartTime) / 1000;
        
        // Prepare element interactions data
        const elementInteractions = [];
        this.elementTimers.forEach((data, elementId) => {
            if (data.totalViewTime > 0 || data.hoverCount > 0 || data.clickCount > 0) {
                elementInteractions.push({
                    element_id: elementId,
                    view_time: data.totalViewTime,
                    hover_count: data.hoverCount,
                    click_count: data.clickCount,
                    first_view_time: data.firstViewTime ? data.firstViewTime.toISOString() : null,
                    last_view_time: data.lastViewTime ? data.lastViewTime.toISOString() : null
                });
            }
        });
        
        try {
            const response = await fetch(`/study/${this.shareToken}/task/${this.getCurrentTaskIndex()}/complete`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    rating: rating,
                    task_start_time: this.taskStartTime.toISOString(),
                    element_interactions: elementInteractions
                })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            console.log('Task completed:', data);
            
            // Stop tracking
            this.stopTracking();
            
            // Handle response
            if (data.study_completed) {
                window.location.href = data.redirect_url;
            } else {
                window.location.href = data.redirect_url;
            }
            
        } catch (error) {
            console.error('Error completing task:', error);
            alert('Error completing task. Please try again.');
        }
    }
    
    getCurrentTaskIndex() {
        // Extract task index from URL or data attribute
        const urlParts = window.location.pathname.split('/');
        const taskIndex = urlParts[urlParts.length - 1];
        return parseInt(taskIndex) || 0;
    }
    
    handleVisibilityChange() {
        if (document.hidden) {
            // Page is hidden, pause timing
            this.pauseTracking();
        } else {
            // Page is visible, resume timing
            this.resumeTracking();
        }
    }
    
    pauseTracking() {
        if (!this.isTracking) return;
        
        // Record current time for all visible elements
        this.elementTimers.forEach((data, elementId) => {
            if (data.startTime) {
                const viewDuration = (new Date() - data.startTime) / 1000;
                data.totalViewTime += viewDuration;
                data.startTime = null;
            }
        });
        
        console.log('Task timing paused due to page visibility change');
    }
    
    resumeTracking() {
        if (!this.isTracking) return;
        
        // Resume timing for visible elements
        this.elementTimers.forEach((data, elementId) => {
            const element = document.querySelector(`[data-element-id="${elementId}"]`);
            if (element && this.isElementVisible(element)) {
                data.startTime = new Date();
            }
        });
        
        console.log('Task timing resumed');
    }
    
    isElementVisible(element) {
        const rect = element.getBoundingClientRect();
        return (
            rect.top >= 0 &&
            rect.left >= 0 &&
            rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
            rect.right <= (window.innerWidth || document.documentElement.clientWidth)
        );
    }
    
    handlePageUnload(event) {
        if (this.isTracking) {
            // Send abandonment data
            this.sendAbandonmentData();
            
            // Show confirmation dialog
            event.preventDefault();
            event.returnValue = 'Are you sure you want to leave? Your progress will be lost.';
            return event.returnValue;
        }
    }
    
    async sendAbandonmentData() {
        try {
            await fetch(`/study/${this.shareToken}/abandon`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    reason: 'Page unload'
                })
            });
        } catch (error) {
            console.error('Error sending abandonment data:', error);
        }
    }
    
    stopTracking() {
        this.isTracking = false;
        
        // Remove event listeners
        document.removeEventListener('visibilitychange', this.visibilityChangeHandler);
        window.removeEventListener('beforeunload', this.pageUnloadHandler);
        
        console.log('Task tracking stopped');
    }
    
    getTaskDuration() {
        if (!this.taskStartTime) return 0;
        return (new Date() - this.taskStartTime) / 1000;
    }
    
    getElementStats(elementId) {
        const data = this.elementTimers.get(elementId);
        if (!data) return null;
        
        return {
            total_view_time: data.totalViewTime,
            hover_count: data.hoverCount,
            click_count: data.clickCount,
            first_view_time: data.firstViewTime,
            last_view_time: data.lastViewTime
        };
    }
    
    // Utility method to format duration
    formatDuration(seconds) {
        if (seconds < 60) {
            return `${seconds.toFixed(1)}s`;
        } else if (seconds < 3600) {
            const minutes = Math.floor(seconds / 60);
            const remainingSeconds = seconds % 60;
            return `${minutes}m ${remainingSeconds.toFixed(0)}s`;
        } else {
            const hours = Math.floor(seconds / 3600);
            const remainingMinutes = Math.floor((seconds % 3600) / 60);
            return `${hours}h ${remainingMinutes}m`;
        }
    }
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        TaskTimer: TaskTimer
      };}
