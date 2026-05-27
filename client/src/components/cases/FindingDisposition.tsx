import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, X, Edit3, RotateCcw, AlertCircle } from 'lucide-react'
import api from '../../services/api'
import { formatCurrency } from '../../utils/formatUtils'
import type { ClaimFinding, DispositionStatus } from '../../types'

interface Props {
  finding: ClaimFinding
  caseId: number
  locked?: boolean    // case is in pending_supervisor — read-only
}

const STATUS_PILL: Record<DispositionStatus, string> = {
  accepted:     'bg-green-100 text-green-700 border-green-200',
  rejected:     'bg-gray-200 text-gray-600 border-gray-300',
  needs_review: 'bg-amber-100 text-amber-800 border-amber-300',
  adjusted:     'bg-blue-100 text-blue-700 border-blue-200',
}

const STATUS_LABEL: Record<DispositionStatus, string> = {
  accepted:     'Accepted',
  rejected:     'Rejected',
  needs_review: 'NEEDS REVIEW',
  adjusted:     'Adjusted',
}

export default function FindingDisposition({ finding, caseId, locked }: Props) {
  const queryClient = useQueryClient()
  const [modal, setModal] = useState<null | 'reject' | 'adjust'>(null)

  const status = (finding.disposition_status ?? null) as DispositionStatus | null
  const needsReview = status === 'needs_review'
  const isFinal = status === 'accepted' || status === 'rejected' || status === 'adjusted'

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['case', caseId] })
  }

  const acceptMut = useMutation({
    mutationFn: async () => (await api.post(`/findings/${finding.id}/accept`, {})).data,
    onSuccess: invalidate,
  })

  return (
    <div className="space-y-2">
      {/* Status row */}
      {status && (
        <div className="flex items-center gap-2 text-xs">
          <span className={`px-2 py-0.5 rounded border font-semibold ${STATUS_PILL[status]}`}>
            {STATUS_LABEL[status]}
          </span>
          {status === 'adjusted' && finding.disposition_adjusted_amount != null && (
            <span className="text-gray-600">
              Adjusted to <span className="font-mono font-semibold">{formatCurrency(finding.disposition_adjusted_amount)}</span>
              {' '}<span className="text-gray-400">(from {formatCurrency(finding.overpayment_amount)})</span>
            </span>
          )}
          {finding.disposition_reason && status !== 'needs_review' && (
            <span className="text-gray-500 italic truncate">"{finding.disposition_reason}"</span>
          )}
        </div>
      )}

      {/* Needs-review prompt */}
      {needsReview && !locked && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
          <div className="flex items-start gap-2 mb-2">
            <AlertCircle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
            <p className="text-xs text-amber-900">
              This finding is from the AI-assisted detector with <span className="font-semibold">medium confidence</span>.
              Accept, reject, or adjust the amount to move this case forward.
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => acceptMut.mutate()}
              disabled={acceptMut.isPending}
              className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold bg-green-600 hover:bg-green-700 text-white rounded transition-colors disabled:opacity-50"
            >
              <Check className="w-3 h-3" /> Accept
            </button>
            <button
              onClick={() => setModal('reject')}
              className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold bg-white hover:bg-red-50 text-red-700 border border-red-200 rounded transition-colors"
            >
              <X className="w-3 h-3" /> Reject
            </button>
            <button
              onClick={() => setModal('adjust')}
              className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold bg-white hover:bg-blue-50 text-blue-700 border border-blue-200 rounded transition-colors"
            >
              <Edit3 className="w-3 h-3" /> Adjust amount
            </button>
          </div>
        </div>
      )}

      {/* Change-disposition link for already-decided findings */}
      {isFinal && !locked && (
        <div className="flex items-center gap-3 text-xs">
          <button
            onClick={() => setModal('reject')}
            className="inline-flex items-center gap-1 text-gray-500 hover:text-red-700 transition-colors"
          >
            <X className="w-3 h-3" /> Reject
          </button>
          <button
            onClick={() => setModal('adjust')}
            className="inline-flex items-center gap-1 text-gray-500 hover:text-blue-700 transition-colors"
          >
            <Edit3 className="w-3 h-3" /> {status === 'adjusted' ? 'Re-adjust' : 'Adjust'}
          </button>
          {status !== 'accepted' && (
            <button
              onClick={() => acceptMut.mutate()}
              disabled={acceptMut.isPending}
              className="inline-flex items-center gap-1 text-gray-500 hover:text-green-700 transition-colors"
            >
              <RotateCcw className="w-3 h-3" /> Reaccept
            </button>
          )}
        </div>
      )}

      {/* Modals */}
      {modal === 'reject' && (
        <ReasonModal
          title="Reject finding"
          subtitle="This finding will be excluded from the case's at-risk total."
          confirmLabel="Reject"
          confirmColor="red"
          finding={finding}
          onSubmit={async (reason) => {
            await api.post(`/findings/${finding.id}/reject`, { reason })
            invalidate()
            setModal(null)
          }}
          onClose={() => setModal(null)}
        />
      )}
      {modal === 'adjust' && (
        <AdjustModal
          finding={finding}
          onSubmit={async (amount, reason) => {
            await api.post(`/findings/${finding.id}/adjust`, { adjusted_amount: amount, reason })
            invalidate()
            setModal(null)
          }}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  )
}

// --- Reject modal (simple required-reason) ---
function ReasonModal({
  title, subtitle, confirmLabel, confirmColor, finding, onSubmit, onClose,
}: {
  title: string; subtitle: string; confirmLabel: string;
  confirmColor: 'red' | 'blue';
  finding: ClaimFinding;
  onSubmit: (reason: string) => Promise<void>;
  onClose: () => void;
}) {
  const [reason, setReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const colors = confirmColor === 'red'
    ? 'bg-red-600 hover:bg-red-700'
    : 'bg-blue-600 hover:bg-blue-700'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-5" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-base font-bold text-gray-900 mb-1">{title}</h3>
        <p className="text-xs text-gray-500 mb-1">{subtitle}</p>
        <p className="text-xs text-gray-700 mb-3 bg-gray-50 border border-gray-200 rounded px-2 py-1">
          {finding.detector_code} — {formatCurrency(finding.overpayment_amount)}
        </p>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={3}
          placeholder="Explain your decision (required)…"
          className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-100 resize-none mb-3"
        />
        {error && <p className="text-xs text-red-600 mb-2">{error}</p>}
        <div className="flex gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50">
            Cancel
          </button>
          <button
            onClick={async () => {
              if (!reason.trim()) return setError('Reason is required')
              setSubmitting(true); setError(null)
              try { await onSubmit(reason.trim()) }
              catch (e: any) { setError(e?.response?.data?.detail ?? 'Failed'); setSubmitting(false) }
            }}
            disabled={submitting || !reason.trim()}
            className={`flex-1 px-4 py-2 text-sm font-semibold text-white rounded-lg ${colors} disabled:bg-gray-200 disabled:text-gray-400`}
          >
            {submitting ? `${confirmLabel}ing…` : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

function AdjustModal({
  finding, onSubmit, onClose,
}: {
  finding: ClaimFinding;
  onSubmit: (amount: number, reason: string) => Promise<void>;
  onClose: () => void;
}) {
  const initial = finding.disposition_adjusted_amount ?? finding.overpayment_amount
  const [amount, setAmount] = useState<string>(initial.toFixed(2))
  const [reason, setReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const parsed = parseFloat(amount)
  const valid = !isNaN(parsed) && parsed >= 0

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-5" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-base font-bold text-gray-900 mb-1">Adjust finding amount</h3>
        <p className="text-xs text-gray-500 mb-3">
          Override the system-calculated overpayment for this finding.
        </p>
        <p className="text-xs text-gray-700 mb-3 bg-gray-50 border border-gray-200 rounded px-2 py-1">
          {finding.detector_code} — system value: {formatCurrency(finding.overpayment_amount)}
        </p>

        <label className="text-xs font-semibold text-gray-600 block mb-1">New amount</label>
        <div className="relative mb-3">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
          <input
            type="number" step="0.01" min="0"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            className="w-full pl-7 pr-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-100 font-mono"
          />
        </div>

        <label className="text-xs font-semibold text-gray-600 block mb-1">
          Reason <span className="text-red-600">(required)</span>
        </label>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={3}
          placeholder="Explain why the amount is being adjusted…"
          className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-100 resize-none mb-3"
        />
        {error && <p className="text-xs text-red-600 mb-2">{error}</p>}
        <div className="flex gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50">
            Cancel
          </button>
          <button
            onClick={async () => {
              if (!valid) return setError('Amount must be a non-negative number')
              if (!reason.trim()) return setError('Reason is required')
              setSubmitting(true); setError(null)
              try { await onSubmit(parsed, reason.trim()) }
              catch (e: any) { setError(e?.response?.data?.detail ?? 'Failed'); setSubmitting(false) }
            }}
            disabled={submitting || !valid || !reason.trim()}
            className="flex-1 px-4 py-2 text-sm font-semibold text-white rounded-lg bg-blue-600 hover:bg-blue-700 disabled:bg-gray-200 disabled:text-gray-400"
          >
            {submitting ? 'Saving…' : 'Save adjustment'}
          </button>
        </div>
      </div>
    </div>
  )
}
