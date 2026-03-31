# Connected App OAuth2 Authentication Guide

## Overview

The Connected App authentication feature allows users to login to the Manage Service Agent using MuleSoft's OAuth2 client credentials flow instead of username/password. This is more secure and is recommended for production environments.

## Quick Start

### 1. Login with Connected App

1. Open the login page
2. Click on the **"Connected App"** tab
3. Enter your **Client Name** (e.g., `client-001`)
4. Click **"Login with Connected App"**

### 2. Available Client Names

The following client credentials are pre-configured:

| Client Name | Status |
|---|---|
| `client-001` | ✅ Active |

To use a different client, add credentials to the CSV file (see section below).

## File Structure

### 1. Credentials Storage

**File:** `connected_apps_credentials.csv`

```csv
clientName,clientId,clientSecret
client-001,fb9773de46a14fea84e345095eca6e39,e1630805355B4a43a8A2316503490233
```

This CSV file stores all connected app credentials. You can add more clients by adding new rows.

### 2. Manager Module

**File:** `connectedapp_manager.py`

This Python module handles all OAuth2 operations:

- **`ConnectedAppManager`** class - Main class for managing connected app operations
  - `get_credentials(client_name)` - Retrieve credentials from CSV
  - `add_credentials(client_name, client_id, client_secret)` - Add/update credentials
  - `authenticate(client_name)` - Get OAuth2 access token
  - `get_user_info(token)` - Get user information
  - `get_environments(token, org_id)` - Get organization environments

### 3. Flask API Endpoint

**Endpoint:** `POST /api/connectedapp/login`

**Request Body:**
```json
{
  "clientName": "client-001"
}
```

**Response (Success):**
```json
{
  "success": true,
  "message": "Connected App authentication successful",
  "environments": [
    {
      "id": "env_id",
      "name": "Production",
      "type": "PRODUCTION"
    }
  ]
}
```

**Response (Error):**
```json
{
  "success": false,
  "error": "Client 'invalid-client' not found in credentials"
}
```

### 4. Frontend Integration

**File:** `public/login.html`

Frontend changes:
- Added "Connected App" login tab
- Added client name input field
- Added `loginConnectedApp()` JavaScript function
- Enter key support for quick login

## Adding New Connected Apps

### Method 1: Manual CSV Edit

1. Open `connected_apps_credentials.csv`
2. Add a new line with your credentials:
   ```csv
   client-002,your_client_id,your_client_secret
   ```
3. Save the file

### Method 2: Programmatic (Python)

```python
from connectedapp_manager import get_connected_app_manager

manager = get_connected_app_manager()
success = manager.add_credentials(
    client_name='client-002',
    client_id='your_client_id',
    client_secret='your_client_secret'
)
```

## Generating OAuth2 Credentials

To get client ID and secret from MuleSoft Anypoint Platform:

1. Navigate to **Access Management** > **Connected Apps**
2. Create a new Connected App
3. Grant required scopes (e.g., View environment, View APIs, etc.)
4. Get the **Client ID** and **Client Secret**
5. Add them to the credentials CSV file with a unique client name

## API Endpoints Accessed

The Connected App uses the following Anypoint API endpoints:

### OAuth2 Token Endpoint
```
POST https://anypoint.mulesoft.com/accounts/api/v2/oauth2/token
```

Parameters:
- `client_id` - Your connected app client ID
- `client_secret` - Your connected app client secret
- `grant_type` - Always `client_credentials`

### Get User Info
```
GET https://anypoint.mulesoft.com/accounts/api/me
Authorization: Bearer {access_token}
```

### Get Environments
```
GET https://anypoint.mulesoft.com/accounts/api/organizations/{org_id}/environments
Authorization: Bearer {access_token}
```

## Session Management

After successful authentication:

- **Session Key:** `anypoint_token` - OAuth2 access token
- **Session Key:** `org_id` - Organization ID
- **Session Key:** `environments` - List of accessible environments
- **Session Key:** `connectedapp_authenticated` - Boolean flag
- **Session Key:** `connectedapp_client_name` - The client name used for login

These are the same session keys used by the standard Anypoint username/password login for compatibility.

## Security Considerations

1. **Store Credentials Securely:** The CSV file contains sensitive credentials. 
   - Consider encrypting the CSV file
   - Restrict file access permissions
   - Use environment variables for production

2. **Token Expiration:** OAuth2 tokens have a limited lifespan (typically 1 hour)
   - Tokens are stored in Flask session
   - Session persists for 1 hour by default
   - Users need to re-authenticate after session expiration

3. **HTTPS:** Always use HTTPS in production
   - The app currently disables SSL verification (`verify=False`) for testing
   - Remove `verify=False` for production deployments

## Troubleshooting

### "Client not found in credentials"
- Verify the client name matches exactly (case-sensitive)
- Check the CSV file has the correct format

### "OAuth2 authentication failed"
- Verify client ID and secret are correct
- Check the connected app is active in Anypoint Platform
- Ensure the app has correct access scopes

### "Could not retrieve organization ID"
- The user account doesn't have organization access
- Contact your Anypoint Platform administrator

### "Failed to get environments"
- The organization might not have any environments configured
- User might not have permission to view environments
- The app handles this gracefully by using an empty list

## Architecture Diagram

```
┌─────────────────────────────────────────────────────┐
│            Frontend (login.html)                     │
│  - Connected App Login Tab                           │
│  - Client Name Input Field                           │
│  - loginConnectedApp() Function                      │
└──────────────────┬──────────────────────────────────┘
                   │
                   │ fetch /api/connectedapp/login
                   ▼
┌─────────────────────────────────────────────────────┐
│      Flask Backend (app.py)                          │
│  - connectedapp_login() Route                        │
│  - Session Management                               │
└──────────────────┬──────────────────────────────────┘
                   │
                   │ uses
                   ▼
┌─────────────────────────────────────────────────────┐
│    ConnectedAppManager (connectedapp_manager.py)    │
│  - Read Credentials from CSV                        │
│  - Authenticate with Anypoint                       │
│  - Get User Info & Environments                     │
└──────────────────┬──────────────────────────────────┘
                   │
                   │ API Calls
                   ▼
┌─────────────────────────────────────────────────────┐
│   MuleSoft Anypoint Platform APIs                   │
│  - OAuth2 Token Endpoint                            │
│  - User Info Endpoint                               │
│  - Environments Endpoint                            │
└─────────────────────────────────────────────────────┘
```

## Examples

### Example 1: Login with Connected App
```bash
# Frontend sends request
curl -X POST http://localhost:3000/api/connectedapp/login \
  -H "Content-Type: application/json" \
  -d '{
    "clientName": "client-001"
  }'
```

### Example 2: Add New Connected App
```python
from connectedapp_manager import get_connected_app_manager

manager = get_connected_app_manager()

# Add new client
manager.add_credentials(
    client_name='production-app',
    client_id='your-production-client-id',
    client_secret='your-production-client-secret'
)

# Get credentials back
creds = manager.get_credentials('production-app')
print(f"Client ID: {creds['clientId']}")
print(f"Client Secret: {creds['clientSecret']}")
```

## Reference

- [MuleSoft Connected Apps Documentation](https://docs.mulesoft.com/cloudhub-2/latest/create-apps)
- [OAuth2 Client Credentials Flow](https://oauth.net/2/grant-types/client-credentials/)
- [Anypoint Platform APIs](https://docs.mulesoft.com/api-manager/2.x/oauth2-provider-configuration)
