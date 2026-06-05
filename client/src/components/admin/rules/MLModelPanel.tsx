import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { RefreshCw } from 'lucide-react'
import api from '../../../services/api'
import { formatDate } from '../../../utils/dateUtils'
import { card } from '../../../utils/designSystem'
import ModelTuningPanel from '../ModelTuningPanel'
import TrainModelPage from '../../../pages/TrainModelPage'

interface MLModelInfo {
  version: string; trained_at: string; accuracy: number
  precision: number; recall: number; f1_score: number
  auc_roc: number; training_samples: number
  feature_importance?: Record<string, number>
}

const FEATURE_LABEL: Record<string, string> = {
  avg_units_per_line: 'Avg units/line', high_value_cpt_ratio: 'High-risk CPT',
  multi_line_claim_ratio: 'Multi-line claims', modifier_usage_rate: 'Modifier usage',
  same_day_multi_cpt_rate: 'Same-day multi-CPT', prior_overpayment_rate: 'Prior overpayment',
  specialty_peer_deviation: 'Peer deviation',
}

export default function MLModelPanel() {
  const qc = useQueryClient()
  const [confirmRetrain, setConfirmRetrain] = useState(false)

  const { data: modelInfo, isLoading } = useQuery<MLModelInfo>({
    queryKey: ['admin', 'model'],
    queryFn: async () => (await api.get<MLModelInfo>('/admin/model')).data,
  })

  const retrainMutation = useMutation({
    mutationFn: async () => (await api.post<MLModelInfo>('/admin/model/retrain')).data,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin', 'model'] }); setConfirmRetrain(false) },
  })

  return (
    <div className="space-y-4">
      {isLoading ? (
        <div className="h-56 bg-white rounded-xl border border-gray-200 animate-pulse" />
      ) : modelInfo ? (
        <div className={card}>
          <div className="flex items-start justify-between mb-5">
            <div>
              <h2 className="text-lg font-bold text-gray-900">Model v{modelInfo.version}</h2>
              <p className="text-sm text-gray-500 mt-0.5">
                Trained {formatDate(modelInfo.trained_at)} · {modelInfo.training_samples.toLocaleString()} samples
              </p>
            </div>
            <button onClick={() => setConfirmRetrain(true)}
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-[#FE017D] text-white text-sm rounded-lg hover:bg-[#e5006f] transition-colors">
              <RefreshCw className="w-3.5 h-3.5" /> Retrain
            </button>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            {([
              ['Accuracy', modelInfo.accuracy], ['Precision', modelInfo.precision],
              ['Recall', modelInfo.recall], ['F1 Score', modelInfo.f1_score], ['AUC-ROC', modelInfo.auc_roc],
            ] as [string, number][]).map(([label, val]) => (
              <div key={label} className="bg-gray-50 rounded-xl p-4 text-center">
                <p className="text-xs text-gray-400 uppercase tracking-wider mb-1">{label}</p>
                <p className="text-2xl font-bold text-gray-900">{(val * 100).toFixed(1)}%</p>
                <div className="mt-2.5 w-full bg-gray-200 rounded-full h-1.5">
                  <div className="h-1.5 rounded-full bg-[#FE017D]" style={{ width: `${val * 100}%` }} />
                </div>
              </div>
            ))}
          </div>

          {modelInfo.feature_importance && Object.keys(modelInfo.feature_importance).length > 0 && (() => {
            const entries = Object.entries(modelInfo.feature_importance)
            const sum = entries.reduce((a, [, v]) => a + v, 0) || 1
            const max = Math.max(...entries.map(([, v]) => v))
            const sorted = [...entries].sort(([, a], [, b]) => b - a)
            return (
              <div className="mt-6 pt-5 border-t border-gray-100">
                <h3 className="text-sm font-bold text-gray-900 mb-3">Feature importances</h3>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                  {sorted.map(([feat, val]) => {
                    const pct = (val / sum) * 100
                    const barPct = max > 0 ? (val / max) * 100 : 0
                    return (
                      <div key={feat} className="bg-gray-50 rounded-xl p-4 text-center">
                        <p className="text-xs text-gray-400 uppercase tracking-wider mb-1 truncate">
                          {FEATURE_LABEL[feat] ?? feat}
                        </p>
                        <p className="text-lg font-bold text-gray-900">{pct.toFixed(1)}%</p>
                        <div className="mt-2.5 w-full bg-gray-200 rounded-full h-1.5">
                          <div className="h-1.5 rounded-full bg-[#FE017D]" style={{ width: `${barPct}%` }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          })()}
        </div>
      ) : (
        <p className="text-sm text-gray-400">Model info not available.</p>
      )}

      {confirmRetrain && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-sm w-full p-6">
            <h3 className="font-semibold text-gray-900 mb-2">Retrain Model?</h3>
            <p className="text-sm text-gray-500 mb-5">This will trigger a new training job. May take several minutes.</p>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setConfirmRetrain(false)} className="px-4 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50">Cancel</button>
              <button onClick={() => retrainMutation.mutate()} disabled={retrainMutation.isPending}
                className="px-4 py-2 text-sm bg-[#FE017D] text-white rounded-lg hover:bg-[#e5006f] disabled:opacity-60">
                {retrainMutation.isPending ? 'Retraining…' : 'Start Retraining'}
              </button>
            </div>
          </div>
        </div>
      )}

      <ModelTuningPanel />
      <div className="pt-2"><TrainModelPage /></div>
    </div>
  )
}
