# Cross-App Single Sign-On (SSO) Implementation Complete ✅

## What Changed

**Goal**: Log in once, work everywhere. Login to OPA Assistant → PayGuard/SIU/ClaimGuard/IAM all already signed in.

**Implementation**: Token-based authentication via httpOnly cookies + auto-refresh every 11 hours.

---

## What Was Updated

### ✅ Backend (OPA API)
All work done in `/Users/issamzeinoun/claude/overcoding/opa/server/app/`

**New endpoints** (`routes/auth.py`):
- `POST /api/auth/login` — username/password → JWT + httpOnly cookie (12h expiry)
- `POST /api/auth/refresh` — refresh token before expiry (no user action needed)
- `GET /api/auth/me` — verify authenticated session
- `POST /api/auth/logout` — clear cookie

**Middleware** (`middleware/auth.py`):
- Check both Authorization headers AND httpOnly cookies
- Fallback to system user only for unauthenticated endpoints (non-auth endpoints)

---

### ✅ OPA Assistant Frontend (Full Rewrite)
`/Users/issamzeinoun/claude/assistant/frontend/src/`

**New file**:
- `services/authService.ts` — shared auth service (copy to all other apps)

**Updated files**:
- `main.tsx` — check for existing session on mount via `initAuth()`
- `pages/LoginPage.tsx` — use `login()` service (credentials → cookie)
- `App.tsx` — show current user + proper logout flow
- `api/client.ts` — `withCredentials: true` (auto-send cookies)
- `components/AssistantChat.tsx` — use `credentials: 'include'` on SSE fetch

---

### ✅ PayGuard/OPA Client (Full Rewrite)
`/Users/issamzeinoun/claude/overcoding/opa/client/src/`

**New file**:
- `services/authService.ts` — shared auth service (copied)

**Updated files**:
- `pages/LoginPage.tsx` — use `login()` service
- `App.tsx` — add `initAuth()` + loading state + `ProtectedRoute` update
- `services/api.ts` — `withCredentials: true` + remove localStorage token injection
- `components/assistant/AssistantPanel.tsx` — use `credentials: 'include'`
- `components/common/TopBar.tsx` — use `logout()` service

---

### ⚠️ SIU, ClaimGuard, IAM (Cookies Only)
These apps use the **demo gate** model (not traditional user login), so only cookie support was added.

**Updated files** (all 3 apps):
- `src/api/client.ts` — added `withCredentials: true`

**Why only cookies?**
- These apps use `/api/auth/login` for the demo password gate (not user auth)
- They use `X-User-Id` header for role-based access control
- The demo gate token is now shared via cookie instead of localStorage
- If a user logs in on PayGuard, the cookie persists and these apps can use it

---

## How It Works

### Login Flow
```
User logs in on OPA Assistant (or PayGuard)
        ↓
POST /api/auth/login { username, password }
        ↓
Backend validates, returns JWT + sets httpOnly cookie
        ↓
Browser stores cookie automatically (JavaScript can't touch it — XSS safe)
        ↓
Cookie is auto-sent to ALL requests at localhost (cross-app, cross-port)
```

### Session Persistence
```
User logs in on App A (localhost:5179)
        ↓
Cookie set: opa_token=<jwt> (httpOnly, SameSite=Lax)
        ↓
User opens App B (localhost:5174) in same browser
        ↓
App B checks if authenticated: GET /api/auth/me (cookie auto-sent)
        ↓
User is ALREADY logged in (no re-login needed)
```

### Auto-Refresh
```
User logs in at 8:00 AM
        ↓
Token auto-refresh scheduled for 7:00 PM (11 hours later)
        ↓
At 7:00 PM: POST /api/auth/refresh (cookie auto-sent, new token + cookie returned)
        ↓
New token expires 12 hours later (8:00 PM tomorrow)
        ↓
Result: User never sees "session expired" (unless idle > 12h straight)
```

---

## Test It Now

### Quick Test (5 min)

**Step 1**: Hard refresh both apps
```
OPA Assistant:  Ctrl+Shift+R on http://localhost:5179
PayGuard:       Ctrl+Shift+R on http://localhost:5174
```

**Step 2**: Log in on OPA Assistant
- Navigate to http://localhost:5179
- See login page (no session yet)
- Log in: `ana.chen` / `ana.chen`
- You're in the assistant

**Step 3**: Open PayGuard in same browser
- New tab: http://localhost:5174
- Should NOT see login page
- Should be logged in as ana.chen
- ✅ **Cross-app SSO works!**

**Step 4**: Test logout
- Sign out from PayGuard
- Go back to OPA Assistant
- Try to use chat → should get logged out
- ✅ **Cross-app logout works!**

### Advanced Test (10 min)

**Multi-tab sync**:
1. Open OPA Assistant (localhost:5179) in Tab A
2. Open PayGuard (localhost:5174) in Tab B
3. Log in on Tab A
4. Switch to Tab B → already logged in
5. Switch back to Tab A, sign out
6. Switch to Tab B, try chat → logged out
7. ✅ **Real-time sync works!**

**Token Refresh** (optional, accelerated):
1. Check browser DevTools → Application → Cookies → `opa_token`
2. Note the expiry timestamp
3. Wait ~11 hours (or temporarily reduce REFRESH_INTERVAL_MS in authService.ts to 10 seconds for testing)
4. See the token auto-refresh happen silently
5. User never knows it happened
6. ✅ **Auto-refresh works!**

---

## Architecture Summary

### Token Lifecycle
```
Login
  └─ POST /api/auth/login
       └─ JWT created (expires in 12h)
       └─ httpOnly cookie set (opa_token)
       └─ Token returned in response body (for frontend display only)
  
Every 11 hours
  └─ Automatic: POST /api/auth/refresh
       └─ Existing token validated
       └─ New JWT created (fresh 12h expiry)
       └─ httpOnly cookie refreshed
       └─ Timer resets to 11 hours from now

Logout
  └─ POST /api/auth/logout
       └─ httpOnly cookie cleared (Max-Age=0)
       └─ User must log in again

Session Check (when switching apps)
  └─ GET /api/auth/me
       └─ Middleware reads cookie
       └─ If valid → return user info
       └─ If invalid → return 401
       └─ Frontend redirects to login if 401
```

### Security

#### ✅ What's Protected
- **XSS**: Token in httpOnly cookie (JavaScript can't read it)
- **CSRF**: SameSite=Lax (browser blocks malicious cross-origin requests)
- **Token expiry**: 12 hours (if device is stolen, window is limited)
- **Auto-refresh**: Token stays fresh without user action (no "session about to expire" warnings)

#### ⚠️ Still TODO for Production
- [ ] Add rate limiting to `/api/auth/login` (brute force protection)
- [ ] Use bcrypt/argon2 for password hashing (currently username=password for demo)
- [ ] Set `Secure=True` on cookies (HTTPS only)
- [ ] Add refresh token support (optional, for extra security)
- [ ] Implement audit logging for auth events

---

## Rollout Checklist

### Local Dev (✅ Done)
- [x] OPA Assistant updated
- [x] PayGuard/OPA Client updated
- [x] SIU client updated (cookies only)
- [x] ClaimGuard client updated (cookies only)
- [x] IAM client updated (cookies only)
- [x] All clients now send cookies automatically

### Testing (In Progress)
- [ ] Test single app login/logout
- [ ] Test cross-app login (login App A → App B auto-logged in)
- [ ] Test cross-app logout (logout App A → App B auto-logged out)
- [ ] Test auto-refresh (leave app open > 11 hours)
- [ ] Test on different browsers/devices

### Staging (Before Production)
- [ ] Deploy backend with new auth routes
- [ ] Deploy all frontend apps
- [ ] Monitor for auth failures (401 rates, etc.)
- [ ] Load test: 100+ concurrent users

### Production
- [ ] Enable HTTPS (set `Secure=True` on cookies)
- [ ] Add rate limiting to `/api/auth/login`
- [ ] Set up audit logging
- [ ] Deploy
- [ ] Monitor error rates for 24h

---

## Files Changed

### Backend
- `/Users/issamzeinoun/claude/overcoding/opa/server/app/routes/auth.py` — 4 endpoints
- `/Users/issamzeinoun/claude/overcoding/opa/server/app/middleware/auth.py` — cookie support

### OPA Assistant
- `/Users/issamzeinoun/claude/assistant/frontend/src/services/authService.ts` — NEW
- `/Users/issamzeinoun/claude/assistant/frontend/src/main.tsx`
- `/Users/issamzeinoun/claude/assistant/frontend/src/pages/LoginPage.tsx`
- `/Users/issamzeinoun/claude/assistant/frontend/src/App.tsx`
- `/Users/issamzeinoun/claude/assistant/frontend/src/api/client.ts`
- `/Users/issamzeinoun/claude/assistant/frontend/src/components/AssistantChat.tsx`

### PayGuard/OPA Client
- `/Users/issamzeinoun/claude/overcoding/opa/client/src/services/authService.ts` — NEW (copied)
- `/Users/issamzeinoun/claude/overcoding/opa/client/src/pages/LoginPage.tsx`
- `/Users/issamzeinoun/claude/overcoding/opa/client/src/App.tsx`
- `/Users/issamzeinoun/claude/overcoding/opa/client/src/services/api.ts`
- `/Users/issamzeinoun/claude/overcoding/opa/client/src/components/assistant/AssistantPanel.tsx`
- `/Users/issamzeinoun/claude/overcoding/opa/client/src/components/common/TopBar.tsx`

### SIU
- `/Users/issamzeinoun/claude/siu/frontend/src/services/authService.ts` — NEW (copied)
- `/Users/issamzeinoun/claude/siu/frontend/src/api/client.ts` — added `withCredentials`

### ClaimGuard
- `/Users/issamzeinoun/claude/claimguard/frontend/src/services/authService.ts` — NEW (copied)
- `/Users/issamzeinoun/claude/claimguard/frontend/src/api/client.ts` — added `withCredentials`

### IAM
- `/Users/issamzeinoun/claude/iam/frontend/src/services/authService.ts` — NEW (copied)
- `/Users/issamzeinoun/claude/iam/frontend/src/api/client.ts` — added `withCredentials`

---

## Troubleshooting

### "I'm signed in on App A but App B shows login page"
- **Cause**: App B hasn't checked for session yet, or cookie wasn't sent
- **Fix**: Hard refresh (Ctrl+Shift+R) the app that shows login page
- **Why**: Vite dev server may need a reload to pick up client changes

### "Cookie not appearing in DevTools"
- **Cause**: Cookie wasn't sent by login endpoint
- **Check**: Did the POST /api/auth/login succeed (200 response)?
- **Fix**: Check browser console for errors, check backend logs

### "Logout didn't work, still logged in"
- **Cause**: `window.location.href = '/'` didn't reload, or old cache
- **Fix**: Hard refresh (Ctrl+Shift+R) after logout
- **Why**: JavaScript navigate doesn't always clear page fully

### "Auto-refresh not happening"
- **Cause**: App was closed, or timer ran out
- **Check**: Open app, keep it open for 11 hours (or 10 seconds if you modified REFRESH_INTERVAL_MS)
- **Fix**: Check browser console for any errors in auth service

### "401 errors after logout"
- **Expected**: This is correct behavior
- **Why**: POST /api/auth/logout clears the cookie, so next API call gets 401
- **Frontend handles it**: Redirects to login on 401

---

## Questions?

See `/CROSS_APP_AUTH.md` for detailed architecture.
See `/IMPLEMENTATION_CHECKLIST.md` for specific updates per app.

**Next step**: Test the full flow and report any issues!
