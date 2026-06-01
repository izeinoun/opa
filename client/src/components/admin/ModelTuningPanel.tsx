import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FlaskConical, Save, RotateCcw, AlertTriangle, CheckCircle, Sparkles } from 'lucide-react'
import api from '../../services/api'
import { card } from '../../utils/designSystem'

// ── Types ────────────────────────────────────────────────────────────────────

interface TrainingConfig {
  n_estimators: number
  max_depth: number | null
  min_samples_split: number
  min_samples_leaf: number
  max_features: string | null
  max_leaf_nodes: number | null
  bootstrap: boolean
  class_weight: string | null
  criterion: string
  decision_threshold_mode: string
  manual_threshold: number | null
  min_auc_to_promote: number | null
  updated_at?: string
}

interface TrialResult {
  method: string
  params_used: Record<string, unknown>
  accuracy: number
  precision: number | null
  recall: number | null
  f1_score: number | null
  f2_score: number | null
  auc_roc: number | null
  decision_threshold: number | null
  positive_rate: number
  training_rows: number
  feature_importance: Record<string, number>
}

// A trial run plus the exact params that produced it (for the history list).
interface TrialRun extends TrialResult {
  attempt: number
  params: TrainingConfig
}

// ── Hyperparameter field metadata ─────────────────────────────────────────────

const FEATURE_LABEL: Record<string, string> = {
  avg_units_per_line: 'Avg units/line', high_value_cpt_ratio: 'High-risk CPT',
  multi_line_claim_ratio: 'Multi-line claims', modifier_usage_rate: 'Modifier usage',
  same_day_multi_cpt_rate: 'Same-day multi-CPT', prior_overpayment_rate: 'Prior overpayment',
  specialty_peer_deviation: 'Peer deviation',
}

const HINT = {
  n_estimators: 'Number of trees in the forest. More = stabler but slower (10–2000).',
  max_depth: 'Max depth of each tree. Empty = unlimited. Lower fights overfitting (1–100).',
  min_samples_split: 'Min samples required to split an internal node (≥2).',
  min_samples_leaf: 'Min samples at a leaf. Higher smooths predictions (1–200).',
  max_features: 'Features considered at each split. sqrt/log2 add randomness; "all" uses every feature.',
  max_leaf_nodes: 'Cap on leaves per tree. Empty = unlimited (2–10000).',
  bootstrap: 'Sample rows with replacement per tree. Off = each tree sees the full set.',
  class_weight: 'Re-weight classes. Note: the pipeline already SMOTE-balances to 50/50, so this has muted effect.',
  criterion: 'Function measuring split quality.',
  decision_threshold_mode: 'auto_f2 sweeps for the F2-optimal cutoff; manual pins it.',
  manual_threshold: 'Probability cutoff used when mode = manual (0–1).',
  min_auc_to_promote: 'On Save, the new version only goes active if its AUC clears this floor. Empty = always promote.',
}

const card2 = 'bg-white rounded-xl border border-gray-200 shadow-sm p-5'
const labelCls = 'block text-xs font-medium text-gray-600 mb-1'
const inputCls = 'w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]'

function fmtPct(v: number | null | undefined) {
  return v == null ? '—' : `${(v * 100).toFixed(1)}%`
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function ModelTuningPanel() {
  const qc = useQueryClient()
  const [form, setForm] = useState<TrainingConfig | null>(null)
  const [trials, setTrials] = useState<TrialRun[]>([])
  const [notes, setNotes] = useState('')
  const [committed, setCommitted] = useState<string | null>(null)

  const { data: config } = useQuery<TrainingConfig>({
    queryKey: ['admin', 'training-config'],
    queryFn: async () => (await api.get<TrainingConfig>('/admin/training-config')).data,
  })

  useEffect(() => { if (config && !form) setForm(config) }, [config, form])

  const set = <K extends keyof TrainingConfig>(k: K, v: TrainingConfig[K]) =>
    setForm((f) => (f ? { ...f, [k]: v } : f))

  const trialMutation = useMutation({
    mutationFn: async (body: TrainingConfig) =>
      (await api.post<TrialResult>('/admin/model/trial', body)).data,
    onSuccess: (data) => {
      setTrials((prev) => [
        { ...data, attempt: prev.length + 1, params: form as TrainingConfig },
        ...prev,
      ])
    },
  })

  const commitMutation = useMutation({
    mutationFn: async (body: TrainingConfig & { notes: string }) =>
      (await api.post<{ version_id: string; providers_updated: number }>('/admin/model/commit', body)).data,
    onSuccess: (data) => {
      setCommitted(data.version_id)
      qc.invalidateQueries({ queryKey: ['admin', 'model'] })
      qc.invalidateQueries({ queryKey: ['admin', 'ml-models'] })
      qc.invalidateQueries({ queryKey: ['ml-info'] })
      setTimeout(() => setCommitted(null), 6000)
    },
  })

  const busy = trialMutation.isPending || commitMutation.isPending
  const error = trialMutation.error || commitMutation.error
  const manualMode = form?.decision_threshold_mode === 'manual'
  const best = trials.length ? trials.reduce((a, b) => ((b.auc_roc ?? 0) > (a.auc_roc ?? 0) ? b : a)) : null

  if (!form) return <div className="h-72 bg-white rounded-xl border border-gray-200 animate-pulse" />

  const numField = (
    key: keyof TrainingConfig, label: string, opts: { min?: number; max?: number; nullable?: boolean } = {}
  ) => (
    <div>
      <label className={labelCls}>{label}</label>
      <input
        type="number" className={inputCls} min={opts.min} max={opts.max}
        value={form[key] == null ? '' : (form[key] as number)}
        placeholder={opts.nullable ? 'unlimited' : undefined}
        onChange={(e) => {
          const raw = e.target.value
          set(key, (raw === '' ? (opts.nullable ? null : 0) : Number(raw)) as never)
        }}
      />
      <p className="text-[11px] text-gray-400 mt-1 leading-snug">{HINT[key as keyof typeof HINT]}</p>
    </div>
  )

  return (
    <div className="space-y-4">
      {/* ── Hyperparameter form ─────────────────────────────────── */}
      <div className={card2}>
        <div className="flex items-center gap-2 mb-1">
          <Sparkles className="w-4 h-4 text-[#FE017D]" />
          <h2 className="text-lg font-bold text-gray-900">RandomForest Hyperparameters</h2>
        </div>
        <p className="text-sm text-gray-500 mb-5">
          Tune the billing-variance classifier, run a trial to inspect validation metrics, retry as
          needed, then save a new model version when you're satisfied.
          {config?.updated_at && <span className="text-gray-400"> · config last saved {new Date(config.updated_at).toLocaleString()}</span>}
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {numField('n_estimators', 'n_estimators', { min: 10, max: 2000 })}
          {numField('max_depth', 'max_depth', { min: 1, max: 100, nullable: true })}
          {numField('min_samples_split', 'min_samples_split', { min: 2, max: 200 })}
          {numField('min_samples_leaf', 'min_samples_leaf', { min: 1, max: 200 })}
          {numField('max_leaf_nodes', 'max_leaf_nodes', { min: 2, max: 10000, nullable: true })}

          <div>
            <label className={labelCls}>max_features</label>
            <select className={inputCls} value={form.max_features ?? 'none'}
              onChange={(e) => set('max_features', e.target.value === 'none' ? null : e.target.value)}>
              <option value="sqrt">sqrt</option>
              <option value="log2">log2</option>
              <option value="none">all features</option>
            </select>
            <p className="text-[11px] text-gray-400 mt-1 leading-snug">{HINT.max_features}</p>
          </div>

          <div>
            <label className={labelCls}>criterion</label>
            <select className={inputCls} value={form.criterion}
              onChange={(e) => set('criterion', e.target.value)}>
              <option value="gini">gini</option>
              <option value="entropy">entropy</option>
              <option value="log_loss">log_loss</option>
            </select>
            <p className="text-[11px] text-gray-400 mt-1 leading-snug">{HINT.criterion}</p>
          </div>

          <div>
            <label className={labelCls}>class_weight</label>
            <select className={inputCls} value={form.class_weight ?? 'none'}
              onChange={(e) => set('class_weight', e.target.value === 'none' ? null : e.target.value)}>
              <option value="none">none</option>
              <option value="balanced">balanced</option>
              <option value="balanced_subsample">balanced_subsample</option>
            </select>
            <p className="text-[11px] text-gray-400 mt-1 leading-snug">{HINT.class_weight}</p>
          </div>

          <div>
            <label className={labelCls}>bootstrap</label>
            <div className="flex items-center gap-2 h-[38px]">
              <button type="button" onClick={() => set('bootstrap', !form.bootstrap)}
                className={`relative w-11 h-6 rounded-full transition-colors ${form.bootstrap ? 'bg-[#FE017D]' : 'bg-gray-300'}`}>
                <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform ${form.bootstrap ? 'translate-x-5' : ''}`} />
              </button>
              <span className="text-sm text-gray-600">{form.bootstrap ? 'on' : 'off'}</span>
            </div>
            <p className="text-[11px] text-gray-400 mt-1 leading-snug">{HINT.bootstrap}</p>
          </div>
        </div>

        {/* Threshold + promotion gate */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-4 pt-4 border-t border-gray-100">
          <div>
            <label className={labelCls}>decision_threshold_mode</label>
            <select className={inputCls} value={form.decision_threshold_mode}
              onChange={(e) => set('decision_threshold_mode', e.target.value)}>
              <option value="auto_f2">auto_f2 (sweep)</option>
              <option value="manual">manual</option>
            </select>
            <p className="text-[11px] text-gray-400 mt-1 leading-snug">{HINT.decision_threshold_mode}</p>
          </div>
          <div>
            <label className={labelCls}>manual_threshold</label>
            <input type="number" step="0.01" min={0} max={1} className={inputCls}
              disabled={!manualMode}
              value={form.manual_threshold == null ? '' : form.manual_threshold}
              placeholder={manualMode ? '0.50' : 'auto'}
              onChange={(e) => set('manual_threshold', e.target.value === '' ? null : Number(e.target.value))} />
            <p className="text-[11px] text-gray-400 mt-1 leading-snug">{HINT.manual_threshold}</p>
          </div>
          <div>
            <label className={labelCls}>min_auc_to_promote</label>
            <input type="number" step="0.01" min={0} max={1} className={inputCls}
              value={form.min_auc_to_promote == null ? '' : form.min_auc_to_promote}
              placeholder="always promote"
              onChange={(e) => set('min_auc_to_promote', e.target.value === '' ? null : Number(e.target.value))} />
            <p className="text-[11px] text-gray-400 mt-1 leading-snug">{HINT.min_auc_to_promote}</p>
          </div>
        </div>

        {manualMode && form.manual_threshold == null && (
          <p className="text-xs text-amber-600 mt-3">manual_threshold is required when mode = manual.</p>
        )}

        {/* Actions */}
        <div className="flex flex-wrap items-center gap-3 mt-5 pt-4 border-t border-gray-100">
          <button onClick={() => trialMutation.mutate(form)}
            disabled={busy || (manualMode && form.manual_threshold == null)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-[#FE017D] text-[#FE017D]
                       text-sm font-semibold rounded-lg hover:bg-[#FE017D]/5 disabled:opacity-40 transition-colors">
            <FlaskConical className={`w-4 h-4 ${trialMutation.isPending ? 'animate-pulse' : ''}`} />
            {trialMutation.isPending ? 'Running trial…' : 'Run Trial'}
          </button>

          <button onClick={() => commitMutation.mutate({ ...form, notes })}
            disabled={busy || (manualMode && form.manual_threshold == null)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-[#FE017D] text-white
                       text-sm font-semibold rounded-lg hover:bg-[#e5006f] disabled:opacity-40 transition-colors">
            <Save className="w-4 h-4" />
            {commitMutation.isPending ? 'Saving version…' : 'Save as New Version'}
          </button>

          {config && (
            <button onClick={() => setForm(config)} disabled={busy}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-sm text-gray-500 hover:text-gray-700 disabled:opacity-40">
              <RotateCcw className="w-3.5 h-3.5" /> Reset to saved
            </button>
          )}

          <input type="text" value={notes} onChange={(e) => setNotes(e.target.value)}
            placeholder="Version notes (optional)…"
            className="flex-1 min-w-[180px] rounded-lg border border-gray-200 px-3 py-2 text-sm
                       focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30" />
        </div>

        {committed && (
          <div className="flex items-center gap-2 bg-green-50 border border-green-200 rounded-lg px-3 py-2.5 mt-4">
            <CheckCircle className="w-4 h-4 text-green-500" />
            <p className="text-xs text-green-700">
              Saved new model version <span className="font-mono">{committed.slice(0, 8)}</span> and pushed updated provider scores.
            </p>
          </div>
        )}
        {error && (
          <div className="flex items-start gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2.5 mt-4">
            <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
            <p className="text-xs text-red-700">
              {(error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? (error as Error)?.message ?? 'Request failed.'}
            </p>
          </div>
        )}
      </div>

      {/* ── Trial history ───────────────────────────────────────── */}
      {trials.length > 0 && (
        <div className={card2}>
          <div className="flex items-center gap-2 mb-1">
            <FlaskConical className="w-4 h-4 text-gray-400" />
            <h3 className="text-sm font-bold text-gray-900">Trial Runs</h3>
            <span className="text-[11px] text-gray-400">
              · not persisted — provider scores & the live model are untouched until you Save
            </span>
          </div>
          <div className="overflow-x-auto mt-3">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] text-gray-400 uppercase tracking-wider border-b border-gray-100">
                  <th className="py-2 pr-3">#</th>
                  <th className="py-2 pr-3">AUC-ROC</th>
                  <th className="py-2 pr-3">F2</th>
                  <th className="py-2 pr-3">Precision</th>
                  <th className="py-2 pr-3">Recall</th>
                  <th className="py-2 pr-3">Accuracy</th>
                  <th className="py-2 pr-3">Threshold</th>
                  <th className="py-2 pr-3">Top feature</th>
                  <th className="py-2 pr-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {trials.map((t) => {
                  const top = Object.entries(t.feature_importance).sort((a, b) => b[1] - a[1])[0]
                  const isBest = best === t
                  return (
                    <tr key={t.attempt} className={isBest ? 'bg-[#FE017D]/5' : ''}>
                      <td className="py-2 pr-3 font-mono text-gray-500">
                        {t.attempt}{isBest && <span className="ml-1 text-[10px] text-[#FE017D] font-semibold">best</span>}
                      </td>
                      <td className="py-2 pr-3 font-semibold text-gray-900">{fmtPct(t.auc_roc)}</td>
                      <td className="py-2 pr-3">{fmtPct(t.f2_score)}</td>
                      <td className="py-2 pr-3">{fmtPct(t.precision)}</td>
                      <td className="py-2 pr-3">{fmtPct(t.recall)}</td>
                      <td className="py-2 pr-3">{fmtPct(t.accuracy)}</td>
                      <td className="py-2 pr-3 font-mono text-gray-500">{t.decision_threshold?.toFixed(2) ?? '—'}</td>
                      <td className="py-2 pr-3 text-gray-600 text-xs">
                        {top ? `${FEATURE_LABEL[top[0]] ?? top[0]} (${(top[1] * 100).toFixed(0)}%)` : '—'}
                      </td>
                      <td className="py-2 pr-3">
                        <button onClick={() => setForm(t.params)}
                          className="text-xs text-[#FE017D] hover:underline">
                          load params
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
