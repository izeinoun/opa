// Phase-1 automation hint: the engine's recommended outcome (recoup /
// not-for-recoup / review) from likelihood + guardrails. Advisory — the
// analyst still confirms via Resolve.
import { Sparkles, ArrowRight } from 'lucide-react'
import type { SuggestedDecision } from '../../types'

const STYLE: Record<string, { box: string; label: string }> = {
  recoup:         { box: 'border-green-200 bg-green-50 text-green-800', label: 'Recoup it' },
  not_for_recoup: { box: 'border-gray-200 bg-gray-50 text-gray-700',   label: 'Not for recoup' },
  review:         { box: 'border-amber-200 bg-amber-50 text-amber-800', label: 'Manual review' },
}

// Only show while the case is still awaiting a decision.
const DECIDABLE = ['new', 'assigned', 'in_review', 'ready_for_notice']

interface Props {
  suggestion?: SuggestedDecision | null
  status: string
  onResolve?: () => void
}

export default function SuggestedDecisionBanner({ suggestion, status, onResolve }: Props) {
  if (!suggestion || !DECIDABLE.includes(status)) return null
  const s = STYLE[suggestion.recommendation] ?? STYLE.review
  return (
    <div className={`w-full flex items-center gap-2.5 px-4 py-2.5 mb-1 rounded-lg border text-sm ${s.box}`}>
      <Sparkles className="w-4 h-4 shrink-0" />
      <span className="flex-1">
        Suggested: <strong>{s.label}</strong> · confidence{' '}
        {Math.round((suggestion.confidence || 0) * 100)}% — {suggestion.reason}
      </span>
      {onResolve && (
        <button onClick={onResolve} className="inline-flex items-center gap-1 font-medium shrink-0 hover:underline">
          Resolve <ArrowRight className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  )
}
