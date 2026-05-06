import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  LayoutDashboard,
  ListChecks,
  Mail,
  Settings,
  Bell,
  ChevronDown,
  Archive,
  ScanLine,
  Users,
} from 'lucide-react'
import api from '../../services/api'
import type { ReferenceDataFreshness, UserRole } from '../../types'

const ROLE_OPTIONS: UserRole[] = ['analyst', 'supervisor', 'admin']

const ROLE_DOT: Record<string, string> = {
  analyst:    'bg-blue-400',
  supervisor: 'bg-purple-400',
  admin:      'bg-[#FE017D]',
  system:     'bg-gray-400',
}

const NAV_LINKS = [
  { to: '/',             label: 'Dashboard',    icon: LayoutDashboard, end: true  },
  { to: '/worklist',     label: 'Worklist',     icon: ListChecks,      end: false },
  { to: '/analyze-835',  label: 'Analyze 835',  icon: ScanLine,        end: false },
  { to: '/members',      label: 'Members',      icon: Users,           end: false },
  { to: '/closed-cases', label: 'Closed Cases', icon: Archive,         end: false },
  { to: '/letters',      label: 'Letters',      icon: Mail,            end: false },
  { to: '/admin',        label: 'Admin',        icon: Settings,        end: false },
]

export default function SideNav() {
  const role = (localStorage.getItem('opa_role') ?? 'analyst') as UserRole
  const [showRoleMenu, setShowRoleMenu] = useState(false)

  const { data: freshness = [] } = useQuery<ReferenceDataFreshness[]>({
    queryKey: ['freshness-banner'],
    queryFn: async () => {
      const res = await api.get<ReferenceDataFreshness[]>('/admin/reference-freshness')
      return res.data
    },
    staleTime: 5 * 60 * 1000,
  })

  const alertCount = freshness.filter((f) => f.status === 'critical' || f.status === 'stale').length

  function handleRoleSwitch(newRole: UserRole) {
    localStorage.setItem('opa_role', newRole)
    setShowRoleMenu(false)
    window.location.reload()
  }

  return (
    <aside className="fixed left-0 top-0 h-screen w-56 bg-white border-r border-gray-100 flex flex-col z-40">
      {/* Header */}
      <div className="px-5 pt-5 pb-4 flex items-center justify-between">
        <p className="text-gray-900 text-xl font-bold tracking-tight">OPA</p>
        <div className="relative">
          <button className="w-8 h-8 rounded-full bg-amber-400 flex items-center justify-center hover:bg-amber-500 transition-colors">
            <Bell className="w-4 h-4 text-white" fill="white" />
          </button>
          {alertCount > 0 && (
            <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] bg-red-500 rounded-full
                             text-white text-[10px] font-bold flex items-center justify-center px-1">
              {alertCount}
            </span>
          )}
        </div>
      </div>

      <div className="mx-5 border-t border-gray-200" />

      {/* Role switcher */}
      <div className="px-4 pt-4 pb-2">
        <div className="relative">
          <button
            onClick={() => setShowRoleMenu((v) => !v)}
            className="w-full flex items-center justify-between px-3 py-2
                       bg-gray-50 hover:bg-gray-100 rounded-xl border border-gray-200
                       transition-colors text-xs text-gray-700"
          >
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${ROLE_DOT[role]}`} />
              <span className="capitalize font-medium">{role}</span>
            </div>
            <ChevronDown className="w-3 h-3 text-gray-400" />
          </button>

          {showRoleMenu && (
            <div className="absolute left-0 right-0 top-10 z-50
                            bg-white border border-gray-200
                            rounded-xl shadow-lg overflow-hidden">
              {ROLE_OPTIONS.map((r) => (
                <button
                  key={r}
                  onClick={() => handleRoleSwitch(r)}
                  className="w-full text-left px-3 py-2.5 text-xs
                             text-gray-700 hover:bg-gray-50
                             flex items-center gap-2 transition-colors"
                >
                  <span className={`w-2 h-2 rounded-full ${ROLE_DOT[r]}`} />
                  <span className="capitalize">{r}</span>
                  {r === role && (
                    <span className="ml-auto text-[#FE017D] font-bold">✓</span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 pt-4">
        <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-widest px-3 mb-3">
          Navigation
        </p>
        <div className="space-y-0.5">
          {NAV_LINKS.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                [
                  'flex items-center gap-3 px-3 py-3 rounded-2xl text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-pink-50 text-[#FE017D] font-semibold'
                    : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700',
                ].join(' ')
              }
            >
              <Icon className="w-[18px] h-[18px] flex-shrink-0" />
              {label}
            </NavLink>
          ))}
        </div>
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-gray-100">
        <p className="text-xs text-gray-400">OPA v0.1.0</p>
      </div>
    </aside>
  )
}
