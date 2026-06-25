import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronDown, User as UserIcon, Shield, ShieldCheck, Bot, LogOut } from 'lucide-react'
import { logout } from '../../services/authService'
import { useCurrentUser } from '../../hooks/useCurrentUser'
import NotificationBell from './NotificationBell'
import AppSwitcher from './AppSwitcher'
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
  const navigate = useNavigate()
  const { currentUser, users, setCurrentUser, isLoading } = useCurrentUser()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const handleLogout = async () => {
    await logout()
    setOpen(false)
    navigate('/login')
  }

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
      <header className="w-full h-12 bg-white border-b border-gray-200 flex items-center justify-end px-5 z-30">
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
  const isDev = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'

  return (
    <header className="w-full h-12 bg-white border-b border-gray-200 flex items-center justify-between gap-3 px-5 z-30">
      <AppSwitcher current="payguard" />

      {/* Center environment label */}
      <div className={`flex-1 text-center text-sm font-semibold ${isDev ? 'text-green-600' : 'text-red-600'}`}>
        {isDev ? 'DEVELOPMENT' : 'PRODUCTION'}
      </div>

      <div className="flex items-center gap-3">
        <span className="w-px h-6 bg-gray-200" aria-hidden />
        <NotificationBell />
        <div ref={ref} className="relative">
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-gray-200 hover:border-gray-300 hover:bg-gray-50 transition-colors"
          aria-label="User menu"
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
          <div className="absolute right-0 mt-2 w-48 bg-white border border-gray-200 rounded-xl shadow-lg py-1 z-40">
            <button
              onClick={handleLogout}
              className="w-full text-left px-4 py-2 flex items-center gap-2 text-red-600 hover:bg-red-50 transition-colors"
            >
              <LogOut className="w-4 h-4" />
              <span className="text-sm font-semibold">Sign Out</span>
            </button>
          </div>
        )}
      </div>
      </div>
    </header>
  )
}
