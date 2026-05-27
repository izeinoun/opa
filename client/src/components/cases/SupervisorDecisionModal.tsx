import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { X, CheckCircle, XCircle } from 'lucide-react'
import api from '../../services/api'
import { formatCurrency } from '../../utils/formatUtils'
import type { CaseDetail } from '../../types'

interface Props {
  case_: CaseDetail
  mode: 'approve' | 'reject'
  onClose: () => void
}

const DISPOSITION_LABELS: Record<string, string> = {
  closed_recovered: 'Recovered',
  closed_written_off: 'Written off',
  closed_overturned: 'Overturned',
  closed_no_overpayment: 'No overpayment',
}

export default function SupervisorDecisionModal({ case_, mode, onClose }: Props) {
  const queryClient = useQueryClient()
  const [reason, setReason] = useState('')

  const isReject = mode === 'reject'
  const reasonRequired = isReject
  const canSubmit = !reasonRequired || reason.trim().length > 0

  const mut = useMutation({
    mutationFn: async () => {
      const path = isReject ? 'reject' : 'approve'
      const body: any = {}
      if (reason.trim()) body.reason = reason.trim()
      const res = await api.post(`/cases/${case_.id}/${path}`, body)
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['case', case_.id] })
      onClose()
    },
  })

  const pending = case_.pending_decision
  const dispLabel = pending ? (DISPOSITION_LABELS[pending.disposition] ?? pending.disposition) : '—'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-5" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            {isReject ? (
              <XCircle className="w-5 h-5 text-red-600" />
            ) : (
              <CheckCircle className="w-5 h-5 text-green-600" />
            )}
            <h3 className="text-base font-bold text-gray-900">
              {isReject ? 'Reject closure' : 'Approve closure'}
            </h3>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Pending decision summary */}
        {pending && (
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 mb-4 text-xs space-y-1">
            <p><span className="text-gray-500">Case:</span> <span className="font-semibold text-gray-900">{case_.case_number}</span></p>
            <p><span className="text-gray-500">At risk:</span> <span className="font-mono font-semibold text-gray-900">{formatCurrency(case_.amount_at_risk)}</span></p>
            <p><span className="text-gray-500">Disposition:</span> <span className="font-semibold text-gray-900">{dispLabel}</span></p>
            {pending.recovered_amount != null && (
              <p><span className="text-gray-500">Recovered:</span> <span className="font-mono font-semibold text-gray-900">{formatCurrency(pending.recovered_amount)}</span></p>
            )}
            {pending.reason && (
              <p className="pt-1 border-t border-gray-200 mt-1.5">
                <span className="text-gray-500">Analyst's reason:</span>
                <br /><span className="text-gray-800 italic">{pending.reason}</span>
              </p>
            )}
          </div>
        )}

        <div className="mb-4">
          <label className="text-xs font-semibold text-gray-600 block mb-1">
            {isReject ? 'Reason for rejection' : 'Comment'} {reasonRequired && <span className="text-red-600">(required)</span>}
          </label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            placeholder={isReject
              ? 'Explain what needs to be revisited. The analyst will see this when the case returns to in_review.'
              : 'Optional comment for the audit log…'
            }
            className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-100 resize-none"
          />
        </div>

        {mut.isError && (
          <p className="text-xs text-red-600 mb-3">
            {(mut.error as any)?.response?.data?.detail ?? 'Failed to submit decision'}
          </p>
        )}

        <div className="flex gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => mut.mutate()}
            disabled={!canSubmit || mut.isPending}
            className={`flex-1 px-4 py-2 text-sm font-semibold text-white rounded-lg transition-colors disabled:bg-gray-200 disabled:text-gray-400 ${
              isReject ? 'bg-red-600 hover:bg-red-700' : 'bg-green-600 hover:bg-green-700'
            }`}
          >
            {mut.isPending
              ? (isReject ? 'Rejecting…' : 'Approving…')
              : (isReject ? 'Reject and return to in-review' : 'Approve closure')}
          </button>
        </div>
      </div>
    </div>
  )
}
