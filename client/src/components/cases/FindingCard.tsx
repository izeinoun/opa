import type { ClaimFinding } from '../../types'
import { formatCurrency } from '../../utils/formatUtils'
import { detectorLabel, DETECTOR_COMPONENT } from '../../utils/priorityUtils'

interface Props {
  finding: ClaimFinding
}

const DETECTOR_COLORS: Record<string, string> = {
  // Canonical short codes
  'DET-01': 'bg-red-100 text-red-800 border-red-200',
  'DET-02': 'bg-orange-100 text-orange-800 border-orange-200',
  'DET-03': 'bg-yellow-100 text-yellow-800 border-yellow-200',
  'DET-04': 'bg-blue-100 text-blue-800 border-blue-200',
  'DET-05': 'bg-purple-100 text-purple-800 border-purple-200',
  'DET-06': 'bg-pink-100 text-pink-800 border-pink-200',
  'DET-07': 'bg-indigo-100 text-indigo-800 border-indigo-200',
  'DET-08': 'bg-rose-100 text-rose-800 border-rose-200',
  'DET-09': 'bg-cyan-100 text-cyan-800 border-cyan-200',
  'DET-10': 'bg-teal-100 text-teal-800 border-teal-200',
  // Internal DB codes
  'DX_CPT_MISMATCH_V1':       'bg-purple-100 text-purple-800 border-purple-200',
  'UPCODING_V1':               'bg-yellow-100 text-yellow-800 border-yellow-200',
  'EXCESS_UNITS_V1':           'bg-pink-100 text-pink-800 border-pink-200',
  'BILLING_VARIANCE_V1':       'bg-blue-100 text-blue-800 border-blue-200',
  'DUPLICATE_CLAIM_V1':        'bg-red-100 text-red-800 border-red-200',
  'MULTI_LINE_COMPLEXITY_V1':  'bg-indigo-100 text-indigo-800 border-indigo-200',
  'POST_DEATH_V1':             'bg-rose-100 text-rose-800 border-rose-200',
  'RETRO_TERM_V1':             'bg-orange-100 text-orange-800 border-orange-200',
  'GENERAL_REVIEW_V1':         'bg-cyan-100 text-cyan-800 border-cyan-200',
}

const COMPONENT_LABEL: Record<string, string> = {
  cpt_risk_score:        'CPT Risk',
  dx_cpt_mismatch_score: 'DX/CPT Mismatch',
  billing_variance_score:'Billing Variance',
  claim_complexity_score:'Claim Complexity',
  provider_risk_tier:    'Provider Risk',
}

function confidenceLevel(score: number): { label: string; barColor: string } {
  if (score >= 0.8) return { label: 'High', barColor: 'bg-red-500' }
  if (score >= 0.6) return { label: 'Medium', barColor: 'bg-yellow-500' }
  return { label: 'Low', barColor: 'bg-green-500' }
}

export default function FindingCard({ finding }: Props) {
  const { label: confLabel, barColor } = confidenceLevel(finding.confidence_score)
  const detectorColor = DETECTOR_COLORS[finding.detector_code] ?? 'bg-gray-100 text-gray-800 border-gray-200'
  const componentKey  = DETECTOR_COMPONENT[finding.detector_code]
  const componentName = componentKey ? COMPONENT_LABEL[componentKey] : null

  return (
    <div className="border border-gray-200 rounded-lg p-4 bg-white shadow-sm">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-bold border ${detectorColor}`}>
            {finding.detector_code}
          </span>
          <span className="text-sm font-semibold text-gray-800">
            {detectorLabel(finding.detector_code)}
          </span>
          <span className="text-xs text-gray-500 italic">{finding.finding_type}</span>
          {componentName && (
            <span className="text-xs bg-[#1e3a5f]/10 text-[#1e3a5f] border border-[#1e3a5f]/20
                             px-2 py-0.5 rounded-full font-medium">
              drives {componentName}
            </span>
          )}
        </div>
        <span className="text-base font-bold text-gray-900 whitespace-nowrap">
          {formatCurrency(finding.overpayment_amount)}
        </span>
      </div>

      <p className="text-sm text-gray-600 mb-3">{finding.description}</p>

      <div>
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-gray-500">Confidence</span>
          <span className="text-xs font-medium text-gray-700">
            {confLabel} ({(finding.confidence_score * 100).toFixed(0)}%)
          </span>
        </div>
        <div className="w-full bg-gray-100 rounded-full h-1.5">
          <div
            className={`h-1.5 rounded-full ${barColor} transition-all`}
            style={{ width: `${finding.confidence_score * 100}%` }}
          />
        </div>
      </div>
    </div>
  )
}
