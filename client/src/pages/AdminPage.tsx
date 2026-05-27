import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle, RefreshCw, CheckCircle, XCircle, Search, Shield, ExternalLink, Sliders, ListChecks,
} from 'lucide-react'
import api from '../services/api'
import { card } from '../utils/designSystem'
import { formatDate } from '../utils/dateUtils'
import LetterTemplatesTab from '../components/admin/LetterTemplatesTab'
import TrainModelPage from './TrainModelPage'
import type { ReferenceDataFreshness, User, CPTCode } from '../types'

type AdminTab = 'freshness' | 'model' | 'users' | 'codes' | 'prioritization' | 'rules' | 'templates'

interface PrioritizationConfig {
  amount_weight: number
  likelihood_weight: number
  urgency_weight: number
  amount_cap: number
  urgency_window_days: number
  high_threshold: number
  medium_threshold: number
  updated_at: string
}

interface DetectorRule {
  rule_code: string
  name: string
  description: string
  enabled: boolean
  score: number
  updated_at: string
}

interface MLModelInfo {
  version: string; trained_at: string; accuracy: number
  precision: number; recall: number; f1_score: number
  auc_roc: number; training_samples: number
  feature_importance?: Record<string, number>
}

const FEATURE_LABEL: Record<string, string> = {
  avg_units_per_line:       'Avg units/line',
  high_value_cpt_ratio:     'High-risk CPT',
  multi_line_claim_ratio:   'Multi-line claims',
  modifier_usage_rate:      'Modifier usage',
  same_day_multi_cpt_rate:  'Same-day multi-CPT',
  prior_overpayment_rate:   'Prior overpayment',
  specialty_peer_deviation: 'Peer deviation',
}

const FEATURE_HINT: Record<string, string> = {
  avg_units_per_line:       'Mean units billed per service line',
  high_value_cpt_ratio:     'Fraction of claims using high-dollar CPT codes',
  multi_line_claim_ratio:   'Fraction of claims with multiple service lines',
  modifier_usage_rate:      'Fraction of lines that carry a CPT modifier',
  same_day_multi_cpt_rate:  'Rate of multiple CPTs billed on the same DOS',
  prior_overpayment_rate:   'Historical recoupment rate for this provider',
  specialty_peer_deviation: 'Z-score vs. specialty peers on key metrics',
}

const SOURCE_META: Record<string, { description: string; url: string }> = {
  'CMS Fee Schedule': {
    description: 'Medicare Physician Fee Schedule rates published by CMS. Used to detect paid amounts exceeding allowed rates.',
    url: 'https://www.cms.gov/medicare/payment/fee-schedules/physician',
  },
  'OIG Exclusion List': {
    description: 'HHS OIG list of providers excluded from federal healthcare programs due to fraud or abuse.',
    url: 'https://oig.hhs.gov/exclusions/',
  },
  'State Medicaid Rates': {
    description: 'State-specific Medicaid reimbursement rates used to validate Medicaid LOB claim payments.',
    url: 'https://www.medicaid.gov/',
  },
  'DMF Death Master File': {
    description: 'SSA Death Master File used to detect post-death billing and claims filed for deceased beneficiaries.',
    url: 'https://www.ntis.gov/ladmf/ladmf.xhtml',
  },
  'NPPES NPI Registry': {
    description: 'National Plan & Provider Enumeration System. Provider identity, specialty, and enrollment verification.',
    url: 'https://npiregistry.cms.hhs.gov/',
  },
  'CPT Code Crosswalk': {
    description: 'AMA CPT procedure code definitions and modifiers. Used for coding accuracy and NCCI edit compliance.',
    url: 'https://www.ama-assn.org/practice-management/cpt',
  },
  'NCCI Policy Manual': {
    description: 'CMS National Correct Coding Initiative policy manual + PTP and MUE edit tables. Drives DET-06 mutually-exclusive pair detection and per-day unit limit checks.',
    url: 'https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-policy-manual',
  },
}

const FRESHNESS_STYLE: Record<string, string> = {
  fresh:    'bg-green-100 text-green-700 border-green-200',
  stale:    'bg-amber-100 text-amber-700 border-amber-200',
  critical: 'bg-red-100 text-red-700 border-red-200',
}

const ROLE_STYLE: Record<string, string> = {
  admin:      'bg-[#FE017D]/10 text-[#FE017D]',
  supervisor: 'bg-purple-100 text-purple-700',
  analyst:    'bg-gray-100 text-gray-600',
}

const TABS: { key: AdminTab; label: string }[] = [
  { key: 'freshness',      label: 'Reference Data'   },
  { key: 'model',          label: 'ML Model'          },
  { key: 'prioritization', label: 'Prioritization'    },
  { key: 'rules',          label: 'Rules'             },
  { key: 'templates',      label: 'Letter Templates'  },
  { key: 'users',          label: 'Users'             },
  { key: 'codes',          label: 'CPT/ICD Codes'    },
]

export default function AdminPage() {
  const [activeTab,     setActiveTab]     = useState<AdminTab>('freshness')
  const [confirmRetrain,setConfirmRetrain]= useState(false)
  const [confirmRecompute, setConfirmRecompute] = useState(false)
  const [recomputeResult, setRecomputeResult]   = useState<{updated: number; scanned: number; errors: number} | null>(null)
  const [codeSearch,    setCodeSearch]    = useState('')
  const [priForm, setPriForm] = useState<PrioritizationConfig | null>(null)
  const [priSaved, setPriSaved] = useState(false)
  const qc = useQueryClient()

  const { data: freshness = [], isLoading: loadingFreshness } = useQuery<ReferenceDataFreshness[]>({
    queryKey: ['admin', 'freshness'],
    queryFn:  async () => (await api.get<ReferenceDataFreshness[]>('/admin/reference-freshness')).data,
  })

  const { data: modelInfo, isLoading: loadingModel } = useQuery<MLModelInfo>({
    queryKey: ['admin', 'model'],
    queryFn:  async () => (await api.get<MLModelInfo>('/admin/model')).data,
    enabled:  activeTab === 'model',
  })

  const { data: users = [], isLoading: loadingUsers } = useQuery<User[]>({
    queryKey: ['admin', 'users'],
    queryFn:  async () => (await api.get<User[]>('/admin/users')).data,
    enabled:  activeTab === 'users',
  })

  const { data: cptCodes = [], isLoading: loadingCodes } = useQuery<CPTCode[]>({
    queryKey: ['admin', 'cpt-codes'],
    queryFn:  async () => (await api.get<CPTCode[]>('/admin/cpt-codes')).data,
    enabled:  activeTab === 'codes',
  })

  const retrainMutation = useMutation({
    mutationFn: async () => (await api.post<MLModelInfo>('/admin/model/retrain')).data,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin','model'] }); setConfirmRetrain(false) },
  })

  const [refreshingSource, setRefreshingSource] = useState<string | null>(null)

  const refreshSourceMutation = useMutation({
    mutationFn: async (sourceName: string) => {
      setRefreshingSource(sourceName)
      return (await api.post(`/admin/reference-freshness/${encodeURIComponent(sourceName)}/refresh`)).data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'freshness'] })
      qc.invalidateQueries({ queryKey: ['freshness-banner'] })
    },
    onSettled: () => setRefreshingSource(null),
  })

  const toggleUserMutation = useMutation({
    mutationFn: async ({ userId, isActive }: { userId: string; isActive: boolean }) =>
      (await api.patch<User>(`/admin/users/${userId}`, { is_active: isActive })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin','users'] }),
  })

  const { data: priConfig, isLoading: loadingPri } = useQuery<PrioritizationConfig>({
    queryKey: ['admin', 'prioritization-config'],
    queryFn:  async () => (await api.get<PrioritizationConfig>('/admin/prioritization-config')).data,
    enabled:  activeTab === 'prioritization',
  })

  const { data: affectedCount } = useQuery<{ open_cases: number }>({
    queryKey: ['admin', 'prioritization-affected'],
    queryFn:  async () => (await api.get<{ open_cases: number }>('/admin/prioritization-config/affected-count')).data,
    enabled:  activeTab === 'prioritization',
  })

  useEffect(() => {
    if (priConfig) setPriForm(priConfig)
  }, [priConfig])

  const savePriMutation = useMutation({
    mutationFn: async (cfg: PrioritizationConfig) =>
      (await api.put<PrioritizationConfig>('/admin/prioritization-config', cfg)).data,
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['admin', 'prioritization-config'] })
      setPriForm(data)
      setPriSaved(true)
      setTimeout(() => setPriSaved(false), 2500)
    },
  })

  const recomputeMutation = useMutation({
    mutationFn: async () =>
      (await api.post<{ scanned: number; updated: number; errors: number }>('/admin/prioritization-config/recompute')).data,
    onSuccess: (data) => {
      setRecomputeResult({ scanned: data.scanned, updated: data.updated, errors: data.errors })
      setConfirmRecompute(false)
      qc.invalidateQueries({ queryKey: ['cases'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })

  const { data: rules = [], isLoading: loadingRules } = useQuery<DetectorRule[]>({
    queryKey: ['admin', 'detector-rules'],
    queryFn:  async () => (await api.get<DetectorRule[]>('/admin/detector-rules')).data,
    enabled:  activeTab === 'rules',
  })

  const [savedRule, setSavedRule] = useState<string | null>(null)
  const [scoreDraft, setScoreDraft] = useState<Record<string, string>>({})

  const updateRuleMutation = useMutation({
    mutationFn: async ({ code, body }: { code: string; body: Partial<DetectorRule> }) =>
      (await api.put<DetectorRule>(`/admin/detector-rules/${code}`, body)).data,
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['admin', 'detector-rules'] })
      setSavedRule(data.rule_code)
      setTimeout(() => setSavedRule((s) => (s === data.rule_code ? null : s)), 1500)
    },
  })

  const weightSum = priForm
    ? +(priForm.amount_weight + priForm.likelihood_weight + priForm.urgency_weight).toFixed(3)
    : 1
  const weightsValid = Math.abs(weightSum - 1.0) < 0.001
  const thresholdsValid = priForm ? priForm.high_threshold > priForm.medium_threshold : true
  const priFormValid = weightsValid && thresholdsValid
  const priFormDirty = priForm && priConfig
    ? JSON.stringify({...priForm, updated_at: ''}) !== JSON.stringify({...priConfig, updated_at: ''})
    : false

  const hasCritical = freshness.some((f) => f.status === 'critical')
  const hasStale    = freshness.some((f) => f.status === 'stale')

  const filteredCodes = codeSearch
    ? cptCodes.filter((c) =>
        c.code.toLowerCase().includes(codeSearch.toLowerCase()) ||
        c.description.toLowerCase().includes(codeSearch.toLowerCase()))
    : cptCodes

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center gap-3">
        <Shield className="w-6 h-6 text-[#1e3a5f]" />
        <h1 className="text-2xl font-bold text-gray-900">Admin</h1>
      </div>

      {/* Alert banner */}
      {(hasCritical || hasStale) && (
        <div className={`rounded-xl border p-4 flex items-start gap-3 ${
          hasCritical
            ? 'bg-red-50 border-red-200 text-red-800'
            : 'bg-amber-50 border-amber-200 text-amber-800'
        }`}>
          <AlertTriangle className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-sm">
              {hasCritical
                ? 'Critical: One or more reference data sources are critically outdated.'
                : 'Warning: Some reference data sources are stale.'}
            </p>
            <p className="text-sm mt-0.5 opacity-75">
              Update affected sources to maintain accurate overpayment detection.
            </p>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b border-gray-200 gap-1">
        {TABS.map((tab) => (
          <button key={tab.key} onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.key
                ? 'border-[#FE017D] text-[#FE017D]'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}>
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── Reference Data ─────────────────────────────────────── */}
      {activeTab === 'freshness' && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          {loadingFreshness ? (
            <div className="p-5 space-y-2 animate-pulse">
              {[...Array(6)].map((_, i) => <div key={i} className="h-11 bg-gray-100 rounded-lg" />)}
            </div>
          ) : (
            <table className="min-w-full divide-y divide-gray-100">
              <thead className="bg-gray-50">
                <tr>
                  {['Source','Status','Last Refreshed','Next Due',''].map((h) => (
                    <th key={h} className="px-5 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {freshness.map((f) => (
                  <tr key={f.source_name} className={
                    f.status === 'critical' ? 'bg-red-50/50' :
                    f.status === 'stale'    ? 'bg-amber-50/50' : ''
                  }>
                    <td className="px-5 py-4">
                      <p className="text-sm font-semibold text-gray-900">{f.source_name}</p>
                      {SOURCE_META[f.source_name] && (
                        <>
                          <p className="text-xs text-gray-500 mt-0.5 max-w-xs">
                            {SOURCE_META[f.source_name].description}
                          </p>
                          <a
                            href={SOURCE_META[f.source_name].url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-xs text-[#FE017D] hover:underline mt-1"
                          >
                            <ExternalLink className="w-3 h-3" />
                            {SOURCE_META[f.source_name].url.replace('https://', '')}
                          </a>
                        </>
                      )}
                    </td>
                    <td className="px-5 py-3.5">
                      <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full
                                        text-xs font-semibold border ${FRESHNESS_STYLE[f.status]}`}>
                        {f.status === 'fresh'
                          ? <CheckCircle className="w-3 h-3" />
                          : <AlertTriangle className="w-3 h-3" />}
                        {f.status.charAt(0).toUpperCase() + f.status.slice(1)}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-sm text-gray-600">{formatDate(f.last_updated)}</td>
                    <td className="px-5 py-3.5 text-sm text-gray-600">{formatDate(f.next_due)}</td>
                    <td className="px-5 py-3.5">
                      <button
                        onClick={() => refreshSourceMutation.mutate(f.source_name)}
                        disabled={refreshingSource === f.source_name}
                        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs
                                    font-medium border transition-colors
                                    ${f.status !== 'fresh'
                                      ? 'border-[#FE017D] text-[#FE017D] hover:bg-[#FE017D]/5'
                                      : 'border-gray-200 text-gray-500 hover:bg-gray-50'
                                    } disabled:opacity-50`}
                      >
                        <RefreshCw className={`w-3 h-3 ${refreshingSource === f.source_name ? 'animate-spin' : ''}`} />
                        {refreshingSource === f.source_name ? 'Refreshing…' : 'Refresh'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ── ML Model ───────────────────────────────────────────── */}
      {activeTab === 'model' && (
        <div className="space-y-4">
          {loadingModel ? (
            <div className="h-56 bg-white rounded-xl border border-gray-200 animate-pulse" />
          ) : modelInfo ? (
            <>
              <div className={card}>
                <div className="flex items-start justify-between mb-5">
                  <div>
                    <h2 className="text-lg font-bold text-gray-900">Model v{modelInfo.version}</h2>
                    <p className="text-sm text-gray-500 mt-0.5">
                      Trained {formatDate(modelInfo.trained_at)} · {modelInfo.training_samples.toLocaleString()} samples
                    </p>
                  </div>
                  <button onClick={() => setConfirmRetrain(true)}
                    className="inline-flex items-center gap-1.5 px-4 py-2
                               bg-[#FE017D] text-white text-sm rounded-lg
                               hover:bg-[#e5006f] transition-colors">
                    <RefreshCw className="w-3.5 h-3.5" /> Retrain
                  </button>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                  {([
                    ['Accuracy',   modelInfo.accuracy  ],
                    ['Precision',  modelInfo.precision  ],
                    ['Recall',     modelInfo.recall     ],
                    ['F1 Score',   modelInfo.f1_score   ],
                    ['AUC-ROC',    modelInfo.auc_roc    ],
                  ] as [string, number][]).map(([label, val]) => (
                    <div key={label} className="bg-gray-50 rounded-xl p-4 text-center">
                      <p className="text-xs text-gray-400 uppercase tracking-wider mb-1">{label}</p>
                      <p className="text-2xl font-bold text-gray-900">{(val * 100).toFixed(1)}%</p>
                      <div className="mt-2.5 w-full bg-gray-200 rounded-full h-1.5">
                        <div className="h-1.5 rounded-full bg-[#FE017D]"
                             style={{ width: `${val * 100}%` }} />
                      </div>
                    </div>
                  ))}
                </div>

                {/* Feature importances */}
                {modelInfo.feature_importance && Object.keys(modelInfo.feature_importance).length > 0 && (() => {
                  const entries = Object.entries(modelInfo.feature_importance)
                  const sum = entries.reduce((a, [, v]) => a + v, 0) || 1
                  const max = Math.max(...entries.map(([, v]) => v))
                  const sorted = [...entries].sort(([, a], [, b]) => b - a)
                  return (
                    <div className="mt-6 pt-5 border-t border-gray-100">
                      <div className="flex items-baseline justify-between mb-3">
                        <h3 className="text-sm font-bold text-gray-900">Feature importances</h3>
                        <p className="text-[11px] text-gray-400">
                          Random Forest impurity-based · sums to 100%
                        </p>
                      </div>
                      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                        {sorted.map(([feat, val]) => {
                          const pct = (val / sum) * 100
                          const barPct = max > 0 ? (val / max) * 100 : 0
                          return (
                            <div key={feat} className="bg-gray-50 rounded-xl p-4 text-center" title={FEATURE_HINT[feat] ?? feat}>
                              <p className="text-xs text-gray-400 uppercase tracking-wider mb-1 truncate">
                                {FEATURE_LABEL[feat] ?? feat}
                              </p>
                              <p className="text-lg font-bold text-gray-900">{pct.toFixed(1)}%</p>
                              <div className="mt-2.5 w-full bg-gray-200 rounded-full h-1.5">
                                <div className="h-1.5 rounded-full bg-[#FE017D]"
                                     style={{ width: `${barPct}%` }} />
                              </div>
                            </div>
                          )
                        })}
                      </div>
                      <p className="text-[11px] text-gray-400 mt-3 leading-relaxed">
                        Each value is the average reduction in node impurity attributable to that feature across all trees, normalized so the set sums to 1.0. Bar width is relative to the strongest feature. For per-provider attribution (which feature drove a specific score), see the Provider Risk page.
                      </p>
                    </div>
                  )
                })()}
              </div>

              {confirmRetrain && (
                <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
                  <div className="bg-white rounded-xl shadow-xl max-w-sm w-full p-6">
                    <h3 className="font-semibold text-gray-900 mb-2">Retrain Model?</h3>
                    <p className="text-sm text-gray-500 mb-5">
                      This will trigger a new training job. The process may take several minutes.
                    </p>
                    <div className="flex gap-2 justify-end">
                      <button onClick={() => setConfirmRetrain(false)}
                        className="px-4 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50">
                        Cancel
                      </button>
                      <button onClick={() => retrainMutation.mutate()}
                        disabled={retrainMutation.isPending}
                        className="px-4 py-2 text-sm bg-[#FE017D] text-white rounded-lg
                                   hover:bg-[#e5006f] disabled:opacity-60">
                        {retrainMutation.isPending ? 'Retraining…' : 'Start Retraining'}
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-gray-400">Model info not available.</p>
          )}

          {/* Train / retrain controls (merged from former "Train Model" tab) */}
          <div className="pt-2">
            <TrainModelPage />
          </div>
        </div>
      )}

      {/* ── Prioritization ─────────────────────────────────────── */}
      {activeTab === 'prioritization' && (
        <div className="space-y-4">
          {loadingPri || !priForm ? (
            <div className="h-72 bg-white rounded-xl border border-gray-200 animate-pulse" />
          ) : (
            <>
              <div className={card}>
                <div className="flex items-start justify-between mb-1">
                  <div>
                    <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                      <Sliders className="w-4 h-4" /> Priority Formula
                    </h2>
                    <p className="text-sm text-gray-500 mt-0.5">
                      <span className="font-mono">priority = (w<sub>amt</sub>·amount_norm + w<sub>lik</sub>·posterior + w<sub>urg</sub>·urgency) × 100</span>
                    </p>
                    <p className="text-xs text-gray-400 mt-1">Last updated {formatDate(priForm.updated_at)}</p>
                  </div>
                </div>

                <div className="mt-5 grid grid-cols-1 md:grid-cols-3 gap-4">
                  {([
                    ['amount_weight',     'Amount weight',     'w_amt'],
                    ['likelihood_weight', 'Posterior weight', 'w_lik'],
                    ['urgency_weight',    'Urgency weight',    'w_urg'],
                  ] as [keyof PrioritizationConfig, string, string][]).map(([key, label, hint]) => (
                    <div key={key}>
                      <label className="block text-xs font-medium text-gray-600 mb-1">
                        {label} <span className="text-gray-400 font-mono">{hint}</span>
                      </label>
                      <input
                        type="number" step="0.01" min="0" max="1"
                        value={priForm[key] as number}
                        onChange={(e) => setPriForm({ ...priForm, [key]: parseFloat(e.target.value) || 0 })}
                        className="w-full px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm
                                   focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]"
                      />
                    </div>
                  ))}
                </div>
                <p className={`text-xs mt-2 ${weightsValid ? 'text-gray-400' : 'text-red-600 font-medium'}`}>
                  Sum of weights: {weightSum.toFixed(3)} {weightsValid ? '✓' : '— must equal 1.000'}
                </p>

                <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Amount cap ($) <span className="text-gray-400">— amounts above this normalize to 1.0</span>
                    </label>
                    <input
                      type="number" step="100" min="1"
                      value={priForm.amount_cap}
                      onChange={(e) => setPriForm({ ...priForm, amount_cap: parseFloat(e.target.value) || 0 })}
                      className="w-full px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm
                                 focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Urgency window (days) <span className="text-gray-400">— urgency = 0 at &gt;= this many days out</span>
                    </label>
                    <input
                      type="number" step="1" min="1" max="365"
                      value={priForm.urgency_window_days}
                      onChange={(e) => setPriForm({ ...priForm, urgency_window_days: parseInt(e.target.value) || 0 })}
                      className="w-full px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm
                                 focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]"
                    />
                  </div>
                </div>

                <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">HIGH threshold</label>
                    <input
                      type="number" step="1" min="0" max="100"
                      value={priForm.high_threshold}
                      onChange={(e) => setPriForm({ ...priForm, high_threshold: parseFloat(e.target.value) || 0 })}
                      className="w-full px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm
                                 focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">MEDIUM threshold</label>
                    <input
                      type="number" step="1" min="0" max="100"
                      value={priForm.medium_threshold}
                      onChange={(e) => setPriForm({ ...priForm, medium_threshold: parseFloat(e.target.value) || 0 })}
                      className="w-full px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm
                                 focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]"
                    />
                  </div>
                </div>
                {!thresholdsValid && (
                  <p className="text-xs mt-2 text-red-600 font-medium">
                    HIGH threshold must be greater than MEDIUM threshold.
                  </p>
                )}

                <div className="mt-6 flex items-center gap-3">
                  <button
                    onClick={() => priForm && savePriMutation.mutate(priForm)}
                    disabled={!priFormValid || !priFormDirty || savePriMutation.isPending}
                    className="inline-flex items-center gap-1.5 px-4 py-2
                               bg-[#FE017D] text-white text-sm rounded-lg
                               hover:bg-[#e5006f] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {savePriMutation.isPending ? 'Saving…' : 'Save changes'}
                  </button>
                  <button
                    onClick={() => priConfig && setPriForm(priConfig)}
                    disabled={!priFormDirty || savePriMutation.isPending}
                    className="px-4 py-2 text-sm border border-gray-200 rounded-lg
                               hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Reset
                  </button>
                  {priSaved && (
                    <span className="inline-flex items-center gap-1 text-xs text-green-700">
                      <CheckCircle className="w-3.5 h-3.5" /> Saved
                    </span>
                  )}
                  {savePriMutation.isError && (
                    <span className="text-xs text-red-600">
                      {(savePriMutation.error as any)?.response?.data?.detail ?? 'Save failed'}
                    </span>
                  )}
                </div>
              </div>

              <div className={card}>
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h3 className="font-semibold text-gray-900">Recompute priorities</h3>
                    <p className="text-sm text-gray-500 mt-1">
                      Apply the saved formula to all open cases
                      {affectedCount && <> ({affectedCount.open_cases.toLocaleString()} cases)</>}.
                      Closed cases are not touched.
                    </p>
                    {priFormDirty && (
                      <p className="text-xs text-amber-700 mt-2">
                        You have unsaved changes — save first, then recompute.
                      </p>
                    )}
                  </div>
                  <button
                    onClick={() => setConfirmRecompute(true)}
                    disabled={priFormDirty}
                    className="inline-flex items-center gap-1.5 px-4 py-2
                               border border-[#FE017D] text-[#FE017D] text-sm rounded-lg
                               hover:bg-[#FE017D]/5 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex-shrink-0"
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
                      This will update <span className="font-semibold">priority</span> and <span className="font-semibold">priority_score</span> on
                      {affectedCount ? ` ${affectedCount.open_cases.toLocaleString()} ` : ' all '}
                      open cases using the saved formula. Closed cases are untouched.
                    </p>
                    <div className="flex gap-2 justify-end">
                      <button onClick={() => setConfirmRecompute(false)}
                        className="px-4 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50">
                        Cancel
                      </button>
                      <button onClick={() => recomputeMutation.mutate()}
                        disabled={recomputeMutation.isPending}
                        className="px-4 py-2 text-sm bg-[#FE017D] text-white rounded-lg
                                   hover:bg-[#e5006f] disabled:opacity-60">
                        {recomputeMutation.isPending ? 'Recomputing…' : 'Confirm recompute'}
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ── Letter Templates ──────────────────────────────────────── */}
      {activeTab === 'templates' && <LetterTemplatesTab />}

      {/* ── Rules ──────────────────────────────────────────────── */}
      {activeTab === 'rules' && (
        <div className="space-y-3">
          <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-sm text-blue-900 flex items-start gap-2">
            <ListChecks className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-medium">Detector rules</p>
              <p className="text-xs text-blue-800 mt-1">
                Disabling a rule skips it on future case analyses. The weight is a multiplier (0.0–1.0) applied to each finding's confidence
                in the posterior update. Defaults: enabled, weight 1.0. Every change is recorded in the audit log.
              </p>
            </div>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            {loadingRules ? (
              <div className="p-5 space-y-2 animate-pulse">
                {[...Array(6)].map((_, i) => <div key={i} className="h-14 bg-gray-100 rounded-lg" />)}
              </div>
            ) : (
              <table className="min-w-full divide-y divide-gray-100">
                <thead className="bg-gray-50">
                  <tr>
                    {['Code','Rule','Weight','Enabled','Last Updated',''].map((h) => (
                      <th key={h} className="px-5 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {rules.map((r) => {
                    const draftVal = scoreDraft[r.rule_code]
                    const displayScore = draftVal !== undefined ? draftVal : r.score.toString()
                    const handleScoreCommit = () => {
                      const parsed = parseFloat(displayScore)
                      setScoreDraft((d) => { const next = {...d}; delete next[r.rule_code]; return next })
                      if (!isNaN(parsed) && parsed >= 0 && parsed <= 1 && parsed !== r.score) {
                        updateRuleMutation.mutate({ code: r.rule_code, body: { score: parsed } })
                      }
                    }
                    return (
                      <tr key={r.rule_code} className={!r.enabled ? 'opacity-60' : ''}>
                        <td className="px-5 py-3.5 text-sm font-mono font-semibold text-gray-900">{r.rule_code}</td>
                        <td className="px-5 py-3.5 max-w-md">
                          <p className="text-sm font-medium text-gray-900">{r.name}</p>
                          <p className="text-xs text-gray-500 mt-0.5">{r.description}</p>
                        </td>
                        <td className="px-5 py-3.5">
                          <input
                            type="number" step="0.1" min="0" max="1"
                            value={displayScore}
                            onChange={(e) => setScoreDraft((d) => ({ ...d, [r.rule_code]: e.target.value }))}
                            onBlur={handleScoreCommit}
                            onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur() }}
                            className="w-20 px-2 py-1.5 bg-white border border-gray-200 rounded-lg text-sm font-mono
                                       focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]"
                          />
                        </td>
                        <td className="px-5 py-3.5">
                          <button
                            onClick={() => updateRuleMutation.mutate({ code: r.rule_code, body: { enabled: !r.enabled } })}
                            disabled={updateRuleMutation.isPending}
                            role="switch"
                            aria-checked={r.enabled}
                            className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                              r.enabled ? 'bg-[#FE017D]' : 'bg-gray-300'
                            }`}
                          >
                            <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                              r.enabled ? 'translate-x-4' : 'translate-x-0.5'
                            }`} />
                          </button>
                          <span className="ml-2 text-xs text-gray-500">{r.enabled ? 'On' : 'Off'}</span>
                        </td>
                        <td className="px-5 py-3.5 text-xs text-gray-500">{formatDate(r.updated_at)}</td>
                        <td className="px-5 py-3.5">
                          {savedRule === r.rule_code && (
                            <span className="inline-flex items-center gap-1 text-xs text-green-700">
                              <CheckCircle className="w-3.5 h-3.5" /> Saved
                            </span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* ── Users ──────────────────────────────────────────────── */}
      {activeTab === 'users' && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          {loadingUsers ? (
            <div className="p-5 space-y-2 animate-pulse">
              {[...Array(6)].map((_, i) => <div key={i} className="h-11 bg-gray-100 rounded-lg" />)}
            </div>
          ) : (
            <table className="min-w-full divide-y divide-gray-100">
              <thead className="bg-gray-50">
                <tr>
                  {['Name','Username','Email','Role','Status','Action'].map((h) => (
                    <th key={h} className="px-5 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {users.map((user) => (
                  <tr key={user.id} className={`transition-colors hover:bg-gray-50 ${!user.is_active ? 'opacity-50' : ''}`}>
                    <td className="px-5 py-3.5 text-sm font-medium text-gray-900">{user.full_name}</td>
                    <td className="px-5 py-3.5 text-sm font-mono text-gray-600">{user.username}</td>
                    <td className="px-5 py-3.5 text-sm text-gray-600">{user.email}</td>
                    <td className="px-5 py-3.5">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${ROLE_STYLE[user.role] ?? 'bg-gray-100 text-gray-600'}`}>
                        {user.role}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      {user.is_active ? (
                        <span className="inline-flex items-center gap-1 text-xs text-green-700">
                          <CheckCircle className="w-3.5 h-3.5" /> Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-xs text-gray-400">
                          <XCircle className="w-3.5 h-3.5" /> Inactive
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3.5">
                      <button
                        onClick={() => toggleUserMutation.mutate({ userId: user.id, isActive: !user.is_active })}
                        disabled={toggleUserMutation.isPending}
                        className={`text-xs px-2.5 py-1 rounded-lg border transition-colors ${
                          user.is_active
                            ? 'border-red-200 text-red-600 hover:bg-red-50'
                            : 'border-green-200 text-green-600 hover:bg-green-50'
                        }`}
                      >
                        {user.is_active ? 'Deactivate' : 'Activate'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ── CPT/ICD Codes ──────────────────────────────────────── */}
      {activeTab === 'codes' && (
        <div className="space-y-4">
          <div className="relative max-w-sm">
            <Search className="absolute left-2.5 top-2.5 w-4 h-4 text-gray-400" />
            <input
              type="text" value={codeSearch} onChange={(e) => setCodeSearch(e.target.value)}
              placeholder="Search codes or descriptions…"
              className="w-full pl-8 pr-3 py-2 bg-white border border-gray-200 rounded-lg text-sm
                         focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]
                         transition-colors"
            />
          </div>

          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            {loadingCodes ? (
              <div className="p-5 space-y-2 animate-pulse">
                {[...Array(8)].map((_, i) => <div key={i} className="h-10 bg-gray-100 rounded-lg" />)}
              </div>
            ) : (
              <>
                <table className="min-w-full divide-y divide-gray-100">
                  <thead className="bg-gray-50">
                    <tr>
                      {['Code','Description','Risk Level','RAC Flag'].map((h) => (
                        <th key={h} className="px-5 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {filteredCodes.length === 0 ? (
                      <tr>
                        <td colSpan={4} className="px-5 py-12 text-center text-sm text-gray-400">
                          {codeSearch ? 'No codes match your search.' : 'No codes available.'}
                        </td>
                      </tr>
                    ) : (
                      filteredCodes.slice(0, 200).map((code) => (
                        <tr key={code.code} className="hover:bg-gray-50 transition-colors">
                          <td className="px-5 py-2.5 text-sm font-mono font-semibold text-gray-900">{code.code}</td>
                          <td className="px-5 py-2.5 text-sm text-gray-600">{code.description}</td>
                          <td className="px-5 py-2.5">
                            <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
                              code.risk_level === 'H' ? 'bg-red-100 text-red-700' :
                              code.risk_level === 'M' ? 'bg-amber-100 text-amber-700' :
                              'bg-green-100 text-green-700'
                            }`}>
                              {code.risk_level === 'H' ? 'High' : code.risk_level === 'M' ? 'Medium' : 'Low'}
                            </span>
                          </td>
                          <td className="px-5 py-2.5">
                            {code.cms_rac_flag
                              ? <CheckCircle className="w-4 h-4 text-[#FE017D]" />
                              : <span className="text-gray-200 text-xs">—</span>}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
                {filteredCodes.length > 200 && (
                  <div className="px-5 py-3 bg-gray-50 border-t border-gray-100 text-xs text-gray-400">
                    Showing 200 of {filteredCodes.length} — refine your search to see more.
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
