import axios from 'axios'

// Backend API base. PayGuard is always served same-origin by the backend — in
// dev Vite proxies `/api` to :8001, and in prod the backend mounts the built
// frontend and serves `/api` itself. So a relative `/api` is correct in every
// environment and needs no host/env var. (Cross-app URLs live in config/appUrls.)
export const API_BASE = '/api'

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
})

export const DEMO_TOKEN_KEY = 'opa_demo_token'

api.interceptors.request.use((config) => {
  // Dev mode: attach role + user_id from localStorage (set by CurrentUserProvider).
  const role = localStorage.getItem('opa_role') ?? 'analyst'
  const userId = localStorage.getItem('opa_user_id')
  config.headers['X-User-Role'] = role
  if (userId) config.headers['X-User-Id'] = userId
  // Demo gate: attach the login token when present (no-op when gate disabled).
  const token = localStorage.getItem(DEMO_TOKEN_KEY)
  if (token) config.headers['Authorization'] = `Bearer ${token}`
  return config
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
    // Skip the auth endpoints so a wrong-password 401 can surface its message.
    const url: string = err.config?.url ?? ''
    if (err.response?.status === 401 && !url.includes('/auth/')) {
      const detail = err.response?.data?.detail
      if (typeof detail === 'string' && detail.startsWith('Unknown user_id')) {
        // The stored persona points at a user that no longer exists (e.g. a
        // re-seeded DB or an older build). Drop it so CurrentUserProvider
        // re-bootstraps to a valid user on the next load — reloading WITHOUT
        // clearing it would just 401 again and loop forever.
        localStorage.removeItem('opa_user_id')
        localStorage.removeItem('opa_role')
      } else {
        // Demo gate rejected us (expired/missing token) — drop it and bounce
        // back to the login screen.
        localStorage.removeItem(DEMO_TOKEN_KEY)
      }
      if (!sessionStorage.getItem(RELOAD_GUARD_KEY)) {
        sessionStorage.setItem(RELOAD_GUARD_KEY, '1')
        window.location.reload()
      }
    }
    console.error('[API Error]', err.response?.data ?? err.message)
    return Promise.reject(err)
  }
)

export default api
