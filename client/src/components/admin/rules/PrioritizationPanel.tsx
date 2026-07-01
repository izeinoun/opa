import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle, RefreshCw, Sliders } from 'lucide-react'
import api from '../../../services/api'
import { formatDate } from '../../../utils/dateUtils'
import { card } from '../../../utils/designSystem'

interface PrioritizationConfig {
  severity_weight: number; urgency_weight: number
  amount_cap: number; rule_leak: number; urgency_window_days: number
  high_threshold: number; medium_threshold: number; updated_at: string
}

export default function PrioritizationPanel() {
  const qc = useQueryClient()
  const [priForm, setPriForm] = useState<PrioritizationConfig | null>(null)
  const [saved, setSaved] = useState(false)
  const [confirmRecompute, setConfirmRecompute] = useState(false)
  const [recomputeResult, setRecomputeResult] = useState<{ updated: number; scanned: number; errors: number } | null>(null)

  const { data: priConfig, isLoading } = useQuery<PrioritizationConfig>({
    queryKey: ['admin', 'prioritization-config'],
    queryFn: async () => (await api.get<PrioritizationConfig>('/admin/prioritization-config')).data,
  })

  const { data: affectedCount } = useQuery<{ open_cases: number }>({
    queryKey: ['admin', 'prioritization-affected'],
    queryFn: async () => (await api.get<{ open_cases: number }>('/admin/prioritization-config/affected-count')).data,
  })

  useEffect(() => { if (priConfig) setPriForm(priConfig) }, [priConfig])

  const saveMutation = useMutation({
    mutationFn: async (cfg: PrioritizationConfig) =>
      (await api.put<PrioritizationConfig>('/admin/prioritization-config', cfg)).data,
    onSuccess: data => {
      qc.invalidateQueries({ queryKey: ['admin', 'prioritization-config'] })
      setPriForm(data); setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    },
  })

  const recomputeMutation = useMutation({
    mutationFn: async () =>
      (await api.post<{ scanned: number; updated: number; errors: number }>('/admin/prioritization-config/recompute')).data,
    onSuccess: data => {
      setRecomputeResult(data); setConfirmRecompute(false)
      qc.invalidateQueries({ queryKey: ['cases'] })
    },
  })

  if (isLoading || !priForm) return <div className="h-72 bg-white rounded-xl border border-gray-200 animate-pulse" />

  const weightSum = +(priForm.severity_weight + priForm.urgency_weight).toFixed(3)
  const weightsValid = Math.abs(weightSum - 1.0) < 0.001
  const thresholdsValid = priForm.high_threshold > priForm.medium_threshold
  const valid = weightsValid && thresholdsValid
  const dirty = priConfig ? JSON.stringify({ ...priForm, updated_at: '' }) !== JSON.stringify({ ...priConfig, updated_at: '' }) : false

  return (
    <div className="space-y-4">
      <div className={card}>
        <div className="flex items-start justify-between mb-1">
          <div>
            <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
              <Sliders className="w-4 h-4" /> Priority Formula
            </h2>
            <p className="text-xs text-gray-400 mt-0.5">Last updated {formatDate(priForm.updated_at)}</p>
          </div>
        </div>

        <p className="text-xs text-gray-500 mt-3 mb-1 leading-relaxed">
          <span className="font-semibold text-gray-700">Option B (EMV).</span> Priority ={' '}
          <span className="font-mono">(w_sev · severity + w_urg · urgency) × 100</span>, where{' '}
          <span className="font-mono">severity = min(Evidence × Amount / cap, 1)</span>. Confidence and
          dollars are multiplied, so a big-dollar low-confidence claim is discounted by its confidence.
        </p>
        <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-4">
          {([['severity_weight', 'Severity weight', 'w_sev'], ['urgency_weight', 'Urgency weight', 'w_urg']] as [keyof PrioritizationConfig, string, string][]).map(([key, label, hint]) => (
            <div key={key}>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                {label} <span className="text-gray-400 font-mono">{hint}</span>
              </label>
              <input type="number" step="0.01" min="0" max="1"
                value={priForm[key] as number}
                onChange={e => setPriForm({ ...priForm, [key]: parseFloat(e.target.value) || 0 })}
                className="w-full px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]"
              />
            </div>
          ))}
        </div>
        <p className={`text-xs mt-2 ${weightsValid ? 'text-gray-400' : 'text-red-600 font-medium'}`}>
          Sum: {weightSum.toFixed(3)} {weightsValid ? '✓' : '— must equal 1.000'}
        </p>

        <div className="mt-5 grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Amount cap ($)</label>
            <input type="number" step={100} min={1}
              value={priForm.amount_cap}
              onChange={e => setPriForm({ ...priForm, amount_cap: parseFloat(e.target.value) || 0 })}
              className="w-full px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Rule leak <span className="text-gray-400 font-mono">L</span>
            </label>
            <input type="number" step={0.01} min={0} max={0.5}
              value={priForm.rule_leak}
              onChange={e => setPriForm({ ...priForm, rule_leak: parseFloat(e.target.value) || 0 })}
              className="w-full px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Urgency window (days)</label>
            <input type="number" step={1} min={1}
              value={priForm.urgency_window_days}
              onChange={e => setPriForm({ ...priForm, urgency_window_days: parseFloat(e.target.value) || 0 })}
              className="w-full px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]"
            />
          </div>
        </div>
        <p className="text-xs text-gray-400 mt-1.5">
          Rule leak = the rule engine's miss rate among clean claims; it sets the Evidence floor
          (a no-findings claim scores E = L). Estimate it by auditing rule-negative claims.
        </p>

        <div className="mt-5 grid grid-cols-2 gap-4">
          {([['high_threshold', 'HIGH threshold'], ['medium_threshold', 'MEDIUM threshold']] as [keyof PrioritizationConfig, string][]).map(([key, label]) => (
            <div key={key}>
              <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
              <input type="number" step="1" min="0" max="100"
                value={priForm[key] as number}
                onChange={e => setPriForm({ ...priForm, [key]: parseFloat(e.target.value) || 0 })}
                className="w-full px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]"
              />
            </div>
          ))}
        </div>
        {!thresholdsValid && <p className="text-xs mt-2 text-red-600 font-medium">HIGH must be greater than MEDIUM.</p>}

        <div className="mt-6 flex items-center gap-3">
          <button onClick={() => priForm && saveMutation.mutate(priForm)}
            disabled={!valid || !dirty || saveMutation.isPending}
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-[#FE017D] text-white text-sm rounded-lg hover:bg-[#e5006f] disabled:opacity-50 transition-colors"
          >
            {saveMutation.isPending ? 'Saving…' : 'Save changes'}
          </button>
          <button onClick={() => priConfig && setPriForm(priConfig)} disabled={!dirty}
            className="px-4 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50"
          >
            Reset
          </button>
          {saved && <span className="inline-flex items-center gap-1 text-xs text-green-700"><CheckCircle className="w-3.5 h-3.5" /> Saved</span>}
        </div>
      </div>

      <div className={card}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="font-semibold text-gray-900">Recompute priorities</h3>
            <p className="text-sm text-gray-500 mt-1">
              Apply the saved formula to all open cases{affectedCount && ` (${affectedCount.open_cases.toLocaleString()} cases)`}.
            </p>
            {dirty && <p className="text-xs text-amber-700 mt-2">Save changes first, then recompute.</p>}
          </div>
          <button onClick={() => setConfirmRecompute(true)} disabled={dirty}
            className="inline-flex items-center gap-1.5 px-4 py-2 border border-[#FE017D] text-[#FE017D] text-sm rounded-lg hover:bg-[#FE017D]/5 disabled:opacity-50 transition-colors flex-shrink-0"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Recompute now
          </button>
        </div>
        {recomputeResult && (
          <div className="mt-4 p-3 bg-green-50 border border-green-200 rounded-lg text-sm text-green-800">
            Recomputed {recomputeResult.updated.toLocaleString()} of {recomputeResult.scanned.toLocaleString()} cases
            {recomputeResult.errors > 0 && <> · {recomputeResult.errors} errors</>}.
          </div>
        )}
      </div>

      {confirmRecompute && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-sm w-full p-6">
            <h3 className="font-semibold text-gray-900 mb-2">Recompute priorities?</h3>
            <p className="text-sm text-gray-500 mb-5">
              Updates priority and priority_score on {affectedCount ? `${affectedCount.open_cases.toLocaleString()} ` : 'all '}open cases.
            </p>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setConfirmRecompute(false)} className="px-4 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50">Cancel</button>
              <button onClick={() => recomputeMutation.mutate()} disabled={recomputeMutation.isPending}
                className="px-4 py-2 text-sm bg-[#FE017D] text-white rounded-lg hover:bg-[#e5006f] disabled:opacity-60">
                {recomputeMutation.isPending ? 'Recomputing…' : 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
