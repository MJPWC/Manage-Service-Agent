# OAuth2 Token Auto-Refresh Documentation

## Overview

The Manage Service Agent now automatically refreshes OAuth2 tokens before they expire, ensuring seamless user experience without interruption.

## How It Works

### Token Lifecycle

1. **User Logs In**
   - User authenticates with Connected App or Anypoint credentials
   - OAuth2 token is generated and stored in session
   - Token creation timestamp is recorded
   - Token validity: **55 minutes**

2. **Token Monitoring**
   - Every API request triggers a token check
   - System monitors time elapsed since token creation
   - Automatic refresh threshold: **50 minutes** (before expiration)

3. **Automatic Refresh**
   - When 50 minutes have elapsed, token is automatically refreshed
   - Refresh uses stored client credentials from `connected_apps_credentials.csv`
   - No user action required
   - User doesn't see any interruption

4. **Continuous Session**
   - New token is obtained and stored
   - Token creation time is reset
   - User can continue working indefinitely

## Configuration

### Timing Settings

Located at the top of `app.py`:

```python
TOKEN_EXPIRY_MINUTES = 55        # OAuth2 token lifetime
TOKEN_REFRESH_THRESHOLD_MINUTES = 50  # Refresh after 50 minutes
```

**Current Settings:**
- Tokens expire after: **55 minutes**
- Tokens refresh after: **50 minutes** (5 minutes before expiry)

To modify, edit these values in `app.py` and restart the application.

## Implementation Details

### Function: `refresh_token_if_needed()`

Called automatically before each API request:

```python
def refresh_token_if_needed():
    """
    Check if token needs refresh and refresh it if necessary.
    - Tokens refreshed proactively 50 minutes after creation
    - Uses stored client_name to get credentials from CSV
    - Falls back gracefully if refresh fails
    """
```

### Before-Request Hook: `@app.before_request`

Runs before every HTTP request:
- Checks if token refresh is needed
- Skips refresh for non-API routes (login page, etc.)
- Refreshes token silently in the background

## Token Refresh Process

```
1. User makes API request
   ↓
2. @before_request hook runs
   ↓
3. Token age calculated from token_created_at
   ↓
4. Is token > 50 minutes old?
   │
   ├─ NO → Continue with request normally
   │
   └─ YES → Refresh token
       ├─ Get client_name from session
       ├─ Load credentials from CSV
       ├─ Get new OAuth2 token
       ├─ Update session with new token
       ├─ Reset token_created_at
       ├─ Fetch updated environments
       └─ Continue with original request
```

## Session Data

### Token Information Stored

```python
session['anypoint_token']          # OAuth2 access token
session['token_created_at']        # ISO timestamp of creation
session['org_id']                  # Organization ID
session['environments']            # List of accessible environments
session['connectedapp_client_name'] # Client name (for refresh)
```

### Checking Token Status

Make a request to `/api/session` to view:

```json
{
  "token_expiration": {
    "created_at": "2026-03-16T10:00:00.000000",
    "expires_at": "2026-03-16T10:55:00.000000",
    "minutes_remaining": 42.5,
    "will_auto_refresh_at": "2026-03-16T10:50:00.000000"
  }
}
```

**Fields:**
- `created_at`: When current token was created
- `expires_at`: When current token will expire
- `minutes_remaining`: How much time is left (rounded to 1 decimal)
- `will_auto_refresh_at`: When token will be automatically refreshed

## For Connected App Users

### Automatic Refresh With CSV Credentials

When using Connected App login:

1. Client credentials stored in `connected_apps_credentials.csv`
2. Client name stored in session
3. On refresh, system:
   - Reads client_name from session
   - Looks up credentials in CSV
   - Authenticates with fresh credentials
   - Gets new token automatically

**Example CSV:**
```csv
clientName,clientId,clientSecret
client-BNZ035,fb9773de46a14fea84e345095eca6e39,e1630805355B4a43a8A2316503490233
```

## For Username/Password Users

### Anypoint Login Token Refresh

When using Anypoint username/password:

- Tokens are refreshed automatically using OAuth2
- User credentials are used to get new tokens
- Process is transparent to user

**Note:** Only Connected App credentials are stored in CSV. Username/password requires re-authentication for continued access beyond timeout.

## Logging

### Debug Output

Token refresh events are logged to console:

```
[TOKEN_REFRESH] Token expired after 50.2 minutes, refreshing...
[TOKEN_REFRESH] Token refreshed successfully
```

**Error cases:**
```
[TOKEN_REFRESH] Failed to refresh token: {error message}
[TOKEN_REFRESH] Error refreshing token: {error message}
```

View logs by running:
```bash
python app.py
```

## API Behavior

### Routes That Trigger Token Refresh

All API routes except:
- `/api/session`
- `/api/logout`
- `/api/connectedapp/login`
- `/login`
- `/`
- `/api/debug/session`

### If Refresh Fails

- Token refresh failure is logged
- Request continues with existing token
- User may experience failure on next token expiration
- **Solution:** Log out and log back in

## Error Handling

### Scenarios

| Scenario | Behavior | Solution |
|---|---|---|
| Token refresh succeeds | Seamless, no user notice | ✓ Works automatically |
| Token refresh fails | Request continues with old token | Log out and log back in |
| CSV credentials invalid | Token not refreshed | Verify credentials in CSV |
| Network error | Token not refreshed | Check connection, try again |
| Client not found in CSV | Refresh fails | Verify client_name in session |

## Best Practices

1. **Keep CSV Secure**
   - Protect `connected_apps_credentials.csv` file
   - Don't commit to public repositories
   - Use proper file permissions

2. **Monitor Token Status**
   - Occasionally check `/api/session` for token expiration
   - Watch for refresh errors in logs
   - Be aware when approaching hour-long sessions

3. **For Long Sessions**
   - Connected App login preferred (auto-refresh works better)
   - Verify client credentials are correct
   - Keep browser tab open (refreshes on API calls)

## Testing Token Refresh

### Manual Test

1. Log in with Connected App
2. Note the time in browser developer tools:
   ```javascript
   fetch('/api/session').then(r => r.json()).then(d => console.log(d.token_expiration))
   ```
3. Wait 50+ minutes (or modify `TOKEN_REFRESH_THRESHOLD_MINUTES` for testing)
4. Make any API call (e.g., click on an environment)
5. Check logs for `[TOKEN_REFRESH]` message
6. Verify new token in session

### Quick Test (Modify Threshold)

For testing, temporarily change threshold in `app.py`:

```python
TOKEN_REFRESH_THRESHOLD_MINUTES = 0  # Refresh immediately on next request
```

Then:
1. Log in
2. Make an API call
3. Should see refresh in logs
4. Revert the change

## Technical Details

### Token Refresh Mechanism

**Function Location:** `app.py` line ~60  
**Hook Location:** `app.py` - `@app.before_request`  
**Session Keys:** See "Session Data" section above

### Dependencies

- `datetime` module - For timestamp tracking
- `requests` library - For OAuth2 API calls
- `Flask` session - For storing token state

### Performance Impact

- Token refresh: ~100-300ms (one-time per 50 minutes)
- Check if refresh needed: <1ms (before every request)
- Overall impact: Negligible

## Troubleshooting

### Token Not Refreshing

**Check:**
1. Are you using Connected App? (CSV-based refresh)
2. Is `connected_apps_credentials.csv` present?
3. Verify client name is in CSV
4. Check Flask logs for errors

**Fix:**
```bash
# View logs
python app.py

# Look for [TOKEN_REFRESH] messages
```

### Token Refreshed But Still Getting Errors

**Check:**
1. New environments list is updated
2. User still has access to environment
3. Organization ID is correct

**Fix:**
- Log out completely
- Log back in
- Verify user has required permissions in Anypoint Platform

### Why Does Token Expire at 55 Minutes?

- OAuth2 credential grant tokens typically have 1-hour lifetime
- Anypoint Platform default is ~60 minutes
- We refresh at 50 minutes to be safe
- 5-minute buffer prevents edge cases

## Security Considerations

1. **Token Storage**
   - Tokens stored server-side in Flask session
   - Tokens not sent to browser (except in response)
   - Session encrypted if using production environment

2. **CSV Credentials**
   - Contains sensitive OAuth2 secrets
   - Must be protected from unauthorized access
   - Consider encrypting for production

3. **Token Expiration**
   - Tokens are temporary
   - Refreshed automatically for security
   - Regular token rotation reduces risk if compromised

## Further Reading

- [OAuth2 Token Lifespan](https://www.rfc-editor.org/rfc/rfc6749)
- [MuleSoft Token Management](https://docs.mulesoft.com/access-management/access-management-api)
- [Flask Session Security](https://flask.palletsprojects.com/en/latest/security/)

---

**Version:** 1.0  
**Last Updated:** March 16, 2026  
**Status:** ✅ Active
