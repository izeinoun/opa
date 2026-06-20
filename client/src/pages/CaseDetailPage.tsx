import { useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  ArrowLeft, ChevronDown, Send, RotateCcw,
  User, FileText, AlertTriangle, Code2, X,
} from 'lucide-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCase } from '../hooks/useCase'
import api from '../services/api'
import PriorityBadge from '../components/common/PriorityBadge'
import StatusBadge from '../components/common/StatusBadge'
import DeadlineIndicator from '../components/common/DeadlineIndicator'
import AuditTimeline from '../components/cases/AuditTimeline'
import DetectorResults from '../components/cases/DetectorResults'
import PriorityScoreCard from '../components/cases/PriorityScoreCard'
import CaseActions from '../components/cases/CaseActions'
import CaseNotes from '../components/cases/CaseNotes'
import CloseCaseModal from '../components/cases/CloseCaseModal'
import SupervisorDecisionModal from '../components/cases/SupervisorDecisionModal'
import RecoupmentsPanel from '../components/cases/RecoupmentsPanel'
import ContactLog from '../components/cases/ContactLog'
import AtRiskOverrideButton from '../components/cases/AtRiskOverrideButton'
import EvidencePanel from '../components/cases/EvidencePanel'
import EvidenceIssuesBanner from '../components/cases/EvidenceIssuesBanner'
import RecoupmentLetterPanel from '../components/cases/RecoupmentLetterPanel'
import EscalateToSIUModal from '../components/cases/EscalateToSIUModal'
import NoticeLetterViewerModal from '../components/cases/NoticeLetterViewerModal'
import { useCurrentUser } from '../hooks/useCurrentUser'
import SendNoticeModal from '../components/letters/SendNoticeModal'
import { formatCurrency } from '../utils/formatUtils'
import { formatDate, formatDateShort } from '../utils/dateUtils'
import { card, detectorBadge } from '../utils/designSystem'
import { appUrl } from '../config/appUrls'
import type {
  CaseStatus, CaseDetail, ClaimFinding, ERATransaction, ERAPaymentLine, Member, Provider, ClaimLine,
  DetectorResult, PriorityBreakdown,
} from '../types'

const VALID_TRANSITIONS: Partial<Record<CaseStatus, CaseStatus[]>> = {
  new:                      ['assigned'],
  assigned:                 ['in_review', 'new'],
  in_review:                ['pending_supervisor', 'notice_sent', 'closed_no_overpayment'],
  pending_supervisor:       ['notice_sent', 'closed_no_overpayment', 'closed_overturned', 'in_review'],
  notice_sent:              ['provider_responded', 'reconciling'],
  provider_responded:       ['reconciling', 'closed_overturned', 'closed_no_overpayment'],
  reconciling:              ['closed_recovered', 'closed_written_off', 'closed_overturned'],
  identified:               ['assigned'],
  pending_dispute:          ['in_review', 'reconciling'],
  pending_provider_response:['provider_responded', 'reconciling'],
  closed_recovered:         [],
  closed_written_off:       [],
  closed_overturned:        [],
  closed_no_overpayment:    [],
  closed_unrecoverable:     [],
}

const STATUS_LABELS: Record<string, string> = {
  new:                      'New',
  assigned:                 'Assigned',
  in_review:                'In Review',
  ready_for_notice:         'Ready for Notice',
  pending_supervisor:       'Pending Supervisor',
  notice_sent:              'Notice Sent',
  provider_responded:       'Provider Responded',
  reconciling:              'Reconciling',
  identified:               'Identified',
  pending_dispute:          'Pending Dispute',
  pending_provider_response:'Pending Provider Response',
  closed_recovered:         'Closed — Recovered',
  closed_written_off:       'Closed — Written Off',
  closed_overturned:        'Closed — Overturned',
  closed_no_overpayment:    'Closed — No Overpayment',
  closed_unrecoverable:     'Closed — Unrecoverable',
}

interface RichClaim {
  id: number; claim_number: string; lob: string
  total_billed: number; total_allowed: number; total_paid: number
  status: string; service_date_start: string
  member?: Member; rendering_provider?: Provider
  provider_org_id?: string; provider_org_name?: string
  primary_icd?: string | null
  other_icd_codes?: string[]
  drg?: string | null
  bill_type?: string | null
  claim_form_type?: string | null
  care_setting?: string | null
  pos_code?: string | null
  lines?: ClaimLine[]; findings?: ClaimFinding[]; era_transactions?: ERATransaction[]
}
type RichCaseDetail = Omit<CaseDetail, 'claim'> & { claim: RichClaim }
type TabKey = 'overview' | 'notes' | 'evidence' | 'disputes' | 'era' | 'output'

const TAB_DEFS: { key: TabKey; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'notes',    label: 'Notes' },
  { key: 'evidence', label: 'Evidence' },
  { key: 'disputes', label: 'Disputes' },
  { key: 'era',      label: '835/ERA' },
  { key: 'output',   label: 'Output' },
]

// CAS reason code lookup — subset of the most common X12 835 codes
const CAS_REASON: Record<string, string> = {
  '1':  'Deductible',
  '2':  'Coinsurance',
  '3':  'Co-pay',
  '4':  'The service is not covered',
  '45': 'Charge exceeds fee schedule',
  '97': 'Payment included in allowance for another service',
  'CO-45': 'Charge exceeds fee schedule / contracted rate',
  'PR-1':  'Deductible',
  'PR-2':  'Coinsurance',
  'OA-23': 'Payment adjusted per utilization guidelines',
}

function ERA835Card({ txn }: { txn: ERATransaction }) {
  const isReversal = txn.transaction_type === 'reversal'
  const amountColor = txn.payment_amount < 0 ? 'text-red-600' : 'text-green-700'
  const [showRaw, setShowRaw] = useState(false)

  const formatted = txn.raw_835?.startsWith('ISA')
    ? txn.raw_835.replace(/~/g, '~\n').trim()
    : null

  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="bg-gray-50 border-b border-gray-200 px-4 py-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="font-mono text-sm font-semibold text-gray-900">{txn.era_number}</span>
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium border ${
            isReversal
              ? 'bg-red-50 text-red-700 border-red-200'
              : 'bg-green-50 text-green-700 border-green-200'
          }`}>
            {txn.transaction_type.charAt(0).toUpperCase() + txn.transaction_type.slice(1)}
          </span>
        </div>
        <div className="flex items-center gap-5 text-sm">
          <span className="text-gray-500">Payer: <span className="font-medium text-gray-800">{txn.payer_name}</span></span>
          <span className="text-gray-500">Date: <span className="font-medium text-gray-800">{formatDate(txn.payment_date)}</span></span>
          <span className="text-gray-500">Claims: <span className="font-medium text-gray-800">{txn.claim_count}</span></span>
          <span className={`text-base font-bold ${amountColor}`}>{formatCurrency(txn.payment_amount)}</span>
          {formatted && (
            <button
              onClick={() => setShowRaw(true)}
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-600 hover:text-indigo-800 transition-colors"
            >
              <Code2 className="w-3.5 h-3.5" />
              View 835
            </button>
          )}
        </div>
      </div>

      {/* Raw 835 modal */}
      {showRaw && formatted && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
          onClick={() => setShowRaw(false)}
        >
          <div
            className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl flex flex-col"
            style={{ maxHeight: '85vh' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex-shrink-0 flex items-center justify-between px-5 py-4 border-b border-gray-100">
              <div className="flex items-center gap-2">
                <Code2 className="w-4 h-4 text-indigo-500" />
                <h3 className="text-sm font-bold text-gray-900">Raw X12 835 — {txn.era_number}</h3>
              </div>
              <button onClick={() => setShowRaw(false)} className="text-gray-400 hover:text-gray-600 transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto bg-gray-50 rounded-b-2xl">
              <pre className="px-5 py-4 font-mono text-xs text-gray-700 leading-6 whitespace-pre-wrap break-all">
                {formatted}
              </pre>
            </div>
          </div>
        </div>
      )}


      {/* Payment lines */}
      {txn.payments.length > 0 && (
        <table className="min-w-full text-sm">
          <thead className="bg-white border-b border-gray-100">
            <tr className="text-xs text-gray-400 uppercase tracking-wider">
              <th className="px-4 py-2.5 text-left">Claim ICN</th>
              <th className="px-4 py-2.5 text-left">CPT</th>
              <th className="px-4 py-2.5 text-left">DOS</th>
              <th className="px-4 py-2.5 text-left">Check #</th>
              <th className="px-4 py-2.5 text-left">Adj. Reason</th>
              <th className="px-4 py-2.5 text-right">Adjustment</th>
              <th className="px-4 py-2.5 text-right">Paid</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {txn.payments.map((p) => {
              const reasonLabel = p.adjustment_reason_code
                ? (CAS_REASON[p.adjustment_reason_code] ?? p.adjustment_reason_code)
                : '—'
              return (
                <tr key={p.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-2.5 font-mono text-gray-700">{p.claim_icn}</td>
                  <td className="px-4 py-2.5 font-mono font-semibold text-gray-900">{p.cpt_code}</td>
                  <td className="px-4 py-2.5 text-gray-600">{p.service_date ? formatDateShort(p.service_date) : '—'}</td>
                  <td className="px-4 py-2.5 font-mono text-gray-500">{p.check_number ?? '—'}</td>
                  <td className="px-4 py-2.5 text-gray-600">
                    {p.adjustment_reason_code && (
                      <span className="inline-flex items-center gap-1.5">
                        <span className="font-mono text-xs bg-gray-100 text-gray-700 px-1.5 py-0.5 rounded">
                          {p.adjustment_reason_code}
                        </span>
                        <span className="text-gray-500">{reasonLabel}</span>
                      </span>
                    )}
                    {!p.adjustment_reason_code && '—'}
                  </td>
                  <td className="px-4 py-2.5 text-right text-amber-700 font-medium">
                    {p.adjustment_amount !== 0 ? formatCurrency(p.adjustment_amount) : '—'}
                  </td>
                  <td className="px-4 py-2.5 text-right font-semibold text-gray-900">
                    {formatCurrency(p.paid_amount)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}

function EscalationBanner({
  caseSeq, esc, canResolve,
}: { caseSeq: number; esc: { reason?: string | null; escalated_at?: string | null; escalated_by_full_name?: string | null }; canResolve: boolean }) {
  const qc = useQueryClient()
  const [resolving, setResolving] = useState(false)
  const resolveMut = useMutation({
    mutationFn: async () => (await api.post(`/cases/${caseSeq}/escalate/resolve`, {})).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['case', caseSeq] }),
  })
  return (
    <div className="bg-orange-500 border-l-4 border-orange-700 text-white rounded-xl px-4 py-3 flex items-start gap-3 shadow-md">
      <AlertTriangle className="w-5 h-5 flex-shrink-0 mt-0.5" />
      <div className="flex-1">
        <p className="text-sm font-bold">⚠ Escalated to supervisor</p>
        <p className="text-xs mt-0.5 text-orange-50">
          {esc.escalated_by_full_name ?? 'Someone'}
          {esc.escalated_at ? ` · ${formatDate(esc.escalated_at)}` : ''}
        </p>
        {esc.reason && (
          <p className="text-sm mt-1.5 italic text-orange-50">"{esc.reason}"</p>
        )}
      </div>
      {canResolve && (
        <button
          onClick={() => { setResolving(true); resolveMut.mutate() }}
          disabled={resolving || resolveMut.isPending}
          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold bg-white text-orange-700 hover:bg-orange-50 rounded-lg disabled:opacity-60"
        >
          {resolveMut.isPending ? 'Resolving…' : 'Mark resolved'}
        </button>
      )}
    </div>
  )
}


function SectionHeader({ icon: Icon, label }: { icon: React.ElementType; label: string }) {
  return (
    <h2 className="flex items-center gap-2 text-xs font-semibold text-gray-500 uppercase tracking-wider mb-4">
      <Icon className="w-3.5 h-3.5" />
      {label}
    </h2>
  )
}

export default function CaseDetailPage() {
  const { caseId } = useParams<{ caseId: string }>()
  const navigate = useNavigate()
  const id = parseInt(caseId ?? '0', 10)  // case_sequence integer
  const { currentUser } = useCurrentUser()
  const isSupervisor = currentUser?.role === 'supervisor' || currentUser?.role === 'admin'

  const { data: caseData, isLoading, error, mutateTransition, mutateReopen } = useCase(id)
  const qc = useQueryClient()

  const rerunMutation = useMutation({
    mutationFn: async () => (await api.post(`/cases/${id}/rerun-detectors`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['case', id] }),
  })

  const { data: analysts = [] } = useQuery<{ id: string; full_name: string; role: string }[]>({
    queryKey: ['analysts'],
    queryFn: async () => {
      const res = await api.get<{ id: string; full_name: string; role: string; is_active: boolean }[]>('/admin/users')
      return res.data.filter((u) => u.role === 'analyst' && u.is_active)
    },
    staleTime: 5 * 60 * 1000,
  })

  const assignMutation = useMutation({
    mutationFn: (analyst_id: string | null) =>
      api.patch(`/cases/${id}/assign`, { analyst_id }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['case', id] }),
  })

  const [activeTab,           setActiveTab]           = useState<TabKey>('overview')
  const [showSendNotice,      setShowSendNotice]      = useState(false)
  const [showCloseCase,       setShowCloseCase]       = useState(false)
  const [supervisorMode,      setSupervisorMode]      = useState<'approve' | 'reject' | null>(null)
  const [showNoticeViewer,    setShowNoticeViewer]    = useState(false)
  const [showEscalateToSIU,   setShowEscalateToSIU]   = useState(false)

  if (isLoading) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-8 bg-white rounded-xl border border-gray-200 w-1/4" />
        <div className="h-40 bg-white rounded-xl border border-gray-200" />
        <div className="h-64 bg-white rounded-xl border border-gray-200" />
      </div>
    )
  }

  if (error || !caseData) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <AlertTriangle className="w-8 h-8 text-red-400 mx-auto mb-2" />
          <p className="text-gray-900 font-medium">Failed to load case</p>
          <button onClick={() => navigate('/worklist')}
            className="mt-3 text-sm text-[#FE017D] hover:underline">
            Back to Worklist
          </button>
        </div>
      </div>
    )
  }

  const case_  = caseData as unknown as RichCaseDetail
  const claim  = case_.claim

  return (
    <div className="flex flex-col gap-5">
      {/* Back */}
      <button onClick={() => navigate('/worklist')}
        className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-900 w-fit transition-colors">
        <ArrowLeft className="w-4 h-4" />Back to Worklist
      </button>

      {/* Escalation banner — prominent when active */}
      {case_.escalation?.is_active && (
        <EscalationBanner caseSeq={case_.id} esc={case_.escalation} canResolve={isSupervisor} />
      )}

      {/* Header card */}
      <div className={card}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wider">Case Number</p>
            <div className="flex items-baseline gap-3 mt-0.5">
              <h1 className="text-base font-bold font-mono text-gray-900">{case_.case_number}</h1>
              {claim?.member?.name && (
                <span className="text-sm text-gray-500 font-medium">{claim.member.name}</span>
              )}
            </div>
            <div className="flex items-center flex-wrap gap-2 mt-2">
              <PriorityBadge priority={case_.priority} />
              <StatusBadge status={case_.status} />
              {case_.escalation?.is_active && (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-orange-500 text-white animate-pulse">
                  ⚠ ESCALATED
                </span>
              )}
              {(case_.detector_results ?? [])
                .filter((d) => d.fired)
                .map((d) => (
                  <span key={d.detector_id} className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-bold ${detectorBadge[d.detector_id] ?? 'bg-gray-100 text-gray-600'}`}>
                    {d.detector_id}
                  </span>
                ))
              }
            </div>
          </div>

          {/* Legacy "Assign to Me" / "Transition" / "Reopen" buttons removed —
              all of these actions now live in the right-rail Actions panel. */}
        </div>

        <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-sm text-gray-600 border-t border-gray-100 pt-4">
          <div className="flex flex-col gap-y-1.5">
            <span><span className="text-gray-400">Opened:</span> <strong className="text-gray-900">{formatDate(case_.opened_at)}</strong></span>
            <span className="flex items-center gap-2">
              <span className="text-gray-400">Assignee:</span>
              <select
                value={case_.assignee?.id ?? ''}
                onChange={(e) => assignMutation.mutate(e.target.value || null)}
                disabled={assignMutation.isPending}
                className="text-sm font-medium text-gray-900 bg-transparent border-b border-dashed
                           border-gray-300 hover:border-[#FE017D] focus:border-[#FE017D]
                           focus:outline-none cursor-pointer disabled:opacity-60 transition-colors
                           pr-1 py-0.5"
              >
                <option value="">Unassigned</option>
                {analysts.map((a) => (
                  <option key={a.id} value={a.id}>{a.full_name}</option>
                ))}
              </select>
            </span>
          </div>
          <span><span className="text-gray-400">Deadline:</span> <DeadlineIndicator deadline={case_.deadline} showDays /></span>
          <span><span className="text-gray-400">At Risk:</span> <strong className="text-gray-900">{formatCurrency(case_.amount_at_risk)}</strong></span>
        </div>
      </div>

      {/* (Legacy Transition / Reopen modals removed — Actions panel + ReopenInline + SupervisorDecisionModal handle these now) */}

      {/* Phase 2 — Needs Review banner */}
      {(() => {
        const needsReviewFindings = (case_.detector_results ?? [])
          .filter((d: any) => d.finding?.disposition_status === 'needs_review')
        if (needsReviewFindings.length === 0) return null
        const scrollToFinding = () => {
          const f = needsReviewFindings[0]?.finding
          if (!f) return
          const el = document.getElementById(`finding-${f.id}`)
          el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
        }
        return (
          <div className="bg-amber-50 border border-amber-300 rounded-xl p-4 flex items-start gap-3 mb-5">
            <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-semibold text-amber-900">
                {needsReviewFindings.length === 1
                  ? '1 finding needs your review before this case can move forward'
                  : `${needsReviewFindings.length} findings need your review before this case can move forward`}
              </p>
              <p className="text-xs text-amber-800 mt-0.5">
                AI-assisted detector results with medium confidence require explicit accept or reject.
              </p>
            </div>
            <button
              onClick={scrollToFinding}
              className="px-3 py-1.5 text-xs font-semibold bg-amber-600 hover:bg-amber-700 text-white rounded-lg transition-colors"
            >
              Jump to it
            </button>
          </div>
        )
      })()}

      {/* Top tabs — promoted from the bottom of the page so secondary
          panels (Evidence/Notes/Disputes/835) aren't hidden below the
          two-column overview. */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden mb-5">
        <div className="flex border-b border-gray-100">
          {TAB_DEFS.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={`px-5 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === key
                  ? 'border-[#FE017D] text-[#FE017D]'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Main two-column layout — only renders on the Overview tab. */}
      {activeTab === 'overview' && (
      <>
      <EvidenceIssuesBanner
        claimId={String(claim.id)}
        onReview={() => setActiveTab('evidence')}
      />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Left column */}
        <div className="lg:col-span-2 space-y-4">
          {/* Claim Lines */}
          <div className={card}>
            <SectionHeader icon={FileText} label="Claim Lines" />
            {claim.lines?.length ? (
              <div className="overflow-x-auto -mx-1">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="text-xs text-gray-400 uppercase border-b border-gray-100">
                      {['#', 'CPT', 'Mod', 'Diagnosis Codes', 'Units', 'Billed', 'Paid', 'At Risk', 'Rule'].map((h, i) => (
                        <th key={h} className={`pb-2 pr-4 ${i >= 4 ? 'text-right' : 'text-left'} ${h === 'Rule' ? 'text-left' : ''}`}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {claim.lines.map((line) => (
                      <tr key={line.id} className="hover:bg-gray-50 transition-colors align-top">
                        <td className="py-2.5 pr-4 text-gray-400">{line.line_number}</td>
                        <td className="py-2.5 pr-4 font-mono font-semibold text-gray-900">{line.cpt_code}</td>
                        <td className="py-2.5 pr-4 text-gray-500">{line.modifier ?? '—'}</td>
                        <td className="py-2.5 pr-4">
                          {line.icd_codes?.length ? (
                            <div className="flex flex-wrap gap-1">
                              {line.icd_codes.map((icd) => (
                                <span key={icd} className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-mono font-medium bg-blue-50 text-blue-700 border border-blue-100">
                                  {icd}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <span className="text-gray-400">—</span>
                          )}
                        </td>
                        <td className="py-2.5 pr-4 text-right text-gray-700">{line.units}</td>
                        <td className="py-2.5 pr-4 text-right text-gray-600">{formatCurrency(line.billed_amount)}</td>
                        <td className="py-2.5 pr-4 text-right font-semibold text-gray-900">{formatCurrency(line.paid_amount)}</td>
                        <td className="py-2.5 pr-4 text-right">
                          {line.at_risk_amount && line.at_risk_amount > 0 ? (
                            <span className="font-semibold text-red-700">{formatCurrency(line.at_risk_amount)}</span>
                          ) : (
                            <span className="text-gray-300">—</span>
                          )}
                        </td>
                        <td className="py-2.5">
                          {line.at_risk_detector_id ? (
                            <span
                              title="Highest-priority detector that flagged this line; only this detector contributes to the case's at-risk total."
                              className="inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-semibold bg-amber-50 text-amber-800 border border-amber-200 cursor-help"
                            >
                              {line.at_risk_detector_id}
                            </span>
                          ) : (
                            <span className="text-gray-300 text-xs">—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-gray-400">No claim lines available.</p>
            )}
          </div>

          {/* Detector Results */}
          <div className={card}>
            <DetectorResults
              detectorResults={(case_.detector_results ?? []) as DetectorResult[]}
              caseId={case_.id}
              locked={case_.status === 'pending_supervisor'}
              onRerun={() => rerunMutation.mutate()}
              isRerunning={rerunMutation.isPending}
            />
          </div>
        </div>

        {/* Right column */}
        <div className="space-y-4">
          <CaseActions
            case_={case_ as any}
            onCloseCase={() => setShowCloseCase(true)}
            onApprove={() => setSupervisorMode('approve')}
            onReject={() => setSupervisorMode('reject')}
            hasNeedsReview={(case_.detector_results ?? []).some(
              (d: any) => d.finding?.disposition_status === 'needs_review'
            )}
            onOpenNoticeComposer={() => setShowSendNotice(true)}
            onViewNoticeLetter={() => setShowNoticeViewer(true)}
            hasNotice={(case_.notices ?? []).length > 0}
            onRerun={() => rerunMutation.mutate()}
            isRerunning={rerunMutation.isPending}
          />

          {/* SIU escalation — analyst-initiated handoff to the SIU workspace */}
          {(case_ as any).siu_frozen ? (
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-xs space-y-1.5">
              <div className="flex items-center gap-1.5 font-semibold text-amber-900">
                <span>🔒</span> Under SIU investigation
              </div>
              <p className="text-amber-800">
                Evidence frozen. Case writes are blocked until SIU closes the investigation.
              </p>
              {(case_ as any).siu_investigation_id && (
                <a
                  href={appUrl('siu', `/investigations/${(case_ as any).siu_investigation_id}`)}
                  target="_blank" rel="noreferrer"
                  className="inline-block text-amber-900 underline hover:no-underline"
                >
                  Open in SIU workspace →
                </a>
              )}
            </div>
          ) : (
            <button
              onClick={() => setShowEscalateToSIU(true)}
              className="w-full text-left bg-white border border-amber-200 hover:border-amber-300
                         hover:bg-amber-50/40 rounded-xl p-3 transition-colors text-sm"
            >
              <div className="flex items-center gap-2 font-medium text-amber-900">
                <span className="text-base">⚠️</span> Escalate to SIU
              </div>
              <div className="text-xs text-gray-500 mt-1">
                Refer this case for fraud / SIU investigation. Freezes the evidence bundle.
              </div>
            </button>
          )}

          <PriorityScoreCard
            priority={case_.priority}
            priorityScore={case_.priority_score}
            breakdown={case_.priority_breakdown as PriorityBreakdown | undefined}
            firedDetectors={((case_.detector_results ?? []) as DetectorResult[])
              .filter(d => d.fired && d.finding)
              .map(d => ({
                detector_id: d.detector_id,
                detector_name: d.detector_name,
                confidence: d.finding!.confidence_score,
              }))}
          />

          {/* Case Metadata */}
          <div className={card}>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
              Case Metadata
            </h3>
            <dl className="space-y-2.5 text-sm">
              {[
                ['Amount Billed',  formatCurrency(case_.amount_billed)],
                ['Amount at Risk', (
                  <span className="inline-flex items-center">
                    {formatCurrency(case_.amount_at_risk)}
                    {isSupervisor && (
                      <AtRiskOverrideButton caseSeq={case_.id} currentAmount={case_.amount_at_risk} />
                    )}
                  </span>
                )],
                ['Priority Score', case_.priority_score.toFixed(2)],
                ['Supervisor',     case_.supervisor?.full_name
                  ?? (case_.requires_supervisor_approval
                    ? <span className="text-amber-600 text-xs font-medium">Required — unassigned</span>
                    : <span className="text-gray-400 text-xs">Not required</span>)],
                ...(case_.group_id ? [['Group', String(case_.group_id)]] : []),
              ].map(([label, val]) => (
                <div key={String(label)} className="flex justify-between items-center">
                  <dt className="text-gray-400">{label}</dt>
                  <dd className="font-medium text-gray-900 text-right">{val}</dd>
                </div>
              ))}
            </dl>
          </div>

          {/* Recoveries (Phase 4) */}
          <RecoupmentsPanel
            caseSeq={case_.id}
            caseStatus={case_.status}
            caseAtRisk={case_.amount_at_risk}
          />

          {/* Notes */}
          <CaseNotes caseId={case_.id} />

          {/* Contact Log (Phase 4) */}
          <ContactLog caseId={case_.id} />

          {/* Audit History */}
          <div className={card}>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
              Audit History
            </h3>
            <AuditTimeline logs={case_.audit_logs ?? []} />
          </div>
        </div>
      </div>
      </>
      )}

      {/* Send Notice modal */}
      {showSendNotice && (
        <SendNoticeModal
          caseId={case_.id}
          caseNumber={case_.case_number}
          lob={case_.lob}
          amountAtRisk={case_.amount_at_risk}
          onClose={() => setShowSendNotice(false)}
        />
      )}

      {/* Close Case modal */}
      {showCloseCase && (
        <CloseCaseModal
          case_={case_ as any}
          onClose={() => setShowCloseCase(false)}
        />
      )}

      {/* Supervisor approve / reject modal */}
      {supervisorMode && (
        <SupervisorDecisionModal
          case_={case_ as any}
          mode={supervisorMode}
          onClose={() => setSupervisorMode(null)}
        />
      )}

      {/* View saved notice letter (always-on when a notice exists) */}
      {showNoticeViewer && (
        <NoticeLetterViewerModal
          caseSeq={case_.id}
          caseNumber={case_.case_number}
          onClose={() => setShowNoticeViewer(false)}
        />
      )}

      {/* Escalate to SIU */}
      {showEscalateToSIU && (case_ as any).case_id && (
        <EscalateToSIUModal
          caseId={(case_ as any).case_id}
          caseNumber={case_.case_number}
          onClose={() => setShowEscalateToSIU(false)}
          onEscalated={() => {
            setShowEscalateToSIU(false)
            // Refresh the case so the frozen banner appears.
            window.location.reload()
          }}
        />
      )}

      {/* Tab content — rendered when the corresponding top tab is active. */}
      {activeTab === 'notes' && (
        <div className={card}>
          {case_.notes?.length ? (
            <ul className="space-y-3">
              {case_.notes.map((note) => (
                <li key={note.id} className="border border-gray-100 rounded-xl p-3.5 text-sm">
                  <div className="flex justify-between items-start mb-1.5">
                    <span className="font-medium text-gray-900">{note.user?.full_name ?? 'System'}</span>
                    <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-500 rounded-full">{note.note_type}</span>
                  </div>
                  <p className="text-gray-600">{note.note_text}</p>
                  <p className="text-xs text-gray-400 mt-1.5">{formatDate(note.created_at)}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-gray-400">No notes yet.</p>
          )}
        </div>
      )}

      {activeTab === 'evidence' && (
        <div className={card}>
          <EvidencePanel
            claimId={String(claim.id)}
            userId={currentUser?.id ?? null}
          />
        </div>
      )}

      {activeTab === 'disputes' && (
        <div className={card}>
          {case_.disputes?.length ? (
            <div className="space-y-3">
              {case_.disputes.map((d) => (
                <div key={d.id} className="border border-gray-100 rounded-xl p-3.5 text-sm">
                  <div className="flex justify-between items-start mb-1.5">
                    <span className="font-medium text-gray-900">Dispute #{d.id}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      d.outcome === 'upheld' ? 'bg-green-100 text-green-700' :
                      d.outcome === 'overturned' ? 'bg-red-100 text-red-700' :
                      'bg-gray-100 text-gray-600'
                    }`}>
                      {d.outcome ?? 'Pending'}
                    </span>
                  </div>
                  <p className="text-gray-600 mb-1.5">{d.reason}</p>
                  <div className="text-xs text-gray-400 flex gap-4 flex-wrap">
                    <span>Filed: {formatDate(d.dispute_date)}</span>
                    <span>Due: {formatDate(d.response_due)}</span>
                    {d.response_date && <span>Responded: {formatDate(d.response_date)}</span>}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400">No disputes filed.</p>
          )}
        </div>
      )}

      {activeTab === 'era' && (
        <div className="space-y-4">
          {/* Claim details card */}
          <div className={card}>
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Claim Details</p>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-x-8 gap-y-4 text-sm">

              {/* Member */}
              {claim.member && (<>
                <div>
                  <p className="text-xs text-gray-400">Member Name</p>
                  <p className="font-medium text-gray-900 mt-0.5">{claim.member.name}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400">Member ID</p>
                  <p className="font-mono font-medium text-gray-900 mt-0.5">{claim.member.member_id}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400">DOB</p>
                  <p className="font-medium text-gray-900 mt-0.5">{formatDate(claim.member.dob)}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400">LOB</p>
                  <p className="font-medium text-gray-900 mt-0.5">{claim.lob}</p>
                </div>
              </>)}

              {/* Provider */}
              {claim.rendering_provider && (<>
                <div>
                  <p className="text-xs text-gray-400">Rendering Provider</p>
                  <p className="font-medium text-gray-900 mt-0.5">{claim.rendering_provider.name}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400">NPI</p>
                  <p className="font-mono font-medium text-gray-900 mt-0.5">{claim.rendering_provider.npi}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400">Specialty</p>
                  <p className="font-medium text-gray-900 mt-0.5">{claim.rendering_provider.specialty}</p>
                </div>
                {claim.provider_org_name && (
                  <div>
                    <p className="text-xs text-gray-400">Provider Org</p>
                    <p className="font-medium text-gray-900 mt-0.5">{claim.provider_org_name}</p>
                  </div>
                )}
              </>)}

              {/* Form & setting */}
              {claim.claim_form_type && (
                <div>
                  <p className="text-xs text-gray-400">Claim Form</p>
                  <p className="font-medium text-gray-900 mt-0.5">{claim.claim_form_type}</p>
                </div>
              )}
              {claim.care_setting && (
                <div>
                  <p className="text-xs text-gray-400">Care Setting</p>
                  <p className="font-medium text-gray-900 mt-0.5">{claim.care_setting}</p>
                </div>
              )}
              {claim.bill_type && (
                <div>
                  <p className="text-xs text-gray-400">Bill Type</p>
                  <p className="font-mono font-medium text-gray-900 mt-0.5">{claim.bill_type}</p>
                </div>
              )}
              {claim.pos_code && (
                <div>
                  <p className="text-xs text-gray-400">Place of Service</p>
                  <p className="font-mono font-medium text-gray-900 mt-0.5">{claim.pos_code}</p>
                </div>
              )}

              {/* Diagnoses */}
              {claim.primary_icd && (
                <div>
                  <p className="text-xs text-gray-400">Primary Diagnosis</p>
                  <p className="font-mono font-medium text-gray-900 mt-0.5">{claim.primary_icd}</p>
                </div>
              )}
              {!!claim.other_icd_codes?.length && (
                <div className="col-span-2">
                  <p className="text-xs text-gray-400">Other Diagnoses</p>
                  <p className="font-mono font-medium text-gray-900 mt-0.5">{claim.other_icd_codes.join(', ')}</p>
                </div>
              )}

              {/* DRG */}
              {claim.drg && (
                <div>
                  <p className="text-xs text-gray-400">DRG</p>
                  <p className="font-mono font-medium text-gray-900 mt-0.5">{claim.drg}</p>
                </div>
              )}
            </div>
          </div>

          {/* ERA transactions */}
          <div className={card}>
            {claim.era_transactions?.length ? (
              <div className="space-y-5">
                {claim.era_transactions.map((txn) => (
                  <ERA835Card key={txn.id} txn={txn} />
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-400">No 835/ERA transactions on file for this claim.</p>
            )}
          </div>
        </div>
      )}

      {activeTab === 'output' && (
        <RecoupmentLetterPanel caseSeq={case_.id} caseId={(case_ as any).case_id} />
      )}
    </div>
  )
}
