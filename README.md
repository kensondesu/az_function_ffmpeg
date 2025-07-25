# Azure FFmpeg Processing Function

This project contains an Azure Function that performs video processing using FFmpeg. The function downloads a video from Azure Blob Storage, processes it using FFmpeg commands, and uploads the processed video back to Azure Blob Storage using managed identity authentication.

## Architecture

The solution uses:
- **Azure Functions** (Python 3.11 runtime)
- **Azure Blob Storage** for input/output video files
- **Managed Identity** for secure authentication
- **FFmpeg** for video processing operations
- **Virtual Network Integration** for enhanced security

## Features

- HTTP-triggered function for video processing
- Secure blob storage access using managed identity
- Flexible FFmpeg command execution
- Comprehensive error handling and logging
- Temporary file management with automatic cleanup
- Cross-storage account support

## Prerequisites

### Local Development
- Python 3.11
- Azure Functions Core Tools v4
- Azure CLI
- FFmpeg binary
- Azure Storage Account with blob containers

### Azure Deployment
- Azure subscription
- Resource group with appropriate permissions
- Storage account for function app
- Target storage account for video processing

## Local Development Setup

### 1. Clone and Setup Environment

```bash
git clone <your-repo-url>
cd ffmpegfunction

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Install FFmpeg Binary

Download the appropriate FFmpeg binary for your platform and place it in the `bin` directory:

```bash
mkdir -p bin
# Download FFmpeg binary from https://ffmpeg.org/download.html
# For Linux:
wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
tar -xf ffmpeg-release-amd64-static.tar.xz
cp ffmpeg-*-amd64-static/ffmpeg bin/
chmod +x bin/ffmpeg

# For Windows, download the executable and place it in bin/ffmpeg.exe
```

### 3. Configure Local Settings

Create `local.settings.json` for local development:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "DefaultEndpointsProtocol=https;AccountName=<your-storage-account>;AccountKey=<your-key>;EndpointSuffix=core.windows.net",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AzureWebJobsFeatureFlags": "EnableWorkerIndexing"
  }
}
```

### 4. Run Locally

```bash
# Start the Azure Functions runtime
func start

# The function will be available at:
# http://localhost:7071/api/azffmpeg
```

### 5. Test Locally

```bash
curl -X POST "http://localhost:7071/api/azffmpeg" \
  -H "Content-Type: application/json" \
  -d '{
    "inputBlobUrl": "https://yourstorageaccount.blob.core.windows.net/input/video.mp4",
    "outputContainerName": "https://yourstorageaccount.blob.core.windows.net/output",
    "ffmpegCommand": "-vf scale=640:360"
  }'
```

## Azure Deployment

### 1. Create Azure Resources

```bash
# Set variables
RESOURCE_GROUP="ffmpeg"
LOCATION="swedencentral"
FUNCTION_APP_NAME="azffmpeg"
STORAGE_ACCOUNT="ffmpeg9736"  # Must be globally unique
PLAN_NAME="ASP-ffmpeg-a506"

# Create resource group
az group create --name $RESOURCE_GROUP --location $LOCATION

# Create storage account for function app
az storage account create \
  --name $STORAGE_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku Standard_LRS

# Create function app service plan
az functionapp plan create \
  --name $PLAN_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --is-linux \
  --sku P1v2

# Create function app
az functionapp create \
  --name $FUNCTION_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --plan $PLAN_NAME \
  --runtime python \
  --runtime-version 3.11 \
  --storage-account $STORAGE_ACCOUNT \
  --assign-identity
```

### 2. Configure Managed Identity Permissions

```bash
# Get the function app's managed identity principal ID
PRINCIPAL_ID=$(az functionapp identity show \
  --name $FUNCTION_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --query principalId \
  --output tsv)

# Grant Storage Blob Data Contributor role to the target storage account
TARGET_STORAGE_ACCOUNT="ffmpegteststorage"  # Replace with your target storage account
az role assignment create \
  --assignee $PRINCIPAL_ID \
  --role "Storage Blob Data Contributor" \
  --scope "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Storage/storageAccounts/$TARGET_STORAGE_ACCOUNT"
```

### 3. Deploy Function Code

```bash
# Deploy the function app
func azure functionapp publish $FUNCTION_APP_NAME --python

# Alternatively, using zip deployment
func azure functionapp publish $FUNCTION_APP_NAME --python --build-native-deps
```

### 4. Configure Application Settings (Optional)

```bash
# Add any additional configuration
az functionapp config appsettings set \
  --name $FUNCTION_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --settings "AZURE_STORAGE_ACCOUNT=$TARGET_STORAGE_ACCOUNT"
```

## Usage

### API Endpoint

**POST** `https://your-function-app.azurewebsites.net/api/azffmpeg?code=<function_key>`

### Request Body

```json
{
  "inputBlobUrl": "https://storageaccount.blob.core.windows.net/input/video.mp4",
  "outputContainerName": "https://storageaccount.blob.core.windows.net/output",
  "ffmpegCommand": "-vf scale=640:360"
}
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `inputBlobUrl` | string | Full URL to the input video blob |
| `outputContainerName` | string | Full URL to the output container |
| `ffmpegCommand` | string | FFmpeg processing command (without input/output files) |

### Example Commands

```bash
# Scale video to 640x360
curl -X POST "https://azffmpeg.azurewebsites.net/api/azffmpeg?code=YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "inputBlobUrl": "https://storage.blob.core.windows.net/input/video.mp4",
    "outputContainerName": "https://storage.blob.core.windows.net/output",
    "ffmpegCommand": "-vf scale=640:360"
  }'

# Convert to different format with compression
curl -X POST "https://azffmpeg.azurewebsites.net/api/azffmpeg?code=YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "inputBlobUrl": "https://storage.blob.core.windows.net/input/video.mov",
    "outputContainerName": "https://storage.blob.core.windows.net/output",
    "ffmpegCommand": "-c:v libx264 -crf 23 -c:a aac"
  }'
```

## Repository Structure

```
ffmpegfunction/
├── .github/
│   └── copilot-instructions.md    # GitHub Copilot configuration
├── azffmpeg/
│   ├── __init__.py               # Main function code
│   └── function.json             # Function binding configuration
├── bin/
│   └── ffmpeg                    # FFmpeg binary (not in repo)
├── .funcignore                   # Function deployment ignore rules
├── .gitignore                    # Git ignore rules
├── host.json                     # Function app configuration
├── requirements.txt              # Python dependencies
└── README.md                     # This file
```

## Troubleshooting

### Common Issues

1. **FFmpeg Binary Not Found**
   ```
   Error: FFmpeg binary not found
   ```
   - Ensure FFmpeg binary is in the `bin` directory
   - Verify the binary has executable permissions
   - Check the binary is compatible with Linux x64

2. **Authentication Errors**
   ```
   Error: ManagedIdentityCredential authentication unavailable
   ```
   - Verify managed identity is enabled on the function app
   - Check RBAC permissions on the target storage account
   - Ensure the function app has "Storage Blob Data Contributor" role

3. **Blob Not Found**
   ```
   Error: Input blob not found
   ```
   - Verify the input blob URL is correct
   - Check the blob exists in the specified container
   - Ensure URL encoding is correct for special characters

### Monitoring and Logs

```bash
# View function logs
az functionapp log tail --name $FUNCTION_APP_NAME --resource-group $RESOURCE_GROUP

# Check function app metrics
az monitor metrics list \
  --resource "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Web/sites/$FUNCTION_APP_NAME" \
  --metric "FunctionExecutionCount"
```

### Performance Considerations

- Function timeout is set to 10 minutes by default
- Large video files may require timeout adjustments
- Consider using Durable Functions for very long processing tasks
- Monitor memory usage for large video files

## Security Best Practices

- Uses managed identity for secure authentication
- No storage keys stored in code or configuration
- HTTPS-only communication
- Proper error handling without exposing sensitive information
- Input validation for blob URLs and commands

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues and questions:
- Check the troubleshooting section above
- Review Azure Functions documentation
- Check FFmpeg documentation for command syntax
