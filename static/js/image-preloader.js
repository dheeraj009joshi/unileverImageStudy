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
        
        // Progressive loading properties
        this.batchSize = 5;
        this.currentBatch = 0;
        this.totalBatches = 0;
        this.isSilentMode = false;
        this.loadingComplete = false;
        
        // Image caching
        this.cacheKey = 'imagePreloaderCache';
        this.loadCacheFromStorage();
        
        // Parallel loading configuration - load ALL images simultaneously
        this.maxConcurrent = 50; // Increased for simultaneous loading
        this.activeLoads = 0;
        this.loadQueue = [];
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

        console.log('🔍 collectImageUrls called with studyData:', studyData);
        console.log('🔍 Study type:', studyData?.study_type);

        try {
            if (studyData.study_type === 'grid' || studyData.study_type === 'grid_v2') {
                console.log('🔍 Processing grid study');
                console.log('🔍 Elements:', studyData.elements);
                console.log('🔍 Grid Categories:', studyData.grid_categories);
                
                // For new grid studies, collect from grid_categories
                if (studyData.grid_categories && Array.isArray(studyData.grid_categories)) {
                    console.log(`🔍 Found ${studyData.grid_categories.length} grid categories`);
                    studyData.grid_categories.forEach((category, categoryIndex) => {
                        try {
                            console.log(`🔍 Category ${categoryIndex}:`, category);
                            if (category && category.elements && Array.isArray(category.elements)) {
                                category.elements.forEach((element, elementIndex) => {
                                    try {
                                        console.log(`🔍 Category ${categoryIndex} Element ${elementIndex}:`, element);
                                        // Check for URL in element.content (new structure) or element.image.url (legacy)
                                        const imageUrl = element.content || (element.image && element.image.url);
                                        if (imageUrl && typeof imageUrl === 'string') {
                                            console.log(`✅ Adding grid category image URL: ${imageUrl}`);
                                            imageUrls.add(imageUrl);
                                        } else {
                                            console.log(`❌ Invalid grid category element ${categoryIndex}-${elementIndex}:`, element);
                                        }
                                    } catch (error) {
                                        console.warn('Error processing grid category element:', error);
                                    }
                                });
                            } else {
                                console.log(`❌ No elements array in category ${categoryIndex}:`, category);
                            }
                        } catch (error) {
                            console.warn('Error processing grid category:', error);
                        }
                    });
                }
                
                // For legacy grid studies, collect from elements
                if (studyData.elements && Array.isArray(studyData.elements)) {
                    console.log(`🔍 Found ${studyData.elements.length} legacy elements`);
                    studyData.elements.forEach((element, index) => {
                        try {
                            console.log(`🔍 Legacy Element ${index}:`, element);
                            if (element && element.image && element.image.url && typeof element.image.url === 'string') {
                                console.log(`✅ Adding legacy grid image URL: ${element.image.url}`);
                                imageUrls.add(element.image.url);
                            } else {
                                console.log(`❌ Invalid legacy grid element ${index}:`, element);
                            }
                        } catch (error) {
                            console.warn('Error processing legacy grid element:', error);
                        }
                    });
                } else {
                    console.log('❌ No elements array found in grid study');
                }
            } else if (studyData.study_type === 'layer') {
                console.log('🔍 Processing layer study');
                console.log('🔍 Study layers:', studyData.study_layers);
                console.log('🔍 Study layers type:', typeof studyData.study_layers);
                console.log('🔍 Study layers is array:', Array.isArray(studyData.study_layers));
                console.log('🔍 Study layers length:', studyData.study_layers ? studyData.study_layers.length : 'undefined');
                
                // For layer studies, collect from study_layers
                if (studyData.study_layers && Array.isArray(studyData.study_layers)) {
                    studyData.study_layers.forEach((layer, layerIndex) => {
                        try {
                            console.log(`🔍 Layer ${layerIndex}:`, layer);
                            console.log(`🔍 Layer ${layerIndex} type:`, typeof layer);
                            console.log(`🔍 Layer ${layerIndex} images:`, layer.images);
                            console.log(`🔍 Layer ${layerIndex} images type:`, typeof layer.images);
                            console.log(`🔍 Layer ${layerIndex} images is array:`, Array.isArray(layer.images));
                            
                            if (layer && layer.images && Array.isArray(layer.images)) {
                                console.log(`🔍 Layer ${layerIndex} has ${layer.images.length} images`);
                                layer.images.forEach((image, imageIndex) => {
                                    try {
                                        console.log(`🔍 Layer ${layerIndex} Image ${imageIndex}:`, image);
                                        console.log(`🔍 Layer ${layerIndex} Image ${imageIndex} type:`, typeof image);
                                        console.log(`🔍 Layer ${layerIndex} Image ${imageIndex} url:`, image.url);
                                        console.log(`🔍 Layer ${layerIndex} Image ${imageIndex} url type:`, typeof image.url);
                                        
                                        if (image && image.url && typeof image.url === 'string' && image.url.trim() !== '') {
                                            console.log(`✅ Adding layer image URL: ${image.url}`);
                                            imageUrls.add(image.url);
                                        } else {
                                            console.log(`❌ Invalid layer image ${layerIndex}-${imageIndex}:`, image);
                                        }
                                    } catch (error) {
                                        console.warn('Error processing layer image:', error);
                                    }
                                });
                            } else {
                                console.log(`❌ No images array in layer ${layerIndex}:`, layer);
                            }
                        } catch (error) {
                            console.warn('Error processing layer:', error);
                        }
                    });
                } else {
                    console.log('❌ No study_layers array found in layer study');
                }
                
                // Also collect default background image for layer studies
                if (studyData.default_background && studyData.default_background.url) {
                    console.log('🔍 Found default background:', studyData.default_background);
                    console.log('🔍 Default background URL:', studyData.default_background.url);
                    if (typeof studyData.default_background.url === 'string' && studyData.default_background.url.trim() !== '') {
                        console.log('✅ Adding default background image URL:', studyData.default_background.url);
                        imageUrls.add(studyData.default_background.url);
                    } else {
                        console.log('❌ Invalid default background URL:', studyData.default_background.url);
                    }
                } else {
                    console.log('🔍 No default background found in layer study');
                }
            } else {
                console.log('❌ Unknown study type:', studyData.study_type);
            }
        } catch (error) {
            console.error('Error collecting image URLs:', error);
        }

        const urls = Array.from(imageUrls);
        console.log(`🔍 Collected ${urls.length} image URLs:`, urls);
        return urls;
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
        this.currentBatch = 0;
        this.totalBatches = 0;
        this.isSilentMode = false;
        this.loadingComplete = false;
    }

    /**
     * Start silent loading - load all images at once
     * @param {Object} studyData - Study data containing image URLs
     */
    async preloadStudyImagesSilent(studyData) {
        console.log('🔧 preloadStudyImagesSilent called with:', studyData);
        console.log('🔧 Current page:', window.location.pathname);
        
        if (this.isPreloading) {
            console.log('Silent image preloading already in progress');
            return;
        }

        // Validate study data
        if (!studyData || typeof studyData !== 'object') {
            console.error('Invalid study data provided to silent preloader');
            return;
        }

        this.isPreloading = true;
        this.isSilentMode = true;
        this.progress = { total: 0, loaded: 0, failed: 0 };
        
        console.log('🔧 Starting image preloading on page:', window.location.pathname);

        try {
            // Collect all image URLs
            const imageUrls = this.collectImageUrls(studyData);
            this.progress.total = imageUrls.length;
            
            console.log(`🔧 Silent preloader: Found ${imageUrls.length} images to load`);

            if (imageUrls.length === 0) {
                console.log('🔧 No images found, completing immediately');
                this.loadingComplete = true;
                this.isPreloading = false;
                return;
            }

            // Check cache and filter out already cached images
            const uncachedUrls = imageUrls.filter(url => !this.isImageCached(url));
            const cachedCount = imageUrls.length - uncachedUrls.length;
            
            console.log(`🔧 Cache check: ${cachedCount} cached, ${uncachedUrls.length} need loading`);

            // If all images are cached, complete immediately
            if (uncachedUrls.length === 0) {
                console.log('🔧 All images already cached, completing immediately');
                this.progress.loaded = imageUrls.length;
                this.loadingComplete = true;
                this.isPreloading = false;
                return;
            }

            // Load ALL uncached images simultaneously
            console.log('🔧 Loading ALL uncached images simultaneously...');
            await this.loadImagesInParallel(uncachedUrls);
            
            // Update progress to include cached images
            this.progress.loaded += cachedCount;
            
            // Ensure total count is correct
            if (this.progress.total === 0) {
                this.progress.total = this.progress.loaded;
            }
            
            console.log('🔧 All images loaded:', this.progress.loaded, 'total (', cachedCount, 'cached,', this.progress.loaded - cachedCount, 'new)');
            this.loadingComplete = true;
            this.isPreloading = false;
            
            // Save cache to storage
            this.saveCacheToStorage();

        } catch (error) {
            console.error('Error in silent preloading:', error);
            this.isPreloading = false;
        }
    }

    /**
     * Load a batch of images silently
     * @param {Array} imageUrls - All image URLs
     * @param {number} batchIndex - Current batch index
     */
    async loadBatchSilent(imageUrls, batchIndex) {
        const start = batchIndex * this.batchSize;
        const end = Math.min(start + this.batchSize, imageUrls.length);
        const batchUrls = imageUrls.slice(start, end);
        
        console.log(`Loading batch ${batchIndex + 1}/${this.totalBatches}: ${batchUrls.length} images`);
        
        // Load batch silently
        const promises = batchUrls.map((url, index) => 
            this.preloadSingleImageSilent(url, start + index)
        );
        
        await Promise.allSettled(promises);
        this.currentBatch++;
        
        // Check if all batches are complete
        if (this.currentBatch >= this.totalBatches) {
            this.loadingComplete = true;
            this.isPreloading = false;
            console.log('Silent preloading complete:', this.progress.loaded, 'images loaded');
        }
    }

    /**
     * Preload a single image silently (no progress callbacks)
     * @param {string} url - Image URL
     * @param {number} index - Image index
     * @returns {Promise} Promise that resolves when image is loaded
     */
    preloadSingleImageSilent(url, index) {
        // Return existing promise if already loading
        if (this.loadingPromises.has(url)) {
            return this.loadingPromises.get(url);
        }

        const promise = new Promise((resolve) => {
            // Try WebP optimization first, fallback to original
            this.tryWebPOptimization(url)
                .then(optimizedImg => {
                    if (optimizedImg) {
                        this.loadedImages.set(url, optimizedImg);
                        this.progress.loaded++;
                        console.log(`✅ Image optimized and loaded: ${url}`);
                        resolve(optimizedImg);
                    } else {
                        // Fallback to original image
                        this.loadOriginalImage(url, resolve);
                    }
                })
                .catch(() => {
                    // Fallback to original image
                    this.loadOriginalImage(url, resolve);
                });
        });

        this.loadingPromises.set(url, promise);
        return promise;
    }

    /**
     * Try to optimize image to WebP format
     * @param {string} url - Image URL
     * @returns {Promise} Promise that resolves with optimized image or null
     */
    async tryWebPOptimization(url) {
        try {
            // Check if browser supports WebP
            if (!this.supportsWebP()) {
                console.log('WebP not supported, using original image');
                return null;
            }

            // Load original image
            const originalImg = await this.loadImageAsBlob(url);
            if (!originalImg) return null;

            // Convert to WebP with transparency preservation
            const webpBlob = await this.convertToWebPWithTransparency(originalImg);
            if (!webpBlob) return null;

            // Create optimized image
            const optimizedImg = new Image();
            return new Promise((resolve) => {
                optimizedImg.onload = () => resolve(optimizedImg);
                optimizedImg.onerror = () => resolve(null);
                optimizedImg.src = URL.createObjectURL(webpBlob);
            });
        } catch (error) {
            console.warn('WebP optimization failed:', error);
            return null;
        }
    }

    /**
     * Load image as blob for processing
     * @param {string} url - Image URL
     * @returns {Promise} Promise that resolves with blob
     */
    loadImageAsBlob(url) {
        return fetch(url)
            .then(response => response.blob())
            .catch(() => null);
    }

    /**
     * Convert image to WebP while preserving transparency
     * @param {Blob} imageBlob - Original image blob
     * @returns {Promise} Promise that resolves with WebP blob
     */
    async convertToWebPWithTransparency(imageBlob) {
        return new Promise((resolve) => {
            const img = new Image();
            img.onload = () => {
                try {
                    const canvas = document.createElement('canvas');
                    const ctx = canvas.getContext('2d');
                    
                    // Set canvas size
                    canvas.width = img.width;
                    canvas.height = img.height;
                    
                    // Clear canvas to transparent (not white)
                    ctx.clearRect(0, 0, canvas.width, canvas.height);
                    
                    // Draw image preserving transparency
                    ctx.drawImage(img, 0, 0);
                    
                    // Convert to WebP with transparency
                    canvas.toBlob(
                        (webpBlob) => {
                            if (webpBlob) {
                                console.log(`✅ Converted to WebP: ${(webpBlob.size / 1024).toFixed(1)}KB`);
                                resolve(webpBlob);
                            } else {
                                resolve(null);
                            }
                        },
                        'image/webp',
                        0.85 // 85% quality
                    );
                } catch (error) {
                    console.warn('Canvas conversion failed:', error);
                    resolve(null);
                }
            };
            img.onerror = () => resolve(null);
            img.src = URL.createObjectURL(imageBlob);
        });
    }

    /**
     * Load original image without optimization
     * @param {string} url - Image URL
     * @param {Function} resolve - Promise resolve function
     */
    loadOriginalImage(url, resolve) {
        const testImg = new Image();
        
        testImg.onload = () => {
            this.loadedImages.set(url, testImg);
            this.progress.loaded++;
            console.log(`✅ Original image loaded: ${url}`);
            resolve(testImg);
        };
        
        testImg.onerror = () => {
            this.progress.failed++;
            console.warn(`❌ Failed to load image: ${url}`);
            resolve(null);
        };
        
        testImg.src = url;
    }

    /**
     * Check if browser supports WebP
     * @returns {boolean} True if WebP is supported
     */
    supportsWebP() {
        const canvas = document.createElement('canvas');
        canvas.width = 1;
        canvas.height = 1;
        return canvas.toDataURL('image/webp').indexOf('data:image/webp') === 0;
    }

    /**
     * Continue silent loading from next page
     * @param {Object} studyData - Study data containing image URLs
     */
    async continueSilentLoading(studyData) {
        console.log('🔄 continueSilentLoading called on page:', window.location.pathname);
        console.log('Current state:', {
            isSilentMode: this.isSilentMode,
            loadingComplete: this.loadingComplete,
            loaded: this.progress.loaded,
            total: this.progress.total
        });

        // If not in silent mode, start silent loading
        if (!this.isSilentMode) {
            console.log('🔄 Not in silent mode, starting silent preloading');
            await this.preloadStudyImagesSilent(studyData);
            return;
        }

        // If already complete, return
        if (this.loadingComplete) {
            console.log('✅ Loading already complete');
            return;
        }

        // If still loading, just wait for completion
        console.log('🔄 Images still loading, waiting for completion...');
    }

    /**
     * Check if silent loading is complete
     * @returns {boolean} True if loading is complete
     */
    isLoadingComplete() {
        // If we have loaded images and either loading is complete OR we have images in memory
        const isComplete = (this.loadingComplete && this.progress.loaded > 0) || 
                          (this.loadedImages.size > 0 && this.progress.loaded > 0);
        
        console.log('🔍 isLoadingComplete check:', {
            loadingComplete: this.loadingComplete,
            loaded: this.progress.loaded,
            total: this.progress.total,
            loadedImagesSize: this.loadedImages.size,
            isComplete: isComplete
        });
        return isComplete;
    }

    /**
     * Get loading progress (for conditional indicator)
     * @returns {Object} Progress information
     */
    getLoadingProgress() {
        return {
            loaded: this.progress.loaded,
            total: this.progress.total,
            percentage: this.progress.total > 0 ? Math.round((this.progress.loaded / this.progress.total) * 100) : 0,
            isComplete: this.isLoadingComplete()
        };
    }

    /**
     * Load cache from localStorage
     */
    loadCacheFromStorage() {
        try {
            const cached = localStorage.getItem(this.cacheKey);
            if (cached) {
                const cacheData = JSON.parse(cached);
                console.log('📦 Loaded image cache from storage:', Object.keys(cacheData).length, 'images');
                
                // Convert cached data back to Map
                Object.entries(cacheData).forEach(([url, imageData]) => {
                    if (imageData && imageData.url) {
                        // Create image and load it
                        const img = new Image();
                        img.onload = () => {
                            this.loadedImages.set(url, img);
                            this.progress.loaded++;
                        };
                        img.src = imageData.url;
                    }
                });
                
                // If we have cached images, mark as complete
                if (this.loadedImages.size > 0) {
                    this.loadingComplete = true;
                    console.log('✅ Images loaded from cache, marking as complete');
                }
            }
        } catch (error) {
            console.warn('Failed to load image cache from storage:', error);
        }
    }

    /**
     * Save cache to localStorage
     */
    saveCacheToStorage() {
        try {
            const cacheData = {};
            this.loadedImages.forEach((img, url) => {
                if (img && img.src) {
                    // Store the original URL to avoid CORS issues
                    cacheData[url] = {
                        url: url, // Store the original URL
                        timestamp: Date.now()
                    };
                }
            });
            
            localStorage.setItem(this.cacheKey, JSON.stringify(cacheData));
            console.log('💾 Saved image cache to storage:', Object.keys(cacheData).length, 'images');
        } catch (error) {
            console.warn('Failed to save image cache to storage:', error);
        }
    }

    /**
     * Check if image is already cached
     * @param {string} url - Image URL
     * @returns {boolean} True if image is cached
     */
    isImageCached(url) {
        return this.loadedImages.has(url);
    }

    /**
     * Get cached image
     * @param {string} url - Image URL
     * @returns {Image|null} Cached image or null
     */
    getCachedImage(url) {
        return this.loadedImages.get(url) || null;
    }

    /**
     * Load ALL images simultaneously without chunking
     * @param {Array} urls - Array of image URLs to load
     * @returns {Promise} Promise that resolves when all images are loaded
     */
    async loadImagesInParallel(urls) {
        console.log(`🚀 Loading ALL ${urls.length} images simultaneously (no chunking)`);
        
        // Create promises for ALL images at once
        const allPromises = urls.map((url, index) => 
            this.preloadSingleImageSilent(url, index)
        );
        
        // Wait for ALL images to complete simultaneously
        const results = await Promise.allSettled(allPromises);
        
        // Count successful and failed loads
        const successful = results.filter(result => result.status === 'fulfilled' && result.value !== null).length;
        const failed = results.filter(result => result.status === 'rejected' || result.value === null).length;
        
        console.log(`🎉 All images loaded simultaneously: ${successful} successful, ${failed} failed`);
    }

    /**
     * Split array into chunks
     * @param {Array} array - Array to chunk
     * @param {number} chunkSize - Size of each chunk
     * @returns {Array} Array of chunks
     */
    chunkArray(array, chunkSize) {
        const chunks = [];
        for (let i = 0; i < array.length; i += chunkSize) {
            chunks.push(array.slice(i, i + chunkSize));
        }
        return chunks;
    }
}

// Create global instance
window.imagePreloader = new ImagePreloader();

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ImagePreloader;
}
