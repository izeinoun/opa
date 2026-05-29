"""Pydantic schemas for pre-pay claim intake, AI analysis, documents,
and runtime_config endpoints. Ported from ClaimGuard's schemas.py and
adapted to OPA's UUIDs + normalized FK shape."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# ── AI findings (the unified findings table, shaped for the pre-pay UI) ──

class AIFindingOut(BaseModel):
    id: str                 # finding_id (UUID)
    severity: str           # critical | warning | ok
    title: Optional[str] = None
    body: str               # mapped from findings.rationale
    created_at: str         # mapped from findings.fired_at


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


class PrepayClaimDetail(PrepayClaimOut):
    """Full detail with related collections — used by the claim detail page."""
    extracted_text: Optional[str] = ""
    ai_findings: List[AIFindingOut] = []
    documents: List[DocumentOut] = []


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
