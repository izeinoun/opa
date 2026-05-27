import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ExternalLink, Clock, Inbox, CheckCheck } from 'lucide-react'
import api from '../services/api'
import { useCurrentUser } from '../hooks/useCurrentUser'
import { formatCurrency } from '../utils/formatUtils'
import { formatRelative } from '../utils/dateUtils'

interface ActiveEscalation {
  case_id: string
  case_sequence: number
  case_number: string
  case_status: string
  case_priority: string
  lob: string
  at_risk_amount: number
  case_assignee_full_name: string | null
  escalated_by_full_name: string | null
  escalated_at: string
  reason: string | null
}

const LOB_COLOR: Record<string, string> = {
  MA:       'bg-blue-100 text-blue-700',
  PPO:      'bg-purple-100 text-purple-700',
  Medicaid: 'bg-green-100 text-green-700',
}

const PRIORITY_PILL: Record<string, string> = {
  HIGH:   'bg-red-100 text-red-700',
  MEDIUM: 'bg-yellow-100 text-yellow-700',
  LOW:    'bg-green-100 text-green-700',
}

export default function EscalationsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { currentUser } = useCurrentUser()
  const isSupervisor = currentUser?.role === 'supervisor' || currentUser?.role === 'admin'

  const { data: items = [], isLoading } = useQuery<ActiveEscalation[]>({
    queryKey: ['supervisor-escalations'],
    queryFn: async () => (await api.get<ActiveEscalation[]>('/supervisor/escalations')).data,
    enabled: isSupervisor,
  })

  const resolveMut = useMutation({
    mutationFn: async (caseSeq: number) =>
      api.post(`/cases/${caseSeq}/escalate/resolve`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['supervisor-escalations'] })
      queryClient.invalidateQueries({ queryKey: ['notif-count'] })
    },
  })

  if (!isSupervisor) {
    return (
      <div className="max-w-3xl">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Escalations</h1>
        <div className="bg-white border border-gray-200 rounded-xl p-8 text-center">
          <AlertTriangle className="w-10 h-10 text-gray-300 mx-auto mb-2" />
          <p className="text-sm font-semibold text-gray-700">Supervisor access required</p>
          <p className="text-xs text-gray-500 mt-1">
            This page lists cases analysts have escalated for supervisor review.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-5xl">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Escalations</h1>
          <p className="text-sm text-gray-500 mt-1">
            Cases analysts have flagged for supervisor review. The case state isn't changed —
            the analyst keeps working it; you decide if intervention is needed.
          </p>
        </div>
        {!isLoading && (
          <span className="bg-orange-500 text-white text-sm font-semibold px-3 py-1 rounded-full">
            {items.length} active
          </span>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[...Array(2)].map((_, i) => (
            <div key={i} className="h-32 bg-gray-100 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="bg-white border border-gray-200 rounded-xl p-10 text-center">
          <Inbox className="w-10 h-10 text-gray-300 mx-auto mb-2" />
          <p className="text-sm font-semibold text-gray-700">No active escalations</p>
          <p className="text-xs text-gray-500 mt-1">When an analyst escalates a case it'll appear here.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((e) => (
            <div key={e.case_id} className="bg-white border-l-4 border-orange-500 border-y border-r border-y-gray-200 border-r-gray-200 rounded-xl p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                    <button
                      onClick={() => navigate(`/cases/${e.case_sequence}`)}
                      className="text-sm font-mono font-bold text-gray-900 hover:text-orange-600 inline-flex items-center gap-1"
                    >
                      {e.case_number} <ExternalLink className="w-3 h-3" />
                    </button>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${PRIORITY_PILL[e.case_priority] ?? 'bg-gray-100 text-gray-600'}`}>
                      {e.case_priority}
                    </span>
                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${LOB_COLOR[e.lob] ?? 'bg-gray-100 text-gray-600'}`}>
                      {e.lob}
                    </span>
                    <span className="text-[11px] text-gray-500 font-medium">
                      {e.case_status.replace(/_/g, ' ')}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                    <Field label="At risk" value={formatCurrency(e.at_risk_amount)} mono />
                    <Field label="Case owner" value={e.case_assignee_full_name ?? '—'} />
                    <Field label="Escalated by" value={e.escalated_by_full_name ?? '—'} />
                    <Field label="Escalated" value={formatRelative(e.escalated_at)} />
                  </div>

                  {e.reason && (
                    <div className="bg-orange-50 border border-orange-100 rounded p-2.5 mb-2">
                      <p className="text-[11px] font-semibold text-orange-700 uppercase tracking-wider mb-0.5 inline-flex items-center gap-1">
                        <AlertTriangle className="w-3 h-3" /> Reason
                      </p>
                      <p className="text-sm text-gray-800 italic">"{e.reason}"</p>
                    </div>
                  )}

                  <p className="text-xs text-gray-400 inline-flex items-center gap-1">
                    <Clock className="w-3 h-3" /> {e.escalated_at.slice(0, 19).replace('T', ' ')}
                  </p>
                </div>

                <div className="flex flex-col gap-2 flex-shrink-0">
                  <button
                    onClick={() => navigate(`/cases/${e.case_sequence}`)}
                    className="inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-semibold bg-orange-600 hover:bg-orange-700 text-white rounded transition-colors"
                  >
                    Open case
                  </button>
                  <button
                    onClick={() => resolveMut.mutate(e.case_sequence)}
                    disabled={resolveMut.isPending && resolveMut.variables === e.case_sequence}
                    className="inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-semibold bg-white hover:bg-gray-50 text-gray-700 border border-gray-200 rounded transition-colors disabled:opacity-50"
                  >
                    <CheckCheck className="w-3.5 h-3.5" />
                    {resolveMut.isPending && resolveMut.variables === e.case_sequence ? 'Resolving…' : 'Mark resolved'}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function Field({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div>
      <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">{label}</p>
      <p className={`text-sm text-gray-900 ${mono ? 'font-mono font-semibold' : ''}`}>{value}</p>
    </div>
  )
}
