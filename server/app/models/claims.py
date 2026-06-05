from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from uuid import uuid4

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


def _uuid() -> str:
    return str(uuid4())


def _now() -> str:
    return datetime.utcnow().isoformat()


def line_diag_codes(line: "ClaimLine") -> list[str]:
    """Return the ICD codes assigned to a service line (diag_1–diag_4)."""
    return [c for c in [line.diag_1, line.diag_2, line.diag_3, line.diag_4] if c]


class CaseGroup(Base):
    __tablename__ = "case_groups"

    case_group_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    group_number: Mapped[str] = mapped_column(String(50), unique=True)
    provider_org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("provider_orgs.provider_org_id")
    )
    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.member_id"))
    dos_range_start: Mapped[str] = mapped_column(String(10))
    dos_range_end: Mapped[str] = mapped_column(String(10))
    group_reason: Mapped[str] = mapped_column(Text)
    duplicate_suspected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)

    org: Mapped["ProviderOrg"] = relationship("ProviderOrg", lazy="selectin")
    member: Mapped["Member"] = relationship("Member", lazy="selectin")
    claims: Mapped[List["Claim"]] = relationship(
        "Claim", back_populates="case_group", lazy="selectin"
    )


class Transaction835(Base):
    __tablename__ = "transactions_835"

    transaction_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    transaction_number: Mapped[str] = mapped_column(String(100), unique=True)
    transaction_type: Mapped[str] = mapped_column(String(50))
    payer_name: Mapped[str] = mapped_column(String(255))
    provider_org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("provider_orgs.provider_org_id")
    )
    transaction_date: Mapped[str] = mapped_column(String(10))
    total_amount: Mapped[float] = mapped_column(Float)
    claim_count: Mapped[int] = mapped_column(Integer)
    raw_835_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(30), default=_now)

    org: Mapped["ProviderOrg"] = relationship("ProviderOrg", lazy="selectin")
    payments: Mapped[List["ClaimPayment835"]] = relationship(
        "ClaimPayment835", back_populates="transaction", lazy="selectin"
    )


class EraAdjustmentCode(Base):
    """One CAS triplet (group_code + reason_code + amount) for an 835 SVC line payment."""
    __tablename__ = "era_adjustment_codes"

    adjustment_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    payment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("claim_payments_835.payment_id"), nullable=False
    )
    group_code: Mapped[str] = mapped_column(String(2), nullable=False)   # CO, PR, OA, CR, PI, WO
    reason_code: Mapped[str] = mapped_column(String(10), nullable=False)  # 45, 97, etc.
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, default=1)

    payment: Mapped["ClaimPayment835"] = relationship(
        "ClaimPayment835", back_populates="adjustment_codes", lazy="selectin"
    )


class ClaimPayment835(Base):
    __tablename__ = "claim_payments_835"

    payment_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    transaction_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("transactions_835.transaction_id")
    )
    claim_icn: Mapped[str] = mapped_column(String(100))
    # Nullable soft-FK resolved after 835 is matched to an ingested 837/pre-pay claim.
    claim_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("claims.claim_id"), nullable=True)
    claim_line_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("claim_lines.claim_line_id"), nullable=True)
    cpt_code: Mapped[str] = mapped_column(String(10))
    paid_amount: Mapped[float] = mapped_column(Float)
    adjustment_amount: Mapped[float] = mapped_column(Float, default=0.0)
    check_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    payment_date: Mapped[str] = mapped_column(String(10))

    transaction: Mapped["Transaction835"] = relationship(
        "Transaction835", back_populates="payments", lazy="selectin"
    )
    adjustment_codes: Mapped[List["EraAdjustmentCode"]] = relationship(
        "EraAdjustmentCode", back_populates="payment", lazy="selectin"
    )


class Claim(Base):
    __tablename__ = "claims"

    claim_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    icn: Mapped[str] = mapped_column(String(100), unique=True)
    case_group_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("case_groups.case_group_id"), nullable=True
    )
    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.member_id"))
    provider_org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("provider_orgs.provider_org_id")
    )
    billing_provider_npi: Mapped[str] = mapped_column(String(20))
    rendering_provider_npi: Mapped[str] = mapped_column(String(20))
    lob: Mapped[str] = mapped_column(String(50))
    # Intake discriminator. 'post_pay' = PayGuard pipeline; 'pre_pay' = ClaimGuard
    # pipeline (claim is being reviewed before payment). Drives which edits fire
    # and which workflow the resulting case follows. FWA is NOT a pipeline mode —
    # it's a case/finding disposition that can arise from either pipeline.
    # server_default (not just ORM default=) so create_all-built DBs carry the
    # SQL default — raw INSERTs (seeds, X12 intake) may omit this discriminator.
    pipeline_mode: Mapped[str] = mapped_column(String(20), default="post_pay", server_default="post_pay")
    service_from_date: Mapped[str] = mapped_column(String(10))
    service_to_date: Mapped[str] = mapped_column(String(10))
    claim_type: Mapped[str] = mapped_column(String(50), default="professional")
    # ClaimGuard claim-form metadata (PDF intake). claim_form_type captures the
    # 837/paper form variant; care_setting captures inpatient vs outpatient.
    claim_form_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    care_setting: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    drg: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    # Claim-level specialty for auto-routing (denormalized from provider).
    specialty: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Raw values from the submitted document (PDF or X12), captured before
    # member/provider resolution. Detectors check these to assess what the
    # submitter actually provided, independent of what resolved in our DB.
    submitted_member_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    submitted_patient_dob: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    # Append-only AI evidence corpus from PDF text extraction + recheck notes.
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # LLM-generated plain-language summary; written once after AI analysis.
    claim_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # JSON {cpt_or_icd_code: description} — lets AI fill descriptions for codes
    # not present in cpt_codes / icd_codes lookup tables.
    code_descriptions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    claim_status: Mapped[str] = mapped_column(String(50))
    total_billed: Mapped[float] = mapped_column(Float)
    # Nullable for pre-pay claims (payment hasn't occurred yet).
    total_paid: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    paid_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    authorization_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # UB-04 bill type (e.g. "111" inpatient admit-discharge, "131" outpatient).
    # Populated only for institutional claims; NULL on professional (CMS-1500) claims.
    bill_type: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    submission_date: Mapped[str] = mapped_column(String(10))
    pos_code: Mapped[str] = mapped_column(String(5))
    primary_icd: Mapped[str] = mapped_column(String(10))
    # Intake origin: pdf | x12_837 | x12_835 | manual
    source_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # Absorbed from ClaimHeader837 (dropped table).
    submitter_npi: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    claim_frequency_code: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    era_transaction_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("transactions_835.transaction_id"), nullable=True
    )
    raw_claim_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)

    member: Mapped["Member"] = relationship("Member", lazy="selectin")
    provider_org: Mapped["ProviderOrg"] = relationship("ProviderOrg", lazy="selectin")
    case_group: Mapped[Optional["CaseGroup"]] = relationship(
        "CaseGroup", back_populates="claims", lazy="selectin"
    )
    era_transaction: Mapped[Optional["Transaction835"]] = relationship(
        "Transaction835", foreign_keys=[era_transaction_id], lazy="selectin"
    )
    lines: Mapped[List["ClaimLine"]] = relationship(
        "ClaimLine", back_populates="claim", lazy="selectin"
    )


class ClaimLine(Base):
    __tablename__ = "claim_lines"

    claim_line_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    claim_id: Mapped[str] = mapped_column(String(36), ForeignKey("claims.claim_id"))
    line_number: Mapped[int] = mapped_column(Integer)
    cpt_code: Mapped[str] = mapped_column(String(10))
    # Diagnosis code pointers for this line (replaces icd_codes JSON column).
    diag_1: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    diag_2: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    diag_3: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    diag_4: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    modifier_1: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    modifier_2: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    modifier_3: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    modifier_4: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    units_billed: Mapped[int] = mapped_column(Integer)
    # Nullable on pre-pay lines (no adjudication yet).
    units_paid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    billed_amount: Mapped[float] = mapped_column(Float)
    paid_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    allowed_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pos_code: Mapped[str] = mapped_column(String(5))
    revenue_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    claim: Mapped["Claim"] = relationship("Claim", back_populates="lines", lazy="selectin")
