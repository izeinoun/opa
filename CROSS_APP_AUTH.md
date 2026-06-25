# Cross-App Token Synchronization & Auto-Refresh

> **Status**: Reference implementation in OPA Assistant (`/Users/issamzeinoun/claude/assistant/frontend`). Replicate to PayGuard, SIU, ClaimGuard, IAM.

## Problem Solved

Users log in once and switch seamlessly between apps (PayGuard, ClaimGuard, OPA Assistant, SIU) without re-authenticating. Tokens auto-refresh every 11 hours so they never see a "session expired" message (even with 12-hour expiry).

## Architecture Overview

```
User Login (any app) → OPA Backend /api/auth/login
                         ↓
                    Set httpOnly Cookie (opa_token)
                    Return token in response body
                         ↓
                    Browser auto-sends cookie to all requests
                         ↓
              All apps (localhost:5174, 5179, etc.) see the token
                         ↓
                Every 11 hours, call /api/auth/refresh
                Auto-refresh reschedules itself
                         ↓
              Token stays valid, user never logs out
```

## Backend Implementation (OPA API)

### 1. Auth Routes (`server/app/routes/auth.py`)

Added endpoints:
- `POST /api/auth/login` — sets httpOnly cookie + returns token
- `POST /api/auth/refresh` — validates current token, issues new one, resets cookie
- `GET /api/auth/me` — returns current user (verify session from any app)
- `POST /api/auth/logout` — clears cookie

**Key points:**
- Cookies have `httpOnly=True` (can't be stolen via XSS), `SameSite=Lax` (sent cross-domain but safe), 12-hour max-age.
- All endpoints are idempotent — refresh can be called multiple times safely.
- Token lifetime is 12 hours (`JWT_EXPIRY_MINUTES = 1440`).

### 2. Auth Middleware (`server/app/middleware/auth.py`)

Updated `get_current_user` to check:
1. Authorization header (Bearer token) — used by curl, Postman, etc.
2. httpOnly cookie (fallback) — used by browsers automatically
3. System user fallback for unauthenticated jobs

```python
async def get_current_user(request: Request, authorization: str | None = Header(...), ...):
    # Try header first
    if authorization and "Bearer" in authorization:
        token = authorization.split()[1]
    
    # Fall back to cookie (cross-app sessions)
    if not token:
        token = request.cookies.get("opa_token")
    
    # Verify and resolve user...
```

## Frontend Implementation

### Shared Auth Service (`src/services/authService.ts`)

Create this module in **every frontend app** (PayGuard, SIU, etc.):

```typescript
// Features:
export async function login(username: string, password: string): Promise<User>
export async function logout(): Promise<void>
export async function refreshToken(): Promise<boolean>
export async function getCurrentUser(): Promise<User | null>
export async function initAuth(callbacks): Promise<User | null>
export function setupAuthBroadcaster(onLogin, onLogout, onExpired): cleanup
```

**Key behaviors:**
- `login()` — calls backend, browser gets cookie automatically, starts 11-hour refresh timer.
- `initAuth()` — checks for existing session (cookie), starts refresh timer, sets up broadcast listener.
- `refreshToken()` — called on 11-hour timer, validates token and issues new one without user action.
- `setupAuthBroadcaster()` — listens for login/logout/expiry from other apps via BroadcastChannel (optional but nice).

### App Integration (e.g., OPA Assistant)

#### 1. Update `main.tsx`

```typescript
function Root() {
  const [isLoading, setIsLoading] = useState(true)
  const [isAuthenticated, setIsAuthenticated] = useState(false)

  useEffect(() => {
    // Check if already logged in via cookie on mount
    initAuth({ onAuthChange: (user) => setIsAuthenticated(!!user) })
      .then((user) => {
        setIsAuthenticated(!!user)
        setIsLoading(false)
      })
  }, [])

  if (isLoading) return <LoadingScreen />

  return isAuthenticated ? <App /> : <LoginPage />
}
```

#### 2. Update `LoginPage.tsx`

```typescript
const handleSubmit = async (e: React.FormEvent) => {
  const user = await login(username, password)
  // Token is now in httpOnly cookie, no need to store it
  // Store user_id in sessionStorage if needed for UI
  sessionStorage.setItem('assistant_user_id', user.user_id)
  onSuccess()
}
```

#### 3. Update API client (`api/client.ts`)

```typescript
export const client = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true, // Include cookies in all requests
})

// On 401, session expired, reload
client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      window.location.reload()
    }
    return Promise.reject(err)
  },
)
```

#### 4. Remove localStorage token usage

```typescript
// BEFORE
const token = localStorage.getItem('opa_jwt_token')
headers['Authorization'] = `Bearer ${token}`

// AFTER (not needed, cookie is sent automatically)
fetch(url, { credentials: 'include' })
// Cookie is auto-sent by browser
```

## Testing the Flow

### Manual test (command line):

```bash
# 1. Login (sets cookie)
TOKEN=$(curl -s -X POST http://localhost:8001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"ana.chen","password":"ana.chen"}' \
  | jq -r '.access_token')

# 2. Use the token to call an API
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8001/api/cases | jq '.[0]'

# 3. Get current user (verifies session)
curl -s http://localhost:8001/api/auth/me \
  -H "Cookie: opa_token=$TOKEN" | jq

# 4. Refresh token
curl -s -X POST http://localhost:8001/api/auth/refresh \
  -H "Cookie: opa_token=$TOKEN" | jq '.access_token'
```

### Browser test:

1. **PayGuard (localhost:5174)**
   - Open login page
   - Log in with `ana.chen` / `ana.chen`
   - Open browser DevTools → Application → Cookies → `opa_token` (should exist)

2. **OPA Assistant (localhost:5179)**
   - In same browser, navigate to localhost:5179
   - Should NOT see login page (cookie is sent automatically)
   - Open DevTools → Network → chat request → Cookies (should include `opa_token`)

3. **Log out from PayGuard**
   - Cookie is cleared server-side
   - Switch to OPA Assistant
   - Should see login page (401 on next API call)

## Security Considerations

### ✅ What's Protected

- **httpOnly cookies** — JavaScript can't read them, XSS can't steal them.
- **SameSite=Lax** — browser won't send cookie to cross-origin POST requests (CSRF protected).
- **12-hour lifetime** — short enough to limit exposure if token is compromised.
- **Refresh token optional** — if added, it should be stored securely (httpOnly cookie too).

### ⚠️ Production Checklist

- [ ] Set `Secure=True` in production (HTTPS only).
- [ ] Store refresh tokens in a separate httpOnly cookie if implementing token refresh.
- [ ] Add rate limiting to `/api/auth/login` (prevent brute force).
- [ ] Use stronger password hashing (bcrypt, argon2) — currently username=password for demo.
- [ ] Add CSRF token if ever using `<form>` submissions (not needed for fetch).
- [ ] Log auth events (login, refresh, logout) for audit trail.

## Rollout Plan

### Phase 1: OPA Assistant (✅ Done)
- Reference implementation

### Phase 2: PayGuard
1. Copy `authService.ts` to `client/src/services/authService.ts`
2. Update `main.tsx` → use `initAuth()`
3. Update `LoginPage.tsx` → use `login()`
4. Update `api/client.ts` → set `withCredentials: true`
5. Remove all `localStorage` token references

### Phase 3: SIU
- Same as Phase 2

### Phase 4: ClaimGuard
- Same as Phase 2

### Phase 5: IAM (SSO provider)
- Optionally: make IAM the canonical login page
- Redirect back to referrer app with token
- All other apps accept tokens from IAM

## Fallback: Per-App Login

If an app needs to work offline or without cookies (e.g., electron app), it can:

1. Get token from `/api/auth/login`
2. Store in `sessionStorage` (not localStorage — cleared on browser close)
3. Attach as `Authorization: Bearer <token>` header on all requests
4. Implement local refresh timer

Backend will still accept both methods (header OR cookie).
