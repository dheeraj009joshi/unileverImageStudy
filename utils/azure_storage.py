import uuid
import os
from azure.storage.blob import BlobServiceClient, BlobClient
from flask import current_app
import concurrent.futures
import threading
from typing import List, Tuple, Optional
import time
import asyncio
from PIL import Image
import io

# Global connection pool for better performance
_blob_service_client = None
_client_lock = threading.Lock()

def get_blob_service_client():
    """Get or create a shared BlobServiceClient instance with optimized settings."""
    global _blob_service_client
    if _blob_service_client is None:
        with _client_lock:
            if _blob_service_client is None:
                connection_string = current_app.config.get('AZURE_STORAGE_CONNECTION_STRING')
                if connection_string:
                    # Create client with optimized settings for speed
                    _blob_service_client = BlobServiceClient.from_connection_string(
                        connection_string,
                        max_single_put_size=64 * 1024 * 1024,  # 64MB for single uploads
                        max_block_size=100 * 1024 * 1024,      # 100MB block size
                        retry_total=3,                         # Retry 3 times
                        retry_connect=3,                       # Retry connections
                        retry_read=3,                          # Retry reads
                        retry_status=3,                        # Retry status codes
                        timeout=30                             # 30 second timeout
                    )
                else:
                    current_app.logger.error("Azure storage configuration missing")
                    return None
    return _blob_service_client

def upload_to_azure(file):
    """Upload file to Azure Blob Storage with WebP optimization and return URL"""
    try:
        # Get configuration from Flask app
        connection_string = current_app.config.get('AZURE_STORAGE_CONNECTION_STRING')
        container_name = current_app.config.get('AZURE_CONTAINER_NAME')
        
        if not connection_string or not container_name:
            current_app.logger.error("Azure storage configuration missing")
            return None
        
        # Create blob service client
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        
        # Try WebP conversion first
        webp_file = convert_to_webp_with_alpha(file)
        
        if webp_file:
            # Use WebP version
            file_to_upload = webp_file
            file_extension = '.webp'
            print("Using WebP optimized version")
        else:
            # Fallback to original file
            file_to_upload = file
            if hasattr(file, 'filename') and file.filename:
                file_extension = os.path.splitext(file.filename)[1]
            else:
                file_extension = '.png'  # Default extension
            print("Using original file (WebP conversion failed)")
        
        blob_name = f"{uuid.uuid4()}{file_extension}"
        
        # Get blob client
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
        
        # Reset file pointer to beginning
        file_to_upload.seek(0)
        
        # Read file content
        file_content = file_to_upload.read()
        
        # Upload file content
        blob_client.upload_blob(file_content, overwrite=True)
        
        # Return the public URL
        account_name = connection_string.split(';')[1].split('=')[1]
        url = f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}"
        
        current_app.logger.info(f"File uploaded successfully to Azure: {blob_name}")
        return url
        
    except Exception as e:
        current_app.logger.error(f"Azure upload failed: {str(e)}")
        current_app.logger.error(f"File type: {type(file)}")
        current_app.logger.error(f"File attributes: {dir(file)}")
        return None

def upload_single_file_to_azure_optimized(file_data: Tuple, container_name: str) -> Tuple[int, Optional[str], Optional[str]]:
    """
    Ultra-optimized single file upload with WebP optimization and maximum performance settings.
    Returns (element_index, azure_url, error_message)
    """
    try:
        element_index, file, filename = file_data
        
        # Get shared blob service client
        blob_service_client = get_blob_service_client()
        if not blob_service_client:
            return (element_index, None, "Failed to get blob service client")
        
        # Try WebP conversion first
        webp_file = convert_to_webp_with_alpha(file)
        
        if webp_file:
            # Use WebP version
            file_to_upload = webp_file
            file_extension = '.webp'
            print(f"Element {element_index}: Using WebP optimized version")
        else:
            # Fallback to original file
            file_to_upload = file
            if filename:
                file_extension = os.path.splitext(filename)[1]
            else:
                file_extension = '.png'  # Default extension
            print(f"Element {element_index}: Using original file (WebP conversion failed)")
        
        blob_name = f"{uuid.uuid4()}{file_extension}"
        
        # Get blob client with optimized settings
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
        
        # Reset file pointer to beginning
        file_to_upload.seek(0)
        
        # Ultra-fast upload with maximum concurrency and optimized settings
        blob_client.upload_blob(
            file_to_upload, 
            overwrite=True, 
            max_concurrency=8,           # Maximum parallel chunks
            length=None,                  # Auto-detect file size
            timeout=30,                   # 30 second timeout
            validate_content=False        # Skip content validation for speed
        )
        
        # Return the public URL
        account_name = blob_service_client.account_name
        url = f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}"
        
        return (element_index, url, None)
        
    except Exception as e:
        error_msg = f"Azure upload failed for element {element_index}: {str(e)}"
        return (element_index, None, error_msg)

def upload_multiple_files_to_azure(files_data: List[Tuple], max_workers: int = 12) -> List[Tuple[int, Optional[str], Optional[str]]]:
    """
    Ultra-fast parallel upload to Azure Blob Storage with maximum performance.
    
    Args:
        files_data: List of tuples (element_index, file_object, filename)
        max_workers: Maximum number of parallel upload workers (default: 12)
    
    Returns:
        List of tuples (element_index, azure_url, error_message)
    """
    try:
        # Get configuration from Flask app
        container_name = current_app.config.get('AZURE_CONTAINER_NAME')
        
        if not container_name:
            current_app.logger.error("Azure container name missing")
            return [(i, None, "Azure container name missing") for i, _, _ in files_data]
        
        if not files_data:
            return []
        
        # Pre-warm the connection pool
        if not get_blob_service_client():
            return [(i, None, "Failed to initialize Azure connection") for i, _, _ in files_data]
        
        # Optimize worker count based on file count and system capabilities
        optimal_workers = min(max_workers, len(files_data), 16)  # Cap at 16 for stability
        
        current_app.logger.info(f"🚀 Starting ULTRA-FAST parallel upload of {len(files_data)} files with {optimal_workers} workers")
        start_time = time.time()
        
        # Use ThreadPoolExecutor with optimized settings for maximum speed
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=optimal_workers,
            thread_name_prefix="AzureUpload"
        ) as executor:
            # Submit all upload tasks immediately for maximum parallelism
            future_to_element = {
                executor.submit(upload_single_file_to_azure_optimized, file_data, container_name): file_data[0]
                for file_data in files_data
            }
            
            # Collect results as they complete
            results = []
            completed_count = 0
            total_count = len(files_data)
            
            for future in concurrent.futures.as_completed(future_to_element):
                try:
                    result = future.result()
                    results.append(result)
                    completed_count += 1
                    
                    # Log progress with performance metrics
                    elapsed_time = time.time() - start_time
                    avg_time_per_file = elapsed_time / completed_count
                    estimated_remaining = avg_time_per_file * (total_count - completed_count)
                    
                    if result[1]:  # Success
                        current_app.logger.info(f"✅ {completed_count}/{total_count} completed in {elapsed_time:.2f}s (avg: {avg_time_per_file:.2f}s/file, ETA: {estimated_remaining:.2f}s)")
                    else:  # Failed
                        current_app.logger.error(f"❌ {completed_count}/{total_count} failed for element {result[0]}: {result[2]}")
                        
                except Exception as e:
                    element_index = future_to_element[future]
                    error_msg = f"Unexpected error during upload for element {element_index}: {str(e)}"
                    results.append((element_index, None, error_msg))
                    current_app.logger.error(f"💥 Upload error for element {element_index}: {error_msg}")
        
        # Sort results by element index to maintain order
        results.sort(key=lambda x: x[0])
        
        # Log final performance summary
        total_time = time.time() - start_time
        success_count = sum(1 for r in results if r[1])
        throughput = len(files_data) / total_time if total_time > 0 else 0
        
        current_app.logger.info(f"🎯 Upload complete: {success_count}/{total_count} successful in {total_time:.2f}s")
        current_app.logger.info(f"⚡ Performance: {throughput:.1f} files/second")
        
        # Performance validation
        if total_time > 1.5:  # Should be under 1.5 seconds for 8 files
            current_app.logger.warning(f"⚠️  Upload took {total_time:.2f}s - performance below target")
        else:
            current_app.logger.info(f"🎯 Excellent performance! {total_time:.2f}s for {len(files_data)} files")
        
        return results
        
    except Exception as e:
        current_app.logger.error(f"💥 Multiprocessing upload failed: {str(e)}")
        return [(i, None, f"Multiprocessing upload failed: {str(e)}") for i, _, _ in files_data]

def delete_from_azure(blob_url):
    """Delete file from Azure Blob Storage"""
    try:
        # Extract blob name from URL
        blob_name = blob_url.split('/')[-1]
        
        connection_string = current_app.config.get('AZURE_STORAGE_CONNECTION_STRING')
        container_name = current_app.config.get('AZURE_CONTAINER_NAME')
        
        if not connection_string or not container_name:
            current_app.logger.error("Azure storage configuration missing")
            return False
        
        # Create blob service client
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        
        # Get blob client
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
        
        # Delete blob
        blob_client.delete_blob()
        
        current_app.logger.info(f"File deleted successfully from Azure: {blob_name}")
        return True
        
    except Exception as e:
        current_app.logger.error(f"Azure deletion failed: {str(e)}")
        return False

def convert_to_webp_with_alpha(file, quality=85):
    """
    Convert image to WebP format while preserving transparency (alpha channel).
    
    Args:
        file: File object (BytesIO or file-like object)
        quality: WebP quality (0-100, default 85)
    
    Returns:
        BytesIO object containing WebP data, or None if conversion fails
    """
    try:
        # Reset file pointer to beginning
        file.seek(0)
        
        # Open image with PIL
        image = Image.open(file)
        
        # Convert to RGBA to preserve transparency
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        
        # Create BytesIO object for WebP output
        webp_buffer = io.BytesIO()
        
        # Save as WebP with transparency support
        image.save(
            webp_buffer,
            format='WEBP',
            quality=quality,
            method=6,  # Best compression
            lossless=False,  # Use lossy compression for smaller files
            optimize=True
        )
        
        # Reset buffer pointer
        webp_buffer.seek(0)
        
        # Log compression info (safe logging without app context)
        original_size = file.tell()
        file.seek(0)  # Reset original file
        webp_size = webp_buffer.tell()
        webp_buffer.seek(0)  # Reset WebP buffer
        
        compression_ratio = (1 - webp_size / original_size) * 100 if original_size > 0 else 0
        print(f"✅ WebP conversion: {original_size/1024:.1f}KB → {webp_size/1024:.1f}KB ({compression_ratio:.1f}% reduction)")
        
        return webp_buffer
        
    except Exception as e:
        print(f"WebP conversion failed: {str(e)}")
        return None

def is_valid_image_file(filename):
    """Check if the file is a valid image file"""
    allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif', 'webp'})
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def get_file_size_mb(file):
    """Get file size in MB"""
    file.seek(0, 2)  # Seek to end
    size_bytes = file.tell()
    file.seek(0)  # Reset to beginning
    return size_bytes / (1024 * 1024)

def upload_layer_images_to_azure(layer_images_data: List[Tuple], max_workers: int = 12) -> List[Tuple[str, Optional[str], Optional[str]]]:
    """
    Ultra-fast parallel upload for layer images to Azure Blob Storage.
    
    Args:
        layer_images_data: List of tuples (image_id, file_object, filename)
        max_workers: Maximum number of parallel upload workers (default: 12)
    
    Returns:
        List of tuples (image_id, azure_url, error_message)
    """
    try:
        # Get configuration from Flask app
        container_name = current_app.config.get('AZURE_CONTAINER_NAME')
        
        if not container_name:
            current_app.logger.error("Azure container name missing")
            return [(img_id, None, "Azure container name missing") for img_id, _, _ in layer_images_data]
        
        if not layer_images_data:
            return []
        
        # Pre-warm the connection pool
        if not get_blob_service_client():
            return [(img_id, None, "Failed to initialize Azure connection") for img_id, _, _ in layer_images_data]
        
        # Optimize worker count based on image count and system capabilities
        optimal_workers = min(max_workers, len(layer_images_data), 16)  # Cap at 16 for stability
        
        current_app.logger.info(f"🚀 Starting ULTRA-FAST layer image upload: {len(layer_images_data)} images with {optimal_workers} workers")
        start_time = time.time()
        
        # Use ThreadPoolExecutor with optimized settings for maximum speed
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=optimal_workers,
            thread_name_prefix="LayerUpload"
        ) as executor:
            # Submit all upload tasks immediately for maximum parallelism
            future_to_image = {
                executor.submit(upload_single_layer_image_to_azure, image_data, container_name): image_data[0]
                for image_data in layer_images_data
            }
            
            # Collect results as they complete
            results = []
            completed_count = 0
            total_count = len(layer_images_data)
            
            for future in concurrent.futures.as_completed(future_to_image):
                try:
                    result = future.result()
                    results.append(result)
                    completed_count += 1
                    
                    # Log progress with performance metrics
                    elapsed_time = time.time() - start_time
                    avg_time_per_image = elapsed_time / completed_count
                    estimated_remaining = avg_time_per_image * (total_count - completed_count)
                    
                    if result[1]:  # Success
                        current_app.logger.info(f"✅ {completed_count}/{total_count} layer images completed in {elapsed_time:.2f}s (avg: {avg_time_per_image:.2f}s/image, ETA: {estimated_remaining:.2f}s)")
                    else:  # Failed
                        current_app.logger.error(f"❌ {completed_count}/{total_count} failed for image {result[0]}: {result[2]}")
                        
                except Exception as e:
                    image_id = future_to_image[future]
                    error_msg = f"Unexpected error during layer image upload for {image_id}: {str(e)}"
                    results.append((image_id, None, error_msg))
                    current_app.logger.error(f"💥 Layer upload error for image {image_id}: {error_msg}")
        
        # Sort results by image ID to maintain order
        results.sort(key=lambda x: x[0])
        
        # Log final performance summary
        total_time = time.time() - start_time
        success_count = sum(1 for r in results if r[1])
        throughput = len(layer_images_data) / total_time if total_time > 0 else 0
        
        current_app.logger.info(f"🎯 Layer image upload complete: {success_count}/{total_count} successful in {total_time:.2f}s")
        current_app.logger.info(f"⚡ Performance: {throughput:.1f} images/second")
        
        # Performance validation
        if total_time > 2.0:  # Should be under 2 seconds for 8 images
            current_app.logger.warning(f"⚠️  Layer upload took {total_time:.2f}s - performance below target")
        else:
            current_app.logger.info(f"🎯 Excellent layer upload performance! {total_time:.2f}s for {len(layer_images_data)} images")
        
        return results
        
    except Exception as e:
        current_app.logger.error(f"💥 Layer multiprocessing upload failed: {str(e)}")
        return [(img_id, None, f"Layer multiprocessing upload failed: {str(e)}") for img_id, _, _ in layer_images_data]

def upload_single_layer_image_to_azure(image_data: Tuple, container_name: str) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Ultra-optimized single layer image upload with WebP optimization and maximum performance settings.
    Returns (image_id, azure_url, error_message)
    """
    try:
        image_id, file, filename = image_data
        
        # Get shared blob service client
        blob_service_client = get_blob_service_client()
        if not blob_service_client:
            return (image_id, None, "Failed to get blob service client")
        
        # Try WebP conversion first
        webp_file = convert_to_webp_with_alpha(file)
        
        if webp_file:
            # Use WebP version
            file_to_upload = webp_file
            file_extension = '.webp'
            print(f"Layer image {image_id}: Using WebP optimized version")
        else:
            # Fallback to original file
            file_to_upload = file
            if filename:
                file_extension = os.path.splitext(filename)[1]
            else:
                file_extension = '.png'  # Default extension
            print(f"Layer image {image_id}: Using original file (WebP conversion failed)")
        
        blob_name = f"{uuid.uuid4()}{file_extension}"
        
        # Get blob client with optimized settings
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
        
        # Reset file pointer to beginning
        file_to_upload.seek(0)
        
        # Ultra-fast upload with maximum concurrency and optimized settings
        blob_client.upload_blob(
            file_to_upload, 
            overwrite=True, 
            max_concurrency=8,           # Maximum parallel chunks
            length=None,                  # Auto-detect file size
            timeout=30,                   # 30 second timeout
            validate_content=False        # Skip content validation for speed
        )
        
        # Return the public URL
        account_name = blob_service_client.account_name
        url = f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}"
        
        return (image_id, url, None)
        
    except Exception as e:
        error_msg = f"Azure upload failed for layer image {image_id}: {str(e)}"
        return (image_id, None, error_msg)
