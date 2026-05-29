import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import api from '../services/api'
import type { User } from '../types'

interface CurrentUserContextValue {
  currentUser: User | null
  users: User[]
  setCurrentUser: (u: User) => void
  isLoading: boolean
}

const Ctx = createContext<CurrentUserContextValue | null>(null)

export function CurrentUserProvider({ children }: { children: ReactNode }) {
  const [users, setUsers] = useState<User[]>([])
  const [currentUser, setCurrentUserState] = useState<User | null>(null)
  const [isLoading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    // Use the open /api/users endpoint (not /api/admin/users) so the picker
    // can load before any user is identified. /api/admin is now admin-only;
    // the bootstrap picker can't depend on admin auth.
    api.get<Array<{
      id: string
      name: string
      username: string | null
      email: string | null
      role: string
      is_active: boolean
    }>>('/users')
      .then((res) => {
        if (cancelled) return
        // Adapt the unified backend's shape (`name`) into the legacy
        // PayGuard User interface (`full_name`).
        const all: User[] = res.data.map((u) => ({
          id: u.id,
          username: u.username ?? '',
          email: u.email ?? '',
          full_name: u.name,
          role: u.role as User['role'],
          is_active: u.is_active,
        }))
        setUsers(all)
        const savedId = localStorage.getItem('opa_user_id')
        const saved = savedId ? all.find((u) => u.id === savedId) : null
        const fallback = all.find((u) => u.role === 'analyst') ?? all[0] ?? null
        const chosen = saved ?? fallback
        if (chosen) {
          setCurrentUserState(chosen)
          localStorage.setItem('opa_user_id', chosen.id)
          localStorage.setItem('opa_role', chosen.role)
        }
      })
      .catch((err) => console.error('[CurrentUser] failed to load users', err))
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const setCurrentUser = (u: User) => {
    setCurrentUserState(u)
    localStorage.setItem('opa_user_id', u.id)
    localStorage.setItem('opa_role', u.role)
    // Reload the page so React Query caches reset to the new identity.
    // Cheaper than wiring an explicit cache invalidation across the app.
    window.location.reload()
  }

  return (
    <Ctx.Provider value={{ currentUser, users, setCurrentUser, isLoading }}>
      {children}
    </Ctx.Provider>
  )
}

export function useCurrentUser() {
  const v = useContext(Ctx)
  if (!v) throw new Error('useCurrentUser must be used inside CurrentUserProvider')
  return v
}
