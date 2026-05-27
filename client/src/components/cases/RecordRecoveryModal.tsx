import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { X, DollarSign } from 'lucide-react'
import api from '../../services/api'
import { formatCurrency } from '../../utils/formatUtils'

interface Props {
  caseSeq: number
  caseAtRisk: number
  onClose: () => void
}

const METHOD_OPTIONS = [
  { value: 'check',          label: 'Check' },
  { value: 'eft',            label: 'EFT / wire transfer' },
  { value: 'adjustment',     label: 'Claim adjustment' },
  { value: 'credit_balance', label: 'Credit balance' },
  { value: 'other',          label: 'Other' },
]

export default function RecordRecoveryModal({ caseSeq, caseAtRisk, onClose }: Props) {
  const queryClient = useQueryClient()
  const [amount, setAmount] = useState(caseAtRisk.toFixed(2))
  const [method, setMethod] = useState('check')
  const [refNum, setRefNum] = useState('')
  const [notes, setNotes] = useState('')

  const mut = useMutation({
    mutationFn: async () => api.post(`/cases/${caseSeq}/recoupments`, {
      amount: parseFloat(amount),
      method,
      reference_number: refNum.trim() || null,
      notes: notes.trim() || null,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['case', caseSeq] })
      queryClient.invalidateQueries({ queryKey: ['recoupments', caseSeq] })
      onClose()
    },
  })

  const parsed = parseFloat(amount)
  const valid = !isNaN(parsed) && parsed > 0

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-5" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-bold text-gray-900 inline-flex items-center gap-2">
            <DollarSign className="w-4 h-4 text-green-600" /> Record recovery
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="w-4 h-4" />
          </button>
        </div>

        <p className="text-xs text-gray-500 mb-3">
          Log a payment received from the provider. Moves the case to reconciling.
        </p>

        <label className="text-xs font-semibold text-gray-600 block mb-1">Amount recovered</label>
        <div className="relative mb-3">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
          <input type="number" step="0.01" min="0" value={amount}
            onChange={(e) => setAmount(e.target.value)}
            className="w-full pl-7 pr-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-100 font-mono"
          />
        </div>
        <p className="text-[11px] text-gray-400 mb-3">Case at-risk: {formatCurrency(caseAtRisk)}</p>

        <label className="text-xs font-semibold text-gray-600 block mb-1">Method</label>
        <select value={method} onChange={(e) => setMethod(e.target.value)}
          className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg mb-3 bg-white">
          {METHOD_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>

        <label className="text-xs font-semibold text-gray-600 block mb-1">
          Reference number <span className="text-gray-400 font-normal">(check #, EFT trace, etc.)</span>
        </label>
        <input type="text" value={refNum} onChange={(e) => setRefNum(e.target.value)}
          placeholder="optional"
          className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg mb-3 font-mono"
        />

        <label className="text-xs font-semibold text-gray-600 block mb-1">Notes</label>
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)}
          rows={2} placeholder="optional"
          className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg mb-3 resize-none"
        />

        {mut.isError && (
          <p className="text-xs text-red-600 mb-2">
            {(mut.error as any)?.response?.data?.detail ?? 'Failed to record'}
          </p>
        )}

        <div className="flex gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50">
            Cancel
          </button>
          <button onClick={() => mut.mutate()} disabled={!valid || mut.isPending}
            className="flex-1 px-4 py-2 text-sm font-semibold text-white bg-green-600 hover:bg-green-700 rounded-lg disabled:bg-gray-200 disabled:text-gray-400">
            {mut.isPending ? 'Recording…' : 'Record recovery'}
          </button>
        </div>
      </div>
    </div>
  )
}
