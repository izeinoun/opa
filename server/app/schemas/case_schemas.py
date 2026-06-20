from pydantic import BaseModel
from typing import Optional, List


class UserRead(BaseModel):
    id: str
    username: str
    full_name: str
    email: str
    role: str
    is_active: bool


class ProviderRead(BaseModel):
    id: str
    npi: str
    name: str
    specialty: str
    risk_tier: int
    billing_variance_score: float
    is_excluded: bool


class MemberRead(BaseModel):
    id: str
    member_id: str
    name: str
    dob: str
    lob: str


class ClaimLineRead(BaseModel):
    id: str
    line_number: int
    cpt_code: str
    icd_codes: List[str]
    units: int
    billed_amount: float
    allowed_amount: float
    paid_amount: float
    modifier: Optional[str] = None
    service_date: str
    at_risk_amount: Optional[float] = None
    at_risk_detector_id: Optional[str] = None


class ClaimFindingRead(BaseModel):
    id: str
    detector_code: str
    finding_type: str
    description: str
    overpayment_amount: float
    confidence_score: float
    evidence_json: str
    created_at: str
    # Per-finding dedup attribution (computed at serialization time):
    attributed_amount: float = 0.0   # $ this finding contributes to case at-risk total
    suppressed_amount: float = 0.0   # $ this finding claimed but lost to higher-priority detector
    superseded_by: List[str] = []    # detector_ids that won the suppressed lines
    # Phase 2 — analyst disposition:
    disposition_status: Optional[str] = None        # accepted | rejected | needs_review | adjusted
    disposition_adjusted_amount: Optional[float] = None
    disposition_reason: Optional[str] = None
    # FWA flagging — when true, this finding also represents an FWA rule
    # firing; SIU triages these. `fwa_rule_code` is the FWA-XX label.
    fwa_indicator: bool = False
    fwa_rule_code: Optional[str] = None


class ERAPaymentLineRead(BaseModel):
    id: str
    claim_icn: str
    cpt_code: str
    paid_amount: float
    adjustment_amount: float
    adjustment_reason_code: Optional[str] = None
    check_number: Optional[str] = None
    payment_date: str
    service_date: Optional[str] = None


class ERATransactionRead(BaseModel):
    id: str
    era_number: str
    transaction_type: str
    payer_name: str
    payment_date: str
    payment_amount: float
    claim_count: int
    payments: List[ERAPaymentLineRead] = []
    raw_835: Optional[str] = None


class ClaimSummary(BaseModel):
    id: str
    claim_number: str
    lob: str
    total_billed: float
    total_allowed: Optional[float] = None
    total_paid: Optional[float] = None      # nullable since pre-pay claims have no payment yet
    status: str
    service_date_start: str
    member: Optional[MemberRead] = None
    rendering_provider: Optional[ProviderRead] = None
    provider_org_id: Optional[str] = None
    provider_org_name: Optional[str] = None
    # Claim-level coding & form fields
    primary_icd: Optional[str] = None
    other_icd_codes: List[str] = []         # all ICD codes across claim lines, deduped, excl. primary
    drg: Optional[str] = None
    bill_type: Optional[str] = None
    claim_form_type: Optional[str] = None   # CMS-1500 | UB-04
    care_setting: Optional[str] = None      # Inpatient | Outpatient
    pos_code: Optional[str] = None
    lines: List[ClaimLineRead] = []
    findings: List[ClaimFindingRead] = []
    era_transactions: List[ERATransactionRead] = []


class LikelihoodBreakdown(BaseModel):
    cpt_risk_score: float
    provider_risk_tier: int
    dx_cpt_mismatch_score: float
    claim_complexity_score: float
    billing_variance_score: float
    likelihood_score: float


class AuditLogRead(BaseModel):
    id: str
    action: str
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    notes: Optional[str] = None
    created_at: str
    user: Optional[UserRead] = None


class CaseNoteRead(BaseModel):
    id: str
    body: str
    created_at: str
    author: Optional[UserRead] = None


class CaseNoteCreate(BaseModel):
    body: str


class DisputeRead(BaseModel):
    id: str
    dispute_date: str
    reason: str
    response_due: str
    response_date: Optional[str] = None
    outcome: Optional[str] = None
    notes: Optional[str] = None


class RecoveryNoticeRead(BaseModel):
    id: str
    sent_date: str
    amount_demanded: float
    response_due: str
    delivery_method: str
    status: str
    # Optional rich fields populated by the letters routes; case detail summaries leave them blank
    notice_id: Optional[str] = None
    template_id: Optional[str] = None
    lob: Optional[str] = None
    sent_at: Optional[str] = None
    generated_at: Optional[str] = None
    letter_content: Optional[str] = None


class WorkflowNoteRead(BaseModel):
    id: str
    note_text: str
    note_type: str
    created_at: str
    user: Optional[UserRead] = None


class PriorityBreakdown(BaseModel):
    total_score: float
    band: str
    amount_pts: float
    likelihood_pts: float
    urgency_pts: float
    amount_at_risk: float
    likelihood_score: float   # posterior — drives the 0.45 pts
    prior_score: float        # ML model output (composite_likelihood)
    urgency_factor: float
    urgency_override_applied: bool
    days_overdue: Optional[int] = None
    days_until: Optional[int] = None


class DetectorResultRead(BaseModel):
    detector_id: str
    detector_name: str
    fired: bool
    finding: Optional[ClaimFindingRead] = None


class EscalationSummary(BaseModel):
    is_active: bool
    reason: Optional[str] = None
    escalated_at: Optional[str] = None
    escalated_by_full_name: Optional[str] = None
    escalated_by_user_id: Optional[str] = None


class CaseSummary(BaseModel):
    id: int           # = case_sequence (integer) for human-readable routing
    case_id: Optional[str] = None        # UUID; required by SIU escalation endpoint
    case_number: str
    status: str
    priority: str
    priority_score: float
    likelihood_score: float
    amount_billed: Optional[float] = None
    amount_at_risk: Optional[float] = None  # nullable for pre-pay cases (no overpayment yet)
    deadline: Optional[str] = None
    is_active: bool
    opened_at: str
    lob: str
    assignee: Optional[UserRead] = None
    claim: Optional[ClaimSummary] = None
    requires_supervisor_approval: bool = False
    primary_detector_id: Optional[str] = None
    primary_detector_name: Optional[str] = None
    escalation: Optional[EscalationSummary] = None
    # SIU integration
    siu_investigation_id: Optional[str] = None
    siu_frozen: bool = False
    law_enforcement_hold: bool = False


class PendingDecision(BaseModel):
    """Stashed closure submitted by an analyst awaiting supervisor approval."""
    disposition: str
    reason: Optional[str] = None
    recovered_amount: Optional[float] = None
    submitted_by_user_id: Optional[str] = None
    submitted_at: Optional[str] = None


class CaseDetail(CaseSummary):
    supervisor: Optional[UserRead] = None
    breakdown: Optional[LikelihoodBreakdown] = None
    audit_logs: List[AuditLogRead] = []
    disputes: List[DisputeRead] = []
    notices: List[RecoveryNoticeRead] = []
    notes: List[WorkflowNoteRead] = []
    case_notes: List[CaseNoteRead] = []
    group_id: Optional[str] = None
    priority_breakdown: Optional[PriorityBreakdown] = None
    detector_results: List[DetectorResultRead] = []
    pending_decision: Optional[PendingDecision] = None
    posterior_score: Optional[float] = None


class CaseCreate(BaseModel):
    claim_id: str
    assignee_id: Optional[str] = None


class CaseTransition(BaseModel):
    to_status: str
    reason: Optional[str] = None
    recovered_amount: Optional[float] = None


class SupervisorDecision(BaseModel):
    reason: Optional[str] = None  # required on reject, optional on approve


class CaseListResponse(BaseModel):
    items: List[CaseSummary]
    total: int
    page: int
    page_size: int


class WorklistFilters(BaseModel):
    # Special-case filter: cases assigned to me OR unassigned. Used by the
    # "My cases & Unassigned" worklist toggle. Set by the route from the
    # current user — never accepted directly from the client.
    mine_or_unassigned_for_user_id: Optional[str] = None
    # Pipeline gate. Set by the PayGuard route to 'post_pay' so pre-pay
    # ClaimGuard cases (PREPAY-CASE-*) don't leak into the post-pay worklist.
    pipeline_mode: Optional[str] = None
    # ↓ existing fields below ↓
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee_id: Optional[str] = None
    lob: Optional[str] = None
    detector_code: Optional[str] = None
    days_open_min: Optional[int] = None
    days_open_max: Optional[int] = None
    group_id: Optional[str] = None
    search: Optional[str] = None
    exclude_closed: bool = False
    closed_only: bool = False
    overdue_only: bool = False


class ClaimDetail(ClaimSummary):
    pass


class CPTCodeRead(BaseModel):
    code: str
    description: str
    code_type: str
    risk_level: str
    cms_rac_flag: bool
    specialty_typical: str
    typical_setting: str
    applicable_settings: Optional[str]   # JSON array
    is_add_on: bool
    global_period_days: Optional[int]
    risk_score: float
    audit_notes: Optional[str]
    source_authority: Optional[str]
    source_document: Optional[str]
    last_reviewed_at: Optional[str]
    data_confidence: float
    rule_certainty: str


class ICDCodeRead(BaseModel):
    code: str
    description: str
    code_type: str
    category: str
    chapter: Optional[str]
    is_manifestation: bool
    is_etiology: bool
    typical_setting: str
    applicable_settings: Optional[str]   # JSON array
    typical_drg: Optional[str]           # soft ref to drg_codes.code
    valid_as_primary_dx: bool
    audit_notes: Optional[str]
    source_authority: Optional[str]
    source_document: Optional[str]
    last_reviewed_at: Optional[str]
    data_confidence: float
    rule_certainty: str


class DRGCodeRead(BaseModel):
    code: str
    description: str
    drg_type: str
    mdc: Optional[str]
    mdc_description: Optional[str]
    weight: Optional[float]
    geometric_mean_los: Optional[float]
    arithmetic_mean_los: Optional[float]
    is_surgical: bool
    effective_fy: Optional[str]
    mcc_drg: Optional[str]
    base_drg: Optional[str]
    typical_principal_dx: Optional[str]   # JSON array
    typical_procedures: Optional[str]     # JSON array
    clinical_criteria: Optional[str]
    audit_notes: Optional[str]
    source_authority: Optional[str]
    source_document: Optional[str]
    last_reviewed_at: Optional[str]
    data_confidence: float
    rule_certainty: str


class ModifierCodeRead(BaseModel):
    code: str
    description: str
    modifier_type: str
    applies_to: str
    payment_impact: Optional[str]
    payment_factor: Optional[float]
    ncci_override: bool
    requires_documentation: bool
    audit_risk_score: float
    audit_notes: Optional[str]
    source_authority: Optional[str]
    source_document: Optional[str]
    last_reviewed_at: Optional[str]
    data_confidence: float
    rule_certainty: str
