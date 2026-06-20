"""Pydantic schemas for the File Intake (simulated drop-folder) feature."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class ExtractedServiceLine(BaseModel):
    """A document's per-line (procedure, date-of-service) pair used for
    line-to-line matching against a claim's lines."""
    cpt: Optional[str] = None
    date: Optional[str] = None


class IntakeFileOut(BaseModel):
    intake_id: str
    app: str
    category: str
    filename: str
    file_size_kb: int
    uploaded_at: str
    uploaded_by_user_id: Optional[str] = None
    extraction_status: Optional[str] = None
    extracted_member_number: Optional[str] = None
    extracted_member_name: Optional[str] = None
    extracted_dob: Optional[str] = None
    extracted_service_dates: List[str] = []
    extracted_service_lines: List[ExtractedServiceLine] = []
    status: str
    candidate_case_ids: List[str] = []
    message: Optional[str] = None
    result_case_id: Optional[str] = None
    result_claim_id: Optional[str] = None
    result_document_id: Optional[str] = None
    result_case_number: Optional[str] = None   # convenience for UI links
    created_at: str
    updated_at: str


class OutputFileOut(BaseModel):
    """A system-generated output document (e.g. a recoupment letter) surfaced
    in the Intake Portal's Output Files section."""
    document_id: str
    filename: str
    kind: str
    case_id: Optional[str] = None
    case_number: Optional[str] = None
    case_sequence: Optional[int] = None
    uploaded_at: str
    file_size_kb: int


class CandidateCaseOut(BaseModel):
    """A case the admin can pick from when resolving an unmatched document."""
    case_id: str
    case_number: str
    member_name: Optional[str] = None
    service_from_date: Optional[str] = None
    service_to_date: Optional[str] = None
    priority: Optional[str] = None
    status: str
    total_overpayment_amount: Optional[float] = None


class UnmatchedOut(IntakeFileOut):
    candidates: List[CandidateCaseOut] = []


class ResolveRequest(BaseModel):
    case_id: str
    user_id: Optional[str] = None
