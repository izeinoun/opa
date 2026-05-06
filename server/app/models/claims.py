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


class ClaimPayment835(Base):
    __tablename__ = "claim_payments_835"

    payment_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    transaction_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("transactions_835.transaction_id")
    )
    claim_icn: Mapped[str] = mapped_column(String(100))
    cpt_code: Mapped[str] = mapped_column(String(10))
    paid_amount: Mapped[float] = mapped_column(Float)
    adjustment_amount: Mapped[float] = mapped_column(Float, default=0.0)
    adjustment_reason_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    check_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    payment_date: Mapped[str] = mapped_column(String(10))

    transaction: Mapped["Transaction835"] = relationship(
        "Transaction835", back_populates="payments", lazy="selectin"
    )


class ClaimHeader837(Base):
    __tablename__ = "claim_headers_837"

    header_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    claim_icn: Mapped[str] = mapped_column(String(100), unique=True)
    submitter_npi: Mapped[str] = mapped_column(String(20))
    billing_provider_npi: Mapped[str] = mapped_column(String(20))
    submission_date: Mapped[str] = mapped_column(String(10))
    total_billed: Mapped[float] = mapped_column(Float)
    claim_frequency_code: Mapped[str] = mapped_column(String(5), default="1")
    raw_837_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(30), default=_now)


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
    service_from_date: Mapped[str] = mapped_column(String(10))
    service_to_date: Mapped[str] = mapped_column(String(10))
    claim_type: Mapped[str] = mapped_column(String(50), default="professional")
    claim_status: Mapped[str] = mapped_column(String(50))
    total_billed: Mapped[float] = mapped_column(Float)
    total_paid: Mapped[float] = mapped_column(Float)
    paid_date: Mapped[str] = mapped_column(String(10))
    authorization_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    submission_date: Mapped[str] = mapped_column(String(10))
    pos_code: Mapped[str] = mapped_column(String(5))
    primary_icd: Mapped[str] = mapped_column(String(10))
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
    icd_codes: Mapped[str] = mapped_column(Text)            # JSON array
    modifier_1: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    modifier_2: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    units_billed: Mapped[int] = mapped_column(Integer)
    units_paid: Mapped[int] = mapped_column(Integer)
    billed_amount: Mapped[float] = mapped_column(Float)
    paid_amount: Mapped[float] = mapped_column(Float)
    allowed_amount: Mapped[float] = mapped_column(Float)
    pos_code: Mapped[str] = mapped_column(String(5))
    revenue_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    claim: Mapped["Claim"] = relationship("Claim", back_populates="lines", lazy="selectin")
