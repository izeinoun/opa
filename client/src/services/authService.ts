/**
 * Cross-app authentication service with auto-refresh & session sync.
 *
 * Features:
 * - Cookie-based tokens (auto-sent on every request)
 * - Auto-refresh every 11 hours (before 12-hour expiry)
 * - BroadcastChannel for inter-app sync (login/logout notifications)
 * - Graceful fallback if token expires
 */
import { API_BASE_URL } from '../config/appUrls'

export interface User {
  user_id: string
  username: string
  full_name: string
  role: string
  email: string
}

interface TokenResponse {
  access_token: string
  user_id: string
  role: string
  full_name: string
}

const REFRESH_INTERVAL_MS = 11 * 60 * 60 * 1000 // 11 hours
let refreshTimeoutId: ReturnType<typeof setTimeout> | null = null
let broadcastChannel: BroadcastChannel | null = null

/**
 * Get current authenticated user. Returns null if not logged in.
 * This can be called from any app to verify cross-app session state.
 */
export async function getCurrentUser(): Promise<User | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/me`, {
      credentials: 'include', // Send cookies
    })
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
}

/**
 * Log in with username/password. Sets httpOnly cookie automatically.
 * Broadcasts login event to other apps.
 */
export async function login(username: string, password: string): Promise<User> {
  const res = await fetch(`${API_BASE_URL}/api/auth/login`, {
    method: 'POST',
    credentials: 'include', // Enable cookie handling
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })

  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Login failed')
  }

  const data: TokenResponse = await res.json()

  // Broadcast to other tabs/apps
  broadcastEvent('auth:login', { user_id: data.user_id })

  // Start auto-refresh
  scheduleTokenRefresh()

  return {
    user_id: data.user_id,
    username: '', // Fetch via /me if needed
    full_name: data.full_name,
    role: data.role,
    email: '',
  }
}

/**
 * Log out. Clears cookie and broadcasts to other apps.
 * Always completes (even if network fails), ensuring clean state.
 */
export async function logout(): Promise<void> {
  clearRefreshTimer()

  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/logout`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
    })

    if (!res.ok) {
      console.warn('[Auth] Logout endpoint returned', res.status)
    }
  } catch (e) {
    console.warn('[Auth] Logout failed:', e)
    // Continue with local cleanup even if network call fails
  }

  // Broadcast to other tabs/apps
  broadcastEvent('auth:logout', {})

  // Clear any stored user data
  try {
    sessionStorage.removeItem('assistant_user_id')
  } catch {
    // Ignore
  }
}

/**
 * Refresh the access token before it expires.
 * Called automatically on a 11-hour timer.
 */
export async function refreshToken(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
    })

    if (!res.ok) {
      // Token expired or invalid, user must log in again
      broadcastEvent('auth:expired', {})
      return false
    }

    // Success — reschedule next refresh
    scheduleTokenRefresh()
    return true
  } catch (e) {
    console.error('Token refresh failed:', e)
    return false
  }
}

/**
 * Schedule automatic token refresh 11 hours from now.
 */
function scheduleTokenRefresh(): void {
  clearRefreshTimer()
  refreshTimeoutId = setTimeout(async () => {
    const ok = await refreshToken()
    if (ok) {
      // Successfully refreshed, timer was rescheduled
      console.log('[Auth] Token refreshed')
    } else {
      console.warn('[Auth] Token refresh failed, user logged out')
    }
  }, REFRESH_INTERVAL_MS)
}

function clearRefreshTimer(): void {
  if (refreshTimeoutId) {
    clearTimeout(refreshTimeoutId)
    refreshTimeoutId = null
  }
}

/**
 * Broadcast auth event to other tabs/apps at same origin.
 * Other apps listen and can update their state.
 */
function broadcastEvent(type: string, data: any): void {
  if (!broadcastChannel) {
    try {
      broadcastChannel = new BroadcastChannel('opa_auth')
    } catch {
      return // BroadcastChannel not supported
    }
  }
  broadcastChannel.postMessage({ type, data })
}

/**
 * Listen for auth events from other apps (e.g., login on PayGuard, notify SIU).
 * Call this on app mount.
 */
export function setupAuthBroadcaster(
  onLoginElsewhere: () => void,
  onLogoutElsewhere: () => void,
  onExpiredElsewhere: () => void,
): () => void {
  if (!broadcastChannel) {
    try {
      broadcastChannel = new BroadcastChannel('opa_auth')
    } catch {
      return () => {} // BroadcastChannel not supported, return no-op cleanup
    }
  }

  const handler = (evt: MessageEvent) => {
    if (evt.data.type === 'auth:login') onLoginElsewhere()
    else if (evt.data.type === 'auth:logout') onLogoutElsewhere()
    else if (evt.data.type === 'auth:expired') onExpiredElsewhere()
  }

  broadcastChannel.addEventListener('message', handler)

  return () => {
    broadcastChannel?.removeEventListener('message', handler)
  }
}

/**
 * Initialize auth on app mount:
 * 1. Check if user is already logged in (via cookie)
 * 2. Set up auto-refresh
 * 3. Set up broadcast listener
 */
export async function initAuth(callbacks: {
  onAuthChange?: (user: User | null) => void
}): Promise<User | null> {
  const user = await getCurrentUser()

  if (user) {
    // Already logged in via cookie, start refresh cycle
    scheduleTokenRefresh()
  }

  // Set up listener for auth events from other apps
  setupAuthBroadcaster(
    () => {
      // Another app logged in, refresh our session
      getCurrentUser().then(callbacks.onAuthChange)
    },
    () => {
      // Another app logged out, clear ours
      clearRefreshTimer()
      callbacks.onAuthChange?.(null)
    },
    () => {
      // Another app's token expired, clear ours
      clearRefreshTimer()
      callbacks.onAuthChange?.(null)
    },
  )

  return user
}
