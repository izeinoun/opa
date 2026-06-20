import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { DollarSign, Plus, CheckCircle2 } from 'lucide-react'
import api from '../../services/api'
import { formatCurrency } from '../../utils/formatUtils'
import { formatDate } from '../../utils/dateUtils'
import RecordRecoveryModal from './RecordRecoveryModal'

interface Recoupment {
  id: string
  amount: number
  method: string
  reference_number?: string | null
  notes?: string | null
  recorded_by_full_name?: string | null
  recorded_at: string
}

const METHOD_LABEL: Record<string, string> = {
  check: 'Check', eft: 'EFT', adjustment: 'Adjustment',
  credit_balance: 'Credit balance', other: 'Other',
}

interface Props {
  caseSeq: number
  caseStatus: string
  caseAtRisk: number
}

const ALLOWED_FROM = new Set(['notice_sent', 'provider_responded', 'reconciling'])

export default function RecoupmentsPanel({ caseSeq, caseStatus, caseAtRisk }: Props) {
  const qc = useQueryClient()
  const [showModal, setShowModal] = useState(false)
  const canRecord = ALLOWED_FROM.has(caseStatus)
  // A reconciling case can be finalized as recovered once the analyst is
  // satisfied (e.g. a negotiated partial); a full recovery auto-closes already.
  const canFinalize = caseStatus === 'reconciling'

  const finalizeMut = useMutation({
    mutationFn: async () =>
      (await api.post(`/cases/${caseSeq}/transition`, {
        to_status: 'closed_recovered',
        reason: 'Recovery reconciled',
      })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['case', caseSeq] })
      qc.invalidateQueries({ queryKey: ['recoupments', caseSeq] })
    },
  })

  const { data: items = [], isLoading } = useQuery<Recoupment[]>({
    queryKey: ['recoupments', caseSeq],
    queryFn: async () => (await api.get<Recoupment[]>(`/cases/${caseSeq}/recoupments`)).data,
  })

  const totalRecovered = items.reduce((sum, r) => sum + (r.amount || 0), 0)

  // Don't render the panel at all if the case never reached notice_sent and no recoupments exist
  if (!canRecord && items.length === 0) return null

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <DollarSign className="w-4 h-4 text-green-600" />
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Recoveries</h3>
          {items.length > 0 && (
            <span className="text-xs text-gray-400">
              {items.length} · total {formatCurrency(totalRecovered)}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {canFinalize && (
            <button
              onClick={() => finalizeMut.mutate()}
              disabled={finalizeMut.isPending}
              className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold border border-green-600 text-green-700 hover:bg-green-50 rounded transition-colors disabled:opacity-50"
            >
              <CheckCircle2 className="w-3 h-3" />
              {finalizeMut.isPending ? 'Closing…' : 'Mark reconciled & close'}
            </button>
          )}
          {canRecord && (
            <button
              onClick={() => setShowModal(true)}
              className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold bg-green-600 hover:bg-green-700 text-white rounded transition-colors"
            >
              <Plus className="w-3 h-3" /> Record recovery
            </button>
          )}
        </div>
      </div>

      {isLoading ? (
        <p className="text-xs text-gray-400 italic">Loading…</p>
      ) : items.length === 0 ? (
        <p className="text-xs text-gray-400 italic">No recoveries recorded yet.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((r) => (
            <li key={r.id} className="border border-gray-100 rounded-lg p-2.5">
              <div className="flex items-baseline justify-between gap-2 mb-1">
                <span className="text-sm font-mono font-bold text-green-700">
                  {formatCurrency(r.amount)}
                </span>
                <span className="text-xs text-gray-500">
                  {METHOD_LABEL[r.method] ?? r.method}
                  {r.reference_number && <span className="font-mono ml-1">· {r.reference_number}</span>}
                </span>
              </div>
              <div className="flex items-baseline justify-between gap-2 text-[11px] text-gray-500">
                <span>{r.recorded_by_full_name ?? 'Unknown'} · {formatDate(r.recorded_at)}</span>
              </div>
              {r.notes && (
                <p className="text-xs text-gray-700 mt-1 italic">"{r.notes}"</p>
              )}
            </li>
          ))}
        </ul>
      )}

      {showModal && (
        <RecordRecoveryModal
          caseSeq={caseSeq}
          caseAtRisk={caseAtRisk}
          onClose={() => setShowModal(false)}
        />
      )}
    </div>
  )
}
