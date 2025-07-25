import logging
import os
import subprocess
import shutil
import tempfile
from azure.storage.blob import BlobServiceClient, BlobClient
from azure.identity import ManagedIdentityCredential
from azure.core.exceptions import ResourceNotFoundError, ClientAuthenticationError
import azure.functions as func
from urllib.parse import urlparse

# Expects inputBlobUrl, outputContainerName, and ffmpegCommand in the request body
# inputBlobUrl: URL of the input video blob
# outputContainerName: URL of the output container where the processed video will be uploaded
# ffmpegCommand: FFmpeg command to process the video (e.g., "-vf scale=1280:720")
# This function uses Azure Functions with a managed identity to access Azure Blob Storage
# and FFmpeg to process the video. It downloads the input video, processes it with FFmpeg,
# and uploads the processed video back to Azure Blob Storage.

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Processing HTTP request.')

    # Get request body
    try:
        req_body = req.get_json()
    except ValueError:
        req_body = None
    
    # Get params from body first, query params as fallback
    input_blob_url = req_body.get('inputBlobUrl') if req_body else req.params.get('inputBlobUrl')
    output_container_name = req_body.get('outputContainerName') if req_body else req.params.get('outputContainerName')
    ffmpeg_command = req_body.get('ffmpegCommand') if req_body else req.params.get('ffmpegCommand')

    if not input_blob_url or not output_container_name or not ffmpeg_command:
        return func.HttpResponse(
            "Please pass inputBlobUrl, outputContainerName, and ffmpegCommand in the request body",
            status_code=400
        )

    # Create temporary directory to process files
    temp_dir = tempfile.mkdtemp(dir='/tmp')
    temp_input_path = os.path.join(temp_dir, 'input.mp4')
    temp_output_path = os.path.join(temp_dir, 'output.mp4')

    logging.info(f"Input URL: {input_blob_url}")
    logging.info(f"Output container: {output_container_name}")
    logging.info(f"Command: {ffmpeg_command}")
    logging.info(f"Current directory: {os.getcwd()}")
    logging.info(f"Temp directory: {temp_dir}")

    try:
        # Parse the input URL
        parsed_url = urlparse(input_blob_url)
        
        # Extract account name from hostname
        input_account_name = parsed_url.netloc.split('.')[0]
        logging.info(f"Storage account name: {input_account_name}")
        
        # Extract container and blob path
        path_parts = parsed_url.path.strip('/').split('/')
        
        if not path_parts or len(path_parts) < 2:
            logging.error("Invalid blob URL format")
            return func.HttpResponse("Invalid blob URL format. URL must include container name and blob path.", status_code=400)
        
        input_container_name = path_parts[0]
        input_blob_name = '/'.join(path_parts[1:])
        
        # Use managed identity to access blob storage
        # Ensure right permissions on storage account - Blob Data Contributor role - for the function app identity
        credential = ManagedIdentityCredential()
        
        # Download input file
        input_blob_url_for_client = f"https://{input_account_name}.blob.core.windows.net/{input_container_name}/{input_blob_name}"
        logging.info(f"Accessing blob at: {input_blob_url_for_client}")
        
        input_blob_client = BlobClient.from_blob_url(input_blob_url_for_client, credential=credential)
        
        try:
            with open(temp_input_path, 'wb') as input_file:
                download_stream = input_blob_client.download_blob()
                input_file.write(download_stream.readall())
            logging.info(f"Successfully downloaded blob from {input_container_name}/{input_blob_name}")
        except ResourceNotFoundError as e:
            logging.error(f"Input blob not found: {input_container_name}/{input_blob_name}, Error: {str(e)}")
            return func.HttpResponse(f"Input blob not found at {input_container_name}/{input_blob_name}", status_code=404)
        except Exception as e:
            logging.error(f"Error downloading blob: {str(e)}")
            return func.HttpResponse(f"Error downloading input file: {str(e)}", status_code=500)
    except Exception as e:
        logging.error(f"Unexpected error accessing blob storage: {str(e)}")
        return func.HttpResponse(f"Unexpected error accessing blob storage: {str(e)}", status_code=500)

    # Execute FFmpeg command
    try:
        # Try to find ffmpeg in multiple locations
        ffmpeg_locations = [
            os.path.join(os.getcwd(), 'bin', 'ffmpeg'),
            '/home/site/wwwroot/bin/ffmpeg',
            shutil.which('ffmpeg'),
            '/usr/bin/ffmpeg',
            '/usr/local/bin/ffmpeg'
        ]
        
        ffmpeg_path = None
        for location in ffmpeg_locations:
            if location and os.path.exists(location):
                ffmpeg_path = location
                break
        
        if not ffmpeg_path:
            logging.error("FFmpeg binary not found in any of the expected locations")
            return func.HttpResponse("FFmpeg binary not found", status_code=500)
            # Make sure ffmpeg is on the bin path and is executable 
        
        logging.info(f"Using FFmpeg at: {ffmpeg_path}")
        
        # Build argument list
        cmd_parts = [ffmpeg_path, '-i', temp_input_path]
        
        # Parse ffmpeg_command
        if ffmpeg_command:
            # Split the command by space, but respect quotes
            import shlex
            cmd_parts.extend(shlex.split(ffmpeg_command))
        
        # Add output path
        cmd_parts.append(temp_output_path)
        
        logging.info(f"Executing command: {' '.join(cmd_parts)}")
        
        # Run FFmpeg with argument list
        process = subprocess.run(
            cmd_parts,
            capture_output=True,
            text=True
        )
        
        if process.returncode != 0:
            logging.error(f"FFmpeg error: {process.stderr}")
            return func.HttpResponse(f"FFmpeg error: {process.stderr}", status_code=500)
        
        logging.info("FFmpeg command executed successfully")
    except Exception as e:
        logging.error(f"Error executing FFmpeg: {str(e)}")
        return func.HttpResponse(f"Error executing FFmpeg: {str(e)}", status_code=500)

    # Upload output file
    try:
        # Parse the output container URL
        output_parsed_url = urlparse(output_container_name)
        output_account_name = output_parsed_url.netloc.split('.')[0]
        output_container_path = output_parsed_url.path.strip('/').split('/')[0]
        
        logging.info(f"Output account: {output_account_name}, container: {output_container_path}")
        
        # Create output blob client
        output_blob_url = f"https://{output_account_name}.blob.core.windows.net/{output_container_path}/output.mp4"
        output_blob_client = BlobClient.from_blob_url(output_blob_url, credential=credential)
        
        with open(temp_output_path, 'rb') as output_file:
            output_blob_client.upload_blob(output_file, overwrite=True)
            
        logging.info(f"Successfully uploaded result to {output_container_path}/output.mp4")
    except Exception as e:
        logging.error(f"Error uploading processed file: {str(e)}")
        return func.HttpResponse(f"Video processing completed but upload failed: {str(e)}", status_code=500)
    finally:
        # Clean up temporary files
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
            logging.info(f"Cleaned up temporary directory: {temp_dir}")
        except Exception as cleanup_error:
            logging.warning(f"Failed to clean up temporary files: {str(cleanup_error)}")

    return func.HttpResponse("Video processed successfully", status_code=200)