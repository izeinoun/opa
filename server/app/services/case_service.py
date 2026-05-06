import json
from typing import Optional, List
from datetime import datetime, timedelta
from datetime import date as date_type
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
)

DETECTOR_REGISTRY = [
    {"id": "DET-01", "name": "Duplicate Payment"},
    {"id": "DET-02", "name": "Retro Eligibility Check"},
    {"id": "DET-04", "name": "Fee Schedule Mispricing"},
    {"id": "DET-06", "name": "NCCI / MUE Violation"},
    {"id": "DET-08", "name": "Excluded Provider"},
    {"id": "DET-09", "name": "Coding Errors"},
]

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


def _serialize_line(line: ClaimLine, service_date: str) -> ClaimLineRead:
    try:
        icd_codes = json.loads(line.icd_codes)
    except Exception:
        icd_codes = [line.icd_codes] if line.icd_codes else []
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
    )


def _serialize_finding(cf) -> ClaimFindingRead:
    f = cf.finding if hasattr(cf, "finding") else cf
    return ClaimFindingRead(
        id=f.finding_id,
        detector_code=f.detector_id,
        finding_type=f.severity,
        description=f.rationale,
        overpayment_amount=f.overpayment_amount,
        confidence_score=f.confidence,
        evidence_json=f.evidence,
        created_at=f.fired_at,
    )


def _serialize_finding_raw(f) -> ClaimFindingRead:
    return ClaimFindingRead(
        id=f.finding_id,
        detector_code=f.detector_id,
        finding_type=f.severity,
        description=f.rationale,
        overpayment_amount=f.overpayment_amount,
        confidence_score=f.confidence,
        evidence_json=f.evidence or "{}",
        created_at=(f.fired_at or "")[:10],
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


def _serialize_notice(n: ProviderNotice) -> RecoveryNoticeRead:
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
    lines = [_serialize_line(l, claim.service_from_date) for l in (claim.lines or [])]

    findings = []
    for cf in (case.case_findings or []):
        if cf.finding:
            findings.append(_serialize_finding(cf))

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
        lines=lines,
        findings=findings,
        era_transactions=era_transactions,
    )


def _serialize_case_summary(case: OpaCase) -> CaseSummary:
    likelihood = 0.0
    if case.likelihood_score:
        likelihood = case.likelihood_score.composite_likelihood

    amount_billed = case.claim.total_billed if case.claim else 0.0

    claim_summary = None
    if case.claim:
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
        )

    return CaseSummary(
        id=case.case_sequence,
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
    )


def _serialize_case_detail(case: OpaCase) -> CaseDetail:
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

    priority_breakdown = None
    if case.likelihood_score:
        ls = case.likelihood_score
        today = date_type.today()
        deadline = None
        days_overdue = None
        days_until = None
        try:
            deadline = date_type.fromisoformat(case.deadline_date)
            delta = (deadline - today).days
            if delta < 0:
                days_overdue = -delta   # positive int: how many days past due
                days_until = 0
            else:
                days_until = delta      # positive int: days remaining
        except Exception:
            pass
        # Override fires when: stored flag, already overdue, OR ≤5 days remaining
        override = (
            bool(ls.urgency_override_applied)
            or (days_overdue is not None and days_overdue > 0)
            or (days_until is not None and days_until <= 5)
        )
        amount_norm = min(case.total_overpayment_amount / 50_000.0, 1.0)
        amount_pts  = round(amount_norm * 40, 2)
        likelihood_pts = round(ls.composite_likelihood * 40, 2)
        urgency_pts = round(ls.urgency_factor * 20, 2)
        priority_breakdown = PriorityBreakdown(
            total_score=case.priority_score,
            band=case.priority,
            amount_pts=amount_pts,
            likelihood_pts=likelihood_pts,
            urgency_pts=urgency_pts,
            amount_at_risk=case.total_overpayment_amount,
            likelihood_score=ls.composite_likelihood,
            urgency_factor=ls.urgency_factor,
            urgency_override_applied=override,
            days_overdue=days_overdue,
            days_until=days_until,
        )

    raw_findings = [cf.finding for cf in (case.case_findings or []) if cf.finding]
    fired_by_det: dict = {}
    for f in raw_findings:
        canonical = _DET_CODE_MAP.get(f.detector_id)
        if canonical and canonical not in fired_by_det:
            fired_by_det[canonical] = f

    detector_results = []
    for det in DETECTOR_REGISTRY:
        finding = fired_by_det.get(det["id"])
        detector_results.append(DetectorResultRead(
            detector_id=det["id"],
            detector_name=det["name"],
            fired=finding is not None,
            finding=_serialize_finding_raw(finding) if finding else None,
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
        group_id=case.case_group_id,
        priority_breakdown=priority_breakdown,
        detector_results=detector_results,
    )


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
        return _serialize_case_detail(case)

    async def transition(
        self,
        case_sequence: int,
        transition: CaseTransition,
        acting_user_id: Optional[str],
    ) -> CaseDetail:
        case = await self.case_dao.get_by_sequence(case_sequence)
        if case is None:
            raise ValueError(f"Case {case_sequence} not found")

        from_status = case.status
        await self.case_dao.transition_status(case_sequence, transition.to_status)

        await self.audit_dao.create_entry(
            case_id=case.case_id,
            actor_user_id=acting_user_id,
            action="STATUS_TRANSITION",
            from_status=from_status,
            to_status=transition.to_status,
            reason=transition.notes,
        )

        case_refreshed = await self.case_dao.get_with_full_details(case_sequence)
        return _serialize_case_detail(case_refreshed)

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

        await self.audit_dao.create_entry(
            case_id=case.case_id,
            actor_user_id=supervisor_id,
            action="CASE_REOPENED",
            from_status=from_status,
            to_status="assigned",
            reason=reason,
        )

        case_refreshed = await self.case_dao.get_with_full_details(case_sequence)
        return _serialize_case_detail(case_refreshed)
