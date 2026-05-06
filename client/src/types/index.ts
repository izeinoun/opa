export type Priority = 'HIGH' | 'MEDIUM' | 'LOW'
export type CaseStatus =
  | 'new' | 'assigned' | 'in_review' | 'pending_supervisor'
  | 'notice_sent' | 'provider_responded' | 'reconciling'
  | 'closed_recovered' | 'closed_written_off' | 'closed_overturned' | 'closed_no_overpayment'
  // seed data uses 'identified' as an alias for 'new'
  | 'identified' | 'pending_dispute' | 'closed_unrecoverable' | 'pending_provider_response'
export type LOB = 'MA' | 'PPO' | 'Medicaid'
export type UserRole = 'analyst' | 'supervisor' | 'admin' | 'system'

export interface User {
  id: string       // UUID
  username: string
  email: string
  full_name: string
  role: UserRole
  is_active: boolean
}

export interface Provider {
  id: string       // UUID
  npi: string
  name: string
  specialty: string
  risk_tier: number
  billing_variance_score: number
  is_excluded: boolean
}

export interface Member {
  id: string       // UUID
  member_id: string
  name: string
  dob: string
  lob: LOB
}

export interface CPTCode {
  code: string
  description: string
  risk_level: 'H' | 'M' | 'L'
  cms_rac_flag: boolean
}

export interface ClaimLine {
  id: string       // UUID
  line_number: number
  cpt_code: string
  icd_codes: string[]
  units: number
  billed_amount: number
  allowed_amount: number
  paid_amount: number
  modifier: string | null
  service_date: string
}

export interface ClaimFinding {
  id: string       // UUID
  detector_code: string
  finding_type: string
  description: string
  overpayment_amount: number
  confidence_score: number
  evidence_json: string
  created_at: string
}

export interface ERAPaymentLine {
  id: string
  claim_icn: string
  cpt_code: string
  paid_amount: number
  adjustment_amount: number
  adjustment_reason_code: string | null
  check_number: string | null
  payment_date: string
}

export interface ERATransaction {
  id: string
  era_number: string
  transaction_type: string
  payer_name: string
  payment_date: string
  payment_amount: number
  claim_count: number
  payments: ERAPaymentLine[]
  raw_835?: string | null
}

export interface PriorityBreakdown {
  total_score: number
  band: string
  amount_pts: number
  likelihood_pts: number
  urgency_pts: number
  amount_at_risk: number
  likelihood_score: number  // posterior — drives 0.45 pts
  prior_score: number       // ML model output
  urgency_factor: number
  urgency_override_applied: boolean
  days_overdue: number | null
  days_until: number | null
}

export interface DetectorResult {
  detector_id: string
  detector_name: string
  fired: boolean
  finding: ClaimFinding | null
}

export interface ClaimSummary {
  id: string       // UUID
  claim_number: string
  lob: LOB
  total_billed: number
  total_allowed: number
  total_paid: number
  status: string
  service_date_start: string
  member?: { id: string; member_id: string; name: string; dob: string; lob: string }
}

export interface ClaimDetail extends ClaimSummary {
  member: Member
  rendering_provider: Provider
  lines: ClaimLine[]
  findings: ClaimFinding[]
  era_transactions: ERATransaction[]
}

export interface AuditLog {
  id: string       // UUID
  action: string
  from_status: string | null
  to_status: string | null
  notes: string | null
  created_at: string
  user?: User
}

export interface Dispute {
  id: string       // UUID
  dispute_date: string
  reason: string
  response_due: string
  response_date: string | null
  outcome: string | null
  notes: string | null
}

export interface RecoveryNotice {
  id: string       // UUID
  sent_date: string
  amount_demanded: number
  response_due: string
  delivery_method: string
  status: string
}

export interface WorkflowNote {
  id: string       // UUID
  note_text: string
  note_type: string
  created_at: string
  user?: User
}

export interface LikelihoodBreakdown {
  cpt_risk_score: number
  provider_risk_tier: number
  dx_cpt_mismatch_score: number
  claim_complexity_score: number
  billing_variance_score: number
  likelihood_score: number
}

export interface CaseSummary {
  id: number          // case_sequence integer for routing
  case_number: string
  status: CaseStatus
  priority: Priority
  priority_score: number
  likelihood_score: number
  amount_billed: number
  amount_at_risk: number
  deadline: string | null
  is_active: boolean
  opened_at: string
  lob: LOB | string
  assignee?: User
  claim: ClaimSummary
  requires_supervisor_approval: boolean
}

export interface CaseDetail extends CaseSummary {
  supervisor?: User
  breakdown: LikelihoodBreakdown
  audit_logs: AuditLog[]
  disputes: Dispute[]
  notices: RecoveryNotice[]
  notes: WorkflowNote[]
  group_id: string | null
  priority_breakdown?: PriorityBreakdown
  detector_results?: DetectorResult[]
  posterior_score?: number
}

export interface CaseListResponse {
  items: CaseSummary[]
  total: number
  page: number
  page_size: number
}

export interface WorklistFilters {
  status?: CaseStatus
  priority?: Priority
  lob?: LOB
  search?: string
  page?: number
  page_size?: number
  exclude_closed?: boolean
  closed_only?: boolean
  overdue_only?: boolean
}

// Dashboard types
export interface KPICard {
  label: string
  value: number | string
  delta?: number
  unit?: string
}

export interface AgingBucket {
  label: string
  count: number
  amount: number
}

export interface WorkloadItem {
  assignee: string
  open_cases: number
  high_priority: number
  total_at_risk: number
}

export interface RecoveryPoint {
  month: string
  recovered: number
  written_off: number
  pending: number
}

export interface DetectorStat {
  detector_code: string
  total_findings: number
  confirmed_overpayment: number
  avg_confidence: number
}

export interface StatusCount {
  status: string
  count: number
}

export interface DashboardData {
  kpis: KPICard[]
  aging: AgingBucket[]
  workload: WorkloadItem[]
  recovery: RecoveryPoint[]
  detectors: DetectorStat[]
  status_distribution: StatusCount[]
}

// Letter types
export interface LetterTemplate {
  id: string       // template_id string (e.g. "TMPL-MA-001")
  code: string
  name: string
  template_type: string
  lob: string
  version: number
  is_active: boolean
  created_at: string
  regulatory_reference?: string
}

export interface LetterTemplateDetail extends LetterTemplate {
  content_html: string
}

export interface RenderedLetter {
  case_id: number
  template_code: string
  html_content: string
  rendered_at: string
}

// Reference freshness
export interface ReferenceDataFreshness {
  source_name: string
  last_updated: string
  next_due: string
  status: 'fresh' | 'stale' | 'critical'
  affected_detectors?: string[]
}
