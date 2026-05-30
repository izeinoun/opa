import json
from typing import Optional, List
from datetime import datetime, timedelta
from datetime import date as date_type
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..dao.case_dao import CaseDAO
from ..dao.audit_log_dao import AuditLogDAO
from ..models.workflow import OpaCase, AuditLog, CaseFinding, Dispute, ProviderNotice
from ..models.claims import Claim, ClaimLine
from ..models.reference import Provider, Member
from ..schemas.case_schemas import (
    CaseTransition,
    CaseDetail,
    CaseSummary,
    CaseListResponse,
    WorklistFilters,
    LikelihoodBreakdown,
    ClaimSummary,
    ClaimSummary as ClaimSummaryModel,
    ClaimLineRead,
    ClaimFindingRead,
    ERATransactionRead,
    ERAPaymentLineRead,
    AuditLogRead,
    DisputeRead,
    RecoveryNoticeRead,
    UserRead,
    MemberRead,
    ProviderRead,
    PriorityBreakdown,
    DetectorResultRead,
    CaseNoteRead,
    PendingDecision,
)

def _fmt_money(amount: float) -> str:
    try:
        return f"${float(amount):,.2f}"
    except Exception:
        return "$?"


DETECTOR_REGISTRY = [
    {"id": "DET-01", "name": "Duplicate Payment"},
    {"id": "DET-02", "name": "Retro Eligibility Check"},
    {"id": "DET-04", "name": "Fee Schedule Mispricing"},
    {"id": "DET-06", "name": "NCCI / MUE Violation"},
    {"id": "DET-08", "name": "Excluded Provider"},
    {"id": "DET-09", "name": "Coding Errors"},
]

_DETECTOR_NAME_BY_ID = {d["id"]: d["name"] for d in DETECTOR_REGISTRY}

def _compute_posterior(prior: float, fired_findings: list) -> float:
    """
    Bayesian update of likelihood given what detectors found on this claim.
    - DET-08 fires → 0.98 (hard compliance fact)
    - No detectors → prior × 0.50
    - N detectors  → sequential update: p = p + (1-p) × confidence
    """
    if any(_DET_CODE_MAP.get(f.detector_id) == "DET-08" for f in fired_findings):
        return 0.98
    if not fired_findings:
        return round(prior * 0.50, 4)
    posterior = prior
    for f in fired_findings:
        posterior = posterior + (1.0 - posterior) * f.confidence
    return round(min(posterior, 1.0), 4)


_DET_CODE_MAP: dict = {
    "DET-01": "DET-01", "DUPLICATE_CLAIM_V1": "DET-01",
    "DET-02": "DET-02", "RETRO_TERM_V1": "DET-02",
    "DET-04": "DET-04", "BILLING_VARIANCE_V1": "DET-04",
    "DET-06": "DET-06", "EXCESS_UNITS_V1": "DET-06", "MULTI_LINE_COMPLEXITY_V1": "DET-06",
    "DET-08": "DET-08", "POST_DEATH_V1": "DET-08",
    "DET-09": "DET-09", "DX_CPT_MISMATCH_V1": "DET-09",
    "UPCODING_V1": "DET-09", "GENERAL_REVIEW_V1": "DET-09",
}


def _serialize_user(user) -> UserRead:
    return UserRead(
        id=user.user_id,
        username=user.username,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
    )


def _provider_risk_tier(billing_variance: float) -> int:
    if billing_variance >= 0.8:
        return 5
    elif billing_variance >= 0.6:
        return 4
    elif billing_variance >= 0.4:
        return 3
    elif billing_variance >= 0.2:
        return 2
    return 1


def _serialize_provider(p) -> ProviderRead:
    return ProviderRead(
        id=p.provider_id,
        npi=p.npi,
        name=p.name,
        specialty=p.specialty,
        risk_tier=_provider_risk_tier(p.billing_variance_score),
        billing_variance_score=p.billing_variance_score,
        is_excluded=p.is_excluded,
    )


def _serialize_member(m) -> MemberRead:
    return MemberRead(
        id=m.member_id,
        member_id=m.member_number,
        name=f"{m.first_name} {m.last_name}",
        dob=m.date_of_birth,
        lob=m.lob,
    )


def _serialize_line(
    line: ClaimLine,
    service_date: str,
    at_risk_breakdown: Optional[dict] = None,
) -> ClaimLineRead:
    try:
        icd_codes = json.loads(line.icd_codes)
    except Exception:
        icd_codes = [line.icd_codes] if line.icd_codes else []
    attrib = (at_risk_breakdown or {}).get(line.claim_line_id)
    return ClaimLineRead(
        id=line.claim_line_id,
        line_number=line.line_number,
        cpt_code=line.cpt_code,
        icd_codes=icd_codes if isinstance(icd_codes, list) else [str(icd_codes)],
        units=line.units_billed,
        billed_amount=line.billed_amount,
        allowed_amount=line.allowed_amount,
        paid_amount=line.paid_amount,
        modifier=line.modifier_1,
        service_date=service_date,
        at_risk_amount=round(attrib["amount"], 2) if attrib else None,
        at_risk_detector_id=attrib["detector_id"] if attrib else None,
    )


def _serialize_finding(cf, attribution: Optional[dict] = None,
                       dispositions_by_fid: Optional[dict] = None) -> ClaimFindingRead:
    f = cf.finding if hasattr(cf, "finding") else cf
    attr = (attribution or {}).get(f.finding_id) or {}
    d = (dispositions_by_fid or {}).get(f.finding_id)
    return ClaimFindingRead(
        id=f.finding_id,
        detector_code=f.detector_id,
        finding_type=f.severity,
        description=f.rationale,
        overpayment_amount=f.overpayment_amount,
        confidence_score=f.confidence,
        evidence_json=f.evidence,
        created_at=f.fired_at,
        attributed_amount=attr.get("attributed_amount", 0.0),
        suppressed_amount=attr.get("suppressed_amount", 0.0),
        superseded_by=attr.get("superseded_by", []),
        disposition_status=d.status if d else None,
        disposition_adjusted_amount=d.adjusted_amount if d else None,
        disposition_reason=d.reason if d else None,
    )


def _serialize_finding_raw(f, attribution: Optional[dict] = None,
                           dispositions_by_fid: Optional[dict] = None) -> ClaimFindingRead:
    attr = (attribution or {}).get(f.finding_id) or {}
    d = (dispositions_by_fid or {}).get(f.finding_id)
    return ClaimFindingRead(
        id=f.finding_id,
        detector_code=f.detector_id,
        finding_type=f.severity,
        description=f.rationale,
        overpayment_amount=f.overpayment_amount,
        confidence_score=f.confidence,
        evidence_json=f.evidence or "{}",
        created_at=(f.fired_at or "")[:10],
        attributed_amount=attr.get("attributed_amount", 0.0),
        suppressed_amount=attr.get("suppressed_amount", 0.0),
        superseded_by=attr.get("superseded_by", []),
        disposition_status=d.status if d else None,
        disposition_adjusted_amount=d.adjusted_amount if d else None,
        disposition_reason=d.reason if d else None,
    )


def _serialize_era(txn) -> ERATransactionRead:
    payments = []
    for p in (txn.payments or []):
        payments.append(ERAPaymentLineRead(
            id=p.payment_id,
            claim_icn=p.claim_icn,
            cpt_code=p.cpt_code,
            paid_amount=p.paid_amount,
            adjustment_amount=p.adjustment_amount,
            adjustment_reason_code=p.adjustment_reason_code,
            check_number=p.check_number,
            payment_date=p.payment_date,
        ))
    return ERATransactionRead(
        id=txn.transaction_id,
        era_number=txn.transaction_number,
        transaction_type=txn.transaction_type,
        payer_name=txn.payer_name,
        payment_date=txn.transaction_date,
        payment_amount=txn.total_amount,
        claim_count=txn.claim_count,
        payments=payments,
        raw_835=txn.raw_835_json or None,
    )


def _serialize_audit(log: AuditLog) -> AuditLogRead:
    user = _serialize_user(log.actor) if log.actor else None
    return AuditLogRead(
        id=log.audit_id,
        action=log.action,
        from_status=log.from_state,
        to_status=log.to_state,
        notes=log.reason,
        created_at=log.created_at,
        user=user,
    )


def _serialize_dispute(d: Dispute) -> DisputeRead:
    from datetime import date as dt
    try:
        rd = dt.fromisoformat(d.received_date)
        response_due = (rd + timedelta(days=30)).isoformat()
    except Exception:
        response_due = d.received_date

    outcome = None
    if d.status == "upheld":
        outcome = "upheld"
    elif d.status == "overturned":
        outcome = "overturned"

    return DisputeRead(
        id=d.dispute_id,
        dispute_date=d.received_date,
        reason=d.dispute_reason_text,
        response_due=response_due,
        response_date=d.resolution_date,
        outcome=outcome,
        notes=d.resolution_notes,
    )


def _serialize_notice(n: ProviderNotice, *, include_content: bool = False) -> RecoveryNoticeRead:
    try:
        payload = json.loads(n.letter_content or "{}")
    except Exception:
        payload = {}
    return RecoveryNoticeRead(
        id=n.notice_id,
        sent_date=(n.sent_at or n.generated_at or "")[:10],
        amount_demanded=float(payload.get("amount_demanded", 0.0)),
        response_due=str(payload.get("response_due", "")),
        delivery_method=str(payload.get("delivery_method", "mail")),
        status=n.status,
        notice_id=n.notice_id,
        template_id=n.template_id,
        lob=n.lob,
        sent_at=n.sent_at,
        generated_at=n.generated_at,
        letter_content=payload.get("html") if include_content else None,
    )


def _serialize_claim(case: OpaCase) -> Optional[ClaimSummaryModel]:
    claim = case.claim
    if not claim:
        return None

    rendering_provider = None
    if claim.provider_org and claim.provider_org.providers:
        for p in claim.provider_org.providers:
            if p.npi == claim.rendering_provider_npi:
                rendering_provider = _serialize_provider(p)
                break
        if rendering_provider is None and claim.provider_org.providers:
            rendering_provider = _serialize_provider(claim.provider_org.providers[0])

    member = _serialize_member(claim.member) if claim.member else None

    raw_findings = []
    case_finding_records = []
    for cf in (case.case_findings or []):
        if cf.finding:
            case_finding_records.append(cf)
            raw_findings.append(cf.finding)

    # Build a dispositions map from the already-loaded attribute. We populate
    # this lazily — when _serialize_case_detail is called synchronously we use
    # the dispositions cached on `case._dispositions_by_finding_id` (set by the
    # async caller below).
    dispositions_by_fid = getattr(case, "_dispositions_by_finding_id", {}) or {}

    from .amount_at_risk import attribute_findings
    from .disposition_service import compute_at_risk_with_dispositions
    _, line_breakdown = compute_at_risk_with_dispositions(
        list(claim.lines or []), raw_findings, dispositions_by_fid,
    )
    attribution = attribute_findings(list(claim.lines or []), raw_findings, line_breakdown)
    findings = [_serialize_finding(cf, attribution, dispositions_by_fid) for cf in case_finding_records]
    lines = [_serialize_line(l, claim.service_from_date, line_breakdown) for l in (claim.lines or [])]

    era_transactions = []
    if claim.era_transaction:
        era_transactions = [_serialize_era(claim.era_transaction)]

    total_allowed = sum(l.allowed_amount for l in (claim.lines or []))
    if total_allowed == 0:
        total_allowed = claim.total_paid

    return ClaimSummaryModel(
        id=claim.claim_id,
        claim_number=claim.icn,
        lob=claim.lob,
        total_billed=claim.total_billed,
        total_allowed=total_allowed,
        total_paid=claim.total_paid,
        status=claim.claim_status,
        service_date_start=claim.service_from_date,
        member=member,
        rendering_provider=rendering_provider,
        provider_org_id=claim.provider_org.provider_org_id if claim.provider_org else None,
        provider_org_name=claim.provider_org.name if claim.provider_org else None,
        lines=lines,
        findings=findings,
        era_transactions=era_transactions,
    )


def _derive_escalation(case: OpaCase) -> Optional["EscalationSummary"]:
    """Walk audit log to determine if the case currently has an unresolved
    escalation. The most recent ESCALATED_TO_SUPERVISOR without a later
    ESCALATION_RESOLVED is considered active."""
    from ..schemas.case_schemas import EscalationSummary
    if not (case.audit_logs):
        return EscalationSummary(is_active=False)

    # Sort newest first
    sorted_logs = sorted(case.audit_logs, key=lambda l: l.created_at, reverse=True)
    latest_escalation = None
    for log in sorted_logs:
        if log.action == "ESCALATION_RESOLVED":
            return EscalationSummary(is_active=False)
        if log.action == "ESCALATED_TO_SUPERVISOR":
            latest_escalation = log
            break

    if latest_escalation is None:
        return EscalationSummary(is_active=False)

    actor_name = latest_escalation.actor.full_name if latest_escalation.actor else None
    actor_id = latest_escalation.actor.user_id if latest_escalation.actor else None
    return EscalationSummary(
        is_active=True,
        reason=latest_escalation.reason,
        escalated_at=latest_escalation.created_at,
        escalated_by_full_name=actor_name,
        escalated_by_user_id=actor_id,
    )


def _serialize_case_summary(case: OpaCase) -> CaseSummary:
    likelihood = 0.0
    if case.likelihood_score:
        likelihood = case.likelihood_score.composite_likelihood

    amount_billed = case.claim.total_billed if case.claim else 0.0

    claim_summary = None
    if case.claim:
        rendering_provider = None
        if case.claim.provider_org and case.claim.provider_org.providers:
            for p in case.claim.provider_org.providers:
                if p.npi == case.claim.rendering_provider_npi:
                    rendering_provider = _serialize_provider(p)
                    break
            if rendering_provider is None:
                rendering_provider = _serialize_provider(case.claim.provider_org.providers[0])
        claim_summary = ClaimSummary(
            id=case.claim.claim_id,
            claim_number=case.claim.icn,
            lob=case.claim.lob,
            total_billed=case.claim.total_billed,
            total_allowed=case.claim.total_paid,
            total_paid=case.claim.total_paid,
            status=case.claim.claim_status,
            service_date_start=case.claim.service_from_date,
            member=_serialize_member(case.claim.member) if case.claim.member else None,
            rendering_provider=rendering_provider,
        )

    return CaseSummary(
        id=case.case_sequence,
        case_id=case.case_id,
        case_number=case.case_number,
        status=case.status,
        priority=case.priority,
        priority_score=case.priority_score,
        likelihood_score=likelihood,
        amount_billed=amount_billed,
        amount_at_risk=case.total_overpayment_amount,
        deadline=case.deadline_date,
        opened_at=case.identified_date,
        is_active=case.is_active,
        lob=case.lob,
        assignee=_serialize_user(case.assigned_analyst) if case.assigned_analyst else None,
        claim=claim_summary,
        requires_supervisor_approval=case.requires_supervisor_approval,
        primary_detector_id=case.primary_detector_id or None,
        primary_detector_name=_DETECTOR_NAME_BY_ID.get(case.primary_detector_id or "") or None,
        escalation=_derive_escalation(case),
        siu_investigation_id=case.siu_investigation_id,
        siu_frozen=case.siu_frozen,
        law_enforcement_hold=case.law_enforcement_hold,
    )


def _serialize_case_detail(case: OpaCase, max_amount: float = 10_000.0) -> CaseDetail:
    summary = _serialize_case_summary(case)

    breakdown = None
    if case.likelihood_score:
        ls = case.likelihood_score
        breakdown = LikelihoodBreakdown(
            cpt_risk_score=ls.cpt_risk_score,
            provider_risk_tier=_provider_risk_tier(ls.billing_variance_score),
            dx_cpt_mismatch_score=ls.dx_cpt_mismatch_score,
            claim_complexity_score=ls.claim_complexity_score,
            billing_variance_score=ls.billing_variance_score,
            likelihood_score=ls.composite_likelihood,
        )

    raw_findings = [cf.finding for cf in (case.case_findings or []) if cf.finding]
    fired_findings = [f for f in raw_findings if f.confidence is not None]
    prior = case.likelihood_score.composite_likelihood if case.likelihood_score else 0.30
    posterior = _compute_posterior(prior, fired_findings)

    priority_breakdown = None
    if case.likelihood_score:
        ls = case.likelihood_score
        today = date_type.today()
        days_overdue = None
        days_until = None
        urgency = 0.5
        try:
            deadline = date_type.fromisoformat(case.deadline_date)
            delta = (deadline - today).days
            if delta < 0:
                days_overdue = -delta
                days_until = 0
                urgency = 1.0
            else:
                days_until = delta
                urgency = max(0.0, min(1.0, 1.0 - delta / 30.0))
        except Exception:
            pass
        amount_norm = min(case.total_overpayment_amount / max(max_amount, 1.0), 1.0)
        amount_pts = round(amount_norm * 60, 2)
        likelihood_pts = round(posterior * 35, 2)
        urgency_pts = round(urgency * 5, 2)
        priority_breakdown = PriorityBreakdown(
            total_score=case.priority_score,
            band=case.priority,
            amount_pts=amount_pts,
            likelihood_pts=likelihood_pts,
            urgency_pts=urgency_pts,
            amount_at_risk=case.total_overpayment_amount,
            likelihood_score=posterior,
            prior_score=ls.composite_likelihood,
            urgency_factor=urgency,
            urgency_override_applied=False,
            days_overdue=days_overdue,
            days_until=days_until,
        )

    fired_by_det: dict = {}
    for f in raw_findings:
        canonical = _DET_CODE_MAP.get(f.detector_id)
        if canonical and canonical not in fired_by_det:
            fired_by_det[canonical] = f

    from .amount_at_risk import attribute_findings
    from .disposition_service import compute_at_risk_with_dispositions
    dispositions_by_fid_dr = getattr(case, "_dispositions_by_finding_id", {}) or {}
    if case.claim:
        _, line_breakdown = compute_at_risk_with_dispositions(
            list(case.claim.lines or []), raw_findings, dispositions_by_fid_dr,
        )
        attribution = attribute_findings(list(case.claim.lines or []), raw_findings, line_breakdown)
    else:
        line_breakdown = {}
        attribution = {}

    detector_results = []
    for det in DETECTOR_REGISTRY:
        finding = fired_by_det.get(det["id"])
        detector_results.append(DetectorResultRead(
            detector_id=det["id"],
            detector_name=det["name"],
            fired=finding is not None,
            finding=_serialize_finding_raw(finding, attribution, dispositions_by_fid_dr) if finding else None,
        ))
    detector_results.sort(key=lambda x: (not x.fired, x.detector_id))

    full_claim = _serialize_claim(case)
    audit_logs = [_serialize_audit(log) for log in (case.audit_logs or [])]
    disputes = [_serialize_dispute(d) for d in (case.disputes or [])]
    notices = [_serialize_notice(n) for n in (case.notices or [])]

    summary_dict = summary.model_dump(exclude={"claim"})
    return CaseDetail(
        **summary_dict,
        claim=full_claim,
        supervisor=None,
        breakdown=breakdown,
        audit_logs=audit_logs,
        disputes=disputes,
        notices=notices,
        notes=[],
        case_notes=[
            CaseNoteRead(
                id=n.note_id,
                body=n.body,
                created_at=n.created_at,
                author=UserRead(
                    id=n.author.user_id,
                    username=n.author.username,
                    full_name=n.author.full_name,
                    email=n.author.email or "",
                    role=n.author.role,
                    is_active=n.author.is_active,
                ) if n.author else None,
            )
            for n in (case.notes or [])
        ],
        group_id=case.case_group_id,
        priority_breakdown=priority_breakdown,
        detector_results=detector_results,
        posterior_score=posterior,
        pending_decision=_parse_pending_decision(case.decision_metadata),
    )


def _parse_pending_decision(raw):
    if not raw:
        return None
    import json
    try:
        data = json.loads(raw)
    except Exception:
        return None
    return PendingDecision(**data)


class CaseService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.case_dao = CaseDAO(session)
        self.audit_dao = AuditLogDAO(session)

    async def get_worklist(
        self,
        filters: WorklistFilters,
        skip: int = 0,
        limit: int = 25,
        page: int = 1,
    ) -> CaseListResponse:
        items, total = await self.case_dao.get_worklist(filters, skip, limit)
        summaries = [_serialize_case_summary(c) for c in items]
        return CaseListResponse(items=summaries, total=total, page=page, page_size=limit)

    async def get_case_detail(self, case_sequence: int) -> CaseDetail:
        case = await self.case_dao.get_with_full_details(case_sequence)
        if case is None:
            raise ValueError(f"Case sequence {case_sequence} not found")
        await self._attach_dispositions(case)
        return _serialize_case_detail(case, max_amount=5_000.0)

    async def _attach_dispositions(self, case) -> None:
        """Load dispositions for all findings on this case and stash them on
        the case object so the synchronous serializer can reach them."""
        from .disposition_service import load_dispositions_by_finding
        finding_ids = [cf.finding.finding_id for cf in (case.case_findings or []) if cf.finding]
        case._dispositions_by_finding_id = await load_dispositions_by_finding(self.session, finding_ids)

    async def transition(
        self,
        case_sequence: int,
        transition: CaseTransition,
        acting_user_id: Optional[str],
    ) -> CaseDetail:
        from datetime import datetime
        import json

        case = await self.case_dao.get_by_sequence(case_sequence)
        if case is None:
            raise ValueError(f"Case {case_sequence} not found")

        from_status = case.status
        to_status = transition.to_status

        CLOSURES_REQUIRING_REASON = {"closed_overturned", "closed_no_overpayment"}
        CLOSURES = {
            "closed_recovered", "closed_written_off",
            "closed_overturned", "closed_no_overpayment",
        }
        # Forward states that require all needs_review findings be resolved first
        FORWARD_FROM_IN_REVIEW = CLOSURES | {"notice_sent", "ready_for_notice"}
        SUPERVISOR_THRESHOLD = 2000.0

        # Require reason on overturn / no-overpayment closures (compliance)
        if to_status in CLOSURES_REQUIRING_REASON and not (transition.reason and transition.reason.strip()):
            raise ValueError(f"A reason is required for {to_status}")

        # Phase 2 gate: cannot leave in_review for a forward state while any
        # finding is in needs_review status
        if from_status == "in_review" and to_status in FORWARD_FROM_IN_REVIEW:
            from .disposition_service import case_has_blocking_findings
            if await case_has_blocking_findings(self.session, case.case_id):
                raise ValueError(
                    "One or more findings need analyst review (accept or reject) "
                    "before this case can move forward."
                )

        # $2K supervisor gate: any closure on a case with at-risk > $2K is held
        # pending_supervisor with the requested disposition stashed in
        # decision_metadata.
        is_closure = to_status in CLOSURES
        amount = case.total_overpayment_amount or 0.0
        if is_closure and amount > SUPERVISOR_THRESHOLD:
            case.status = "pending_supervisor"
            case.decision_metadata = json.dumps({
                "disposition": to_status,
                "reason": transition.reason,
                "recovered_amount": transition.recovered_amount,
                "submitted_by_user_id": acting_user_id,
                "submitted_at": datetime.utcnow().isoformat(),
            })
            await self.session.flush()
            await self.audit_dao.create_entry(
                case_id=case.case_id,
                actor_user_id=acting_user_id,
                action="CLOSURE_SUBMITTED_FOR_APPROVAL",
                from_status=from_status,
                to_status="pending_supervisor",
                reason=transition.reason or f"Closure as {to_status} requires supervisor approval (at-risk > $2,000)",
            )
            # Notify every supervisor that an approval is needed
            from .notification_service import notify_supervisors
            pretty = to_status.replace("closed_", "").replace("_", " ")
            await notify_supervisors(
                self.session,
                kind="approval_requested",
                title=f"Approval needed: {case.case_number}",
                body=f"Closure as '{pretty}' ({_fmt_money(amount)})",
                case_id=case.case_id,
                actor_user_id=acting_user_id,
                link=f"/approvals",
            )
        else:
            # Direct transition (non-closure, or closure below threshold)
            await self.case_dao.transition_status(case_sequence, to_status)
            await self.audit_dao.create_entry(
                case_id=case.case_id,
                actor_user_id=acting_user_id,
                action="STATUS_TRANSITION",
                from_status=from_status,
                to_status=to_status,
                reason=transition.reason,
            )
            # Side effect: when transitioning to notice_sent, auto-generate the
            # recovery letter from the default LOB template (P4-1)
            if to_status == "notice_sent" and from_status != "notice_sent":
                from .letter_service import LetterService
                try:
                    await LetterService(self.session).auto_generate_for_case(case_sequence)
                except Exception as exc:
                    # Don't fail the transition if letter generation hiccups —
                    # log into audit and continue
                    import logging
                    logging.getLogger(__name__).warning(
                        "Letter auto-generation failed for case %s: %s", case_sequence, exc
                    )

        case_refreshed = await self.case_dao.get_with_full_details(case_sequence)
        await self._attach_dispositions(case_refreshed); return _serialize_case_detail(case_refreshed)

    async def approve_pending(
        self,
        case_sequence: int,
        supervisor_id: str,
        reason: Optional[str] = None,
    ) -> CaseDetail:
        """Supervisor approves the pending closure stored in decision_metadata."""
        import json
        case = await self.case_dao.get_by_sequence(case_sequence)
        if case is None:
            raise ValueError(f"Case {case_sequence} not found")
        if case.status != "pending_supervisor":
            raise ValueError("Case is not awaiting supervisor approval")
        if not case.decision_metadata:
            raise ValueError("Case has no pending decision recorded")

        decision = json.loads(case.decision_metadata)
        target_status = decision.get("disposition")
        if not target_status:
            raise ValueError("Pending decision is missing a disposition")

        from_status = case.status
        await self.case_dao.transition_status(case_sequence, target_status)
        case.decision_metadata = None
        await self.session.flush()

        await self.audit_dao.create_entry(
            case_id=case.case_id,
            actor_user_id=supervisor_id,
            action="SUPERVISOR_APPROVED",
            from_status=from_status,
            to_status=target_status,
            reason=reason or f"Approved closure as {target_status}",
        )

        # Notify the analyst who submitted (if known)
        submitter_id = decision.get("submitted_by_user_id")
        if submitter_id and submitter_id != supervisor_id:
            from .notification_service import notify
            await notify(
                self.session,
                recipient_user_id=submitter_id,
                kind="approval_decided",
                title=f"Closure approved: {case.case_number}",
                body=f"Supervisor approved your '{target_status}' submission",
                case_id=case.case_id,
                actor_user_id=supervisor_id,
                link=f"/cases/{case.case_sequence}",
            )

        case_refreshed = await self.case_dao.get_with_full_details(case_sequence)
        await self._attach_dispositions(case_refreshed); return _serialize_case_detail(case_refreshed)

    async def reject_pending(
        self,
        case_sequence: int,
        supervisor_id: str,
        reason: str,
    ) -> CaseDetail:
        """Supervisor rejects the pending closure; returns case to in_review."""
        import json
        case = await self.case_dao.get_by_sequence(case_sequence)
        if case is None:
            raise ValueError(f"Case {case_sequence} not found")
        if case.status != "pending_supervisor":
            raise ValueError("Case is not awaiting supervisor approval")
        if not reason or not reason.strip():
            raise ValueError("A reason is required to reject a pending closure")

        # Capture submitter before we clear decision_metadata
        submitter_id = None
        if case.decision_metadata:
            try:
                submitter_id = json.loads(case.decision_metadata).get("submitted_by_user_id")
            except Exception:
                pass

        from_status = case.status
        await self.case_dao.transition_status(case_sequence, "in_review")
        case.decision_metadata = None
        await self.session.flush()

        await self.audit_dao.create_entry(
            case_id=case.case_id,
            actor_user_id=supervisor_id,
            action="SUPERVISOR_REJECTED",
            from_status=from_status,
            to_status="in_review",
            reason=reason.strip(),
        )

        if submitter_id and submitter_id != supervisor_id:
            from .notification_service import notify
            await notify(
                self.session,
                recipient_user_id=submitter_id,
                kind="approval_decided",
                title=f"Closure rejected: {case.case_number}",
                body=f"Supervisor sent it back: {reason.strip()[:100]}",
                case_id=case.case_id,
                actor_user_id=supervisor_id,
                link=f"/cases/{case.case_sequence}",
            )

        case_refreshed = await self.case_dao.get_with_full_details(case_sequence)
        await self._attach_dispositions(case_refreshed); return _serialize_case_detail(case_refreshed)

    async def reopen(
        self,
        case_sequence: int,
        supervisor_id: Optional[str],
        reason: str,
    ) -> CaseDetail:
        case = await self.case_dao.get_by_sequence(case_sequence)
        if case is None:
            raise ValueError(f"Case {case_sequence} not found")

        from_status = case.status
        case.status = "assigned"
        case.is_active = True
        case.case_sequence = case.case_sequence  # no-op but refresh
        await self.session.flush()

        # Notify the assigned analyst that their case was reopened
        if case.assigned_analyst_id and case.assigned_analyst_id != supervisor_id:
            from .notification_service import notify
            await notify(
                self.session,
                recipient_user_id=case.assigned_analyst_id,
                kind="case_reopened",
                title=f"Case reopened: {case.case_number}",
                body=f"Supervisor reopened: {reason[:100]}" if reason else "Supervisor reopened the case",
                case_id=case.case_id,
                actor_user_id=supervisor_id,
                link=f"/cases/{case.case_sequence}",
            )

        await self.audit_dao.create_entry(
            case_id=case.case_id,
            actor_user_id=supervisor_id,
            action="CASE_REOPENED",
            from_status=from_status,
            to_status="assigned",
            reason=reason,
        )

        case_refreshed = await self.case_dao.get_with_full_details(case_sequence)
        await self._attach_dispositions(case_refreshed); return _serialize_case_detail(case_refreshed)
