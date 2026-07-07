import type { CaseGuidance } from './guidance'
export type { CaseGuidance } from './guidance'

export type Priority = 'HIGH' | 'MEDIUM' | 'LOW'
export type CaseStatus =
  | 'new' | 'assigned' | 'in_review' | 'ready_for_notice' | 'pending_supervisor'
  | 'notice_sent' | 'provider_responded' | 'reconciling'
  | 'closed_recovered' | 'closed_written_off' | 'closed_overturned' | 'closed_no_overpayment'
  | 'closed_not_for_recoup'
  // 835-created case awaiting its matching 837 (diagnoses) before dx-rules run
  | 'awaiting_837'
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

export interface CPTCodeFull {
  code: string
  description: string
  code_type: string
  risk_level: string
  cms_rac_flag: boolean
  specialty_typical: string
  typical_setting: string
  applicable_settings: string | null   // JSON array
  is_add_on: boolean
  global_period_days: number | null
  risk_score: number
  audit_notes: string | null
  source_authority: string | null
  source_document: string | null
  last_reviewed_at: string | null
  data_confidence: number
  rule_certainty: string
}

export interface ExcludedProvider {
  excluded_provider_id: string
  npi: string
  last_name: string | null
  first_name: string | null
  middle_name: string | null
  business_name: string | null
  general_category: string | null
  specialty: string | null
  city: string | null
  state: string | null
  exclusion_type: string | null
  exclusion_date: string | null
  reinstate_date: string | null
  waiver_date: string | null
  source: string
}

export interface ExcludedProviderList {
  items: ExcludedProvider[]
  total: number
  page: number
  page_size: number
}

export interface ICDCodeFull {
  code: string
  description: string
  code_type: string
  category: string
  chapter: string | null
  is_manifestation: boolean
  is_etiology: boolean
  typical_setting: string
  applicable_settings: string | null   // JSON array of care settings
  typical_drg: string | null           // soft ref to DRG code
  valid_as_primary_dx: boolean
  audit_notes: string | null
  source_authority: string | null
  source_document: string | null
  last_reviewed_at: string | null
  data_confidence: number
  rule_certainty: string
}

export interface DRGCode {
  code: string
  description: string
  drg_type: string
  mdc: string | null
  mdc_description: string | null
  weight: number | null
  geometric_mean_los: number | null
  arithmetic_mean_los: number | null
  is_surgical: boolean
  effective_fy: string | null
  mcc_drg: string | null
  base_drg: string | null
  typical_principal_dx: string | null   // JSON array
  typical_procedures: string | null     // JSON array
  clinical_criteria: string | null
  audit_notes: string | null
  source_authority: string | null
  source_document: string | null
  last_reviewed_at: string | null
  data_confidence: number
  rule_certainty: string
}

export interface ModifierCode {
  code: string
  description: string
  modifier_type: string
  applies_to: string
  payment_impact: string | null
  payment_factor: number | null
  ncci_override: boolean
  requires_documentation: boolean
  audit_risk_score: number
  audit_notes: string | null
  source_authority: string | null
  source_document: string | null
  last_reviewed_at: string | null
  data_confidence: number
  rule_certainty: string
}

export interface CptDxCoverage {
  cpt_code: string
  icd_code: string
  coverage_type: string
  rationale: string | null
  source_authority: string | null
  source_document: string | null
  last_reviewed_at: string | null
  data_confidence: number
  rule_certainty: string
}

export interface CptModifierMap {
  cpt_code: string
  modifier_code: string
  payment_factor: number | null
  ncci_override: boolean
  notes: string | null
  source_authority: string | null
  source_document: string | null
  last_reviewed_at: string | null
  data_confidence: number
  rule_certainty: string
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
  at_risk_amount?: number | null
  at_risk_detector_id?: string | null
}

export type DispositionStatus = 'accepted' | 'rejected' | 'needs_review' | 'adjusted'

export interface ClaimFinding {
  id: string       // UUID
  detector_code: string
  finding_type: string
  description: string
  overpayment_amount: number
  confidence_score: number
  evidence_json: string
  created_at: string
  attributed_amount?: number   // $ this finding contributes to case at-risk total
  suppressed_amount?: number   // $ this finding claimed but lost dedup to a higher-priority detector
  superseded_by?: string[]     // detector_ids that won the lines this finding claimed
  // Phase 2 disposition state:
  disposition_status?: DispositionStatus | null
  disposition_adjusted_amount?: number | null
  disposition_reason?: string | null
  // NULL/absent = system-seeded default disposition; set = real analyst decision
  disposition_decided_by_user_id?: string | null
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
  service_date: string | null
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
  severity_pts: number      // EMV-normalized × severity_weight
  urgency_pts: number
  amount_at_risk: number
  evidence_score: number    // E — rule corroboration (noisy-OR), prior excluded
  emv: number               // E × amount_at_risk (expected recoverable value)
  prior_score: number       // ML model screening score
  rule_leak: number         // L — evidence floor / rule leakage rate
  disagreement: boolean     // high prior but rules found ~nothing → human review
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
  rendering_provider?: { id: string; npi: string; name: string; specialty: string }
  provider_org_id?: string
  provider_org_name?: string
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
  case_id: string     // UUID for API calls
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
  awaiting_overdue?: boolean
  primary_detector_id?: string | null
  primary_detector_name?: string | null
  escalation?: EscalationSummary | null
}

export interface CaseNote {
  id: string
  body: string
  created_at: string
  author?: User
}

export interface PendingDecision {
  disposition: string
  reason?: string
  recovered_amount?: number
  submitted_by_user_id?: string
  submitted_at?: string
}

export interface EscalationSummary {
  is_active: boolean
  reason?: string | null
  escalated_at?: string | null
  escalated_by_full_name?: string | null
  escalated_by_user_id?: string | null
}

export interface CaseDetail extends CaseSummary {
  supervisor?: User
  breakdown: LikelihoodBreakdown
  audit_logs: AuditLog[]
  disputes: Dispute[]
  notices: RecoveryNotice[]
  notes: WorkflowNote[]
  case_notes: CaseNote[]
  group_id: string | null
  era_transaction_number?: string | null
  era_claim_count?: number | null
  era_sibling_case_numbers?: string[]
  priority_breakdown?: PriorityBreakdown
  detector_results?: DetectorResult[]
  posterior_score?: number
  pending_decision?: PendingDecision | null
  suggested_decision?: SuggestedDecision | null
  guidance?: CaseGuidance | null
}

export interface SuggestedDecision {
  recommendation: 'recoup' | 'not_for_recoup' | 'review'
  confidence: number   // 0..1
  reason: string
}

export interface CaseListResponse {
  items: CaseSummary[]
  total: number
  page: number
  page_size: number
}

export interface WorklistFilters {
  status?: CaseStatus
  statuses?: CaseStatus[]    // multi-status queue filter (OR)
  priority?: Priority
  lob?: LOB
  detector_code?: string
  assignee_id?: string
  scope?: 'mine_or_unassigned'   // when set, server restricts to current user + unassigned
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
