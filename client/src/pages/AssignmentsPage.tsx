import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Users, Inbox, ExternalLink, ChevronDown } from 'lucide-react'
import api from '../services/api'
import { useCurrentUser } from '../hooks/useCurrentUser'
import { formatCurrency } from '../utils/formatUtils'
import type { User } from '../types'

interface AnalystWorkload {
  user_id: string
  full_name: string
  username: string
  role: string
  total_active: number
  new: number
  assigned: number
  in_review: number
  ready_for_notice: number
  pending_supervisor: number
  notice_sent: number
  provider_responded: number
  reconciling: number
}

interface UnassignedCase {
  case_id: string
  case_sequence: number
  case_number: string
  status: string
  priority: string
  priority_score: number
  at_risk_amount: number
  lob: string
  primary_detector_id: string
  deadline_date?: string | null
}

interface AssignmentsResponse {
  analysts: AnalystWorkload[]
  unassigned: UnassignedCase[]
}

const STATUS_COLS: { key: keyof AnalystWorkload; label: string }[] = [
  { key: 'new',               label: 'New' },
  { key: 'assigned',          label: 'Assigned' },
  { key: 'in_review',         label: 'In Review' },
  { key: 'ready_for_notice',  label: 'Ready' },
  { key: 'pending_supervisor',label: 'Pend. Sup.' },
  { key: 'notice_sent',       label: 'Notice' },
  { key: 'provider_responded',label: 'Responded' },
  { key: 'reconciling',       label: 'Recon.' },
]

const PRIORITY_PILL: Record<string, string> = {
  HIGH:   'bg-red-100 text-red-700',
  MEDIUM: 'bg-yellow-100 text-yellow-700',
  LOW:    'bg-green-100 text-green-700',
}

export default function AssignmentsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { currentUser, users } = useCurrentUser()

  const isSupervisor = currentUser?.role === 'supervisor' || currentUser?.role === 'admin'

  const { data, isLoading } = useQuery<AssignmentsResponse>({
    queryKey: ['supervisor-assignments'],
    queryFn: async () => (await api.get<AssignmentsResponse>('/supervisor/assignments')).data,
    enabled: isSupervisor,
  })

  const assignMut = useMutation({
    mutationFn: async ({ caseSeq, analyst_id }: { caseSeq: number; analyst_id: string }) =>
      api.patch(`/cases/${caseSeq}/assign`, { analyst_id }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['supervisor-assignments'] })
      queryClient.invalidateQueries({ queryKey: ['notif-count'] })
    },
  })

  if (!isSupervisor) {
    return (
      <div className="max-w-3xl">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Assignments</h1>
        <div className="bg-white border border-gray-200 rounded-xl p-8 text-center">
          <Users className="w-10 h-10 text-gray-300 mx-auto mb-2" />
          <p className="text-sm font-semibold text-gray-700">Supervisor access required</p>
          <p className="text-xs text-gray-500 mt-1">
            This page is for supervisors to manage analyst workload and the unassigned pool.
          </p>
        </div>
      </div>
    )
  }

  const analysts = users.filter((u) => u.role === 'analyst' && u.is_active)

  return (
    <div className="max-w-7xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Assignments</h1>
        <p className="text-sm text-gray-500 mt-1">
          Pick up unassigned cases and balance analyst workload.
        </p>
      </div>

      {/* Unassigned pool */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <Inbox className="w-4 h-4 text-amber-600" />
          <h2 className="text-sm font-bold text-gray-900 uppercase tracking-wider">Unassigned pool</h2>
          {data && (
            <span className="text-xs text-gray-500">{data.unassigned.length} case{data.unassigned.length === 1 ? '' : 's'}</span>
          )}
        </div>
        {isLoading ? (
          <div className="h-32 bg-gray-100 rounded-xl animate-pulse" />
        ) : !data?.unassigned.length ? (
          <p className="text-sm text-gray-400 italic px-4 py-6 bg-white border border-gray-200 rounded-xl">
            No unassigned cases. 🎉
          </p>
        ) : (
          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <table className="min-w-full">
              <thead className="bg-gray-50">
                <tr>
                  {['Case #', 'Priority', 'At Risk', 'LOB', 'Status', 'Assign to'].map((h) => (
                    <th key={h} className="px-4 py-2.5 text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data.unassigned.map((c) => (
                  <tr key={c.case_id} className="hover:bg-gray-50">
                    <td className="px-4 py-2.5">
                      <button
                        onClick={() => navigate(`/cases/${c.case_sequence}`)}
                        className="text-sm font-mono font-semibold text-gray-900 hover:text-indigo-600 inline-flex items-center gap-1"
                      >
                        {c.case_number} <ExternalLink className="w-3 h-3" />
                      </button>
                    </td>
                    <td className="px-4 py-2.5">
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${PRIORITY_PILL[c.priority] ?? 'bg-gray-100 text-gray-600'}`}>
                        {c.priority} {c.priority_score.toFixed(0)}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-sm font-mono text-gray-900">{formatCurrency(c.at_risk_amount)}</td>
                    <td className="px-4 py-2.5 text-xs text-gray-600">{c.lob}</td>
                    <td className="px-4 py-2.5 text-xs text-gray-600">{c.status.replace(/_/g, ' ')}</td>
                    <td className="px-4 py-2.5">
                      <AssignPicker
                        analysts={analysts}
                        onPick={(u) => assignMut.mutate({ caseSeq: c.case_sequence, analyst_id: u.id })}
                        loading={assignMut.isPending && assignMut.variables?.caseSeq === c.case_sequence}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Workload by analyst */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <Users className="w-4 h-4 text-indigo-600" />
          <h2 className="text-sm font-bold text-gray-900 uppercase tracking-wider">Workload by analyst</h2>
        </div>
        {isLoading ? (
          <div className="h-48 bg-gray-100 rounded-xl animate-pulse" />
        ) : (
          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <table className="min-w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-2.5 text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider">Analyst</th>
                  <th className="px-4 py-2.5 text-right text-[11px] font-semibold text-gray-500 uppercase tracking-wider">Total</th>
                  {STATUS_COLS.map((col) => (
                    <th key={col.key as string} className="px-3 py-2.5 text-right text-[11px] font-semibold text-gray-500 uppercase tracking-wider">{col.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {(data?.analysts ?? []).map((a) => (
                  <tr key={a.user_id} className="hover:bg-gray-50">
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium text-gray-900">{a.full_name}</p>
                        {a.role === 'supervisor' && (
                          <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-purple-100 text-purple-700">sup</span>
                        )}
                      </div>
                      <p className="text-[11px] text-gray-400 font-mono">{a.username}</p>
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <span className={`text-sm font-bold tabular-nums ${a.total_active >= 5 ? 'text-red-600' : a.total_active >= 3 ? 'text-amber-600' : 'text-gray-900'}`}>
                        {a.total_active}
                      </span>
                    </td>
                    {STATUS_COLS.map((col) => {
                      const v = a[col.key] as number
                      return (
                        <td key={col.key as string} className="px-3 py-2.5 text-right text-sm tabular-nums">
                          <span className={v > 0 ? 'text-gray-900' : 'text-gray-300'}>{v}</span>
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}

function AssignPicker({ analysts, onPick, loading }: {
  analysts: User[]; onPick: (u: User) => void; loading: boolean
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className="relative inline-block">
      <button
        onClick={() => setOpen((v) => !v)}
        disabled={loading}
        className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-semibold bg-white text-indigo-700 border border-indigo-200 rounded hover:bg-indigo-50 disabled:opacity-50 transition-colors"
      >
        {loading ? 'Assigning…' : 'Pick analyst…'}
        <ChevronDown className="w-3 h-3" />
      </button>
      {open && (
        <div className="absolute right-0 mt-1 w-56 bg-white border border-gray-200 rounded-lg shadow-lg z-30 max-h-72 overflow-y-auto">
          {analysts.map((u) => (
            <button
              key={u.id}
              onClick={() => { setOpen(false); onPick(u) }}
              className="w-full text-left px-3 py-1.5 text-sm hover:bg-gray-50 text-gray-800"
            >
              {u.full_name}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
