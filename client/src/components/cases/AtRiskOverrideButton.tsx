import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Pencil, X } from 'lucide-react'
import api from '../../services/api'
import { formatCurrency } from '../../utils/formatUtils'

interface Props {
  caseSeq: number
  currentAmount: number
}

export default function AtRiskOverrideButton({ caseSeq, currentAmount }: Props) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [amount, setAmount] = useState(currentAmount.toFixed(2))
  const [reason, setReason] = useState('')

  const mut = useMutation({
    mutationFn: async () =>
      api.patch(`/cases/${caseSeq}/override-amount`, {
        amount: parseFloat(amount),
        reason: reason.trim(),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['case', caseSeq] })
      setOpen(false)
      setReason('')
    },
  })

  const parsed = parseFloat(amount)
  const valid = !isNaN(parsed) && parsed >= 0 && reason.trim().length > 0

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        title="Override at-risk amount (supervisor)"
        className="ml-1.5 text-gray-300 hover:text-indigo-600 transition-colors"
        aria-label="Override at-risk amount"
      >
        <Pencil className="w-3 h-3" />
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40" onClick={() => setOpen(false)}>
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-5" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-base font-bold text-gray-900">Override at-risk amount</h3>
              <button onClick={() => setOpen(false)} className="text-gray-400 hover:text-gray-600">
                <X className="w-4 h-4" />
              </button>
            </div>
            <p className="text-xs text-gray-500 mb-3">
              Manual supervisor override. Does not touch individual finding dispositions —
              the audit log will show old → new with your reason.
            </p>

            <p className="text-xs text-gray-700 mb-3 bg-gray-50 border border-gray-200 rounded px-2 py-1">
              Current: <span className="font-mono font-semibold">{formatCurrency(currentAmount)}</span>
            </p>

            <label className="text-xs font-semibold text-gray-600 block mb-1">New amount</label>
            <div className="relative mb-3">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
              <input type="number" step="0.01" min="0" value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="w-full pl-7 pr-3 py-2 text-sm border border-gray-200 rounded-lg font-mono focus:outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-100"
              />
            </div>

            <label className="text-xs font-semibold text-gray-600 block mb-1">
              Reason <span className="text-red-600">(required)</span>
            </label>
            <textarea value={reason} onChange={(e) => setReason(e.target.value)}
              rows={3} placeholder="Explain the override for the audit log…"
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg resize-none focus:outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-100 mb-3"
            />

            {mut.isError && (
              <p className="text-xs text-red-600 mb-2">
                {(mut.error as any)?.response?.data?.detail ?? 'Failed'}
              </p>
            )}

            <div className="flex gap-2">
              <button onClick={() => setOpen(false)} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50">
                Cancel
              </button>
              <button onClick={() => mut.mutate()} disabled={!valid || mut.isPending}
                className="flex-1 px-4 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg disabled:bg-gray-200 disabled:text-gray-400">
                {mut.isPending ? 'Saving…' : 'Save override'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
