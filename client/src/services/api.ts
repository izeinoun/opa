import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  // Dev mode: attach role header
  const role = localStorage.getItem('opa_role') ?? 'analyst'
  config.headers['X-User-Role'] = role
  config.headers['X-User-Id'] = localStorage.getItem('opa_user_id') ?? '1'
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
