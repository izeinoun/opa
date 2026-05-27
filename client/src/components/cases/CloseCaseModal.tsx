import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { X, AlertCircle, Send } from 'lucide-react'
import api from '../../services/api'
import { formatCurrency } from '../../utils/formatUtils'
import type { CaseDetail } from '../../types'

const SUPERVISOR_THRESHOLD = 2000

type Disposition = 'closed_recovered' | 'closed_written_off' | 'closed_overturned' | 'closed_no_overpayment'

const DISPOSITION_OPTIONS: { value: Disposition; label: string; desc: string }[] = [
  { value: 'closed_recovered',     label: 'Recovered',       desc: 'Provider paid back (record the amount)' },
  { value: 'closed_written_off',   label: 'Written off',     desc: 'Decided not to pursue (small amount, expired, etc.)' },
  { value: 'closed_overturned',    label: 'Overturned',      desc: 'Review found the original finding was wrong' },
  { value: 'closed_no_overpayment', label: 'No overpayment', desc: "Provider successfully disputed; finding withdrawn" },
]

const REQUIRES_REASON: Set<Disposition> = new Set(['closed_overturned', 'closed_no_overpayment'])

interface Props {
  case_: CaseDetail
  onClose: () => void
}

export default function CloseCaseModal({ case_, onClose }: Props) {
  const queryClient = useQueryClient()
  const [disposition, setDisposition] = useState<Disposition>('closed_recovered')
  const [recoveredAmount, setRecoveredAmount] = useState<string>(case_.amount_at_risk.toFixed(2))
  const [reason, setReason] = useState('')
  const [routedToSupervisor, setRoutedToSupervisor] = useState(false)

  const willRouteToSupervisor = case_.amount_at_risk > SUPERVISOR_THRESHOLD
  const reasonRequired = REQUIRES_REASON.has(disposition)
  const reasonMissing = reasonRequired && !reason.trim()
  const recoveredAmountInvalid =
    disposition === 'closed_recovered' &&
    (!recoveredAmount.trim() || isNaN(parseFloat(recoveredAmount)) || parseFloat(recoveredAmount) < 0)

  const canSubmit = !reasonMissing && !recoveredAmountInvalid

  const submitMut = useMutation({
    mutationFn: async () => {
      const body: any = { to_status: disposition }
      if (reason.trim()) body.reason = reason.trim()
      if (disposition === 'closed_recovered') body.recovered_amount = parseFloat(recoveredAmount)
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
            which exceeds the $2,000 threshold. Your closure as{' '}
            <span className="font-semibold">{DISPOSITION_OPTIONS.find((d) => d.value === disposition)?.label}</span>{' '}
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
            Close case {case_.case_number}
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
              $2,000 — closure will be sent to a supervisor for approval before becoming final.
            </p>
          </div>
        )}

        {/* Disposition selector */}
        <div className="space-y-2 mb-4">
          <label className="text-xs font-semibold text-gray-600">Disposition</label>
          {DISPOSITION_OPTIONS.map((opt) => (
            <label
              key={opt.value}
              className={`flex gap-2.5 items-start p-2.5 rounded-lg border cursor-pointer transition-colors ${
                disposition === opt.value
                  ? 'border-indigo-400 bg-indigo-50'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              <input
                type="radio"
                name="disposition"
                value={opt.value}
                checked={disposition === opt.value}
                onChange={() => setDisposition(opt.value)}
                className="mt-0.5"
              />
              <div className="flex-1">
                <p className="text-sm font-semibold text-gray-900">{opt.label}</p>
                <p className="text-xs text-gray-500 mt-0.5">{opt.desc}</p>
              </div>
            </label>
          ))}
        </div>

        {/* Recovered amount (only when recovered) */}
        {disposition === 'closed_recovered' && (
          <div className="mb-4">
            <label className="text-xs font-semibold text-gray-600 block mb-1">
              Recovered amount
            </label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
              <input
                type="number"
                step="0.01"
                min="0"
                value={recoveredAmount}
                onChange={(e) => setRecoveredAmount(e.target.value)}
                className="w-full pl-7 pr-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-100 font-mono"
              />
            </div>
            <p className="text-[11px] text-gray-400 mt-1">
              At-risk: {formatCurrency(case_.amount_at_risk)}. Partial recovery is allowed.
            </p>
          </div>
        )}

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
              ? 'Explain why this case is being closed without a recovery…'
              : 'Optional context for the audit log…'
            }
            className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-100 resize-none"
          />
        </div>

        {submitMut.isError && (
          <p className="text-xs text-red-600 mb-3">
            {(submitMut.error as any)?.response?.data?.detail ?? 'Failed to close case'}
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
              : willRouteToSupervisor ? 'Submit for approval' : 'Close case'}
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
