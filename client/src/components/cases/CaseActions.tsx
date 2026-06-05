import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  UserPlus, Play, Send, Mail, CheckSquare, Lock, ChevronDown, ListChecks, Undo2, RefreshCw, FileText, ArrowUpCircle,
} from 'lucide-react'
import api from '../../services/api'
import { useCurrentUser } from '../../hooks/useCurrentUser'
import type { CaseDetail, User } from '../../types'

interface Props {
  case_: CaseDetail
  onCloseCase: () => void           // opens the Close Case modal
  onApprove?: () => void            // supervisor approval (Task 9)
  onReject?: () => void             // supervisor rejection (Task 9)
  hasNeedsReview?: boolean          // Phase 2: any DET-09 finding awaiting review
  onOpenNoticeComposer?: () => void // opens SendNoticeModal (preview + edit + send)
  onViewNoticeLetter?: () => void   // opens viewer for a saved notice
  hasNotice?: boolean               // case has at least one ProviderNotice
  onRerun?: () => void              // re-run all detectors against this claim
  isRerunning?: boolean
}

const TERMINAL = new Set([
  'closed_recovered', 'closed_written_off',
  'closed_overturned', 'closed_no_overpayment',
  'closed_unrecoverable',
])

export default function CaseActions({
  case_, onCloseCase, onApprove, onReject, hasNeedsReview = false,
  onOpenNoticeComposer, onViewNoticeLetter, hasNotice = false,
  onRerun, isRerunning = false,
}: Props) {
  const { currentUser, users } = useCurrentUser()
  const queryClient = useQueryClient()
  const [reassignOpen, setReassignOpen] = useState(false)
  const [escalateOpen, setEscalateOpen] = useState(false)
  const [escalateReason, setEscalateReason] = useState('')
  const [escalateError, setEscalateError] = useState<string | null>(null)

  const caseId = case_.id
  const status = case_.status
  const isLocked = status === 'pending_supervisor'
  const isTerminal = TERMINAL.has(status)
  const isSupervisor = currentUser?.role === 'supervisor' || currentUser?.role === 'admin'
  const ownerId = case_.assignee?.id ?? null
  const isOwner = ownerId === currentUser?.id

  // Mutations
  const transitionMut = useMutation({
    mutationFn: async (body: { to_status: string; reason?: string }) => {
      const res = await api.post(`/cases/${caseId}/transition`, body)
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['case', caseId] })
    },
  })

  const assignMut = useMutation({
    mutationFn: async (analyst_id: string | null) => {
      const res = await api.patch(`/cases/${caseId}/assign`, { analyst_id })
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['case', caseId] })
      setReassignOpen(false)
    },
  })

  const escalateMut = useMutation({
    mutationFn: async (reason: string) =>
      (await api.post(`/cases/${caseId}/escalate`, { reason })).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['case', caseId] })
      queryClient.invalidateQueries({ queryKey: ['notif-count'] })
      setEscalateOpen(false)
      setEscalateReason('')
      setEscalateError(null)
    },
    onError: (err: any) => {
      setEscalateError(err?.response?.data?.detail ?? 'Failed to escalate')
    },
  })

  // --- Locked state ---
  if (isLocked && !isSupervisor) {
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 space-y-3">
        <div className="flex items-center gap-2">
          <Lock className="w-4 h-4 text-amber-700" />
          <span className="text-sm font-semibold text-amber-900">Awaiting supervisor approval</span>
        </div>
        {case_.pending_decision && (
          <div className="text-xs text-amber-900 bg-white border border-amber-200 rounded-lg p-2.5 space-y-1">
            <p><span className="font-semibold">Pending:</span> {prettyDisposition(case_.pending_decision.disposition)}</p>
            {case_.pending_decision.recovered_amount != null && (
              <p><span className="font-semibold">Recovered amount:</span> ${case_.pending_decision.recovered_amount.toFixed(2)}</p>
            )}
            {case_.pending_decision.reason && (
              <p><span className="font-semibold">Reason:</span> {case_.pending_decision.reason}</p>
            )}
          </div>
        )}
        <p className="text-xs text-amber-700">This case is read-only until a supervisor approves or rejects. You can still add notes below.</p>
      </div>
    )
  }

  // --- Supervisor approve / reject buttons ---
  if (isLocked && isSupervisor) {
    return (
      <div className="bg-white border border-gray-200 rounded-xl p-4 space-y-3">
        <p className="text-xs font-bold text-gray-500 uppercase tracking-wider">Awaiting your approval</p>
        {case_.pending_decision && (
          <div className="text-xs bg-gray-50 border border-gray-200 rounded-lg p-2.5 space-y-1">
            <p><span className="text-gray-500">Disposition:</span> <span className="font-semibold text-gray-900">{prettyDisposition(case_.pending_decision.disposition)}</span></p>
            {case_.pending_decision.recovered_amount != null && (
              <p><span className="text-gray-500">Recovered:</span> <span className="font-mono font-semibold text-gray-900">${case_.pending_decision.recovered_amount.toFixed(2)}</span></p>
            )}
            {case_.pending_decision.reason && (
              <p><span className="text-gray-500">Reason:</span> <span className="text-gray-800">{case_.pending_decision.reason}</span></p>
            )}
            {case_.pending_decision.submitted_by_user_id && (
              <p className="text-gray-400 mt-1.5">
                Submitted by {users.find((u) => u.id === case_.pending_decision!.submitted_by_user_id)?.full_name ?? 'unknown'}
              </p>
            )}
          </div>
        )}
        <div className="flex gap-2">
          <button
            onClick={onApprove}
            className="flex-1 bg-green-600 hover:bg-green-700 text-white text-sm font-semibold py-2 rounded-lg transition-colors"
          >
            Approve
          </button>
          <button
            onClick={onReject}
            className="flex-1 bg-white hover:bg-red-50 text-red-700 border border-red-200 text-sm font-semibold py-2 rounded-lg transition-colors"
          >
            Reject
          </button>
        </div>
      </div>
    )
  }

  // --- Terminal cases: supervisor can reopen ---
  const reopenMut = useMutation({
    mutationFn: async (reason: string) =>
      (await api.post(`/cases/${caseId}/reopen`, { reason })).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['case', caseId] })
    },
  })

  if (isTerminal) {
    return (
      <div className="bg-gray-50 border border-gray-200 rounded-xl p-4 space-y-3">
        <div>
          <p className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">Case Closed</p>
          <p className="text-sm text-gray-700">{prettyStatus(status)}</p>
        </div>
        {hasNotice && (
          <ActionButton
            icon={FileText}
            label="View notice letter"
            onClick={() => onViewNoticeLetter?.()}
            variant="secondary"
            disabled={!onViewNoticeLetter}
            disabledTooltip=""
          />
        )}
        {isSupervisor && (
          <ReopenInline
            onReopen={(reason) => reopenMut.mutate(reason)}
            loading={reopenMut.isPending}
            error={(reopenMut.error as any)?.response?.data?.detail}
          />
        )}
      </div>
    )
  }

  // --- Active case: action buttons ---
  const canStartReview = status === 'new' || status === 'assigned'
  const canMarkReviewComplete = status === 'in_review'
  const canSendNotice = status === 'ready_for_notice'
  const canRecall = status === 'ready_for_notice'
  const canMarkResponse = status === 'notice_sent'
  const canClose = ['in_review', 'ready_for_notice', 'provider_responded', 'reconciling'].includes(status)

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 space-y-2.5">
      <p className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">Actions</p>

      {/* Take ownership / reassign */}
      {!isOwner && (
        <ActionButton
          icon={UserPlus}
          label="Take ownership"
          onClick={() => assignMut.mutate(currentUser!.id)}
          loading={assignMut.isPending}
          variant="primary"
        />
      )}
      {isSupervisor && (
        <div className="relative">
          <ActionButton
            icon={UserPlus}
            label="Reassign…"
            onClick={() => setReassignOpen((v) => !v)}
            variant="secondary"
            trailing={<ChevronDown className="w-3.5 h-3.5" />}
          />
          {reassignOpen && (
            <ReassignDropdown
              users={users}
              currentAssigneeId={ownerId}
              onPick={(u) => assignMut.mutate(u.id)}
              onUnassign={() => assignMut.mutate(null)}
              loading={assignMut.isPending}
            />
          )}
        </div>
      )}

      {canStartReview && (
        <ActionButton
          icon={Play}
          label="Start review"
          onClick={() => transitionMut.mutate({ to_status: 'in_review' })}
          loading={transitionMut.isPending}
          variant="primary"
          disabled={!isOwner}
          disabledTooltip="Take ownership first"
        />
      )}

      {canMarkReviewComplete && (
        <ActionButton
          icon={ListChecks}
          label="Mark review complete"
          onClick={() => transitionMut.mutate({ to_status: 'ready_for_notice' })}
          loading={transitionMut.isPending}
          variant="primary"
          disabled={!isOwner || hasNeedsReview}
          disabledTooltip={
            hasNeedsReview
              ? 'Resolve all "needs review" findings first'
              : 'Only the case owner can mark review complete'
          }
        />
      )}

      {canSendNotice && (
        <ActionButton
          icon={Send}
          label="Preview & send notice"
          onClick={() => onOpenNoticeComposer?.()}
          variant="primary"
          disabled={!onOpenNoticeComposer}
          disabledTooltip=""
        />
      )}

      {/* Always available when a notice exists: read-only viewer for the saved letter */}
      {hasNotice && (
        <ActionButton
          icon={FileText}
          label="View notice letter"
          onClick={() => onViewNoticeLetter?.()}
          variant="secondary"
          disabled={!onViewNoticeLetter}
          disabledTooltip=""
        />
      )}

      {canRecall && (
        <ActionButton
          icon={Undo2}
          label="Recall to review"
          onClick={() => transitionMut.mutate({ to_status: 'in_review', reason: 'Recalled from ready-for-notice queue' })}
          loading={transitionMut.isPending}
          variant="secondary"
          disabled={!isOwner && !isSupervisor}
          disabledTooltip="Owner or supervisor required"
        />
      )}

      {canMarkResponse && (
        <ActionButton
          icon={Mail}
          label="Mark provider response received"
          onClick={() => transitionMut.mutate({ to_status: 'provider_responded' })}
          loading={transitionMut.isPending}
          variant="primary"
          disabled={!isOwner}
          disabledTooltip="Only the case owner can mark a response"
        />
      )}

      {canClose && (
        <ActionButton
          icon={CheckSquare}
          label="Close case…"
          onClick={onCloseCase}
          variant="secondary"
          disabled={!isOwner || hasNeedsReview}
          disabledTooltip={
            hasNeedsReview
              ? 'Resolve all "needs review" findings first'
              : 'Only the case owner can close'
          }
        />
      )}

      {onRerun && (
        <ActionButton
          icon={RefreshCw}
          label={isRerunning ? 'Running detectors…' : 'Re-run detectors'}
          onClick={onRerun}
          loading={isRerunning}
          variant="secondary"
        />
      )}

      {/* Escalation — available on any active case to anyone who can write */}
      <ActionButton
        icon={ArrowUpCircle}
        label="Escalate to supervisor"
        onClick={() => { setEscalateOpen(true); setEscalateError(null) }}
        variant="secondary"
        disabled={false}
        disabledTooltip=""
      />

      {escalateOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
             onClick={() => setEscalateOpen(false)}>
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-5" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-base font-bold text-gray-900 mb-1 inline-flex items-center gap-2">
              <ArrowUpCircle className="w-4 h-4 text-amber-600" /> Escalate to supervisor
            </h3>
            <p className="text-xs text-gray-500 mb-3">
              Notifies all supervisors so they can review this case. The case stays in your queue —
              status doesn't change.
            </p>
            <label className="text-xs font-semibold text-gray-600 block mb-1">
              Reason <span className="text-red-600">(required)</span>
            </label>
            <textarea
              value={escalateReason}
              onChange={(e) => setEscalateReason(e.target.value)}
              rows={3}
              placeholder="Why does this need supervisor attention?"
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-100 resize-none mb-3"
              autoFocus
            />
            {escalateError && (
              <p className="text-xs text-red-600 mb-2">{escalateError}</p>
            )}
            <div className="flex gap-2">
              <button onClick={() => setEscalateOpen(false)}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50">
                Cancel
              </button>
              <button
                onClick={() => escalateMut.mutate(escalateReason.trim())}
                disabled={!escalateReason.trim() || escalateMut.isPending}
                className="flex-1 px-4 py-2 text-sm font-semibold text-white bg-amber-600 hover:bg-amber-700 rounded-lg disabled:bg-gray-200 disabled:text-gray-400"
              >
                {escalateMut.isPending ? 'Escalating…' : 'Escalate'}
              </button>
            </div>
          </div>
        </div>
      )}

      {transitionMut.isError && (
        <p className="text-xs text-red-600 mt-2">
          {(transitionMut.error as any)?.response?.data?.detail ?? 'Action failed'}
        </p>
      )}
      {assignMut.isError && (
        <p className="text-xs text-red-600 mt-2">
          {(assignMut.error as any)?.response?.data?.detail ?? 'Assignment failed'}
        </p>
      )}
    </div>
  )
}

function ActionButton({
  icon: Icon, label, onClick, loading, variant, disabled, disabledTooltip, trailing,
}: {
  icon: any; label: string; onClick: () => void;
  loading?: boolean; variant: 'primary' | 'secondary';
  disabled?: boolean; disabledTooltip?: string; trailing?: React.ReactNode
}) {
  const base = 'w-full inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors'
  const styles = variant === 'primary'
    ? 'bg-indigo-600 text-white hover:bg-indigo-700 disabled:bg-gray-200 disabled:text-gray-400'
    : 'bg-white text-gray-700 border border-gray-200 hover:bg-gray-50 disabled:bg-gray-50 disabled:text-gray-400'
  return (
    <button
      onClick={onClick}
      disabled={disabled || loading}
      title={disabled ? disabledTooltip : undefined}
      className={`${base} ${styles}`}
    >
      <Icon className="w-3.5 h-3.5 flex-shrink-0" />
      <span className="flex-1 text-left">{label}</span>
      {loading && <span className="text-xs">…</span>}
      {trailing}
    </button>
  )
}

function ReassignDropdown({
  users, currentAssigneeId, onPick, onUnassign, loading,
}: {
  users: User[]; currentAssigneeId: string | null;
  onPick: (u: User) => void; onUnassign: () => void; loading: boolean
}) {
  const analysts = users.filter((u) => u.role === 'analyst' && u.is_active)
  return (
    <div className="absolute left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg py-1 z-40 max-h-72 overflow-y-auto">
      {analysts.map((u) => (
        <button
          key={u.id}
          onClick={() => onPick(u)}
          disabled={loading}
          className={`w-full text-left px-3 py-1.5 text-sm hover:bg-gray-50 ${
            u.id === currentAssigneeId ? 'bg-indigo-50 text-indigo-700 font-semibold' : 'text-gray-800'
          }`}
        >
          {u.full_name}
        </button>
      ))}
      <div className="border-t border-gray-100 my-1" />
      <button
        onClick={onUnassign}
        disabled={loading}
        className="w-full text-left px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-50 italic"
      >
        Unassign
      </button>
    </div>
  )
}

function ReopenInline({ onReopen, loading, error }: {
  onReopen: (reason: string) => void; loading: boolean; error?: string
}) {
  const [show, setShow] = useState(false)
  const [reason, setReason] = useState('')
  if (!show) {
    return (
      <button
        onClick={() => setShow(true)}
        className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-semibold bg-amber-600 hover:bg-amber-700 text-white rounded-lg transition-colors"
      >
        <RefreshCw className="w-3.5 h-3.5" /> Reopen case
      </button>
    )
  }
  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold text-gray-600">Reopen this case?</p>
      <textarea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        rows={2}
        placeholder="Reason (required)…"
        className="w-full px-2.5 py-1.5 text-xs border border-gray-200 rounded focus:outline-none focus:border-indigo-400 resize-none"
      />
      {error && <p className="text-xs text-red-600">{error}</p>}
      <div className="flex gap-2">
        <button onClick={() => { setShow(false); setReason('') }} className="px-2.5 py-1.5 text-xs text-gray-700 bg-white border border-gray-200 rounded hover:bg-gray-50">
          Cancel
        </button>
        <button
          onClick={() => onReopen(reason.trim())}
          disabled={!reason.trim() || loading}
          className="flex-1 px-2.5 py-1.5 text-xs font-semibold bg-amber-600 hover:bg-amber-700 text-white rounded disabled:bg-gray-200 disabled:text-gray-400"
        >
          {loading ? 'Reopening…' : 'Confirm reopen'}
        </button>
      </div>
    </div>
  )
}


function prettyStatus(s: string): string {
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function prettyDisposition(d: string): string {
  const map: Record<string, string> = {
    closed_recovered: 'Closed — Recovered',
    closed_written_off: 'Closed — Written Off',
    closed_overturned: 'Closed — Overturned',
    closed_no_overpayment: 'Closed — No Overpayment',
  }
  return map[d] ?? d
}
