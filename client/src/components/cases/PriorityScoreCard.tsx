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

interface FiredDetector {
  detector_id: string
  detector_name?: string
  confidence: number
}

interface Props {
  priority: string
  priorityScore: number
  breakdown?: PriorityBreakdown
  firedDetectors?: FiredDetector[]
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

export default function PriorityScoreCard({ priority, priorityScore, breakdown, firedDetectors = [] }: Props) {
  const [showBreakdown, setShowBreakdown] = useState(false)
  const [showFeatures,  setShowFeatures]  = useState(false)
  const [showEvidence,  setShowEvidence]  = useState(false)
  const pct = Math.min(priorityScore, 100)

  // Walk the noisy-OR ("fill the glass") step-by-step so the modal can show the
  // math. Mirrors backend _compute_evidence_score: seed at the leak floor L, then
  // each rule pours in its confidence-share of the room still left to 100%.
  const leak = breakdown?.rule_leak ?? 0.03
  const evidenceSteps: { detector_id: string; confidence: number; before: number; after: number }[] = []
  const det08Fired = firedDetectors.some(d => d.detector_id === 'DET-08')
  if (breakdown && !det08Fired && firedDetectors.length > 0) {
    let p = leak
    for (const f of firedDetectors) {
      const after = p + (1 - p) * f.confidence
      evidenceSteps.push({ detector_id: f.detector_id, confidence: f.confidence, before: p, after })
      p = after
    }
  }

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

        {/* Evidence Score (was Posterior) */}
        {breakdown && (
          <div className="rounded-lg p-3 border border-gray-200">
            <div className="flex items-center justify-between mb-1">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Evidence</p>
              <button
                onClick={() => setShowEvidence(true)}
                className="text-gray-400 hover:text-indigo-500 transition-colors"
                aria-label="How was the evidence score calculated?"
              >
                <Info className="w-3 h-3" />
              </button>
            </div>
            <div className="flex items-baseline gap-1 mb-2">
              <span className={`text-xl font-bold ${scoreColor(breakdown.evidence_score)}`}>
                {Math.round(breakdown.evidence_score * 100)}%
              </span>
            </div>
            <div className="w-full bg-gray-100 rounded-full h-1.5">
              <div
                className={`h-1.5 rounded-full transition-all ${scoreBar(breakdown.evidence_score)}`}
                style={{ width: `${Math.round(breakdown.evidence_score * 100)}%` }}
              />
            </div>
            <p className="text-xs text-gray-400 mt-1.5">From rules</p>
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
            <p className="text-xs text-gray-400 mt-1.5">ML screen</p>
          </div>
        )}
      </div>

      {/* Model–rule disagreement banner */}
      {breakdown?.disagreement && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
          <span className="mt-0.5 text-amber-500">⚑</span>
          <p className="text-xs text-amber-800 leading-relaxed">
            <span className="font-semibold">Model–rule disagreement.</span> The ML prior is high
            ({Math.round(breakdown.prior_score * 100)}%) but the rules found essentially nothing
            (evidence {Math.round(breakdown.evidence_score * 100)}%). Worth a human look — either a
            missed issue or a rule-coverage gap.
          </p>
        </div>
      )}

      {/* Collapsible component bars under Priority */}
      {breakdown && showBreakdown && (
        <div className="border-t border-gray-100 pt-3 space-y-3">
          <ComponentBar
            label={`Severity — EMV (${formatCurrency(breakdown.emv)})`}
            value={breakdown.severity_pts}
            max={95}
            color="bg-blue-400"
          />
          <p className="text-[11px] text-gray-400 -mt-1.5 pl-0.5">
            = Evidence {Math.round(breakdown.evidence_score * 100)}% × Amount {formatCurrency(breakdown.amount_at_risk)} = {formatCurrency(breakdown.emv)} expected
          </p>
          <ComponentBar
            label={`Urgency${breakdown.days_overdue != null && breakdown.days_overdue > 0 ? ` (${breakdown.days_overdue}d overdue)` : breakdown.days_until != null ? ` (${breakdown.days_until}d remaining)` : ''}`}
            value={breakdown.urgency_pts}
            max={5}
            color="bg-orange-400"
          />
        </div>
      )}

      {/* Evidence-score explanation modal */}
      {showEvidence && breakdown && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
          onClick={() => setShowEvidence(false)}
        >
          <div
            className="bg-white rounded-xl shadow-xl w-full max-w-md p-5 max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold text-gray-900">How was the Evidence score calculated?</h3>
              <button onClick={() => setShowEvidence(false)} className="text-gray-400 hover:text-gray-600 transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-xs text-gray-600 leading-relaxed">
              Evidence measures how sure the <span className="font-semibold">rules</span> are that a real
              issue exists — pure corroboration, independent of the ML prior. Picture filling a glass: it
              starts a little full at the <span className="font-semibold">leak floor (L = {Math.round(leak * 100)}%)</span>,
              and each fired rule pours in its confidence-share of the room still left to 100%. More
              corroborating rules → higher evidence, so it can exceed any single rule's confidence.
            </p>

            <div className="mt-4 text-xs">
              <p className="font-semibold text-gray-700 mb-2">For this case:</p>

              {det08Fired ? (
                <div className="bg-rose-50 border border-rose-100 rounded-lg p-3 space-y-1">
                  <p className="text-rose-700 font-semibold">DET-08 (Excluded Provider) fired</p>
                  <p className="text-gray-700">
                    Evidence is pinned at <span className="font-bold">98%</span> — payments to OIG-excluded
                    providers are a hard compliance fact, not a probability.
                  </p>
                </div>
              ) : firedDetectors.length === 0 ? (
                <div className="bg-amber-50 border border-amber-100 rounded-lg p-3 space-y-1">
                  <p className="text-amber-700 font-semibold">No rules fired</p>
                  <p className="text-gray-700">
                    Evidence sits at the leak floor <span className="font-bold">{Math.round(leak * 100)}%</span> —
                    nothing was poured in. The ML prior does not prop this up.
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="flex items-center justify-between bg-gray-50 rounded px-3 py-2">
                    <span className="text-gray-600">Start — leak floor (L)</span>
                    <span className="font-mono font-bold text-gray-900">
                      {Math.round(leak * 100)}%
                    </span>
                  </div>

                  {evidenceSteps.map((s) => (
                    <div key={s.detector_id} className="border border-gray-100 rounded-lg p-2.5 space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-gray-800">
                          + {s.detector_id} fired
                        </span>
                        <span className="text-gray-500">confidence {Math.round(s.confidence * 100)}%</span>
                      </div>
                      <p className="font-mono text-[11px] text-gray-700 bg-gray-50 rounded px-2 py-1">
                        {Math.round(s.before * 100)}% + {Math.round(s.confidence * 100)}% of the{' '}
                        {Math.round((1 - s.before) * 100)}% room
                        {' '}= <span className="font-bold text-gray-900">{Math.round(s.after * 100)}%</span>
                      </p>
                    </div>
                  ))}

                  <div className="flex items-center justify-between bg-indigo-50 border border-indigo-100 rounded px-3 py-2 mt-2">
                    <span className="text-indigo-700 font-semibold">Evidence</span>
                    <span className="font-mono font-bold text-indigo-700">
                      {Math.round(breakdown.evidence_score * 100)}%
                    </span>
                  </div>
                </div>
              )}
            </div>

            {/* EMV — how evidence turns into priority */}
            <div className="mt-4 text-xs bg-blue-50 border border-blue-100 rounded-lg p-3 space-y-1">
              <p className="font-semibold text-blue-800">Severity = Expected Value (EMV)</p>
              <p className="text-gray-700 font-mono text-[11px]">
                {Math.round(breakdown.evidence_score * 100)}% × {formatCurrency(breakdown.amount_at_risk)} ={' '}
                <span className="font-bold">{formatCurrency(breakdown.emv)}</span>
              </p>
              <p className="text-gray-600">
                Evidence × amount-at-risk is the expected recoverable value — what actually drives Priority.
              </p>
            </div>

            <div className="mt-4 text-xs text-gray-500 border-t border-gray-100 pt-3 space-y-1">
              <p className="font-semibold text-gray-600">Edge cases</p>
              <p>• DET-08 (Excluded Provider) → evidence pinned at 98%, no update.</p>
              <p>• No rules fired → evidence = leak floor L ({Math.round(leak * 100)}%); the prior is excluded.</p>
              <p>• Informational findings ($0, e.g. coding warnings) don't add evidence.</p>
            </div>
          </div>
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
