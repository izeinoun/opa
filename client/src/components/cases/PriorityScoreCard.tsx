import { useState } from 'react'
import { Info, X, ChevronDown, ChevronUp } from 'lucide-react'
import type { PriorityBreakdown } from '../../types'
import { formatCurrency } from '../../utils/formatUtils'

const LIKELIHOOD_FEATURES = [
  { name: 'Prior Overpayment Rate',      description: 'Historical rate of confirmed overpayments for this provider' },
  { name: 'Specialty Peer Deviation',    description: 'Billing deviation vs. peer providers in the same specialty' },
  { name: 'High-Value CPT Ratio',        description: 'Proportion of high-risk CPT codes billed' },
  { name: 'Modifier Usage Rate',         description: 'Frequency of claim modifiers, which can inflate reimbursement' },
  { name: 'Same-Day Multi-CPT Rate',     description: 'Rate of billing multiple CPT codes on the same service date' },
  { name: 'Avg Units per Line',          description: 'Average units billed per claim line vs. expected norms' },
  { name: 'Multi-Line Claim Ratio',      description: 'Share of claims with multiple service lines' },
]

interface Props {
  priority: string
  priorityScore: number
  breakdown?: PriorityBreakdown
}

function ComponentBar({ label, value, max, color }: {
  label: string; value: number; max: number; color: string
}) {
  const pct = Math.min((value / max) * 100, 100)
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-gray-500">{label}</span>
        <span className="font-semibold text-gray-700">{value.toFixed(1)} / {max} pts</span>
      </div>
      <div className="w-full bg-gray-100 rounded-full h-1.5">
        <div className={`h-1.5 rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

const BAND_COLOR: Record<string, string> = {
  HIGH: 'text-red-600', MEDIUM: 'text-yellow-600', LOW: 'text-green-600',
}
const BAND_BAR: Record<string, string> = {
  HIGH: 'bg-red-500', MEDIUM: 'bg-yellow-500', LOW: 'bg-green-500',
}
const BAND_DOT: Record<string, string> = {
  HIGH: 'bg-red-500', MEDIUM: 'bg-yellow-500', LOW: 'bg-green-500',
}

function scoreColor(v: number) {
  return v >= 0.75 ? 'text-red-600' : v >= 0.50 ? 'text-yellow-600' : 'text-green-600'
}
function scoreBar(v: number) {
  return v >= 0.75 ? 'bg-red-500' : v >= 0.50 ? 'bg-yellow-500' : 'bg-green-500'
}

export default function PriorityScoreCard({ priority, priorityScore, breakdown }: Props) {
  const [showBreakdown, setShowBreakdown] = useState(false)
  const [showFeatures,  setShowFeatures]  = useState(false)
  const pct = Math.min(priorityScore, 100)

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 space-y-4">

      {/* Three score tiles */}
      <div className="grid grid-cols-3 gap-3">

        {/* Priority Score — clickable to expand bars */}
        <button
          onClick={() => breakdown && setShowBreakdown(v => !v)}
          className={`text-left rounded-lg p-3 border transition-colors ${
            breakdown ? 'cursor-pointer hover:bg-gray-50' : 'cursor-default'
          } ${showBreakdown ? 'border-gray-300 bg-gray-50' : 'border-gray-200'}`}
        >
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Priority</span>
            {breakdown && (showBreakdown
              ? <ChevronUp className="w-3 h-3 text-gray-400" />
              : <ChevronDown className="w-3 h-3 text-gray-400" />)}
          </div>
          <div className="flex items-baseline gap-1 mb-2">
            <span className={`text-xl font-bold ${BAND_COLOR[priority] ?? 'text-gray-700'}`}>
              {priorityScore.toFixed(1)}
            </span>
            <span className="text-xs text-gray-400">/ 100</span>
          </div>
          <div className="w-full bg-gray-100 rounded-full h-1.5">
            <div
              className={`h-1.5 rounded-full transition-all ${BAND_BAR[priority] ?? 'bg-gray-400'}`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="flex items-center gap-1 mt-1.5">
            <span className={`w-1.5 h-1.5 rounded-full ${BAND_DOT[priority] ?? 'bg-gray-400'}`} />
            <span className={`text-xs font-bold ${BAND_COLOR[priority] ?? 'text-gray-600'}`}>{priority}</span>
          </div>
        </button>

        {/* Posterior Score */}
        {breakdown && (
          <div className="rounded-lg p-3 border border-gray-200">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Posterior</p>
            <div className="flex items-baseline gap-1 mb-2">
              <span className={`text-xl font-bold ${scoreColor(breakdown.likelihood_score)}`}>
                {Math.round(breakdown.likelihood_score * 100)}%
              </span>
            </div>
            <div className="w-full bg-gray-100 rounded-full h-1.5">
              <div
                className={`h-1.5 rounded-full transition-all ${scoreBar(breakdown.likelihood_score)}`}
                style={{ width: `${Math.round(breakdown.likelihood_score * 100)}%` }}
              />
            </div>
            <p className="text-xs text-gray-400 mt-1.5">After detectors</p>
          </div>
        )}

        {/* Prior Score */}
        {breakdown && (
          <div className="rounded-lg p-3 border border-gray-200">
            <div className="flex items-center justify-between mb-1">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Prior</p>
              <button
                onClick={() => setShowFeatures(true)}
                className="text-gray-400 hover:text-indigo-500 transition-colors"
              >
                <Info className="w-3 h-3" />
              </button>
            </div>
            <div className="flex items-baseline gap-1 mb-2">
              <span className={`text-xl font-bold ${scoreColor(breakdown.prior_score)}`}>
                {Math.round(breakdown.prior_score * 100)}%
              </span>
            </div>
            <div className="w-full bg-gray-100 rounded-full h-1.5">
              <div
                className={`h-1.5 rounded-full transition-all ${scoreBar(breakdown.prior_score)}`}
                style={{ width: `${Math.round(breakdown.prior_score * 100)}%` }}
              />
            </div>
            <p className="text-xs text-gray-400 mt-1.5">ML model</p>
          </div>
        )}
      </div>

      {/* Collapsible component bars under Priority */}
      {breakdown && showBreakdown && (
        <div className="border-t border-gray-100 pt-3 space-y-3">
          <ComponentBar
            label={`Amount at Risk (${formatCurrency(breakdown.amount_at_risk)})`}
            value={breakdown.amount_pts}
            max={60}
            color="bg-blue-400"
          />
          <ComponentBar
            label={`Posterior Confidence (${Math.round(breakdown.likelihood_score * 100)}%)`}
            value={breakdown.likelihood_pts}
            max={35}
            color="bg-indigo-400"
          />
          <ComponentBar
            label={`Urgency${breakdown.days_overdue != null && breakdown.days_overdue > 0 ? ` (${breakdown.days_overdue}d overdue)` : breakdown.days_until != null ? ` (${breakdown.days_until}d remaining)` : ''}`}
            value={breakdown.urgency_pts}
            max={5}
            color="bg-orange-400"
          />
        </div>
      )}

      {/* Likelihood features modal */}
      {showFeatures && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
          onClick={() => setShowFeatures(false)}
        >
          <div
            className="bg-white rounded-xl shadow-xl w-full max-w-sm p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-bold text-gray-900">Likelihood Model — 7 Features</h3>
              <button onClick={() => setShowFeatures(false)} className="text-gray-400 hover:text-gray-600 transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>
            <ul className="space-y-3">
              {LIKELIHOOD_FEATURES.map((f, i) => (
                <li key={f.name} className="flex gap-3">
                  <span className="flex-shrink-0 w-5 h-5 rounded-full bg-indigo-100 text-indigo-600
                                   text-xs font-bold flex items-center justify-center mt-0.5">
                    {i + 1}
                  </span>
                  <div>
                    <p className="text-xs font-semibold text-gray-800">{f.name}</p>
                    <p className="text-xs text-gray-500 mt-0.5">{f.description}</p>
                  </div>
                </li>
              ))}
            </ul>
            <p className="mt-4 text-xs text-gray-400 border-t border-gray-100 pt-3">
              Computed by the billing variance RandomForest model trained on provider claim history.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
