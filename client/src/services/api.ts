import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  // Dev mode: attach role + user_id from localStorage (set by CurrentUserProvider).
  const role = localStorage.getItem('opa_role') ?? 'analyst'
  const userId = localStorage.getItem('opa_user_id')
  config.headers['X-User-Role'] = role
  if (userId) config.headers['X-User-Id'] = userId
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    console.error('[API Error]', err.response?.data ?? err.message)
    return Promise.reject(err)
  }
)

export default api
