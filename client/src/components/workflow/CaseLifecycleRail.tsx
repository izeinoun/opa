// Shared workflow lifecycle stepper, driven by the backend Case Guidance Engine
// (server/app/services/case_guidance_service.py). Rendered horizontally on the
// PayGuard case page and vertically in the Assistant cockpit's left column.
// See docs/workflow-guidance-plan.md (Parts 2 & 5).
import { Check, AlertTriangle, Minus } from 'lucide-react'
import type { LifecycleStep, LifecycleStepState } from '../../types/guidance'

interface Props {
  steps: LifecycleStep[]
  orientation?: 'horizontal' | 'vertical'
  className?: string
}

const DOT: Record<LifecycleStepState, string> = {
  completed: 'bg-green-500 border-green-500 text-white',
  current:   'bg-[#FE017D] border-[#FE017D] text-white ring-4 ring-pink-100',
  blocked:   'bg-amber-500 border-amber-500 text-white ring-4 ring-amber-100',
  upcoming:  'bg-white border-gray-300 text-gray-400',
  skipped:   'bg-gray-50 border-dashed border-gray-300 text-gray-300',
}

const LABEL: Record<LifecycleStepState, string> = {
  completed: 'text-gray-500',
  current:   'text-[#FE017D] font-semibold',
  blocked:   'text-amber-700 font-semibold',
  upcoming:  'text-gray-400',
  skipped:   'text-gray-300 line-through',
}

const CONNECTOR: Record<LifecycleStepState, string> = {
  completed: 'bg-green-400',
  current:   'bg-gray-200',
  blocked:   'bg-gray-200',
  upcoming:  'bg-gray-200',
  skipped:   'bg-gray-100',
}

function Dot({ step, index }: { step: LifecycleStep; index: number }) {
  const cls = DOT[step.state]
  return (
    <div
      className={`flex items-center justify-center w-6 h-6 rounded-full border text-[11px] font-bold flex-shrink-0 ${cls}`}
      title={step.detail ?? undefined}
    >
      {step.state === 'completed' ? <Check className="w-3.5 h-3.5" />
        : step.state === 'blocked' ? <AlertTriangle className="w-3.5 h-3.5" />
        : step.state === 'skipped' ? <Minus className="w-3 h-3" />
        : index + 1}
    </div>
  )
}

export default function CaseLifecycleRail({ steps, orientation = 'horizontal', className = '' }: Props) {
  if (!steps?.length) return null

  if (orientation === 'vertical') {
    return (
      <ol className={`flex flex-col ${className}`}>
        {steps.map((step, i) => (
          <li key={step.key} className="flex gap-3">
            <div className="flex flex-col items-center">
              <Dot step={step} index={i} />
              {i < steps.length - 1 && (
                <div className={`w-px flex-1 my-1 ${CONNECTOR[step.state]}`} style={{ minHeight: 16 }} />
              )}
            </div>
            <div className="pb-3 -mt-0.5">
              <p className={`text-sm leading-6 ${LABEL[step.state]}`}>{step.label}</p>
              {step.detail && (
                <p className="text-xs text-amber-700 mt-0.5">{step.detail}</p>
              )}
            </div>
          </li>
        ))}
      </ol>
    )
  }

  // Horizontal
  return (
    <div className={`flex items-start ${className}`}>
      {steps.map((step, i) => (
        <div key={step.key} className="flex items-start flex-1 last:flex-none">
          <div className="flex flex-col items-center text-center" style={{ minWidth: 0 }}>
            <Dot step={step} index={i} />
            <p className={`text-xs mt-1.5 leading-tight px-1 ${LABEL[step.state]}`}>{step.label}</p>
            {step.detail && (
              <p className="text-[10px] text-amber-700 mt-0.5 px-1 leading-tight">{step.detail}</p>
            )}
          </div>
          {i < steps.length - 1 && (
            <div className={`h-px flex-1 mt-3 mx-1 ${CONNECTOR[step.state]}`} />
          )}
        </div>
      ))}
    </div>
  )
}
