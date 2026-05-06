import { useState } from 'react'
import { AlertTriangle, ChevronDown, ChevronRight } from 'lucide-react'
import type { PriorityBreakdown, LikelihoodBreakdown, ClaimFinding } from '../../types'
import LikelihoodBreakdownChart from './LikelihoodBreakdown'
import { formatCurrency } from '../../utils/formatUtils'

interface Props {
  priority: string
  priorityScore: number
  breakdown?: PriorityBreakdown
  likelihood?: LikelihoodBreakdown
  findings?: ClaimFinding[]
}

function ComponentBar({
  label, value, max, color, pill,
}: {
  label: string
  value: number
  max: number
  color: string
  pill?: React.ReactNode
}) {
  const pct = Math.min((value / max) * 100, 100)
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-gray-600 font-medium">{label}</span>
        <div className="flex items-center gap-1.5">
          {pill}
          <span className="font-semibold text-gray-800">{value.toFixed(1)} / {max} pts</span>
        </div>
      </div>
      <div className="w-full bg-gray-100 rounded-full h-2">
        <div
          className={`h-2 rounded-full transition-all ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

const BAND_COLOR: Record<string, string> = {
  HIGH:   'text-red-600',
  MEDIUM: 'text-yellow-600',
  LOW:    'text-green-600',
}

const BAND_DOT: Record<string, string> = {
  HIGH:   'bg-red-500',
  MEDIUM: 'bg-yellow-500',
  LOW:    'bg-green-500',
}

export default function PriorityScoreCard({ priority, priorityScore, breakdown, likelihood, findings = [] }: Props) {
  const [showLikelihood, setShowLikelihood] = useState(false)
  const scoreColor = BAND_COLOR[priority] ?? 'text-gray-700'
  const pct = Math.min(priorityScore, 100)

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 space-y-4">
      {/* Header */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
            Priority Score
          </span>
          <div className="flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full ${BAND_DOT[priority] ?? 'bg-gray-400'}`} />
            <span className={`text-sm font-bold ${scoreColor}`}>{priority}</span>
          </div>
        </div>
        <div className="flex items-end gap-2 mb-2">
          <span className={`text-2xl font-bold ${scoreColor}`}>{priorityScore.toFixed(1)}</span>
          <span className="text-xs text-gray-400 mb-1">/ 100</span>
        </div>
        <div className="w-full bg-gray-100 rounded-full h-2">
          <div
            className={`h-2 rounded-full transition-all ${priority === 'HIGH' ? 'bg-red-500' : priority === 'MEDIUM' ? 'bg-yellow-500' : 'bg-green-500'}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/* Override banner */}
      {breakdown?.urgency_override_applied && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-2 flex items-start gap-2">
          <AlertTriangle className="w-3 h-3 text-red-500 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-xs text-red-700 font-medium">Urgency Override Active</p>
            <p className="text-xs text-red-600 mt-0.5">
              {breakdown.days_overdue != null && breakdown.days_overdue > 0
                ? `This case is ${breakdown.days_overdue} day${breakdown.days_overdue !== 1 ? 's' : ''} past the compliance deadline. Priority forced to HIGH.`
                : breakdown.days_until != null && breakdown.days_until <= 5
                ? `Deadline in ${breakdown.days_until} day${breakdown.days_until !== 1 ? 's' : ''} — priority forced to HIGH regardless of score.`
                : 'Deadline breached — priority forced to HIGH regardless of likelihood score.'}
            </p>
          </div>
        </div>
      )}

      {/* Component breakdown */}
      {breakdown && (
        <div className="space-y-3">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            Component Breakdown
          </p>

          <ComponentBar
            label={`Amount at Risk (${formatCurrency(breakdown.amount_at_risk)})`}
            value={breakdown.amount_pts}
            max={40}
            color="bg-blue-400"
          />

          <ComponentBar
            label={`Likelihood (${Math.round(breakdown.likelihood_score * 100)}%)`}
            value={breakdown.likelihood_pts}
            max={40}
            color="bg-indigo-400"
          />

          <ComponentBar
            label={`Urgency${breakdown.days_overdue != null && breakdown.days_overdue > 0 ? ` (${breakdown.days_overdue}d overdue)` : breakdown.days_until != null && breakdown.days_until <= 5 ? ` (${breakdown.days_until}d remaining)` : ''}`}
            value={breakdown.urgency_pts}
            max={20}
            color={breakdown.urgency_override_applied ? 'bg-red-500' : 'bg-orange-400'}
            pill={
              breakdown.urgency_pts >= 19.9
                ? <span className="bg-red-100 text-red-700 text-xs font-bold px-1.5 py-0.5 rounded-full">MAX</span>
                : breakdown.urgency_override_applied
                ? <span className="bg-red-100 text-red-700 text-xs font-bold px-1.5 py-0.5 rounded-full">OVERRIDE</span>
                : undefined
            }
          />
        </div>
      )}

      {/* Collapsible likelihood detail */}
      {likelihood && (
        <div>
          <button
            onClick={() => setShowLikelihood(v => !v)}
            className="w-full flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700
                       transition-colors py-1 border-t border-gray-100 pt-3"
          >
            {showLikelihood ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            <span className="font-medium">
              Likelihood Detail — how {breakdown ? Math.round(breakdown.likelihood_score * 100) : '—'}% was computed
            </span>
          </button>
          {showLikelihood && (
            <div className="mt-2">
              <LikelihoodBreakdownChart breakdown={likelihood} findings={findings} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
