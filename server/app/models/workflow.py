from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from uuid import uuid4

from sqlalchemy import Boolean, Float, ForeignKey, Integer, PrimaryKeyConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


def _uuid() -> str:
    return str(uuid4())


def _now() -> str:
    return datetime.utcnow().isoformat()


class OpaUser(Base):
    __tablename__ = "opa_users"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    full_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)


class Finding(Base):
    __tablename__ = "findings"

    finding_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    claim_id: Mapped[str] = mapped_column(String(36), ForeignKey("claims.claim_id"))
    claim_line_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("claim_lines.claim_line_id"), nullable=True
    )
    detector_id: Mapped[str] = mapped_column(String(50))
    detector_version: Mapped[str] = mapped_column(String(20))
    fired_at: Mapped[str] = mapped_column(String(30))
    overpayment_amount: Mapped[float] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Float)
    rationale: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)             # JSON
    rule_version: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="active")

    claim: Mapped["Claim"] = relationship("Claim", lazy="selectin")
    claim_line: Mapped[Optional["ClaimLine"]] = relationship("ClaimLine", lazy="selectin")


class OpaCase(Base):
    __tablename__ = "opa_cases"

    case_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_number: Mapped[str] = mapped_column(String(50), unique=True)
    case_sequence: Mapped[int] = mapped_column(Integer, default=1)
    claim_id: Mapped[str] = mapped_column(String(36), ForeignKey("claims.claim_id"))
    case_group_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("case_groups.case_group_id"), nullable=True
    )
    primary_detector_id: Mapped[str] = mapped_column(String(50))
    lob: Mapped[str] = mapped_column(String(50))
    provider_org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("provider_orgs.provider_org_id")
    )
    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.member_id"))
    assigned_analyst_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("opa_users.user_id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(50), default="new")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[str] = mapped_column(String(20))
    priority_score: Mapped[float] = mapped_column(Float)
    total_overpayment_amount: Mapped[float] = mapped_column(Float)
    recommended_recovery_method: Mapped[str] = mapped_column(String(50))
    identified_date: Mapped[str] = mapped_column(String(10))
    deadline_date: Mapped[str] = mapped_column(String(10))
    deadline_breached: Mapped[bool] = mapped_column(Boolean, default=False)
    lookback_window_start: Mapped[str] = mapped_column(String(10))
    provider_response_due_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    is_sensitive_provider: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_supervisor_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_bundle: Mapped[str] = mapped_column(Text)      # JSON
    case_json: Mapped[str] = mapped_column(Text)            # JSON
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)

    # One-active-per-claim: enforced at CaseService layer.
    # SQLite partial unique indexes are unreliable across versions;
    # CaseService.create_case() and reopen() check is_active before proceeding.

    claim: Mapped["Claim"] = relationship("Claim", lazy="selectin")
    case_group: Mapped[Optional["CaseGroup"]] = relationship("CaseGroup", lazy="selectin")
    assigned_analyst: Mapped[Optional["OpaUser"]] = relationship(
        "OpaUser", foreign_keys=[assigned_analyst_id], lazy="selectin"
    )
    case_findings: Mapped[List["CaseFinding"]] = relationship(
        "CaseFinding", back_populates="case", lazy="selectin"
    )
    likelihood_score: Mapped[Optional["LikelihoodScore"]] = relationship(
        "LikelihoodScore", back_populates="case", uselist=False, lazy="selectin"
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog", back_populates="case", lazy="selectin"
    )
    disputes: Mapped[List["Dispute"]] = relationship(
        "Dispute", back_populates="case", lazy="selectin"
    )
    notices: Mapped[List["ProviderNotice"]] = relationship(
        "ProviderNotice", back_populates="case", lazy="selectin"
    )
    recoupment_actions: Mapped[List["RecoupmentAction"]] = relationship(
        "RecoupmentAction", back_populates="case", lazy="selectin"
    )
    reconciliations: Mapped[List["Reconciliation"]] = relationship(
        "Reconciliation", back_populates="case", lazy="selectin"
    )


class CaseFinding(Base):
    __tablename__ = "case_findings"
    __table_args__ = (PrimaryKeyConstraint("case_id", "finding_id"),)

    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("opa_cases.case_id"))
    finding_id: Mapped[str] = mapped_column(String(36), ForeignKey("findings.finding_id"))

    case: Mapped["OpaCase"] = relationship(
        "OpaCase", back_populates="case_findings", lazy="selectin"
    )
    finding: Mapped["Finding"] = relationship("Finding", lazy="selectin")


class LikelihoodScore(Base):
    __tablename__ = "likelihood_scores"

    score_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("opa_cases.case_id"), unique=True
    )
    provider_risk_score: Mapped[float] = mapped_column(Float)
    cpt_risk_score: Mapped[float] = mapped_column(Float)
    dx_cpt_mismatch_score: Mapped[float] = mapped_column(Float)
    claim_complexity_score: Mapped[float] = mapped_column(Float)
    billing_variance_score: Mapped[float] = mapped_column(Float)
    composite_likelihood: Mapped[float] = mapped_column(Float)
    urgency_factor: Mapped[float] = mapped_column(Float)
    urgency_override_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    priority_score: Mapped[float] = mapped_column(Float)
    score_json: Mapped[str] = mapped_column(Text)           # JSON
    scored_at: Mapped[str] = mapped_column(String(30))

    case: Mapped["OpaCase"] = relationship(
        "OpaCase", back_populates="likelihood_score", lazy="selectin"
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    audit_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("opa_cases.case_id"), nullable=True
    )
    actor_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("opa_users.user_id"))
    action: Mapped[str] = mapped_column(String(100))
    from_state: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    to_state: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meta_json: Mapped[str] = mapped_column(Text)            # JSON — never null, use "{}". Renamed from 'metadata' (SQLAlchemy reserved name).
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    # no updated_at — audit rows are immutable

    case: Mapped[Optional["OpaCase"]] = relationship(
        "OpaCase", back_populates="audit_logs", lazy="selectin"
    )
    actor: Mapped["OpaUser"] = relationship(
        "OpaUser", foreign_keys=[actor_user_id], lazy="selectin"
    )


class Dispute(Base):
    __tablename__ = "disputes"

    dispute_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("opa_cases.case_id"))
    received_date: Mapped[str] = mapped_column(String(10))
    submitted_by_name: Mapped[str] = mapped_column(String(255))
    channel: Mapped[str] = mapped_column(String(50))
    dispute_reason_code: Mapped[str] = mapped_column(String(20))
    dispute_reason_text: Mapped[str] = mapped_column(Text)
    supporting_evidence_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(30))
    resolution_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("opa_users.user_id"), nullable=True
    )
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)

    case: Mapped["OpaCase"] = relationship("OpaCase", back_populates="disputes", lazy="selectin")
    resolved_by: Mapped[Optional["OpaUser"]] = relationship(
        "OpaUser", foreign_keys=[resolved_by_user_id], lazy="selectin"
    )


class LetterTemplate(Base):
    """template_id is a human-readable string key (e.g. 'INIT-NOTICE-MA'), not a UUID."""
    __tablename__ = "letter_templates"

    template_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    lob: Mapped[str] = mapped_column(String(50))
    template_name: Mapped[str] = mapped_column(String(255))
    regulatory_reference: Mapped[str] = mapped_column(Text)
    template_content: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("opa_users.user_id"))
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)

    created_by: Mapped["OpaUser"] = relationship(
        "OpaUser", foreign_keys=[created_by_user_id], lazy="selectin"
    )


class ProviderNotice(Base):
    __tablename__ = "provider_notices"

    notice_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("opa_cases.case_id"))
    template_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("letter_templates.template_id")
    )
    lob: Mapped[str] = mapped_column(String(50))
    generated_at: Mapped[str] = mapped_column(String(30))
    letter_content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30))
    approved_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("opa_users.user_id"), nullable=True
    )
    approved_at: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    sent_at: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)

    case: Mapped["OpaCase"] = relationship(
        "OpaCase", back_populates="notices", lazy="selectin"
    )
    template: Mapped["LetterTemplate"] = relationship("LetterTemplate", lazy="selectin")
    approved_by: Mapped[Optional["OpaUser"]] = relationship(
        "OpaUser", foreign_keys=[approved_by_user_id], lazy="selectin"
    )


class RecoupmentAction(Base):
    __tablename__ = "recoupment_actions"

    recoupment_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("opa_cases.case_id"))
    method: Mapped[str] = mapped_column(String(50))
    requested_amount: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(30))
    submitted_at: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    confirmed_at: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    recovery_835_transaction_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("transactions_835.transaction_id"), nullable=True
    )
    staging_output_json: Mapped[str] = mapped_column(Text)  # JSON
    staging_status: Mapped[str] = mapped_column(String(30), default="pending")
    staging_exported_at: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)

    case: Mapped["OpaCase"] = relationship(
        "OpaCase", back_populates="recoupment_actions", lazy="selectin"
    )
    recovery_835: Mapped[Optional["Transaction835"]] = relationship(
        "Transaction835", foreign_keys=[recovery_835_transaction_id], lazy="selectin"
    )


class Reconciliation(Base):
    __tablename__ = "reconciliations"

    reconciliation_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("opa_cases.case_id"))
    expected_amount: Mapped[float] = mapped_column(Float)
    actual_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    match_type: Mapped[str] = mapped_column(String(30), default="pending")
    recovery_835_transaction_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("transactions_835.transaction_id"), nullable=True
    )
    recovery_835_payment_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("claim_payments_835.payment_id"), nullable=True
    )
    plb_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    treasury_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    exception_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reconciled_at: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)

    case: Mapped["OpaCase"] = relationship(
        "OpaCase", back_populates="reconciliations", lazy="selectin"
    )
    recovery_835: Mapped[Optional["Transaction835"]] = relationship(
        "Transaction835", foreign_keys=[recovery_835_transaction_id], lazy="selectin"
    )
    recovery_payment: Mapped[Optional["ClaimPayment835"]] = relationship(
        "ClaimPayment835", foreign_keys=[recovery_835_payment_id], lazy="selectin"
    )
