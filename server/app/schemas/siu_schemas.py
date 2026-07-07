"""Pydantic schemas for the SIU workspace.

Maps to UC-SIU-01..06 in the spec. Distinct from prepay_schemas / case_schemas
because SIU is its own app with its own response shape.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ── Enums (string-literal types for clarity at the API boundary) ──────────

InvestigationType = Literal[
    "TIME_VOLUME_ANOMALY",
    "SUBROGATION",
    "EXCLUDED_PROVIDER",
    "FRAUD_PATTERN",
    "OTHER",
]

InvestigationStatus = Literal[
    "OPEN",
    "PENDING_EXTERNAL_INFO",
    "PENDING_LAW_ENFORCEMENT",
    "REFERRAL_SUBMITTED",
    "CLOSED",
]

InvestigationOutcome = Literal[
    "FRAUD_CONFIRMED",
    "NO_FRAUD_FOUND",
    "INSUFFICIENT_EVIDENCE",
    "SUBROGATION_RECOVERY_INITIATED",
    "CASE_CLOSED_NO_ACTION",
]

EscalationSource = Literal[
    "analyst_referral",
    "dce_13",
    "dce_15",
    "pattern_threshold",
]

NoteType = Literal[
    "Interview",
    "Document Review",
    "External Source",
    "Internal Analysis",
    "Law Enforcement Coordination",
]

AgencyName = Literal["FBI", "OIG", "State AG", "Local Law Enforcement", "Other"]
ReferralType = Literal["Criminal Fraud", "Civil Recovery", "Both"]
ReferralOutcome = Literal["PURSUED", "DECLINED"]

SiuMode = Literal["A", "B"]   # A = internal, B = outsourced


# ── Inputs ────────────────────────────────────────────────────────────────

class EscalateCaseIn(BaseModel):
    """UC-SIU-01: PI analyst (or auto-router via DCE-13/15) escalates a case."""
    # Case UUID, or the numeric case sequence (assistant callers) — the service
    # resolves either.
    case_id: str = Field(coerce_numbers_to_str=True)
    investigation_type: InvestigationType = "OTHER"
    escalation_source: EscalationSource = "analyst_referral"
    escalation_reason: str = Field(min_length=1)
    # Optional — if provided, attach to an existing investigation (pattern grouping).
    # If omitted, a new investigation row is created for this case.
    target_investigation_id: Optional[str] = None


class OpenInvestigationIn(BaseModel):
    """UC-SIU-02: investigator confirms they're taking the case."""
    investigator_assigned_user_id: Optional[str] = None   # defaults to caller
    # Allow type refinement on open (case may turn out to be different than guessed)
    investigation_type: Optional[InvestigationType] = None


class AddCaseToInvestigationIn(BaseModel):
    """UC-SIU-02 alternate flow: pattern grouping — add another escalated
    case to an already-open investigation. The case must currently be in
    SIU_REFERRAL state (i.e. previously escalated)."""
    case_id: str


class AddNoteIn(BaseModel):
    """UC-SIU-03: investigator adds an immutable note."""
    note_date: str             # YYYY-MM-DD
    note_type: NoteType
    body: str = Field(min_length=1)
    is_confidential: bool = False


class UpdateInvestigationStatusIn(BaseModel):
    """UC-SIU-03: status updates without closing."""
    status: InvestigationStatus
    investigation_type: Optional[InvestigationType] = None


class FileReferralIn(BaseModel):
    """UC-SIU-04: file a formal law enforcement referral."""
    referral_date: str
    agency_name: AgencyName
    referral_type: ReferralType
    referral_summary: str = Field(min_length=100)   # min enforced per spec
    referral_contact_name: str = Field(min_length=1)


class RecordReferralOutcomeIn(BaseModel):
    """UC-SIU-04: record response/outcome from the agency."""
    response_received_date: str
    referral_outcome: ReferralOutcome
    outcome_notes: Optional[str] = None


class CloseInvestigationIn(BaseModel):
    """UC-SIU-05: close out the investigation with disposition."""
    outcome: InvestigationOutcome
    closure_notes: str = Field(min_length=50)        # min enforced per spec


class GenerateExportIn(BaseModel):
    """UC-SIU-06: generate (or re-generate) a JSON export package."""
    delivery_destination: Optional[str] = None


# ── Outputs ───────────────────────────────────────────────────────────────

class CaseSummaryForSIU(BaseModel):
    """Slim case shape embedded inside SIU queue + investigation responses."""
    case_id: str
    case_number: str
    claim_id: str
    icn: Optional[str] = None
    provider_org_name: Optional[str] = None
    billing_provider_npi: Optional[str] = None
    member_name: Optional[str] = None
    pipeline_mode: str
    claim_status: str
    case_status: str
    total_overpayment_amount: Optional[float] = None
    detector_ids: List[str] = []      # findings.detector_id values on this claim
    siu_frozen: bool
    law_enforcement_hold: bool


class InvestigationNoteOut(BaseModel):
    note_id: str
    investigation_id: str
    note_date: str
    note_type: str
    body: str
    is_confidential: bool
    author_user_id: str
    author_name: Optional[str] = None
    created_at: str


class LawEnforcementReferralOut(BaseModel):
    referral_id: str
    investigation_id: str
    referral_date: str
    agency_name: str
    referral_type: str
    referral_summary: str
    referral_contact_name: str
    submitted_by_user_id: str
    submitted_at: str
    response_received_date: Optional[str] = None
    referral_outcome: Optional[str] = None
    outcome_notes: Optional[str] = None
    closed_at: Optional[str] = None


class SIUExportPackageOut(BaseModel):
    package_id: str
    investigation_id: str
    version: int
    integrity_hash: str
    generated_at: str
    generated_by_user_id: Optional[str] = None
    delivery_status: str
    delivery_destination: Optional[str] = None
    delivery_attempts: int = 0
    last_attempt_at: Optional[str] = None
    last_error: Optional[str] = None
    # The package_json body is NOT included in the list response (large);
    # fetch it via the dedicated download endpoint.


class InvestigationOut(BaseModel):
    investigation_id: str
    investigation_type: str
    status: str
    outcome: Optional[str] = None
    closure_notes: Optional[str] = None
    escalation_source: str
    escalation_reason: str
    escalated_by_user_id: Optional[str] = None
    escalated_at: str
    investigator_assigned_user_id: Optional[str] = None
    investigator_assigned_name: Optional[str] = None
    opened_at: Optional[str] = None
    closed_at: Optional[str] = None
    closed_by_user_id: Optional[str] = None
    law_enforcement_hold: bool
    siu_mode: str
    created_at: str
    updated_at: str
    # Embedded collections
    cases: List[CaseSummaryForSIU] = []
    notes: List[InvestigationNoteOut] = []
    referrals: List[LawEnforcementReferralOut] = []
    exports: List[SIUExportPackageOut] = []


class SIUQueueRow(BaseModel):
    """Light-weight queue row — one per investigation in SIU_REFERRAL or
    SIU_INVESTIGATION_OPEN status (the active SIU workload)."""
    investigation_id: str
    investigation_type: str
    status: str
    escalation_source: str
    escalation_reason: str
    escalated_at: str
    investigator_assigned_user_id: Optional[str] = None
    investigator_assigned_name: Optional[str] = None
    law_enforcement_hold: bool
    siu_mode: str
    # Pipeline of the originating claim(s). Derived from the first linked
    # case's claim.pipeline_mode. 'mixed' if linked cases span both pipelines
    # (rare — pattern investigations across pre-pay + post-pay claims).
    pipeline_mode: str
    # Aggregates across all linked cases
    case_count: int
    provider_org_names: List[str] = []
    detector_ids: List[str] = []
    total_at_risk: Optional[float] = None   # sum of total_overpayment_amount
