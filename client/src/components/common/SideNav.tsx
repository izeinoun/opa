import { Link, useLocation } from 'react-router-dom'
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
  FileInput,
  FileOutput,
  Send,
  Flag,
} from 'lucide-react'
import api from '../../services/api'
import { getStatusCounts } from '../../services/caseService'
import type { CaseStatus, ReferenceDataFreshness, UserRole } from '../../types'

// Typography + palette mirror ClaimGuard's left nav so the platform reads
// consistently. Accent stays PayGuard pink for the active icon + row tint.
const BRAND    = '#FE017D'   // PayGuard accent — active icon
const BRAND_BG = '#fdf2f8'   // pink-50 — active row background

type LinkSpec = {
  to: string
  label: string
  icon: any
  // When set, this is a lifecycle stage tab on the Worklist (/worklist?stage=…).
  stage?: string
  // Statuses whose live counts sum into this item's badge.
  badgeStatuses?: CaseStatus[]
  // Active when pathname starts with `to` (covers nested routes).
  matchPrefix?: boolean
  supervisorOnly?: boolean
  adminOnly?: boolean
}

type NavSection = { heading?: string; links: LinkSpec[] }

// The nav is organized around the case LIFECYCLE rather than a flat list.
// "Cases" maps each stage to the statuses it rolls up (the badge counts);
// everything that isn't a case queue is pushed into its own section.
const SECTIONS: NavSection[] = [
  { links: [{ to: '/', label: 'Dashboard', icon: LayoutDashboard }] },
  {
    heading: 'Cases',
    links: [
      { to: '/worklist', stage: 'intake',    label: 'Intake',    icon: Inbox,      badgeStatuses: ['new', 'awaiting_837'] },
      { to: '/worklist', stage: 'review',    label: 'Review',    icon: ListChecks, badgeStatuses: ['assigned', 'in_review', 'ready_for_notice'] },
      { to: '/worklist', stage: 'approvals', label: 'Approvals', icon: ShieldCheck, badgeStatuses: ['pending_supervisor'], supervisorOnly: true },
      { to: '/worklist', stage: 'recovery',  label: 'Recovery',  icon: Send,       badgeStatuses: ['notice_sent', 'provider_responded', 'reconciling'] },
      { to: '/closed-cases', label: 'Closed', icon: Archive, matchPrefix: true },
    ],
  },
  {
    heading: 'Smart Views',
    links: [
      { to: '/worklist', stage: 'jeopardy', label: 'Jeopardy / Overdue', icon: AlertTriangle },
      { to: '/escalations', label: 'Escalations', icon: Flag, matchPrefix: true, supervisorOnly: true },
    ],
  },
  {
    heading: 'Insights',
    links: [
      { to: '/provider-risk', label: 'Provider Risk', icon: ShieldAlert, matchPrefix: true, supervisorOnly: true },
      { to: '/assignments',   label: 'Assignments',   icon: UserCog,     matchPrefix: true, supervisorOnly: true },
    ],
  },
  {
    heading: 'Tools',
    links: [
      { to: '/analyze-835',  label: 'Analyze 835',  icon: ScanLine,   matchPrefix: true },
      { to: '/file-intake',  label: 'File Intake',  icon: FileInput,  matchPrefix: true, adminOnly: true },
      { to: '/output-files', label: 'Output Files', icon: FileOutput, matchPrefix: true, adminOnly: true },
    ],
  },
  {
    heading: 'Reference',
    links: [
      { to: '/members',       label: 'Members',       icon: Users, matchPrefix: true },
      { to: '/fee-schedules', label: 'Fee Schedules', icon: Table, matchPrefix: true },
    ],
  },
  { links: [{ to: '/admin', label: 'Admin', icon: Settings, matchPrefix: true, adminOnly: true }] },
]

export default function SideNav() {
  // Read the primary role of the currently-selected user (set by the TopBar
  // user picker into opa_role). Used only to filter which nav links show —
  // this is a UX nicety, not security. Server enforces real access.
  const role = (localStorage.getItem('opa_role') ?? 'analyst') as UserRole
  const { pathname, search } = useLocation()
  const currentStage = new URLSearchParams(search).get('stage') ?? ''

  const { data: freshness = [] } = useQuery<ReferenceDataFreshness[]>({
    queryKey: ['freshness-banner'],
    queryFn: async () => {
      const res = await api.get<ReferenceDataFreshness[]>('/admin/reference-freshness')
      return res.data
    },
    staleTime: 5 * 60 * 1000,
    enabled: role === 'admin',
  })

  // Live per-status counts drive the stage badges — the at-a-glance "where is
  // the work piling up" signal. Org-wide so the nav reads as a pipeline overview.
  const { data: counts = {} } = useQuery<Record<string, number>>({
    queryKey: ['status-counts'],
    queryFn: () => getStatusCounts(),
    staleTime: 30 * 1000,
  })

  const alertCount = freshness.filter((f) => f.status === 'critical' || f.status === 'stale').length

  const visible = (l: LinkSpec) =>
    (!l.supervisorOnly || role === 'supervisor' || role === 'admin') &&
    (!l.adminOnly || role === 'admin')

  const isActive = (l: LinkSpec): boolean => {
    if (l.stage !== undefined) return pathname === '/worklist' && currentStage === l.stage
    if (l.to === '/') return pathname === '/'
    if (l.matchPrefix) return pathname === l.to || pathname.startsWith(l.to + '/')
    return pathname === l.to
  }

  const badgeFor = (l: LinkSpec): number =>
    (l.badgeStatuses ?? []).reduce((sum, s) => sum + (counts[s] ?? 0), 0)

  const href = (l: LinkSpec) => (l.stage ? `/worklist?stage=${l.stage}` : l.to)

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
      <nav className="flex-1 px-3 pt-3 overflow-y-auto">
        {SECTIONS.map((section, si) => {
          const links = section.links.filter(visible)
          if (!links.length) return null
          return (
            <div key={section.heading ?? `sec-${si}`} className={si === 0 ? 'mb-1' : 'mt-4 mb-1'}>
              {section.heading && (
                <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider px-3 mb-1.5">
                  {section.heading}
                </p>
              )}
              <div className="space-y-0.5">
                {links.map((l) => {
                  const active = isActive(l)
                  const badge = badgeFor(l)
                  const Icon = l.icon
                  return (
                    <Link
                      key={l.label}
                      to={href(l)}
                      className={`flex items-center gap-3 px-3 py-2.5 rounded-2xl text-sm transition-colors ${
                        active
                          ? 'text-slate-900 font-medium'
                          : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                      }`}
                      style={active ? { backgroundColor: BRAND_BG } : undefined}
                    >
                      <Icon
                        className="w-[18px] h-[18px] flex-shrink-0"
                        style={{ color: active ? BRAND : '#94a3b8' }}
                      />
                      <span className="flex-1">{l.label}</span>
                      {badge > 0 && (
                        <span
                          className={`min-w-[20px] h-5 px-1.5 rounded-full text-[11px] font-semibold
                                      flex items-center justify-center ${
                            active ? 'bg-[#FE017D] text-white' : 'bg-slate-100 text-slate-500'
                          }`}
                        >
                          {badge}
                        </span>
                      )}
                    </Link>
                  )
                })}
              </div>
            </div>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-slate-100">
        <p className="text-[11px] text-slate-400">PayGuard v0.1.0</p>
      </div>
    </aside>
  )
}
