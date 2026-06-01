// Shared-login gate. When the backend reports the demo gate is enabled and no
// valid token is stored, show a password screen. On success, store the token
// and render the app. When the gate is disabled (local dev), render children
// immediately. Pairs with the backend DemoGateMiddleware.
import { useEffect, useState, ReactNode } from 'react'
import { Lock, Loader2 } from 'lucide-react'
import api, { DEMO_TOKEN_KEY } from '../../services/api'

export default function DemoGate({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<'checking' | 'locked' | 'open'>('checking')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    let cancelled = false
    api.get<{ gate_enabled: boolean }>('/auth/status')
      .then((res) => {
        if (cancelled) return
        if (!res.data.gate_enabled) { setPhase('open'); return }
        // Gate on: trust a stored token; the API 401 interceptor forces
        // re-login if it's actually expired/invalid.
        setPhase(localStorage.getItem(DEMO_TOKEN_KEY) ? 'open' : 'locked')
      })
      .catch(() => { if (!cancelled) setPhase('open') }) // fail open for dev/offline
    return () => { cancelled = true }
  }, [])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true); setError('')
    try {
      const res = await api.post<{ token: string }>('/auth/login', { password })
      localStorage.setItem(DEMO_TOKEN_KEY, res.data.token)
      setPhase('open')
    } catch (err: any) {
      setError(err?.response?.status === 401 ? 'Incorrect password' : 'Login failed. Try again.')
    } finally {
      setSubmitting(false)
    }
  }

  if (phase === 'checking') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <Loader2 className="w-6 h-6 text-gray-300 animate-spin" />
      </div>
    )
  }

  if (phase === 'locked') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100 p-4">
        <form onSubmit={submit} className="bg-white rounded-2xl border border-gray-200 shadow-sm p-8 w-full max-w-sm">
          <div className="w-10 h-10 rounded-xl bg-[#FE017D]/10 flex items-center justify-center mb-4">
            <Lock className="w-5 h-5 text-[#FE017D]" />
          </div>
          <h1 className="text-lg font-bold text-gray-900">Payment Integrity — Demo</h1>
          <p className="text-sm text-gray-500 mt-1 mb-5">Enter the demo password to continue.</p>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoFocus
            placeholder="Password"
            className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 mb-3 focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]/40"
          />
          {error && <p className="text-xs text-red-600 mb-3">{error}</p>}
          <button
            type="submit"
            disabled={submitting || !password}
            className="w-full bg-[#FE017D] text-white text-sm font-medium rounded-lg py-2 disabled:opacity-40 hover:bg-[#d4016a] transition-colors flex items-center justify-center gap-2"
          >
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
            Enter
          </button>
        </form>
      </div>
    )
  }

  return <>{children}</>
}
