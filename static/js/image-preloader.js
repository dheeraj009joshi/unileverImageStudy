/**
 * Image Preloading Service
 * Preloads all study images in the background for instant display during tasks
 */

class ImagePreloader {
    constructor() {
        this.loadedImages = new Map();
        this.loadingPromises = new Map();
        this.progress = {
            total: 0,
            loaded: 0,
            failed: 0
        };
        this.isPreloading = false;
        this.preloadComplete = false;
    }

    /**
     * Start preloading images for a study
     * @param {Object} studyData - Study data containing image URLs
     * @param {Function} onProgress - Progress callback function
     * @param {Function} onComplete - Completion callback function
     */
    async preloadStudyImages(studyData, onProgress = null, onComplete = null) {
        if (this.isPreloading) {
            console.log('Image preloading already in progress');
            return;
        }

        // Validate study data
        if (!studyData || typeof studyData !== 'object') {
            console.error('Invalid study data provided to preloader');
            if (onComplete) onComplete();
            return;
        }

        this.isPreloading = true;
        this.preloadComplete = false;
        this.progress = { total: 0, loaded: 0, failed: 0 };

        // Debug logging for troubleshooting
        console.log('ImagePreloader: Starting preload for study type:', studyData.study_type);
        
        try {
            // Collect all image URLs based on study type
            const imageUrls = this.collectImageUrls(studyData);
            this.progress.total = imageUrls.length;
            
            console.log('ImagePreloader: Found', imageUrls.length, 'images to preload');
            if (imageUrls.length > 0) {
                console.log('ImagePreloader: First few URLs:', imageUrls.slice(0, 3));
            }

            if (imageUrls.length === 0) {
                // No images to preload - complete immediately
                console.log('ImagePreloader: No images found, completing immediately');
                this.preloadComplete = true;
                this.isPreloading = false;
                if (onComplete) onComplete();
                return;
            }

            // Start preloading all images
            const preloadPromises = imageUrls.map((url, index) => 
                this.preloadSingleImage(url, index, onProgress)
            );

            // Wait for all images to load (or fail)
            await Promise.allSettled(preloadPromises);

            this.preloadComplete = true;
            this.isPreloading = false;

            // Silent completion - no console logs for clean UX
            if (onComplete) onComplete();

        } catch (error) {
            // Silent error handling - no console errors for clean UX
            this.isPreloading = false;
            if (onComplete) onComplete();
        }
    }

    /**
     * Collect all image URLs from study data
     * @param {Object} studyData - Study data
     * @returns {Array} Array of image URLs
     */
    collectImageUrls(studyData) {
        const imageUrls = new Set(); // Use Set to avoid duplicates

        try {
            if (studyData.study_type === 'grid') {
                // For grid studies, collect from elements
                if (studyData.elements && Array.isArray(studyData.elements)) {
                    studyData.elements.forEach(element => {
                        try {
                            if (element && element.image && element.image.url && typeof element.image.url === 'string') {
                                imageUrls.add(element.image.url);
                            }
                        } catch (error) {
                            console.warn('Error processing grid element:', error);
                        }
                    });
                }
            } else if (studyData.study_type === 'layer') {
                // For layer studies, collect from study_layers
                if (studyData.study_layers && Array.isArray(studyData.study_layers)) {
                    studyData.study_layers.forEach(layer => {
                        try {
                            if (layer && layer.images && Array.isArray(layer.images)) {
                                layer.images.forEach(image => {
                                    try {
                                        if (image && image.url && typeof image.url === 'string') {
                                            imageUrls.add(image.url);
                                        }
                                    } catch (error) {
                                        console.warn('Error processing layer image:', error);
                                    }
                                });
                            }
                        } catch (error) {
                            console.warn('Error processing layer:', error);
                        }
                    });
                }
            }
        } catch (error) {
            console.error('Error collecting image URLs:', error);
        }

        return Array.from(imageUrls);
    }

    /**
     * Preload a single image
     * @param {string} url - Image URL
     * @param {number} index - Image index for progress tracking
     * @param {Function} onProgress - Progress callback
     * @returns {Promise} Promise that resolves when image is loaded
     */
    preloadSingleImage(url, index, onProgress) {
        // Return existing promise if already loading
        if (this.loadingPromises.has(url)) {
            return this.loadingPromises.get(url);
        }

        const promise = new Promise((resolve, reject) => {
            // Handle CORS gracefully - try different strategies
            const tryLoadImage = (corsMode) => {
                const testImg = new Image();
                
                testImg.onload = () => {
                    // Success - use this image
                    this.loadedImages.set(url, testImg);
                    this.progress.loaded++;
                    
                    if (onProgress) {
                        onProgress({
                            loaded: this.progress.loaded,
                            total: this.progress.total,
                            percentage: Math.round((this.progress.loaded / this.progress.total) * 100),
                            currentUrl: url
                        });
                    }
                    
                    resolve(testImg);
                };
                
                testImg.onerror = () => {
                    // Failed with this CORS mode, try next
                    if (corsMode === 'anonymous') {
                        tryLoadImage('use-credentials');
                    } else if (corsMode === 'use-credentials') {
                        tryLoadImage('none');
                    } else {
                        // All CORS modes failed
                        this.progress.failed++;
                        
                        if (onProgress) {
                            onProgress({
                                loaded: this.progress.loaded,
                                total: this.progress.total,
                                percentage: Math.round((this.progress.loaded / this.progress.total) * 100),
                                currentUrl: url,
                                failed: this.progress.failed
                            });
                        }
                        
                        resolve(null);
                    }
                };
                
                // Set CORS mode
                if (corsMode === 'none') {
                    testImg.crossOrigin = null;
                } else {
                    testImg.crossOrigin = corsMode;
                }
                
                testImg.src = url;
            };
            
            // Start with anonymous CORS
            tryLoadImage('anonymous');
        });

        this.loadingPromises.set(url, promise);
        return promise;
    }

    /**
     * Get a preloaded image
     * @param {string} url - Image URL
     * @returns {Image|null} Preloaded image or null if not found
     */
    getPreloadedImage(url) {
        return this.loadedImages.get(url) || null;
    }

    /**
     * Check if an image is preloaded
     * @param {string} url - Image URL
     * @returns {boolean} True if image is preloaded
     */
    isImagePreloaded(url) {
        return this.loadedImages.has(url);
    }

    /**
     * Get preloading status
     * @returns {Object} Preloading status information
     */
    getStatus() {
        return {
            isPreloading: this.isPreloading,
            preloadComplete: this.preloadComplete,
            progress: { ...this.progress },
            loadedCount: this.loadedImages.size
        };
    }

    /**
     * Check if images are ready for tasks
     * @returns {boolean} True if all images are loaded
     */
    areImagesReady() {
        return this.preloadComplete && this.progress.loaded > 0;
    }

    /**
     * Get loading progress percentage
     * @returns {number} Progress percentage (0-100)
     */
    getProgressPercentage() {
        if (this.progress.total === 0) return 100;
        return Math.round((this.progress.loaded / this.progress.total) * 100);
    }

    /**
     * Wait for preloading to complete
     * @param {number} timeout - Maximum time to wait in milliseconds
     * @returns {Promise} Promise that resolves when preloading is complete
     */
    waitForCompletion(timeout = 55000) {
        return new Promise((resolve, reject) => {
            if (this.preloadComplete) {
                resolve(this.getStatus());
                return;
            }

            const startTime = Date.now();
            const checkInterval = setInterval(() => {
                if (this.preloadComplete) {
                    clearInterval(checkInterval);
                    resolve(this.getStatus());
                } else if (Date.now() - startTime > timeout) {
                    clearInterval(checkInterval);
                    reject(new Error('Preloading timeout'));
                }
            }, 100);
        });
    }

    /**
     * Clear all preloaded images (for memory management)
     */
    clear() {
        this.loadedImages.clear();
        this.loadingPromises.clear();
        this.progress = { total: 0, loaded: 0, failed: 0 };
        this.isPreloading = false;
        this.preloadComplete = false;
    }
}

// Create global instance
window.imagePreloader = new ImagePreloader();

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ImagePreloader;
}
