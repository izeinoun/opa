import axios from 'axios'

// Backend API base. PayGuard is always served same-origin by the backend — in
// dev Vite proxies `/api` to :8001, and in prod the backend mounts the built
// frontend and serves `/api` itself. So a relative `/api` is correct in every
// environment and needs no host/env var. (Cross-app URLs live in config/appUrls.)
export const API_BASE = '/api'

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true, // Include httpOnly cookies in all requests
})

// Reentrancy guard so a persistent 401 can never become an infinite
// reload storm: we reload at most once per page load, and clear the flag
// the moment any request succeeds.
const RELOAD_GUARD_KEY = 'opa_auth_reloading'

api.interceptors.response.use(
  (res) => {
    sessionStorage.removeItem(RELOAD_GUARD_KEY)
    return res
  },
  (err) => {
    // Skip the auth endpoints so login errors can surface their messages.
    const url: string = err.config?.url ?? ''
    if (err.response?.status === 401 && !url.includes('/auth/')) {
      // Session expired, redirect to login
      // Cookie was cleared server-side, reload to get login page
      if (!sessionStorage.getItem(RELOAD_GUARD_KEY)) {
        sessionStorage.setItem(RELOAD_GUARD_KEY, '1')
        window.location.href = '/login'
      }
    }
    console.error('[API Error]', err.response?.data ?? err.message)
    return Promise.reject(err)
  }
)

// Deprecated: JWT_TOKEN_KEY is no longer used for auth (cookies handle it now).
// Keeping export for backward compatibility.
export const JWT_TOKEN_KEY = 'opa_jwt_token'

export default api
