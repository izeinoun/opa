import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ShieldCheck, CheckCircle, XCircle, ExternalLink, Inbox, Clock } from 'lucide-react'
import api from '../services/api'
import { useCurrentUser } from '../hooks/useCurrentUser'
import { formatCurrency } from '../utils/formatUtils'
import { formatRelative } from '../utils/dateUtils'

interface PendingApproval {
  case_id: string
  case_sequence: number
  case_number: string
  lob: string
  at_risk_amount: number
  submitted_by: string | null
  submitted_by_full_name: string | null
  submitted_at: string | null
  disposition: string | null
  reason: string | null
  recovered_amount: number | null
  case_assignee_full_name: string | null
}

const DISPOSITION_LABEL: Record<string, string> = {
  closed_recovered: 'Recovered',
  closed_written_off: 'Written off',
  closed_overturned: 'Overturned',
  closed_no_overpayment: 'No overpayment',
}

const LOB_COLOR: Record<string, string> = {
  MA:       'bg-blue-100 text-blue-700',
  PPO:      'bg-purple-100 text-purple-700',
  Medicaid: 'bg-green-100 text-green-700',
}

export default function ApprovalsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { currentUser } = useCurrentUser()
  const [activeModal, setActiveModal] = useState<{ caseSeq: number; mode: 'approve' | 'reject' } | null>(null)

  const isSupervisor = currentUser?.role === 'supervisor' || currentUser?.role === 'admin'

  const { data: items = [], isLoading, error } = useQuery<PendingApproval[]>({
    queryKey: ['supervisor-approvals'],
    queryFn: async () => (await api.get<PendingApproval[]>('/supervisor/approvals')).data,
    enabled: isSupervisor,
  })

  if (!isSupervisor) {
    return (
      <div className="max-w-3xl">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Approvals</h1>
        <div className="bg-white border border-gray-200 rounded-xl p-8 text-center">
          <ShieldCheck className="w-10 h-10 text-gray-300 mx-auto mb-2" />
          <p className="text-sm font-semibold text-gray-700">Supervisor access required</p>
          <p className="text-xs text-gray-500 mt-1">
            This page lists case closures awaiting supervisor review. Switch to a supervisor user to view it.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-5xl">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Approvals Needed</h1>
          <p className="text-sm text-gray-500 mt-1">
            Cases over $2,000 awaiting your review before closure.
          </p>
        </div>
        {!isLoading && (
          <span className="bg-amber-100 text-amber-800 text-sm font-semibold px-3 py-1 rounded-full">
            {items.length} pending
          </span>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-32 bg-gray-100 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-600">Failed to load approvals.</p>
      ) : items.length === 0 ? (
        <div className="bg-white border border-gray-200 rounded-xl p-10 text-center">
          <Inbox className="w-10 h-10 text-gray-300 mx-auto mb-2" />
          <p className="text-sm font-semibold text-gray-700">All caught up</p>
          <p className="text-xs text-gray-500 mt-1">No cases are currently waiting for approval.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((a) => (
            <div key={a.case_id} className="bg-white border border-gray-200 rounded-xl p-4 hover:border-gray-300 transition-colors">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1.5">
                    <button
                      onClick={() => navigate(`/cases/${a.case_sequence}`)}
                      className="text-sm font-mono font-bold text-gray-900 hover:text-indigo-600 inline-flex items-center gap-1"
                    >
                      {a.case_number} <ExternalLink className="w-3 h-3" />
                    </button>
                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${LOB_COLOR[a.lob] ?? 'bg-gray-100 text-gray-600'}`}>
                      {a.lob}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                    <Field label="At risk" value={formatCurrency(a.at_risk_amount)} mono />
                    <Field
                      label="Requested disposition"
                      value={a.disposition ? (DISPOSITION_LABEL[a.disposition] ?? a.disposition) : '—'}
                    />
                    <Field
                      label="Recovered amount"
                      value={a.recovered_amount != null ? formatCurrency(a.recovered_amount) : '—'}
                      mono={a.recovered_amount != null}
                    />
                    <Field
                      label="Submitted by"
                      value={a.submitted_by_full_name ?? a.case_assignee_full_name ?? '—'}
                    />
                  </div>

                  {a.reason && (
                    <div className="bg-gray-50 border border-gray-100 rounded p-2 mb-2">
                      <p className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider mb-0.5">Analyst's reason</p>
                      <p className="text-sm text-gray-800 italic">"{a.reason}"</p>
                    </div>
                  )}

                  {a.submitted_at && (
                    <p className="text-xs text-gray-400 inline-flex items-center gap-1">
                      <Clock className="w-3 h-3" /> submitted {formatRelative(a.submitted_at)}
                    </p>
                  )}
                </div>

                <div className="flex flex-col gap-2 flex-shrink-0">
                  <button
                    onClick={() => setActiveModal({ caseSeq: a.case_sequence, mode: 'approve' })}
                    className="inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-semibold bg-green-600 hover:bg-green-700 text-white rounded transition-colors"
                  >
                    <CheckCircle className="w-3.5 h-3.5" /> Approve
                  </button>
                  <button
                    onClick={() => setActiveModal({ caseSeq: a.case_sequence, mode: 'reject' })}
                    className="inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-semibold bg-white hover:bg-red-50 text-red-700 border border-red-200 rounded transition-colors"
                  >
                    <XCircle className="w-3.5 h-3.5" /> Reject
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {activeModal && (
        <InlineDecisionModal
          caseSeq={activeModal.caseSeq}
          mode={activeModal.mode}
          onClose={() => setActiveModal(null)}
          onDone={() => {
            queryClient.invalidateQueries({ queryKey: ['supervisor-approvals'] })
            queryClient.invalidateQueries({ queryKey: ['notif-count'] })
            setActiveModal(null)
          }}
        />
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

function InlineDecisionModal({
  caseSeq, mode, onClose, onDone,
}: { caseSeq: number; mode: 'approve' | 'reject'; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState('')
  const isReject = mode === 'reject'

  const mut = useMutation({
    mutationFn: async () => {
      const path = isReject ? 'reject' : 'approve'
      const body: any = {}
      if (reason.trim()) body.reason = reason.trim()
      return api.post(`/cases/${caseSeq}/${path}`, body)
    },
    onSuccess: onDone,
  })

  const canSubmit = !isReject || reason.trim().length > 0

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-5" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-base font-bold text-gray-900 mb-3 flex items-center gap-2">
          {isReject ? <XCircle className="w-5 h-5 text-red-600" /> : <CheckCircle className="w-5 h-5 text-green-600" />}
          {isReject ? 'Reject closure' : 'Approve closure'}
        </h3>
        <label className="text-xs font-semibold text-gray-600 block mb-1">
          {isReject ? 'Reason' : 'Comment'} {isReject && <span className="text-red-600">(required)</span>}
        </label>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={3}
          placeholder={isReject ? 'Explain what needs to be revisited…' : 'Optional…'}
          className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-100 resize-none mb-3"
        />
        {mut.isError && (
          <p className="text-xs text-red-600 mb-2">
            {(mut.error as any)?.response?.data?.detail ?? 'Failed to submit'}
          </p>
        )}
        <div className="flex gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50">
            Cancel
          </button>
          <button
            onClick={() => mut.mutate()}
            disabled={!canSubmit || mut.isPending}
            className={`flex-1 px-4 py-2 text-sm font-semibold text-white rounded-lg disabled:bg-gray-200 disabled:text-gray-400 ${
              isReject ? 'bg-red-600 hover:bg-red-700' : 'bg-green-600 hover:bg-green-700'
            }`}
          >
            {mut.isPending ? '...' : isReject ? 'Reject' : 'Approve'}
          </button>
        </div>
      </div>
    </div>
  )
}
