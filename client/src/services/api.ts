import axios from 'axios'

// Backend API base. Defaults to the relative `/api` path — which works in dev
// (Vite proxies it to :8001) and for same-origin deploys where the backend also
// serves the built frontend. Set VITE_API_URL to the backend's URL when the
// frontend is deployed separately from the API (e.g. distinct Railway services).
// Vite inlines this at BUILD time, so it must be set as a build-time env var.
const API_ROOT = import.meta.env.VITE_API_URL?.replace(/\/$/, '')
export const API_BASE = API_ROOT ? `${API_ROOT}/api` : '/api'

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

api.interceptors.response.use(
  (res) => res,
  (err) => {
    // Gate rejected us (expired/missing token) — drop it and return to login.
    // Skip the auth endpoints so a wrong-password 401 can surface its message.
    const url: string = err.config?.url ?? ''
    if (err.response?.status === 401 && !url.includes('/auth/')) {
      localStorage.removeItem(DEMO_TOKEN_KEY)
      window.location.reload()
    }
    console.error('[API Error]', err.response?.data ?? err.message)
    return Promise.reject(err)
  }
)

export default api
