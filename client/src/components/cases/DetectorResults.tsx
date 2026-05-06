import { useState } from 'react'
import { Zap, ChevronDown, ChevronRight } from 'lucide-react'
import type { DetectorResult } from '../../types'
import { formatCurrency } from '../../utils/formatUtils'
import { formatDate } from '../../utils/dateUtils'

const DETECTOR_DESCRIPTION: Record<string, string> = {
  'DET-01': 'Checks for duplicate paid claim lines using provider, member, date of service, CPT code, place of service, and ICN logic.',
  'DET-02': "Identifies claims paid for dates of service after a member's retroactive coverage termination, accounting for grace periods.",
  'DET-04': "Flags paid amounts that exceed the contracted or allowable rate from the provider's fee schedule for the applicable line of business.",
  'DET-06': 'Identifies services billed with units exceeding Medicare MUE limits, or procedure code combinations that should be bundled per NCCI edits.',
  'DET-08': 'Detects claims paid to providers appearing on the OIG LEIE exclusion list or other exclusion sources, based on effective dates.',
  'DET-09': 'AI-assisted review using Claude to identify upcoding (billing higher complexity than documented) and unbundling (splitting components that should be billed together).',
}

const DETECTOR_COLOR: Record<string, string> = {
  'DET-01': 'bg-red-100 text-red-800 border-red-200',
  'DET-02': 'bg-orange-100 text-orange-800 border-orange-200',
  'DET-04': 'bg-blue-100 text-blue-800 border-blue-200',
  'DET-06': 'bg-pink-100 text-pink-800 border-pink-200',
  'DET-08': 'bg-rose-100 text-rose-800 border-rose-200',
  'DET-09': 'bg-purple-100 text-purple-800 border-purple-200',
}

function DetectorCard({ result }: { result: DetectorResult }) {
  const [showEvidence, setShowEvidence] = useState(false)
  const { fired, finding, detector_id, detector_name } = result
  const badgeColor = DETECTOR_COLOR[detector_id] ?? 'bg-gray-100 text-gray-700 border-gray-200'
  const desc = DETECTOR_DESCRIPTION[detector_id] ?? 'No description available.'

  let evidence: Record<string, unknown> | null = null
  if (finding?.evidence_json) {
    try { evidence = JSON.parse(finding.evidence_json) } catch { evidence = null }
  }

  return (
    <div className={`bg-white rounded-xl border border-gray-200 shadow-sm p-4
                     border-l-4 ${fired ? 'border-l-amber-400' : 'border-l-green-300'} ${!fired ? 'opacity-80' : ''}`}>
      {/* Header */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-bold border ${badgeColor}`}>
            {detector_id}
          </span>
          <span className="text-sm font-semibold text-gray-800">{detector_name}</span>
          {finding && (
            <>
              <span className={`text-xs px-1.5 py-0.5 rounded border font-medium ${
                finding.finding_type === 'HIGH'
                  ? 'bg-red-50 text-red-700 border-red-200'
                  : 'bg-yellow-50 text-yellow-700 border-yellow-200'
              }`}>
                {finding.finding_type}
              </span>
              <span className="text-xs text-gray-400">
                Confidence: {Math.round(finding.confidence_score * 100)}%
              </span>
            </>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {fired ? (
            <>
              <span className="bg-red-100 text-red-700 text-xs font-bold px-2 py-0.5 rounded-full">
                FIRED
              </span>
              {finding && (
                <span className="text-base font-bold text-[#1e3a5f]">
                  {formatCurrency(finding.overpayment_amount)}
                </span>
              )}
            </>
          ) : (
            <span className="bg-green-100 text-green-700 text-xs font-medium px-2 py-0.5 rounded-full">
              CLEAR
            </span>
          )}
        </div>
      </div>

      {/* Always-shown description */}
      <p className="text-xs text-gray-500 mt-1 mb-2">{desc}</p>

      {fired && finding ? (
        <>
          <p className="text-sm text-gray-700 mt-2 border-t border-gray-100 pt-2">{finding.description}</p>
          <div className="flex items-center justify-between mt-3 text-xs text-gray-400">
            <span>Fired: {formatDate(finding.created_at)}</span>
            {evidence && (
              <button
                onClick={() => setShowEvidence(v => !v)}
                className="flex items-center gap-1 text-indigo-600 hover:text-indigo-800 transition-colors font-medium"
              >
                {showEvidence ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                {showEvidence ? 'Hide Evidence' : 'Show Evidence'}
              </button>
            )}
          </div>
          {showEvidence && evidence && (
            <pre className="mt-2 bg-gray-50 border border-gray-100 rounded-lg p-3
                            font-mono text-xs text-gray-700 overflow-x-auto whitespace-pre-wrap">
              {JSON.stringify(evidence, null, 2)}
            </pre>
          )}
        </>
      ) : (
        <p className="text-xs text-gray-400 italic">No issues detected by this rule.</p>
      )}
    </div>
  )
}

interface Props {
  detectorResults: DetectorResult[]
  onRerun?: () => void
  isRerunning?: boolean
}

export default function DetectorResults({ detectorResults, onRerun, isRerunning }: Props) {
  const firedCount = detectorResults.filter(d => d.fired).length
  const totalCount = detectorResults.length

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Zap className="w-4 h-4 text-teal-600" />
          <span className="text-sm font-semibold text-[#1e3a5f]">Detector Results</span>
          {firedCount > 0 ? (
            <span className="bg-red-100 text-red-700 text-xs px-2 py-0.5 rounded-full font-medium">
              {firedCount} fired / {totalCount} run
            </span>
          ) : (
            <span className="bg-green-100 text-green-700 text-xs px-2 py-0.5 rounded-full font-medium">
              0 fired / {totalCount} run
            </span>
          )}
        </div>
        {onRerun && (
          <button
            onClick={onRerun}
            disabled={isRerunning}
            className="text-xs text-indigo-600 hover:text-indigo-800 disabled:opacity-50
                       flex items-center gap-1 transition-colors font-medium"
          >
            {isRerunning ? 'Running…' : '↺ Re-run'}
          </button>
        )}
      </div>
      <div className="space-y-3">
        {detectorResults.map(r => (
          <DetectorCard key={r.detector_id} result={r} />
        ))}
        {detectorResults.length === 0 && (
          <p className="text-sm text-gray-400 italic">No detector data. Click Re-run to evaluate this claim.</p>
        )}
      </div>
    </div>
  )
}
