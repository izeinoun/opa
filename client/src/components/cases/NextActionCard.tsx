// Prominent "what to do next" card for the case page, driven by the Case
// Guidance Engine's next_action. Sits at the top of the right rail, above
// CaseActions. See docs/workflow-guidance-plan.md (Part 2B).
import { ArrowRight, Clock } from 'lucide-react'
import type { NextAction } from '../../types/guidance'

interface Props {
  action: NextAction
  onAct: (action: NextAction) => void
}

export default function NextActionCard({ action, onAct }: Props) {
  const actionable = action.actionable !== false

  return (
    <div className="rounded-xl border border-pink-200 bg-gradient-to-br from-pink-50 to-white shadow-sm p-4">
      <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-[#FE017D]">
        {actionable ? <ArrowRight className="w-3.5 h-3.5" /> : <Clock className="w-3.5 h-3.5" />}
        Next step
      </p>
      <p className="mt-1.5 text-sm font-bold text-gray-900">{action.label}</p>
      <p className="mt-1 text-xs text-gray-600 leading-relaxed">{action.explanation}</p>
      {actionable && (
        <button
          onClick={() => onAct(action)}
          className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-[#FE017D] hover:bg-pink-600 rounded-lg transition-colors"
        >
          {action.label}
          <ArrowRight className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  )
}
