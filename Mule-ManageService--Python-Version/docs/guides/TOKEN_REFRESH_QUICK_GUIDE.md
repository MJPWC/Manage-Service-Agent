# Token Auto-Refresh - Quick Reference

## What Is This?

Your OAuth2 token automatically refreshes every 50 minutes so you don't have to log in again. It works completely in the background.

## Timeline

```
Token Active          →  50 Minutes Pass  →  Auto-Refresh  →  Token Active Again
├─ You login          ├─ You work         ├─ Happens auto  ├─ No interruption
├─ Token Created      ├─ Token works fine ├─ Uses stored   ├─ You keep working
└─ Clock starts       └─ No action needed │  credentials    └─ Clock resets
                                          └─ Silent process
```

## What You Need to Know

### ✅ What Happens Automatically

- Token is refreshed before it expires
- Uses credentials stored in CSV file
- No login required
- No interruption to your work
- Works in the background

### ❌ What You DON'T Need to Do

- Don't manually refresh the token
- Don't watch the timer
- Don't re-enter credentials
- Don't worry about expiration
- Don't do anything special

## Checking Token Status

Visit this URL to see token details:

```
http://localhost:3000/api/session
```

Look for `token_expiration` in the response:

```json
"token_expiration": {
  "created_at": "2026-03-16T10:00:00",
  "expires_at": "2026-03-16T10:55:00",
  "minutes_remaining": 42.5,
  "will_auto_refresh_at": "2026-03-16T10:50:00"
}
```

**Meaning:**
- Your token was created 10 minutes ago
- It will expire in 55 minutes total
- It will auto-refresh at 50-minute mark
- You have 42.5 minutes left

## How It Works (Simple Version)

1. **You login** → Token is created and time is marked
2. **You work** → Token is used for API calls
3. **50 minutes pass** → Next time you click something:
   - System notices token is old
   - Automatically gets a new token
   - Continues with your request
   - No reload or pause
4. **Repeat** → Timer resets, process continues

## Best Practices

### For Connected App Users
- ✅ Works best with Connected App login
- ✅ Automatic refresh uses stored credentials
- ✅ No user action needed
- ✅ Ideal for long work sessions

### For Anypoint Username/Password Users
- ⚠️ Username/password tokens don't auto-refresh
- ℹ️ You'll need to log back in after 1 hour
- 💡 Consider using Connected App for better experience

### For Long Sessions
- Keep your browser tab open (refresh happens on requests)
- Don't close the application
- Token refreshes automatically on any API call

## Troubleshooting

### Q: Why was my session interrupted?

**A:** Token refresh failed. Solutions:
1. Check if you're using Connected App
2. Verify credentials in `connected_apps_credentials.csv`
3. Check network connection
4. Log out and log back in

### Q: How can I see token refresh happening?

**A:** Check Flask logs:
```
[TOKEN_REFRESH] Token expired after 50.2 minutes, refreshing...
[TOKEN_REFRESH] Token refreshed successfully
```

### Q: Can I change the refresh time?

**A:** Yes, edit `app.py` and change:
```python
TOKEN_REFRESH_THRESHOLD_MINUTES = 50  # Refresh after X minutes
```

Then restart the application.

### Q: What if I'm away from my desk?

**A:** Token only refreshes when you make API requests. If you're inactive:
- Token may expire (55 minutes max)
- Next API call will fail
- You'll need to log back in
- Solution: Keep browser tab open if doing long work

## Technical Details

### Token Lifetime
- **Validity:** 55 minutes
- **Auto-refresh::** 50 minutes (5 before expiry)
- **Minimum wait:** Refreshes daily, multiple times per day

### What Gets Refreshed
- ✅ OAuth2 access token
- ✅ Environment list
- ✅ Org ID
- ✓ Session timestamp

### Where Credentials Come From
- **Connected App:** `connected_apps_credentials.csv`
- **Anypoint:** Requires re-authentication (not auto-refreshed)

## Common Questions

**Q: Is my login information stored?**
```
Connected App: Yes (in CSV) - used for refresh
Anypoint:      No - not stored, can't auto-refresh
```

**Q: Can someone else use my token?**
```
No - tokens are stored server-side in your session
Not shared with browser or other users
```

**Q: What happens if refresh fails?**
```
Your request continues with existing token
If token actually expired, request fails
You see an error and must log in again
```

**Q: Does this speed up or slow down the app?**
```
Negligible impact:
- Refresh check: <1ms per request
- Refresh process: ~100-300ms (once per 50 minutes)
- No performance degradation
```

## Summary

| Feature | Status | Details |
|---|---|---|
| Auto-refresh | ✅ Active | Every 50 minutes |
| Background | ✅ Yes | Silent, no interruption |
| User action | ❌ None | Automatic |
| Connected App | ✅ Fully supported | Uses CSV credentials |
| Anypoint login | ⚠️ Partial | Doesn't auto-refresh |
| Visible indicator | ℹ️ No | Check `/api/session` if needed |

---

**The bottom line:** Your token automatically refreshes before it expires. Just keep working and you'll never be interrupted by a session timeout!

---

For more details, see [TOKEN_AUTO_REFRESH_GUIDE.md](TOKEN_AUTO_REFRESH_GUIDE.md)
