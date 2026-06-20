import { NavLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  LayoutDashboard,
  ListChecks,
  Settings,
  Archive,
  ScanLine,
  Users,
  Table,
  ShieldCheck,
  UserCog,
  AlertTriangle,
  ShieldAlert,
  Inbox,
  FileOutput,
} from 'lucide-react'
import api from '../../services/api'
import type { ReferenceDataFreshness, UserRole } from '../../types'

// Typography + palette mirror ClaimGuard's left nav so the platform reads
// consistently. Accent stays PayGuard pink for the active icon + row tint.
const BRAND    = '#FE017D'   // PayGuard accent — active icon
const BRAND_BG = '#fdf2f8'   // pink-50 — active row background

type NavLinkSpec = {
  to: string
  label: string
  icon: any
  end: boolean
  supervisorOnly?: boolean
  adminOnly?: boolean
}

const NAV_LINKS: NavLinkSpec[] = [
  { to: '/',             label: 'Dashboard',    icon: LayoutDashboard, end: true  },
  { to: '/worklist',     label: 'Worklist',     icon: ListChecks,      end: false },
  { to: '/approvals',    label: 'Approvals',    icon: ShieldCheck,     end: false, supervisorOnly: true },
  { to: '/escalations',  label: 'Escalations',  icon: AlertTriangle,   end: false, supervisorOnly: true },
  { to: '/assignments',  label: 'Assignments',  icon: UserCog,         end: false, supervisorOnly: true },
  { to: '/provider-risk', label: 'Provider Risk', icon: ShieldAlert,   end: false, supervisorOnly: true },
  { to: '/analyze-835',  label: 'Analyze 835',  icon: ScanLine,        end: false },
  { to: '/file-intake',  label: 'File Intake',  icon: Inbox,           end: false, adminOnly: true },
  { to: '/output-files', label: 'Output Files', icon: FileOutput,      end: false, adminOnly: true },
  { to: '/members',      label: 'Members',      icon: Users,           end: false },
  { to: '/fee-schedules', label: 'Fee Schedules', icon: Table,          end: false },
  { to: '/closed-cases', label: 'Closed Cases',  icon: Archive,         end: false },
  { to: '/admin',        label: 'Admin',        icon: Settings,        end: false, adminOnly: true },
]

export default function SideNav() {
  // Read the primary role of the currently-selected user (set by the TopBar
  // user picker into opa_role). Used only to filter which nav links show —
  // this is a UX nicety, not security. Server enforces real access.
  const role = (localStorage.getItem('opa_role') ?? 'analyst') as UserRole

  const { data: freshness = [] } = useQuery<ReferenceDataFreshness[]>({
    queryKey: ['freshness-banner'],
    queryFn: async () => {
      const res = await api.get<ReferenceDataFreshness[]>('/admin/reference-freshness')
      return res.data
    },
    staleTime: 5 * 60 * 1000,
    enabled: role === 'admin',
  })

  const alertCount = freshness.filter((f) => f.status === 'critical' || f.status === 'stale').length

  return (
    <aside className="fixed left-0 top-0 h-screen w-56 bg-white border-r border-slate-200 flex flex-col z-40">
      {/* Header */}
      <div className="px-5 pt-5 pb-4 flex items-center justify-between">
        <p className="text-slate-900 text-lg font-semibold tracking-tight leading-none">PayGuard</p>
        <div className="relative">
          <button className="w-8 h-8 flex items-center justify-center">
            <img src="/favicon.svg" alt="PayGuard" className="w-7 h-7" />
          </button>
          {alertCount > 0 && (
            <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] bg-red-500 rounded-full
                             text-white text-[10px] font-bold flex items-center justify-center px-1">
              {alertCount}
            </span>
          )}
        </div>
      </div>

      <div className="mx-5 border-t border-slate-100" />

      {/* Navigation */}
      <nav className="flex-1 px-3 pt-4">
        <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider px-3 mb-3">
          Navigation
        </p>
        <div className="space-y-0.5">
          {NAV_LINKS
            .filter((l) => !l.supervisorOnly || role === 'supervisor' || role === 'admin')
            .filter((l) => !l.adminOnly || role === 'admin')
            .map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-3 rounded-2xl text-sm transition-colors ${
                  isActive
                    ? 'text-slate-900 font-medium'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                }`
              }
              style={({ isActive }) =>
                isActive ? { backgroundColor: BRAND_BG } : undefined
              }
            >
              {({ isActive }) => (
                <>
                  <Icon
                    className="w-[18px] h-[18px] flex-shrink-0"
                    style={{ color: isActive ? BRAND : '#94a3b8' }}
                  />
                  {label}
                </>
              )}
            </NavLink>
          ))}
        </div>
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-slate-100">
        <p className="text-[11px] text-slate-400">PayGuard v0.1.0</p>
      </div>
    </aside>
  )
}
