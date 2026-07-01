import { useState } from 'react'
import { Zap, ChevronDown, ChevronRight, AlertTriangle } from 'lucide-react'
import type { DetectorResult } from '../../types'
import { formatCurrency } from '../../utils/formatUtils'
import { formatDate } from '../../utils/dateUtils'
import FindingDisposition from './FindingDisposition'

// Keys to hide entirely (internal IDs, redundant context).
const HIDDEN_KEYS = new Set([
  'line_id', 'lob', 'total_overpayment',
  'claim_id', 'duplicate_claim_id', 'provider_id', 'member_id',
  'affected_line_ids',
])

// Friendly labels for known evidence keys.
const KEY_LABELS: Record<string, string> = {
  line_number: 'Line #',
  cpt_code: 'CPT',
  cpt_code_a: 'CPT A',
  cpt_code_b: 'CPT B',
  paid_amount: 'Paid',
  paid_a: 'Paid (A)',
  paid_b: 'Paid (B)',
  allowed_amount: 'Allowed',
  overpayment: 'Overpayment',
  duplicate_icn: 'Duplicate Claim #',
  duplicate_paid: 'Paid on Duplicate',
  original_paid: 'Paid on This Claim',
  overlapping_cpts: 'Overlapping CPTs',
  member_number: 'Member ID',
  member_lob: 'Member LOB',
  claim_lob: 'Claim LOB',
  claim_icn: 'Claim #',
  service_date: 'Service Date',
  plan_start_date: 'Plan Start Date',
  total_paid: 'Total Paid',
  provider_npi: 'Provider NPI',
  provider_name: 'Provider',
  exclusion_source: 'Exclusion Source',
  exclusion_effective_date: 'Exclusion Effective',
  units_billed: 'Units Billed',
  mue_limit: 'MUE Limit',
}

// Keys whose values are currency amounts.
const CURRENCY_KEYS = new Set([
  'paid_amount', 'allowed_amount', 'overpayment',
  'paid_a', 'paid_b', 'duplicate_paid', 'original_paid', 'total_paid',
])

function label(key: string): string {
  return KEY_LABELS[key] ?? key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function formatValue(key: string, val: unknown): React.ReactNode {
  if (val === null || val === undefined || val === '') return <span className="text-gray-400">—</span>
  if (Array.isArray(val)) return val.join(', ')
  if (typeof val === 'number' && CURRENCY_KEYS.has(key)) return formatCurrency(val)
  if (typeof val === 'boolean') return val ? 'Yes' : 'No'
  return String(val)
}

function isArrayOfObjects(val: unknown): val is Record<string, unknown>[] {
  return Array.isArray(val) && val.length > 0 && typeof val[0] === 'object' && val[0] !== null && !Array.isArray(val[0])
}

function EvidenceView({ evidence }: { evidence: Record<string, unknown> }) {
  const entries = Object.entries(evidence).filter(([k]) => !HIDDEN_KEYS.has(k))
  const scalarEntries = entries.filter(([, v]) => !isArrayOfObjects(v))
  const tableEntries  = entries.filter(([, v]) => isArrayOfObjects(v)) as [string, Record<string, unknown>[]][]

  return (
    <div className="mt-2 bg-gray-50 border border-gray-100 rounded-lg p-3 space-y-3 text-sm">
      {scalarEntries.length > 0 && (
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1.5">
          {scalarEntries.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-gray-500">{label(k)}</dt>
              <dd className="text-gray-900 font-medium">{formatValue(k, v)}</dd>
            </div>
          ))}
        </dl>
      )}

      {tableEntries.map(([k, rows]) => {
        const cols = Array.from(
          rows.reduce<Set<string>>((acc, row) => {
            Object.keys(row).forEach(c => { if (!HIDDEN_KEYS.has(c)) acc.add(c) })
            return acc
          }, new Set<string>())
        )
        return (
          <div key={k}>
            {scalarEntries.length > 0 && <div className="text-xs font-semibold text-gray-500 mb-1.5 uppercase tracking-wide">{label(k)}</div>}
            <div className="overflow-x-auto">
              <table className="min-w-full text-xs border border-gray-200 rounded">
                <thead className="bg-gray-100">
                  <tr>
                    {cols.map(c => (
                      <th key={c} className={`px-2 py-1.5 font-semibold text-gray-600 ${CURRENCY_KEYS.has(c) ? 'text-right' : 'text-left'}`}>
                        {label(c)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-100">
                  {rows.map((row, i) => (
                    <tr key={i}>
                      {cols.map(c => (
                        <td key={c} className={`px-2 py-1.5 ${CURRENCY_KEYS.has(c) ? 'text-right font-mono' : 'text-gray-800'}`}>
                          {formatValue(c, row[c])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )
      })}
    </div>
  )
}

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

function DetectorCard({ result, caseId, locked }: { result: DetectorResult; caseId: number; locked?: boolean }) {
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
                  : finding.finding_type === 'MEDIUM'
                  ? 'bg-yellow-50 text-yellow-700 border-yellow-200'
                  : 'bg-gray-50 text-gray-700 border-gray-200'
              }`}>
                Severity: {finding.finding_type.charAt(0) + finding.finding_type.slice(1).toLowerCase()}
              </span>
              {(finding as any).fwa_indicator && (finding as any).fwa_rule_code && (
                <span
                  title="Fraud / Waste / Abuse signal — flagged for SIU review"
                  className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-red-600 text-white"
                >
                  {(finding as any).fwa_rule_code}
                </span>
              )}
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
          {/* Phase 2: per-finding disposition controls + status badge */}
          <div id={`finding-${finding.id}`} className="mt-2 border-t border-gray-100 pt-2">
            <FindingDisposition finding={finding} caseId={caseId} locked={locked} />
          </div>

          {/* Dedup attribution notice — appears when finding's claim was suppressed by a higher-priority detector */}
          {finding.suppressed_amount !== undefined && finding.suppressed_amount > 0 && (
            <div className={`mt-2 flex items-start gap-2 px-3 py-2 rounded-lg border text-xs ${
              (finding.attributed_amount ?? 0) === 0
                ? 'bg-amber-50 border-amber-200 text-amber-800'
                : 'bg-blue-50 border-blue-200 text-blue-800'
            }`}>
              <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="font-semibold">
                  {(finding.attributed_amount ?? 0) === 0
                    ? 'Not counted in At Risk total'
                    : 'Partially counted in At Risk total'}
                  {' — needs analyst review'}
                </p>
                <p className="mt-0.5">
                  This finding claimed{' '}
                  <span className="font-mono font-semibold">{formatCurrency(finding.suppressed_amount)}</span>
                  {' '}on lines already attributed to {finding.superseded_by?.join(', ')} (higher dedup priority).
                  {(finding.attributed_amount ?? 0) > 0 && (
                    <> Only <span className="font-mono font-semibold">{formatCurrency(finding.attributed_amount ?? 0)}</span> contributed to the total.</>
                  )}
                  {' '}The underlying issue still warrants manual review.
                </p>
              </div>
            </div>
          )}

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
          {showEvidence && evidence && <EvidenceView evidence={evidence} />}
        </>
      ) : (
        <p className="text-xs text-gray-400 italic">No issues detected by this rule.</p>
      )}
    </div>
  )
}

interface Props {
  detectorResults: DetectorResult[]
  caseId: number
  locked?: boolean
  onRerun?: () => void
  isRerunning?: boolean
}

export default function DetectorResults({ detectorResults, caseId, locked, onRerun, isRerunning }: Props) {
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
          <DetectorCard key={r.detector_id} result={r} caseId={caseId} locked={locked} />
        ))}
        {detectorResults.length === 0 && (
          <p className="text-sm text-gray-400 italic">No detector data. Click Re-run to evaluate this claim.</p>
        )}
      </div>
    </div>
  )
}
