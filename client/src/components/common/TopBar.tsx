import { useState, useRef, useEffect } from 'react'
import { ChevronDown, User as UserIcon, Shield, ShieldCheck } from 'lucide-react'
import { useCurrentUser } from '../../hooks/useCurrentUser'
import NotificationBell from './NotificationBell'
import type { User, UserRole } from '../../types'

const ROLE_STYLE: Record<UserRole, string> = {
  admin:      'bg-[#FE017D]/10 text-[#FE017D] border-[#FE017D]/30',
  supervisor: 'bg-purple-100 text-purple-700 border-purple-200',
  analyst:    'bg-blue-100 text-blue-700 border-blue-200',
  system:     'bg-gray-100 text-gray-600 border-gray-200',
}

const ROLE_ICON: Record<UserRole, typeof UserIcon> = {
  admin:      ShieldCheck,
  supervisor: Shield,
  analyst:    UserIcon,
  system:     UserIcon,
}

const ROLE_ORDER: UserRole[] = ['supervisor', 'analyst', 'admin', 'system']

export default function TopBar() {
  const { currentUser, users, setCurrentUser, isLoading } = useCurrentUser()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  if (isLoading || !currentUser) {
    return (
      <header className="fixed top-0 left-56 right-0 h-12 bg-white border-b border-gray-200 flex items-center justify-end px-5 z-30">
        <span className="text-xs text-gray-400">Loading…</span>
      </header>
    )
  }

  const groups: Record<UserRole, User[]> = { admin: [], supervisor: [], analyst: [], system: [] }
  for (const u of users) {
    if (!u.is_active) continue
    if (u.role in groups) groups[u.role].push(u)
  }

  const CurrentIcon = ROLE_ICON[currentUser.role]

  return (
    <header className="fixed top-0 left-56 right-0 h-12 bg-white border-b border-gray-200 flex items-center justify-end gap-3 px-5 z-30">
      <NotificationBell />
      <div ref={ref} className="relative">
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-gray-200 hover:border-gray-300 hover:bg-gray-50 transition-colors"
          aria-label="Switch user"
        >
          <CurrentIcon className="w-4 h-4 text-gray-500" />
          <div className="text-left leading-tight">
            <p className="text-xs font-semibold text-gray-800">{currentUser.full_name}</p>
            <span className={`inline-block mt-0.5 px-1.5 py-px rounded text-[10px] font-medium border ${ROLE_STYLE[currentUser.role]}`}>
              {currentUser.role}
            </span>
          </div>
          <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
        </button>

        {open && (
          <div className="absolute right-0 mt-2 w-72 bg-white border border-gray-200 rounded-xl shadow-lg py-2 max-h-96 overflow-y-auto z-40">
            <div className="px-4 py-2 border-b border-gray-100">
              <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Switch user (demo)</p>
              <p className="text-xs text-gray-500 mt-0.5">All actions are recorded under the selected user.</p>
            </div>
            {ROLE_ORDER.map((role) => {
              const list = groups[role]
              if (!list.length) return null
              return (
                <div key={role} className="py-1">
                  <p className="px-4 py-1 text-[10px] font-bold text-gray-400 uppercase tracking-wider">
                    {role}s
                  </p>
                  {list.map((u) => {
                    const Icon = ROLE_ICON[u.role]
                    const active = u.id === currentUser.id
                    return (
                      <button
                        key={u.id}
                        onClick={() => { setOpen(false); setCurrentUser(u) }}
                        className={`w-full text-left px-4 py-1.5 flex items-center gap-2 hover:bg-gray-50 transition-colors ${
                          active ? 'bg-indigo-50' : ''
                        }`}
                      >
                        <Icon className="w-3.5 h-3.5 text-gray-400" />
                        <div className="flex-1">
                          <p className={`text-sm ${active ? 'font-semibold text-indigo-700' : 'text-gray-800'}`}>
                            {u.full_name}
                          </p>
                          <p className="text-[11px] text-gray-400 font-mono">{u.username}</p>
                        </div>
                        {active && <span className="text-[10px] text-indigo-600 font-semibold">active</span>}
                      </button>
                    )
                  })}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </header>
  )
}
