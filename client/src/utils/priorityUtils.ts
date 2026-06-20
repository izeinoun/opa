import type { Priority, CaseStatus } from '../types'

export function priorityColor(priority: Priority): string {
  switch (priority) {
    case 'HIGH':   return 'bg-red-100 text-red-800'
    case 'MEDIUM': return 'bg-yellow-100 text-yellow-800'
    default:       return 'bg-green-100 text-green-800'
  }
}

export function priorityBorderColor(priority: Priority): string {
  switch (priority) {
    case 'HIGH':   return 'border-red-400'
    case 'MEDIUM': return 'border-yellow-400'
    default:       return 'border-green-400'
  }
}

export function statusColor(status: CaseStatus | string): string {
  const map: Record<string, string> = {
    new:                      'bg-gray-100 text-gray-800',
    identified:               'bg-gray-100 text-gray-800',
    assigned:                 'bg-blue-100 text-blue-800',
    in_review:                'bg-indigo-100 text-indigo-800',
    pending_supervisor:       'bg-purple-100 text-purple-800',
    notice_sent:              'bg-orange-100 text-orange-800',
    provider_responded:       'bg-cyan-100 text-cyan-800',
    pending_provider_response:'bg-cyan-50 text-cyan-700',
    reconciling:              'bg-teal-100 text-teal-800',
    pending_dispute:          'bg-amber-100 text-amber-800',
    closed_recovered:         'bg-green-100 text-green-800',
    closed_written_off:       'bg-red-100 text-red-800',
    closed_overturned:        'bg-yellow-100 text-yellow-800',
    closed_no_overpayment:    'bg-slate-100 text-slate-800',
    closed_not_for_recoup:    'bg-slate-100 text-slate-700',
    closed_unrecoverable:     'bg-slate-100 text-slate-600',
  }
  return map[status] ?? 'bg-gray-100 text-gray-600'
}

export function statusLabel(status: CaseStatus | string): string {
  const map: Record<string, string> = {
    new:                      'New',
    identified:               'Identified',
    assigned:                 'Assigned',
    in_review:                'In Review',
    ready_for_notice:         'Ready for Notice',
    pending_supervisor:       'Pending Supervisor',
    notice_sent:              'Notice Sent',
    provider_responded:       'Provider Responded',
    pending_provider_response:'Pending Provider Response',
    reconciling:              'Reconciling',
    pending_dispute:          'Pending Dispute',
    closed_recovered:         'Closed — Recovered',
    closed_written_off:       'Closed — Written Off',
    closed_overturned:        'Closed — Overturned',
    closed_no_overpayment:    'Closed — No Overpayment',
    closed_not_for_recoup:    'Closed — Not for Recoup',
    closed_unrecoverable:     'Closed — Unrecoverable',
  }
  return map[status] ?? status
}

export function detectorLabel(code: string): string {
  const labels: Record<string, string> = {
    // Canonical short codes
    'DET-01': 'Duplicate Billing',
    'DET-02': 'Unbundling',
    'DET-03': 'Upcoding',
    'DET-04': 'Fee Schedule',
    'DET-05': 'DX/CPT Mismatch',
    'DET-06': 'Units Exceeded',
    'DET-07': 'Modifier Abuse',
    'DET-08': 'Excluded Provider',
    'DET-09': 'Coordination of Benefits',
    'DET-10': 'Claim Frequency',
    // Internal detector IDs stored in the DB
    'BILLING_VARIANCE_V1':    'Billing Variance',
    'DUPLICATE_CLAIM_V1':     'Duplicate Billing',
    'DX_CPT_MISMATCH_V1':     'DX/CPT Mismatch',
    'EXCESS_UNITS_V1':        'Units Exceeded',
    'GENERAL_REVIEW_V1':      'General Review',
    'MULTI_LINE_COMPLEXITY_V1': 'Multi-Line Complexity',
    'POST_DEATH_V1':          'Post-Death Billing',
    'RETRO_TERM_V1':          'Retroactive Termination',
    'UPCODING_V1':            'Upcoding',
  }
  return labels[code] ?? code
}

// Which likelihood breakdown component each detector primarily drives
export const DETECTOR_COMPONENT: Record<string, string> = {
  'DX_CPT_MISMATCH_V1':       'cpt_risk_score',
  'UPCODING_V1':               'cpt_risk_score',
  'EXCESS_UNITS_V1':           'cpt_risk_score',
  'BILLING_VARIANCE_V1':       'billing_variance_score',
  'MULTI_LINE_COMPLEXITY_V1':  'claim_complexity_score',
  'DUPLICATE_CLAIM_V1':        'claim_complexity_score',
  'POST_DEATH_V1':             'provider_risk_tier',
  'RETRO_TERM_V1':             'provider_risk_tier',
  'GENERAL_REVIEW_V1':         'dx_cpt_mismatch_score',
  // Canonical codes
  'DET-05': 'cpt_risk_score',
  'DET-03': 'cpt_risk_score',
  'DET-06': 'cpt_risk_score',
  'DET-04': 'billing_variance_score',
  'DET-01': 'claim_complexity_score',
  'DET-02': 'claim_complexity_score',
}
