import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, ChevronDown, Send, RotateCcw,
  User, Building2, FileText, AlertTriangle,
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
import SendNoticeModal from '../components/letters/SendNoticeModal'
import { formatCurrency } from '../utils/formatUtils'
import { formatDate } from '../utils/dateUtils'
import { card, detectorBadge } from '../utils/designSystem'
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
  lines?: ClaimLine[]; findings?: ClaimFinding[]; era_transactions?: ERATransaction[]
}
type RichCaseDetail = Omit<CaseDetail, 'claim'> & { claim: RichClaim }
type TabKey = 'notes' | 'disputes' | 'era'

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
        </div>
      </div>

      {/* Payment lines */}
      {txn.payments.length > 0 && (
        <table className="min-w-full text-sm">
          <thead className="bg-white border-b border-gray-100">
            <tr className="text-xs text-gray-400 uppercase tracking-wider">
              <th className="px-4 py-2.5 text-left">Claim ICN</th>
              <th className="px-4 py-2.5 text-left">CPT</th>
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

  const [activeTab,           setActiveTab]           = useState<TabKey>('notes')
  const [showTransitionMenu,  setShowTransitionMenu]  = useState(false)
  const [transitionNotes,     setTransitionNotes]     = useState('')
  const [selectedTransition,  setSelectedTransition]  = useState<CaseStatus | null>(null)
  const [showReopenModal,     setShowReopenModal]     = useState(false)
  const [reopenReason,        setReopenReason]        = useState('')
  const [showSendNotice,      setShowSendNotice]      = useState(false)

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
  const validNext = VALID_TRANSITIONS[case_.status] ?? []
  const isClosed  = case_.status.startsWith('closed_')

  function handleTransition(status: CaseStatus) {
    mutateTransition.mutate({ to_status: status, notes: transitionNotes || undefined })
    setShowTransitionMenu(false); setSelectedTransition(null); setTransitionNotes('')
  }
  function handleReopen() {
    if (!reopenReason.trim()) return
    mutateReopen.mutate(reopenReason)
    setShowReopenModal(false); setReopenReason('')
  }

  return (
    <div className="flex flex-col gap-5">
      {/* Back */}
      <button onClick={() => navigate('/worklist')}
        className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-900 w-fit transition-colors">
        <ArrowLeft className="w-4 h-4" />Back to Worklist
      </button>

      {/* Header card */}
      <div className={card}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wider">Case Number</p>
            <h1 className="text-xl font-bold font-mono text-gray-900 mt-0.5">{case_.case_number}</h1>
            <div className="flex items-center flex-wrap gap-2 mt-2">
              <PriorityBadge priority={case_.priority} />
              <StatusBadge status={case_.status} />
              {(case_.detector_results ?? [])
                .filter((d) => d.fired)
                .map((d) => (
                  <span key={d.detector_id} className="inline-flex items-center gap-1.5">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-bold ${detectorBadge[d.detector_id] ?? 'bg-gray-100 text-gray-600'}`}>
                      {d.detector_id}
                    </span>
                    <span className="text-sm text-gray-700">{d.finding?.finding_type ?? d.detector_name}</span>
                  </span>
                ))
              }
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={() => mutateTransition.mutate({ to_status: 'assigned', notes: 'Self-assigned' })}
              disabled={case_.status !== 'new' && case_.status !== 'assigned'}
              className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg
                         hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed
                         transition-colors text-gray-700"
            >
              Assign to Me
            </button>

            {validNext.length > 0 && (
              <div className="relative">
                <button
                  onClick={() => setShowTransitionMenu((v) => !v)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm
                             bg-[#FE017D] text-white rounded-lg hover:bg-[#e5006f]
                             transition-colors"
                >
                  Transition <ChevronDown className="w-3.5 h-3.5" />
                </button>
                {showTransitionMenu && (
                  <div className="absolute right-0 top-9 z-10 w-56 bg-white
                                  border border-gray-200 rounded-xl shadow-md py-1">
                    {validNext.map((s) => (
                      <button key={s}
                        onClick={() => { setSelectedTransition(s); setShowTransitionMenu(false) }}
                        className="w-full text-left px-4 py-2 text-sm text-gray-700
                                   hover:bg-gray-50 transition-colors">
                        → {STATUS_LABELS[s]}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {isClosed && (
              <button onClick={() => setShowReopenModal(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm
                           border border-amber-200 text-amber-700 rounded-lg
                           hover:bg-amber-50 transition-colors">
                <RotateCcw className="w-3.5 h-3.5" /> Reopen
              </button>
            )}

            <button onClick={() => setShowSendNotice(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm
                         border border-teal-200 text-teal-700 rounded-lg
                         hover:bg-teal-50 transition-colors">
              <Send className="w-3.5 h-3.5" /> Send Notice
            </button>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-sm text-gray-600 border-t border-gray-100 pt-4">
          <span><span className="text-gray-400">Opened:</span> <strong className="text-gray-900">{formatDate(case_.opened_at)}</strong></span>
          <span><span className="text-gray-400">Deadline:</span> <DeadlineIndicator deadline={case_.deadline} showDays /></span>
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
          <span><span className="text-gray-400">At Risk:</span> <strong className="text-gray-900">{formatCurrency(case_.amount_at_risk)}</strong></span>
        </div>
      </div>

      {/* Transition modal */}
      {selectedTransition && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6">
            <h3 className="font-semibold text-gray-900 mb-3">
              Transition to: <span className="text-[#FE017D]">{STATUS_LABELS[selectedTransition]}</span>
            </h3>
            <textarea value={transitionNotes} onChange={(e) => setTransitionNotes(e.target.value)}
              placeholder="Notes (optional)…" rows={3}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm
                         focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 mb-4" />
            <div className="flex gap-2 justify-end">
              <button onClick={() => setSelectedTransition(null)}
                className="px-4 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50">
                Cancel
              </button>
              <button onClick={() => handleTransition(selectedTransition)}
                disabled={mutateTransition.isPending}
                className="px-4 py-2 text-sm bg-[#FE017D] text-white rounded-lg
                           hover:bg-[#e5006f] disabled:opacity-60">
                {mutateTransition.isPending ? 'Saving…' : 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reopen modal */}
      {showReopenModal && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6">
            <h3 className="font-semibold text-gray-900 mb-3">Reopen Case</h3>
            <textarea value={reopenReason} onChange={(e) => setReopenReason(e.target.value)}
              placeholder="Reason for reopening…" rows={3}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm
                         focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 mb-4" />
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowReopenModal(false)}
                className="px-4 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50">
                Cancel
              </button>
              <button onClick={handleReopen}
                disabled={!reopenReason.trim() || mutateReopen.isPending}
                className="px-4 py-2 text-sm bg-amber-600 text-white rounded-lg
                           hover:bg-amber-700 disabled:opacity-60">
                {mutateReopen.isPending ? 'Reopening…' : 'Reopen'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main two-column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Left column */}
        <div className="lg:col-span-2 space-y-4">
          {/* Member */}
          <div className={card}>
            <SectionHeader icon={User} label="Member" />
            {claim.member ? (
              <div className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
                {[
                  ['Name',      claim.member.name],
                  ['Member ID', <span className="font-mono">{claim.member.member_id}</span>],
                  ['DOB',       formatDate(claim.member.dob)],
                  ['LOB',       claim.lob],
                ].map(([label, val]) => (
                  <div key={String(label)}>
                    <p className="text-gray-400 text-xs">{label}</p>
                    <p className="font-medium text-gray-900 mt-0.5">{val}</p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div><p className="text-gray-400 text-xs">Claim #</p><p className="font-mono font-medium">{claim.claim_number}</p></div>
                <div><p className="text-gray-400 text-xs">LOB</p><p className="font-medium">{claim.lob}</p></div>
              </div>
            )}
          </div>

          {/* Provider */}
          <div className={card}>
            <SectionHeader icon={Building2} label="Rendering Provider" />
            {claim.rendering_provider ? (
              <div className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
                {[
                  ['Name',      claim.rendering_provider.name],
                  ['NPI',       <span className="font-mono">{claim.rendering_provider.npi}</span>],
                  ['Specialty', claim.rendering_provider.specialty],
                  ['Billing Risk', (() => {
                    const score = claim.rendering_provider.billing_variance_score
                    if (score > 0.65) return <span title="Computed by ML billing variance model. Reflects deviation from peer cohort billing patterns." className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-700 cursor-help">High</span>
                    if (score >= 0.35) return <span title="Computed by ML billing variance model. Reflects deviation from peer cohort billing patterns." className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-700 cursor-help">Medium</span>
                    return <span title="Computed by ML billing variance model. Reflects deviation from peer cohort billing patterns." className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-green-100 text-green-700 cursor-help">Low</span>
                  })()],
                ].map(([label, val]) => (
                  <div key={String(label)}>
                    <p className="text-gray-400 text-xs">{label}</p>
                    <p className="font-medium text-gray-900 mt-0.5">{val}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-400">Provider details not available.</p>
            )}
          </div>

          {/* Claim Lines */}
          <div className={card}>
            <SectionHeader icon={FileText} label="Claim Lines" />
            {claim.lines?.length ? (
              <div className="overflow-x-auto -mx-1">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="text-xs text-gray-400 uppercase border-b border-gray-100">
                      {['#', 'CPT', 'Mod', 'Units', 'Billed', 'Paid'].map((h, i) => (
                        <th key={h} className={`pb-2 pr-4 ${i >= 3 ? 'text-right' : 'text-left'}`}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {claim.lines.map((line) => (
                      <tr key={line.id} className="hover:bg-gray-50 transition-colors">
                        <td className="py-2.5 pr-4 text-gray-400">{line.line_number}</td>
                        <td className="py-2.5 pr-4 font-mono font-semibold text-gray-900">{line.cpt_code}</td>
                        <td className="py-2.5 pr-4 text-gray-500">{line.modifier ?? '—'}</td>
                        <td className="py-2.5 pr-4 text-right text-gray-700">{line.units}</td>
                        <td className="py-2.5 pr-4 text-right text-gray-600">{formatCurrency(line.billed_amount)}</td>
                        <td className="py-2.5 text-right font-semibold text-gray-900">{formatCurrency(line.paid_amount)}</td>
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
              onRerun={() => rerunMutation.mutate()}
              isRerunning={rerunMutation.isPending}
            />
          </div>
        </div>

        {/* Right column */}
        <div className="space-y-4">
          <PriorityScoreCard
            priority={case_.priority}
            priorityScore={case_.priority_score}
            breakdown={case_.priority_breakdown as PriorityBreakdown | undefined}
            likelihood={case_.breakdown ?? undefined}
            findings={claim.findings ?? []}
          />

          {/* Case Metadata */}
          <div className={card}>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
              Case Metadata
            </h3>
            <dl className="space-y-2.5 text-sm">
              {[
                ['Amount Billed',  formatCurrency(case_.amount_billed)],
                ['Amount at Risk', formatCurrency(case_.amount_at_risk)],
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

          {/* Audit History */}
          <div className={card}>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
              Audit History
            </h3>
            <AuditTimeline logs={case_.audit_logs ?? []} />
          </div>
        </div>
      </div>

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

      {/* Bottom tabs */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="flex border-b border-gray-100">
          {(['notes', 'disputes', 'era'] as TabKey[]).map((tab) => (
            <button key={tab} onClick={() => setActiveTab(tab)}
              className={`px-5 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab
                  ? 'border-[#FE017D] text-[#FE017D]'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}>
              {tab === 'notes' ? 'Notes' : tab === 'disputes' ? 'Disputes' : '835/ERA'}
            </button>
          ))}
        </div>

        <div className="p-5">
          {activeTab === 'notes' && (
            <div>
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

          {activeTab === 'disputes' && (
            <div>
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
            <div>
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
          )}
        </div>
      </div>
    </div>
  )
}
