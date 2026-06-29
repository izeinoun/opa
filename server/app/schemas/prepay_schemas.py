"""Pydantic schemas for pre-pay claim intake, AI analysis, documents,
and runtime_config endpoints. Ported from ClaimGuard's schemas.py and
adapted to OPA's UUIDs + normalized FK shape."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# ── Claim lines ──────────────────────────────────────────────────────────

class ClaimLineOut(BaseModel):
    id: str                             # claim_line_id (UUID)
    line_number: int
    revenue_code: Optional[str] = None  # UB-04 FL 42; null for CMS-1500 lines
    cpt_code: str
    modifier_1: Optional[str] = None
    modifier_2: Optional[str] = None
    units_billed: int = 1
    billed_amount: float
    icd_codes: List[str] = []


# ── AI findings (the unified findings table, shaped for the pre-pay UI) ──

class FindingDecisionOut(BaseModel):
    """A specialist's Accept/Reject decision on a single AI finding."""
    status: str             # accepted | rejected
    comment: Optional[str] = None
    decided_by_user_id: Optional[str] = None
    decided_at: Optional[str] = None


class AIFindingOut(BaseModel):
    id: str                 # finding_id (UUID)
    severity: str           # critical | warning | ok
    title: Optional[str] = None
    body: str               # mapped from findings.rationale
    # Concise, billing-provider-facing pair (null on detector/legacy findings;
    # UI falls back to `body`).
    issue_summary: Optional[str] = None   # mapped from findings.issue_summary
    suggestion: Optional[str] = None      # mapped from findings.suggestion
    created_at: str         # mapped from findings.fired_at
    # detector_id passes through so the UI can distinguish CG-BASIC-V1
    # (general audit) from FWA-04 / FWA-07 (specific fraud signals).
    detector_id: Optional[str] = None
    fwa_indicator: bool = False
    fwa_rule_code: Optional[str] = None
    # Specialist decision (null = still pending review).
    decision: Optional[FindingDecisionOut] = None


class FindingDecisionIn(BaseModel):
    status: str = Field(pattern="^(accepted|rejected|pending)$")
    comment: Optional[str] = None
    user_id: Optional[str] = None


class FindingsLetterIn(BaseModel):
    user_id: Optional[str] = None


class FindingsLetterOut(BaseModel):
    letter: str
    accepted_count: int
    generated_at: str


# ── Documents ────────────────────────────────────────────────────────────

class DocumentOut(BaseModel):
    id: str                 # document_id (UUID)
    claim_id: Optional[str] = None
    case_id: Optional[str] = None
    filename: str
    file_size_kb: int
    kind: str
    uploaded_at: str
    uploaded_by_user_id: Optional[str] = None


# ── Claim payloads (pre-pay shape, separate from PayGuard's CaseDetail) ──

class PrepayClaimOut(BaseModel):
    """Lightweight read model for pre-pay list views."""
    claim_id: str
    icn: str
    pipeline_mode: str
    claim_form_type: Optional[str] = None
    care_setting: Optional[str] = None
    drg: Optional[str] = None
    cpts: List[str] = []                # assembled from claim_lines
    icd10: List[str] = []               # primary_icd + line ICDs
    member_number: Optional[str] = None  # payer-assigned; cross-system join key to ClearLink
    provider_name: Optional[str] = None
    patient_name: Optional[str] = None
    dob: Optional[str] = None
    dos: str
    billed_amount: float
    status: str
    specialty: Optional[str] = None
    description: Optional[str] = None
    summary: Optional[str] = None       # claim_summary (LLM-generated)
    code_descriptions: Optional[dict] = None
    created_at: str
    updated_at: str


class CommentOut(BaseModel):
    """Reads from case_notes; surfaced as 'comment' for ClaimGuard UI parity."""
    id: str                 # note_id
    claim_id: str           # filled from the case→claim relationship
    user_id: str            # author_user_id
    body: str
    created_at: str


class AuditLogOut(BaseModel):
    """Reads from audit_logs. Shape mirrors ClaimGuard's for UI parity."""
    id: str                 # audit_id
    claim_id: Optional[str] = None
    user_id: str            # actor_user_id
    action: str             # human-readable; ClaimGuard concatenates from_state/to_state if structured
    created_at: str


class UserOut(BaseModel):
    """User picker entry. Adapted from opa_users for ClaimGuard UI parity.

    The legacy single 'role' is still populated (from opa_users.role) for
    backward compat with frontends that haven't been updated to read the
    multi-role 'roles' list. New code should read 'roles' and 'apps'."""
    id: str                 # user_id (UUID)
    name: str               # full_name
    username: Optional[str] = None
    email: Optional[str] = None
    role: str               # legacy primary role
    is_active: bool = True
    initials: Optional[str] = None
    color_hex: Optional[str] = None
    specialty: Optional[str] = None
    supervisor_id: Optional[str] = None
    # RBAC — populated from user_roles + role_apps.
    roles: List[str] = []   # role_name list
    apps: List[str] = []    # app_name list (effective union)
    default_app: Optional[str] = None  # app_name; convenient for UI landing
    default_app_id: Optional[str] = None


class AppOut(BaseModel):
    id: str                 # app_id (UUID)
    name: str               # app_name
    description: str = ""
    is_active: bool = True


class RoleOut(BaseModel):
    id: str                 # role_id (UUID)
    name: str               # role_name
    description: str = ""
    apps: List[str] = []    # app_names this role grants


class UserRoleAssignment(BaseModel):
    role_id: str
    granted_by_user_id: Optional[str] = None


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    full_name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=1, max_length=255)
    role: str = "analyst"                   # legacy single role; primary
    initials: Optional[str] = None
    color_hex: Optional[str] = None
    specialty: Optional[str] = None
    default_app_id: Optional[str] = None
    role_ids: List[str] = []                # initial role assignments


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    initials: Optional[str] = None
    color_hex: Optional[str] = None
    specialty: Optional[str] = None
    is_active: Optional[bool] = None
    default_app_id: Optional[str] = None


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    description: str = ""
    app_ids: List[str] = []


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class AppCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    description: str = ""


class AppUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class StatusUpdate(BaseModel):
    status: str
    user_id: Optional[str] = None
    review_time_minutes: Optional[int] = None


class CommentCreate(BaseModel):
    body: str = Field(min_length=1)
    user_id: str


class PrepayClaimDetail(PrepayClaimOut):
    """Full detail with related collections — used by the claim detail page."""
    extracted_text: Optional[str] = ""
    review_time_minutes: int = 0
    assigned_to: Optional[str] = None   # mirrors the inline name; not currently editable
    priority: Optional[str] = None      # ClaimGuard UI expects this; we map from claim metadata
    # Case reference — always present after intake; null only on legacy rows
    # that predate eager case creation.
    case_number: Optional[str] = None   # e.g. "OPA-2026-00042"
    case_status: Optional[str] = None   # prepay: new|in_process|awaiting_info|escalated|closed
    lines: List[ClaimLineOut] = []
    ai_findings: List[AIFindingOut] = []
    documents: List[DocumentOut] = []
    comments: List[CommentOut] = []
    audit_log: List[AuditLogOut] = []


# ── Inputs ───────────────────────────────────────────────────────────────

class RecheckIn(BaseModel):
    note: str = Field(min_length=1)
    user_id: Optional[str] = None


class ReanalyzeIn(BaseModel):
    user_id: Optional[str] = None


class SummaryRequest(BaseModel):
    force: bool = False


class CodeDescriptionsRequest(BaseModel):
    force: bool = False


# ── Runtime config (flat key/value) ──────────────────────────────────────

class RuntimeConfigOut(BaseModel):
    key: str
    value: str
    updated_at: str


class RuntimeConfigUpdate(BaseModel):
    value: str
