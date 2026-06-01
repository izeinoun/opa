from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from uuid import uuid4

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, PrimaryKeyConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


def _uuid() -> str:
    return str(uuid4())


def _now() -> str:
    return datetime.utcnow().isoformat()


class App(Base):
    """A registered front-end application that may be served by the unified
    backend (payguard, claimguard, fwa, cob, ...). Used by the RBAC layer to
    decide whether a user has access to a given app via their role(s)."""
    __tablename__ = "apps"

    app_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    app_name: Mapped[str] = mapped_column(String(50), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)


class Role(Base):
    """Global role identifier — same role can map to multiple apps via
    role_apps. Granular permissions within an app are conveyed by the role
    name (analyst < supervisor < admin) and enforced at the service layer."""
    __tablename__ = "roles"

    role_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    role_name: Mapped[str] = mapped_column(String(50), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)


class RoleApp(Base):
    """Junction: a role grants access to one or more apps."""
    __tablename__ = "role_apps"
    __table_args__ = (PrimaryKeyConstraint("role_id", "app_id"),)

    role_id: Mapped[str] = mapped_column(String(36), ForeignKey("roles.role_id"))
    app_id: Mapped[str] = mapped_column(String(36), ForeignKey("apps.app_id"))


class UserRole(Base):
    """Junction: a user is assigned one or more roles. Tracks grantor +
    timestamp so role changes have an audit trail without separate logging."""
    __tablename__ = "user_roles"
    __table_args__ = (PrimaryKeyConstraint("user_id", "role_id"),)

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("opa_users.user_id"))
    role_id: Mapped[str] = mapped_column(String(36), ForeignKey("roles.role_id"))
    granted_at: Mapped[str] = mapped_column(String(30), default=_now)
    granted_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("opa_users.user_id"), nullable=True
    )


class OpaUser(Base):
    __tablename__ = "opa_users"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    full_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255))
    # Legacy single-role column — deprecated by user_roles. Populated by the
    # backfill migration from the user's primary role. Kept for one release
    # to avoid breaking existing read paths; will be dropped after services
    # are updated to read from user_roles.
    role: Mapped[str] = mapped_column(String(50))
    # Optional landing-page hint (which app to show after login).
    default_app_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("apps.app_id"), nullable=True
    )
    # ClaimGuard fields: initials + color_hex for avatar UI; specialty drives
    # auto-assign-by-specialty; supervisor_id is the supervisor↔specialist hierarchy.
    initials: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    color_hex: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)
    specialty: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    supervisor_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("opa_users.user_id"), nullable=True
    )
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
    # detector_id nullable for AI-generated findings that have no edit code.
    # Convention: AI findings carry detector_id='AI-CLAUDE-V1' or NULL.
    detector_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    detector_version: Mapped[str] = mapped_column(String(20))
    fired_at: Mapped[str] = mapped_column(String(30))
    # Nullable for pre-pay and AI findings where no recoverable dollar amount
    # exists at generation time. Determined later during manual review.
    overpayment_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    severity: Mapped[str] = mapped_column(String(20))
    # Nullable for AI findings (no probabilistic confidence) and pre-pay findings.
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Short label for AI findings (ClaimGuard's `title`, max 200 chars).
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    rationale: Mapped[str] = mapped_column(Text)
    # Provider-facing condensed pair for AI findings (ClaimGuard "AI Findings"
    # tab). `issue_summary` is a one-sentence statement of the problem written
    # for the billing provider; `suggestion` is the concrete corrective action.
    # Both nullable — detector findings and pre-2026-06 AI findings leave them
    # NULL, in which case the UI falls back to `rationale`.
    issue_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggestion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence: Mapped[str] = mapped_column(Text)             # JSON
    rule_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active")
    # FWA (fraud/waste/abuse) marker. `fwa_indicator` is the cheap boolean
    # SIU filters on; `fwa_rule_code` records which FWA-XX rule fired so the
    # UI can label the badge. A finding can be a clinical/coding issue
    # WITHOUT being FWA — these fields stay false/null in that case.
    fwa_indicator: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    fwa_rule_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

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
    # Nullable for pre-pay cases where overpayment hasn't materialized yet.
    total_overpayment_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Cumulative review time across all analyst sessions on this case.
    review_time_minutes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
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
    # JSON blob holding a closure decision while case is pending_supervisor:
    # {disposition, reason, recovered_amount, submitted_by_user_id, submitted_at}
    decision_metadata: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # ── SIU fields (set when case is escalated to SIU) ───────────────────
    # When non-null, this case is in (or has been through) an SIU investigation.
    siu_investigation_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("siu_investigations.investigation_id"), nullable=True
    )
    # Per UC-SIU-04: hard hold preventing recovery + closure actions. Mirrored
    # from any active law_enforcement_referral on the linked investigation.
    law_enforcement_hold: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # Per UC-SIU-01: when true, the case JSON + findings + documents are
    # read-only outside the SIU workspace. The 'frozen evidence bundle'.
    siu_frozen: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
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
    notes: Mapped[List["CaseNote"]] = relationship(
        "CaseNote", back_populates="case", lazy="selectin",
        order_by="CaseNote.created_at",
    )


class CaseNote(Base):
    """Analyst / supervisor notes on a case. Separate from audit_logs by design:
    audit_logs are system-generated records of state changes; notes are free-text
    commentary authored by humans."""
    __tablename__ = "case_notes"

    note_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("opa_cases.case_id"), index=True)
    author_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("opa_users.user_id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(30), default=_now)

    case: Mapped["OpaCase"] = relationship("OpaCase", back_populates="notes")
    author: Mapped["OpaUser"] = relationship("OpaUser", lazy="selectin")


class Notification(Base):
    """Lightweight notification feed for analysts and supervisors.

    Kinds (kept open for forward additions):
      case_assigned        — your case was assigned to you (or to someone else if you owned it)
      approval_requested   — a supervisor needs to review a closure submission
      approval_decided     — your submission was approved or rejected
      case_reopened        — a case you were on was reopened
      note_mention         — (future) someone @mentioned you in a note
    """
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_recipient_created", "recipient_user_id", "created_at"),
        Index("ix_notifications_recipient_unread", "recipient_user_id", "is_read"),
    )

    notification_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    recipient_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("opa_users.user_id"))
    kind: Mapped[str] = mapped_column(String(40))
    case_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("opa_cases.case_id"), nullable=True
    )
    actor_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("opa_users.user_id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    link: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(30), default=_now)

    recipient: Mapped["OpaUser"] = relationship(
        "OpaUser", foreign_keys=[recipient_user_id], lazy="selectin"
    )
    actor: Mapped[Optional["OpaUser"]] = relationship(
        "OpaUser", foreign_keys=[actor_user_id], lazy="selectin"
    )


class ContactLog(Base):
    """Structured log of analyst↔provider contact attempts (Phase 4)."""
    __tablename__ = "contact_logs"

    contact_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("opa_cases.case_id"), index=True)
    logged_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("opa_users.user_id"))
    contact_date: Mapped[str] = mapped_column(String(10))      # YYYY-MM-DD
    method: Mapped[str] = mapped_column(String(30))            # phone, email, letter, in_person, portal
    direction: Mapped[str] = mapped_column(String(15))         # outbound | inbound
    participant_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(30), default=_now)

    logger: Mapped["OpaUser"] = relationship("OpaUser", lazy="selectin")


class FindingDisposition(Base):
    """Per-finding accept/reject/adjust decision driven by an analyst.

    One row per finding (finding_id is unique). Default disposition is seeded
    on detector run:
      - deterministic detectors (DET-01/02/04/06/08) → 'accepted'
      - DET-09 (AI-assisted) HIGH (conf >= 0.85)      → 'accepted'
      - DET-09 MEDIUM (0.65 <= conf < 0.85)           → 'needs_review'
      - DET-09 LOW (conf < 0.65)                      → 'rejected'

    Analysts can later change the disposition via accept/reject/adjust endpoints.
    """
    __tablename__ = "finding_dispositions"

    disposition_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    finding_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("findings.finding_id"), unique=True
    )
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("opa_cases.case_id"), index=True)
    status: Mapped[str] = mapped_column(String(20))  # accepted | rejected | needs_review | adjusted
    original_amount: Mapped[float] = mapped_column(Float)
    adjusted_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decided_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("opa_users.user_id"), nullable=True
    )
    decided_at: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    created_at: Mapped[str] = mapped_column(String(30), default=_now)

    finding: Mapped["Finding"] = relationship("Finding", lazy="selectin")
    decided_by: Mapped[Optional["OpaUser"]] = relationship(
        "OpaUser", foreign_keys=[decided_by_user_id], lazy="selectin"
    )


class PrepayFindingDecision(Base):
    """Billing-provider-facing accept/reject decision on a pre-pay AI finding.

    Distinct from FindingDisposition (which is case/amount-centric and requires
    a case_id): pre-pay AI findings surfaced in ClaimGuard's "AI Findings" tab
    are reviewed by a specialist who Accepts (the issue is valid, include its
    suggestion in the provider correction letter) or Rejects (with an optional
    comment explaining why). One row per finding; absence of a row means the
    finding is still pending review.
    """
    __tablename__ = "prepay_finding_decisions"

    decision_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    finding_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("findings.finding_id"), unique=True
    )
    claim_id: Mapped[str] = mapped_column(String(36), ForeignKey("claims.claim_id"), index=True)
    status: Mapped[str] = mapped_column(String(20))  # accepted | rejected
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decided_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("opa_users.user_id"), nullable=True
    )
    decided_at: Mapped[str] = mapped_column(String(30), default=_now)

    finding: Mapped["Finding"] = relationship("Finding", lazy="selectin")


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
    # Claim-level audits (pre-case lifecycle: PDF upload, initial AI analysis)
    # populate claim_id with case_id NULL. Once a case is created, subsequent
    # audits typically populate case_id (the relationship to claim is derivable).
    claim_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("claims.claim_id"), nullable=True
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


class DocumentTemplate(Base):
    """Generic, LLM-driven document template shared by both apps.

    Distinct from LetterTemplate (PayGuard's deterministic {{placeholder}}
    recovery-notice templates). Here the body is a Markdown template and
    `task_prompt` instructs the LLM how to fill it from caller-supplied
    content; the result is rendered to PDF. Templates are partitioned by the
    `app` discriminator ('payguard' | 'claimguard') so each application
    manages its own set in the same table.
    """
    __tablename__ = "document_templates"

    template_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    app: Mapped[str] = mapped_column(String(30), index=True)  # 'payguard' | 'claimguard'
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Default LLM instructions for this template (caller may override per call).
    task_prompt: Mapped[str] = mapped_column(Text)
    # The Markdown template body the LLM fills / expands.
    template_markdown: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("opa_users.user_id"), nullable=True
    )
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)

    created_by: Mapped[Optional["OpaUser"]] = relationship(
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


class DetectorRuleConfig(Base):
    """One row per detector rule. Editable enable/disable + score multiplier."""
    __tablename__ = "detector_rule_config"

    rule_code: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    score: Mapped[float] = mapped_column(Float, default=1.0)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)
    updated_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("opa_users.user_id"), nullable=True
    )


class PrioritizationConfig(Base):
    """Singleton row (config_id='current') holding the priority-formula knobs."""
    __tablename__ = "prioritization_config"

    config_id: Mapped[str] = mapped_column(String(20), primary_key=True, default="current")
    amount_weight: Mapped[float] = mapped_column(Float, default=0.60)
    likelihood_weight: Mapped[float] = mapped_column(Float, default=0.35)
    urgency_weight: Mapped[float] = mapped_column(Float, default=0.05)
    amount_cap: Mapped[float] = mapped_column(Float, default=5_000.0)
    urgency_window_days: Mapped[int] = mapped_column(Integer, default=30)
    high_threshold: Mapped[float] = mapped_column(Float, default=75.0)
    medium_threshold: Mapped[float] = mapped_column(Float, default=50.0)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)
    updated_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("opa_users.user_id"), nullable=True
    )


class MLTrainingConfig(Base):
    """Singleton (config_id='current'). Admin-editable knobs for the next
    training run of billing_variance_classifier (sklearn RandomForest).

    Resolution rules applied in train_billing_variance.train_model():
      - Any NULL column → use sklearn default for that hyperparameter
      - The resolved config is persisted to ml_model_versions.training_params
        when training completes, so historical lineage is immutable even if
        this row is later edited.
      - decision_threshold_mode:
          'auto_f2' → keep the F2-optimal sweep; manual_threshold ignored
          'manual'  → use manual_threshold verbatim (skip the sweep)
      - min_auc_to_promote: if NULL the new version is auto-activated;
        otherwise it stays inactive until auc_roc clears this floor.
    """
    __tablename__ = "ml_training_config"

    config_id: Mapped[str] = mapped_column(String(20), primary_key=True, default="current")
    n_estimators: Mapped[int] = mapped_column(Integer, default=200)
    max_depth: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    min_samples_split: Mapped[int] = mapped_column(Integer, default=2)
    min_samples_leaf: Mapped[int] = mapped_column(Integer, default=1)
    # 'sqrt' | 'log2' | 'none' | a float-as-string (e.g. '0.5'). NULL/'none' → all features.
    max_features: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default="sqrt")
    max_leaf_nodes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bootstrap: Mapped[bool] = mapped_column(Boolean, default=True)
    # NULL | 'balanced' | 'balanced_subsample'
    class_weight: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    criterion: Mapped[str] = mapped_column(String(20), default="gini")
    decision_threshold_mode: Mapped[str] = mapped_column(String(20), default="auto_f2")
    manual_threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    min_auc_to_promote: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)
    updated_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("opa_users.user_id"), nullable=True
    )


class Document(Base):
    """Inbound document attachments — PDFs (claim forms, medical records, supporting
    files) uploaded during claim review. ClaimGuard relies on this; PayGuard didn't
    previously have it. Attached to either a claim (early lifecycle, pre-case),
    a case once one exists, or an SIU investigation. At least one of
    (claim_id, case_id, investigation_id) should be set."""
    __tablename__ = "documents"

    document_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    claim_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("claims.claim_id"), nullable=True, index=True
    )
    case_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("opa_cases.case_id"), nullable=True, index=True
    )
    # SIU file attachments (interview transcripts, external reports). Optional
    # link to an investigation_note for fine-grained association.
    investigation_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("siu_investigations.investigation_id"), nullable=True
    )
    investigation_note_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("investigation_notes.note_id"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    file_size_kb: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String(30), default="supporting")
    # Values: 'claim_form' | 'supporting' | 'medical_record' | future kinds.
    uploaded_at: Mapped[str] = mapped_column(String(30), default=_now)
    uploaded_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("opa_users.user_id"), nullable=True
    )
    # Per-document PDF text — populated at upload time so the evidence
    # scanner can attribute findings to a specific document without re-
    # extracting. Distinct from the per-claim extracted_text corpus
    # (claims.extracted_text), which we still maintain for the AI summary
    # pipeline. NULL when not yet extracted, "" when extraction succeeded
    # but yielded no text.
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    # Values: 'pending' | 'complete' | 'failed' | NULL for never-attempted.
    extraction_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class CodeEvidenceRequirement(Base):
    """Per-code rule: which ICD-10 or DRG codes call for documentary evidence,
    and a short prompt-friendly description of what evidence looks like.
    Admin-editable; the evidence scanner reads `is_active=True` rows."""
    __tablename__ = "code_evidence_requirements"

    requirement_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code_type: Mapped[str] = mapped_column(String(10))   # 'icd10' | 'drg'
    code: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    # Free-form text fed verbatim into the scan prompt. Should describe what
    # the analyst would look for in the medical record to justify the code.
    requirement_description: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)


class EvidenceFinding(Base):
    """Output of the evidence scan for one (claim, code) pair. Upserted on
    re-scan so the latest result wins. Page + section + verbatim quote let
    the frontend deep-link into the PDF and highlight the match."""
    __tablename__ = "evidence_findings"

    finding_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    claim_id: Mapped[str] = mapped_column(String(36), ForeignKey("claims.claim_id"))
    document_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("documents.document_id"), nullable=True,
    )
    requirement_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("code_evidence_requirements.requirement_id"), nullable=True,
    )
    code_type: Mapped[str] = mapped_column(String(10))   # 'icd10' | 'drg'
    code: Mapped[str] = mapped_column(String(20))
    # 'found' | 'not_found' | 'partial'
    result: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    evidence_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    section_heading: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    # JSON list of alternates: [{document_id, page_number, section_heading,
    # evidence_text}].
    additional_sources: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    gap_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_used: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    scanned_at: Mapped[str] = mapped_column(String(30), default=_now)


class RuntimeConfig(Base):
    """Flat key/value config table for operator-tunable feature flags
    (e.g. ai_suggestions_enabled, high_dollar_threshold, auto_assign).

    Pairs with the structured config singletons (prioritization_config,
    detector_rule_config, ml_training_config) — those hold formula weights
    and ML parameters; this holds runtime toggles. Different concerns,
    both layers coexist."""
    __tablename__ = "runtime_config"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)
    updated_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("opa_users.user_id"), nullable=True
    )


class SIUInvestigation(Base):
    """A formal SIU investigation, opened on top of one or more escalated
    cases. The frozen evidence bundle lives on each case (siu_frozen flag);
    this row carries the investigation lifecycle: status, type, outcome,
    closure notes, law-enforcement hold.

    A single investigation can span multiple cases via investigation_cases
    (e.g. a pattern investigation grouping ≥5 cases for the same NPI).
    """
    __tablename__ = "siu_investigations"

    investigation_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # TIME_VOLUME_ANOMALY | SUBROGATION | EXCLUDED_PROVIDER | FRAUD_PATTERN | OTHER
    investigation_type: Mapped[str] = mapped_column(String(40))
    # OPEN | PENDING_EXTERNAL_INFO | PENDING_LAW_ENFORCEMENT | REFERRAL_SUBMITTED | CLOSED
    status: Mapped[str] = mapped_column(String(40), default="OPEN")
    # Set on closure. FRAUD_CONFIRMED | NO_FRAUD_FOUND | INSUFFICIENT_EVIDENCE |
    # SUBROGATION_RECOVERY_INITIATED | CASE_CLOSED_NO_ACTION
    outcome: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    closure_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Escalation context (where this investigation came from)
    escalation_source: Mapped[str] = mapped_column(String(40))  # analyst_referral|dce_13|dce_15|pattern_threshold
    escalation_reason: Mapped[str] = mapped_column(Text)
    escalated_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("opa_users.user_id"), nullable=True
    )
    escalated_at: Mapped[str] = mapped_column(String(30), default=_now)

    investigator_assigned_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("opa_users.user_id"), nullable=True
    )
    opened_at: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    closed_at: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    closed_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("opa_users.user_id"), nullable=True
    )

    # Hard-hold flag mirrored from active law_enforcement_referrals. Denormalized
    # so the recovery-action guard can be a simple flag check, not a join.
    law_enforcement_hold: Mapped[bool] = mapped_column(Boolean, default=False)

    # Mode A (internal) | Mode B (outsourced) — read from the runtime_config flag
    # at escalation time and pinned here so per-investigation mode is auditable.
    siu_mode: Mapped[str] = mapped_column(String(10), default="A")

    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)


class InvestigationCase(Base):
    """M:N — an investigation can group multiple cases (pattern investigations
    for the same NPI). Each case retains its own case_id but shares the
    investigation_id."""
    __tablename__ = "investigation_cases"
    __table_args__ = (PrimaryKeyConstraint("investigation_id", "case_id"),)

    investigation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("siu_investigations.investigation_id")
    )
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("opa_cases.case_id")
    )


class InvestigationNote(Base):
    """Investigator-authored notes on an investigation. Immutable after save
    (no updated_at column — by design, per spec). Notes can be marked
    CONFIDENTIAL: visible only to SIU + Supervisor roles (enforced at the
    service layer)."""
    __tablename__ = "investigation_notes"

    note_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    investigation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("siu_investigations.investigation_id")
    )
    note_date: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD
    # Interview | Document Review | External Source | Internal Analysis | Law Enforcement Coordination
    note_type: Mapped[str] = mapped_column(String(40))
    body: Mapped[str] = mapped_column(Text)
    is_confidential: Mapped[bool] = mapped_column(Boolean, default=False)
    author_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("opa_users.user_id")
    )
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    # No updated_at — notes are immutable per UC-SIU-03 spec.


class LawEnforcementReferral(Base):
    """Formal referral to a law enforcement agency. Immutable after submission.
    Setting siu_investigations.law_enforcement_hold=true is the side effect
    of creating one of these and is what blocks closure + recovery actions
    until the referral is resolved."""
    __tablename__ = "law_enforcement_referrals"

    referral_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    investigation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("siu_investigations.investigation_id")
    )
    referral_date: Mapped[str] = mapped_column(String(10))
    # FBI | OIG | State AG | Local Law Enforcement | Other
    agency_name: Mapped[str] = mapped_column(String(100))
    # Criminal Fraud | Civil Recovery | Both
    referral_type: Mapped[str] = mapped_column(String(30))
    referral_summary: Mapped[str] = mapped_column(Text)  # min 100 chars enforced in service
    referral_contact_name: Mapped[str] = mapped_column(String(255))
    submitted_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("opa_users.user_id")
    )
    submitted_at: Mapped[str] = mapped_column(String(30), default=_now)
    response_received_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    # PURSUED | DECLINED | nullable while pending
    referral_outcome: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    outcome_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    closed_at: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)


class Connector(Base):
    """A configured external integration (HTTP API, SFTP endpoint, or in-
    process function). Used by ingest pipelines, outbound notifications,
    and (in future) tool-calling agents.

    Patterns adapted from clearlink/server/agents/connectors/executor.js
    with two changes:
      • Adds a 'direction' field (inbound/outbound) so we can model
        webhook-style outbound notifications cleanly alongside data pulls.
      • Adds 'sftp' as a kind for batch-file integrations.

    The kind-specific configuration (URL, SFTP host/port, etc.) lives in
    config_json so the table stays clean and new connector kinds can be
    added without schema churn. Secrets (API keys, passwords) live in
    secret_json — same intent, but encrypted at rest in production
    (currently plain JSON in dev)."""
    __tablename__ = "connectors"

    connector_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    # http | sftp | internal | webhook (the last reserved for outbound push)
    kind: Mapped[str] = mapped_column(String(20))
    direction: Mapped[str] = mapped_column(String(10), default="outbound")  # inbound | outbound
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Type-specific configuration (URL, host, port, headers, sql_template, etc.).
    # JSON. The shape is validated by the service layer per kind.
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    # Sensitive material kept separate so it can be returned masked in
    # list/get responses. JSON. Encrypted at rest in production.
    secret_json: Mapped[str] = mapped_column(Text, default="{}")
    # JSON Schema (subset) validating the input payload passed at run time.
    input_schema_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Dev affordance: if mock_enabled=True, runs return mock_response_json
    # instead of executing. Lets the IAM admin UI stub a connector before
    # the real endpoint is wired.
    mock_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mock_response_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)
    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("opa_users.user_id"), nullable=True
    )


class ConnectorRun(Base):
    """Execution log for connector invocations. Append-only. Powers an
    audit trail per connector (last-run status, error rate, latency
    histograms) and a debug view in the admin UI."""
    __tablename__ = "connector_runs"

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    connector_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("connectors.connector_id")
    )
    triggered_at: Mapped[str] = mapped_column(String(30), default=_now)
    triggered_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("opa_users.user_id"), nullable=True
    )
    # Optional caller-supplied tag to trace a run back to the workflow that
    # invoked it (e.g. an SIU export delivery, a case status change webhook).
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ok: Mapped[bool] = mapped_column(Boolean)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    input_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Detail fields useful for HTTP/SFTP runs: status code, response size, etc.
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class SIUExportPackage(Base):
    """JSON export package generated for outsourced SIU firms (Mode B) — or
    on-demand in either mode. Versioned per investigation so re-exports
    after new notes generate fresh packages with integrity hashes."""
    __tablename__ = "siu_export_packages"

    package_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    investigation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("siu_investigations.investigation_id")
    )
    version: Mapped[int] = mapped_column(Integer)  # monotonic per investigation
    package_json: Mapped[str] = mapped_column(Text)  # the full export payload
    integrity_hash: Mapped[str] = mapped_column(String(64))  # sha256 of package_json
    generated_at: Mapped[str] = mapped_column(String(30), default=_now)
    generated_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("opa_users.user_id"), nullable=True
    )
    # pending | delivered | failed
    delivery_status: Mapped[str] = mapped_column(String(20), default="pending")
    delivery_destination: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    delivery_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


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
