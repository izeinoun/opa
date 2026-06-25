# Cross-App Auth Implementation Checklist

## ✅ Completed: OPA Backend

### Routes (`server/app/routes/auth.py`)
- [x] `POST /api/auth/login` — username/password → jwt + httpOnly cookie
- [x] `POST /api/auth/refresh` — refresh token before expiry
- [x] `GET /api/auth/me` — verify current user/session
- [x] `POST /api/auth/logout` — clear cookie

**Token Config:**
- 12-hour expiry (`JWT_EXPIRY_MINUTES = 1440`)
- httpOnly cookies (XSS safe)
- SameSite=Lax (CSRF safe)
- Set on every login/refresh

### Middleware (`server/app/middleware/auth.py`)
- [x] Accept token from Authorization header (backward compat)
- [x] Accept token from httpOnly cookie (cross-app)
- [x] Fallback to system user for unauthenticated jobs

---

## ✅ Completed: OPA Assistant Frontend

### Auth Service (`src/services/authService.ts`)
- [x] `login(username, password)` — credential validation
- [x] `logout()` — clear session
- [x] `refreshToken()` — called every 11 hours
- [x] `getCurrentUser()` — verify session from any app
- [x] `initAuth(callbacks)` — app startup (check session, start refresh)
- [x] `setupAuthBroadcaster()` — sync login/logout across tabs (BroadcastChannel)

**Auto-Refresh:**
- Timer set for 11 hours after login/refresh
- Reschedules itself on success
- User never sees "token expired" (unless idle > 12h)

### App Integration
- [x] `main.tsx` — use `initAuth()` on mount, check loading state
- [x] `LoginPage.tsx` — call `login()` service instead of direct API
- [x] `App.tsx` — call `logout()` service
- [x] `api/client.ts` — set `withCredentials: true`, remove localStorage token
- [x] `AssistantChat.tsx` — use `credentials: 'include'` in fetch calls

---

## 📋 TODO: Replicate to Other Apps

### PayGuard (`/Users/issamzeinoun/claude/payguard/frontend`)

**Copy & Adapt:**
1. Copy `/Users/issamzeinoun/claude/assistant/frontend/src/services/authService.ts` → `client/src/services/authService.ts`
2. Update `main.tsx` → replace localStorage check with `initAuth()`
3. Update `LoginPage.tsx` → use `login()` service
4. Update `api/client.ts` → set `withCredentials: true`, remove auth header injection
5. Search for `localStorage` references → remove or migrate to `sessionStorage`
6. Test: Log in, verify browser DevTools → Application → Cookies → `opa_token` exists

### SIU (`/Users/issamzeinoun/claude/siu`)

- Same as PayGuard steps above
- Verify assistant can talk to SIU backend (API routes need auth)

### ClaimGuard (`/Users/issamzeinoun/claude/claimguard/frontend`)

- Same as PayGuard steps above
- Update API_BASE_URL in appUrls config if pointing to OPA backend

### IAM (`/Users/issamzeinoun/claude/iam`)

- Could be a central SSO provider
- Or replicate auth service like others
- Decision: make it the canonical login page, then redirect to referrer app?

---

## 🧪 Testing Checklist

### Single App (OPA Assistant)
- [ ] Open http://localhost:5179
- [ ] See login page (no cookie set)
- [ ] Log in with `ana.chen` / `ana.chen`
- [ ] Verify DevTools → Cookies → `opa_token` (httpOnly, SameSite=Lax)
- [ ] Send a chat prompt, verify request includes cookie
- [ ] Navigate away for 5 minutes, return
- [ ] Chat still works (token was auto-refreshed)

### Cross-App Sync
- [ ] Open PayGuard (localhost:5174) in tab 1
- [ ] Open OPA Assistant (localhost:5179) in tab 2
- [ ] Log in on PayGuard with `ana.chen`
- [ ] Switch to OPA Assistant tab
- [ ] Should already be logged in (cookie shared, no 401)
- [ ] Log out from PayGuard
- [ ] Switch to OPA Assistant, make a request
- [ ] Should get 401, reload → login page

### Token Refresh
- [ ] Set a debug breakpoint in `authService.scheduleTokenRefresh()`
- [ ] Verify it fires ~11 hours after login (in testing, set interval to 10s)
- [ ] Verify `/api/auth/refresh` is called
- [ ] Verify new token is returned
- [ ] Verify timer is rescheduled

### Logout Flow
- [ ] Log in on any app
- [ ] Click "Sign Out"
- [ ] Verify `POST /api/auth/logout` called
- [ ] Verify cookie cleared (DevTools)
- [ ] Verify redirect to login page
- [ ] Verify other app sees logout (broadcast event)

---

## 🔐 Security Validation

### Token Theft Prevention
- [x] Tokens in httpOnly cookies (JavaScript can't read)
- [x] Tokens sent only to same-origin (SameSite=Lax)
- [x] No token in URL or localStorage (XSS safe)
- [ ] **TODO**: Rate-limit `/api/auth/login` (brute force protection)
- [ ] **TODO**: Implement refresh token (separate httpOnly cookie, optional)

### Session Hijacking Prevention
- [x] Short-lived tokens (12 hours, auto-refresh every 11)
- [x] Tokens tied to user_id (can't use another user's token)
- [ ] **TODO**: Add IP check (optional, breaks mobile hotspot switching)
- [ ] **TODO**: Add device fingerprint (optional)

### CSRF Protection
- [x] SameSite=Lax cookies (browser blocks cross-origin POST)
- [x] POST requests use fetch with `credentials: 'include'` (modern CSRF safe)
- [ ] **TODO**: Add CSRF token if form submissions ever used

---

## 📊 Monitoring / Observability

Add to your logging:
- Login events (username, timestamp, IP)
- Refresh events (user_id, timestamp, old token exp vs new)
- Logout events (user_id, timestamp)
- 401 errors (user_id, endpoint, reason)

Example log line:
```python
logger.info(f"[AUTH] Login successful for {user.username} (user_id={user.user_id})")
logger.info(f"[AUTH] Token refresh for {user.user_id}, new exp: {datetime.utcfromtimestamp(payload['exp'])}")
```

---

## 🚀 Production Rollout

### Phase 1: Local Dev (Current)
- ✅ All apps run on localhost, share cookies
- ✅ Token refresh tested

### Phase 2: Staging (Before production)
- [ ] Deploy backend with new auth routes to staging
- [ ] Update PayGuard frontend on staging
- [ ] Test: PayGuard ↔ OPA Assistant cross-app sync
- [ ] Verify refresh works over 12+ hours (or accelerate for testing)
- [ ] Load test: 100 concurrent users, refresh every 11h

### Phase 3: Production
- [ ] Set `Secure=True` in cookies (HTTPS only)
- [ ] Set `SameSite=Strict` if same domain (might break redirects from external links)
- [ ] Add rate limiting to `/api/auth/login` (e.g., 5 attempts per IP per minute)
- [ ] Enable audit logging for all auth events
- [ ] Set up alerts for unusual patterns (many refresh failures, many 401s)
- [ ] Deploy backend
- [ ] Gradually roll out frontend (canary, then full)
- [ ] Monitor error rates for 24 hours
- [ ] Monitor token refresh success rate (should be 99%+)

---

## 📝 Notes

### Why 11-hour refresh interval?
- Token expires in 12 hours
- Refresh at 11 hours = 1-hour buffer
- If refresh fails, user still has 1 hour to recover (not immediate logout)
- If refresh succeeds, new token adds 12 more hours
- Result: user never experiences token expiry (unless idle > 12h between refreshes)

### Why httpOnly cookies?
- Cannot be stolen by JavaScript (XSS safe)
- Browser sends automatically (no code to forget)
- Different from `sessionStorage` (cleared on browser close) or `localStorage` (persistent, XSS vulnerable)

### Why BroadcastChannel?
- Allows tabs/apps at same origin to sync
- When user logs in on PayGuard, SIU tab gets notified
- Optional but nice for UX
- Fallback: if app is in different origin or BroadcastChannel not supported, user just makes first request, gets 401, reloads

---

## Questions?

See `/CROSS_APP_AUTH.md` for architecture deep-dive.
