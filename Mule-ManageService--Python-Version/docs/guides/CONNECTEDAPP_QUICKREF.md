# Connected App Quick Reference Guide

## 🚀 Quick Start - Login with Connected App

### Step 1: Open Login Page
Navigate to your Manage Service Agent login page

### Step 2: Select Connected App Tab
Click the **"Connected App"** tab on the login form

### Step 3: Enter Client Name
Enter the client name: **`client-001`**

### Step 4: Click Login
Click **"Login with Connected App"**

✅ **Success!** You'll be redirected to the dashboard

---

## 📋 Available Client Names

| Client Name | Status | Purpose |
|---|---|---|
| `client-001` | ✅ Active | Default OAuth2 connected app |

---

## 🔧 Adding a New Connected App (Admin Only)

### Option 1: Edit CSV File Directly

**File**: `connected_apps_credentials.csv`

1. Open the CSV file
2. Add a new line:
   ```
   your-client-name,your_client_id,your_client_secret
   ```
3. Example:
   ```
   production-app,abc123xyz789,def456uvw012
   ```
4. Save the file

### Option 2: Use Python

```python
from connectedapp_manager import get_connected_app_manager

manager = get_connected_app_manager()
manager.add_credentials(
    client_name='my-app',
    client_id='your_client_id_here',
    client_secret='your_client_secret_here'
)
```

---

## 🔐 Getting OAuth2 Credentials from Anypoint

1. Log in to **MuleSoft Anypoint Platform**
2. Go to **Access Management → Connected Apps**
3. Click **Create Connected App**
4. Fill in the details:
   - Name: `Your App Name`
   - Grant types: Select `Client Credentials`
5. Configure access:
   - Grant access to APIs
   - Grant access for environments
6. Click **Save**
7. Copy these values:
   - **Client ID**: `[COPY THIS]`
   - **Client Secret**: `[COPY THIS]`
8. Add to CSV file:
   ```
   your-app-name,<CLIENT_ID>,<CLIENT_SECRET>
   ```

---

## 🛠️ Troubleshooting

### ❌ "Client not found in credentials"

**Problem**: Client name doesn't exist in CSV

**Solution**:
1. Check spelling (case-sensitive!)
2. Verify CSV file has the entry
3. Restart the application

### ❌ "OAuth2 authentication failed"

**Problem**: Invalid client ID or secret

**Solution**:
1. Check credentials in Anypoint Platform
2. Verify the connected app is active
3. Generate new credentials if needed
4. Update CSV file with correct values

### ❌ "Could not retrieve organization ID"

**Problem**: User account lacks organization access

**Solution**:
1. Contact your Anypoint admin
2. Ensure your account has proper roles
3. Try with a different user account

### ❌ "Request timeout"

**Problem**: Network or Anypoint server issue

**Solution**:
1. Check internet connection
2. Verify Anypoint Platform is accessible
3. Try again in a few moments
4. Check firewall/proxy settings

---

## 📊 CSV File Format

### Valid Format
```csv
clientName,clientId,clientSecret
client-001,fb9773de46a14fea84e345095eca6e39,e1630805355B4a43a8A2316503490233
production,abc123,xyz789
dev-app,id-value,secret-value
```

### Important Notes
- **NO spaces** around commas
- **Header row required**: `clientName,clientId,clientSecret`
- **Client names** must be unique
- **Credentials** must match exactly with Anypoint

---

## 🔄 Session Information

After successful login, you get:
- ✅ Access token (valid for ~1 hour)
- ✅ Organization ID
- ✅ List of environments
- ✅ Same access as username/password login

---

## 🔐 Security Best Practices

1. **Protect CSV File**
   - Restrict file access permissions
   - Don't commit to public repositories
   - Use `.gitignore` to exclude it

2. **Credentials**
   - Don't share client secrets
   - Rotate secrets periodically
   - Use strong, unique secrets

3. **Production**
   - Use HTTPS (enable SSL in production)
   - Store secrets in environment variables
   - Consider encrypting CSV file

---

## 📞 Support

**For Issues**:
1. Check [CONNECTEDAPP_GUIDE.md](CONNECTEDAPP_GUIDE.md) for detailed docs
2. Review error messages in browser console
3. Check application logs
4. Contact Anypoint Platform support if credentials issue

**For Development**:
- See [connectedapp_manager.py](connectedapp_manager.py) source
- Review login implementation in [public/login.html](public/login.html)
- Check Flask route in [app.py](app.py)

---

## 💡 Common Use Cases

### Use Case 1: Production Deployment
```csv
production,prod-client-id-abc123,prod-client-secret-xyz789
staging,stage-client-id-def456,stage-client-secret-uvw012
```

### Use Case 2: Multi-Team Setup
```csv
team-a,team-a-id,team-a-secret
team-b,team-b-id,team-b-secret
team-c,team-c-id,team-c-secret
```

### Use Case 3: Service Accounts
```csv
api-monitor,monitor-id,monitor-secret
log-collector,collector-id,collector-secret
```

---

## 📈 Performance Tips

- **First Login**: Takes ~3-5 seconds (OAuth2 handshake)
- **Subsequent Logins**: Uses cached credentials, faster
- **Session Timeout**: Default 1 hour
- **Re-authentication**: Required after session expires

---

## 🔗 Resources

- [MuleSoft Connected Apps Docs](https://docs.mulesoft.com/cloudhub-2/latest/create-apps)
- [OAuth2 Official Documentation](https://oauth.net/2/)
- [Anypoint Platform APIs](https://docs.mulesoft.com/api-manager/2.x/)

---

**Last Updated**: March 16, 2026  
**Version**: 1.0
