import uuid
import os
from azure.storage.blob import BlobServiceClient
from flask import current_app

def upload_to_azure(file):
    """Upload file to Azure Blob Storage and return URL"""
    try:
        # Get configuration from Flask app
        connection_string = current_app.config.get('AZURE_STORAGE_CONNECTION_STRING')
        container_name = current_app.config.get('AZURE_CONTAINER_NAME')
        
        if not connection_string or not container_name:
            current_app.logger.error("Azure storage configuration missing")
            return None
        
        # Create blob service client
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        
        # Generate unique blob name
        file_extension = os.path.splitext(file.filename)[1] if file.filename else ''
        blob_name = f"{uuid.uuid4()}{file_extension}"
        
        # Get blob client
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
        
        # Reset file pointer to beginning
        file.seek(0)
        
        # Upload file
        blob_client.upload_blob(file.read(), overwrite=True)
        
        # Return the public URL
        account_name = connection_string.split(';')[1].split('=')[1]
        url = f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}"
        
        current_app.logger.info(f"File uploaded successfully to Azure: {blob_name}")
        return url
        
    except Exception as e:
        current_app.logger.error(f"Azure upload failed: {str(e)}")
        return None

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
