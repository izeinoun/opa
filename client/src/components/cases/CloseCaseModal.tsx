import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { X, AlertCircle, Send } from 'lucide-react'
import api from '../../services/api'
import { formatCurrency } from '../../utils/formatUtils'
import type { CaseDetail } from '../../types'

const SUPERVISOR_THRESHOLD = 2000

// Two terminal outcomes:
//   notice_sent           → recoup it: generate the recoupment letter + send it.
//   closed_not_for_recoup → close without pursuing recovery.
type Outcome = 'notice_sent' | 'closed_not_for_recoup'

const OUTCOME_OPTIONS: { value: Outcome; label: string; desc: string }[] = [
  {
    value: 'notice_sent',
    label: 'Recoup it',
    desc: 'Generate the recoupment letter and send it to the provider. The case moves to Notice Sent.',
  },
  {
    value: 'closed_not_for_recoup',
    label: 'Not for recoup',
    desc: 'Close the case without pursuing recovery (no overpayment, dispute upheld, not collectable, etc.).',
  },
]

const REQUIRES_REASON: Set<Outcome> = new Set(['closed_not_for_recoup'])

interface Props {
  case_: CaseDetail
  onClose: () => void
}

export default function CloseCaseModal({ case_, onClose }: Props) {
  const queryClient = useQueryClient()
  // Pre-select the engine's suggested outcome (Phase-1 automation hint).
  const suggested = (case_ as any).suggested_decision
  const [outcome, setOutcome] = useState<Outcome>(
    suggested?.recommendation === 'not_for_recoup' ? 'closed_not_for_recoup' : 'notice_sent',
  )
  const [reason, setReason] = useState('')
  const [routedToSupervisor, setRoutedToSupervisor] = useState(false)

  const willRouteToSupervisor = case_.amount_at_risk > SUPERVISOR_THRESHOLD
  const reasonRequired = REQUIRES_REASON.has(outcome)
  const reasonMissing = reasonRequired && !reason.trim()
  const canSubmit = !reasonMissing

  const submitMut = useMutation({
    mutationFn: async () => {
      const body: any = { to_status: outcome }
      if (reason.trim()) body.reason = reason.trim()
      const res = await api.post(`/cases/${case_.id}/transition`, body)
      return res.data
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['case', case_.id] })
      if (data.status === 'pending_supervisor') {
        setRoutedToSupervisor(true)
      } else {
        onClose()
      }
    },
  })

  const outcomeLabel = OUTCOME_OPTIONS.find((o) => o.value === outcome)?.label ?? ''

  if (routedToSupervisor) {
    return (
      <Backdrop onClose={onClose}>
        <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center">
              <AlertCircle className="w-5 h-5 text-amber-600" />
            </div>
            <h3 className="text-base font-bold text-gray-900">Routed to supervisor</h3>
          </div>
          <p className="text-sm text-gray-700 leading-relaxed">
            This case has an at-risk amount of <span className="font-mono font-semibold">{formatCurrency(case_.amount_at_risk)}</span>,
            which exceeds the $2,000 threshold. Your decision to{' '}
            <span className="font-semibold">{outcomeLabel}</span>{' '}
            has been submitted for supervisor approval.
          </p>
          <button
            onClick={onClose}
            className="mt-5 w-full bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold py-2 rounded-lg transition-colors"
          >
            Got it
          </button>
        </div>
      </Backdrop>
    )
  }

  return (
    <Backdrop onClose={onClose}>
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-bold text-gray-900">
            Resolve case {case_.case_number}
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="w-4 h-4" />
          </button>
        </div>

        {willRouteToSupervisor && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-4 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
            <p className="text-xs text-amber-800">
              At-risk amount <span className="font-mono font-semibold">{formatCurrency(case_.amount_at_risk)}</span> exceeds
              $2,000 — this decision will be sent to a supervisor for approval before it takes effect.
            </p>
          </div>
        )}

        {/* Outcome selector */}
        <div className="space-y-2 mb-4">
          <label className="text-xs font-semibold text-gray-600">Is this case good to recoup?</label>
          {OUTCOME_OPTIONS.map((opt) => (
            <label
              key={opt.value}
              className={`flex gap-2.5 items-start p-2.5 rounded-lg border cursor-pointer transition-colors ${
                outcome === opt.value
                  ? 'border-indigo-400 bg-indigo-50'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              <input
                type="radio"
                name="outcome"
                value={opt.value}
                checked={outcome === opt.value}
                onChange={() => setOutcome(opt.value)}
                className="mt-0.5"
              />
              <div className="flex-1">
                <p className="text-sm font-semibold text-gray-900">{opt.label}</p>
                <p className="text-xs text-gray-500 mt-0.5">{opt.desc}</p>
              </div>
            </label>
          ))}
        </div>

        {/* Reason */}
        <div className="mb-4">
          <label className="text-xs font-semibold text-gray-600 block mb-1">
            Reason {reasonRequired && <span className="text-red-600">(required)</span>}
          </label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            placeholder={reasonRequired
              ? 'Explain why this case is not being recouped…'
              : 'Optional context for the audit log…'
            }
            className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-100 resize-none"
          />
        </div>

        {submitMut.isError && (
          <p className="text-xs text-red-600 mb-3">
            {(submitMut.error as any)?.response?.data?.detail ?? 'Failed to resolve case'}
          </p>
        )}

        <div className="flex gap-2 mt-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => submitMut.mutate()}
            disabled={!canSubmit || submitMut.isPending}
            className="flex-1 inline-flex items-center justify-center gap-1.5 px-4 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-200 disabled:text-gray-400 rounded-lg transition-colors"
          >
            <Send className="w-3.5 h-3.5" />
            {submitMut.isPending
              ? 'Submitting…'
              : willRouteToSupervisor
                ? 'Submit for approval'
                : outcome === 'notice_sent'
                  ? 'Recoup & send letter'
                  : 'Close — not for recoup'}
          </button>
        </div>
      </div>
    </Backdrop>
  )
}

function Backdrop({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
      onClick={onClose}
    >
      <div onClick={(e) => e.stopPropagation()} className="contents">
        {children}
      </div>
    </div>
  )
}
