"""POST /api/analyze/835 — parse a raw X12 835, create a case, run detectors, return CaseDetail."""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from ..middleware.auth import require_app

log = logging.getLogger(__name__)
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.claims import Claim, ClaimLine, ClaimPayment835, Transaction835
from ..models.reference import Member, Provider, ProviderOrg
from ..models.workflow import CaseFinding, Finding, LikelihoodScore, OpaCase
from ..schemas.case_schemas import CaseDetail
from ..services.case_service import CaseService, _compute_posterior, _DET_CODE_MAP
from ..services.detector_service import DetectorService
from ..services.edi_parser import Parsed835, ParsedClaim, parse_835
from ..services.scoring_service import ScoringService
from ..services.prioritization_service import get_config as get_priority_config, compute_priority_with_config
from ..services.amount_at_risk import compute_at_risk_deduped

router = APIRouter(prefix="/api/analyze", tags=["analyze"], dependencies=[Depends(require_app("payguard"))])


class Analyze835Request(BaseModel):
    raw_edi: str


# ── LOB inference ──────────────────────────────────────────────────────────────

def _infer_lob(member_lob: Optional[str], payer_name: str) -> str:
    if member_lob:
        return member_lob
    lower = payer_name.lower()
    if any(kw in lower for kw in ("medicaid", "ahcccs", "dss", "state health", "medi-cal")):
        return "Medicaid"
    if "ppo" in lower:
        return "PPO"
    return "MA"


# ── Member ─────────────────────────────────────────────────────────────────────

async def _get_or_create_member(
    db: AsyncSession,
    p: ParsedClaim,
    lob: str,
) -> Member:
    now = datetime.utcnow().isoformat()

    if p.patient_id:
        result = await db.execute(select(Member).where(Member.member_number == p.patient_id))
        existing = result.scalar_one_or_none()
        if existing:
            return existing

    if p.patient_last and p.patient_first:
        result = await db.execute(
            select(Member).where(Member.last_name == p.patient_last, Member.first_name == p.patient_first)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

    member = Member(
        member_id=str(uuid.uuid4()),
        member_number=p.patient_id or f"MBR-{uuid.uuid4().hex[:8].upper()}",
        first_name=p.patient_first or "Unknown",
        last_name=p.patient_last or "Patient",
        date_of_birth="1970-01-01",
        lob=lob,
        coverage_effective_date="2020-01-01",
        created_at=now,
        updated_at=now,
    )
    db.add(member)
    return member


# ── Provider ───────────────────────────────────────────────────────────────────

async def _get_or_create_provider(
    db: AsyncSession,
    p: ParsedClaim,
) -> Tuple[ProviderOrg, Provider]:
    now = datetime.utcnow().isoformat()
    npi = (p.rendering_npi or "").strip()

    if npi:
        result = await db.execute(select(Provider).where(Provider.npi == npi))
        provider = result.scalar_one_or_none()
        if provider:
            org_result = await db.execute(
                select(ProviderOrg).where(ProviderOrg.provider_org_id == provider.provider_org_id)
            )
            return org_result.scalar_one(), provider

    tin = f"XX{uuid.uuid4().hex[:7].upper()}"
    provider_name = p.rendering_name or f"Provider {npi or 'Unknown'}"

    # Check OIG exclusion reference: if this NPI is in the reference data as excluded,
    # inherit that status for the new provider record.
    is_excluded = False
    exclusion_source: Optional[str] = None
    exclusion_date: Optional[str] = None
    if npi:
        excl_res = await db.execute(
            select(Provider).where(Provider.npi == npi, Provider.is_excluded == True)  # noqa: E712
        )
        excl_ref = excl_res.scalar_one_or_none()
        if excl_ref:
            is_excluded = True
            exclusion_source = excl_ref.exclusion_source
            exclusion_date = excl_ref.exclusion_effective_date

    org = ProviderOrg(
        provider_org_id=str(uuid.uuid4()),
        name=provider_name,
        npi=f"ORG-{uuid.uuid4().hex[:10].upper()}",
        tin=tin,
        org_type="group",
        is_sensitive=False,
        risk_score=0.5,
        created_at=now,
        updated_at=now,
    )
    db.add(org)

    provider = Provider(
        provider_id=str(uuid.uuid4()),
        provider_org_id=org.provider_org_id,
        npi=npi or f"IND-{uuid.uuid4().hex[:10].upper()}",
        tin=tin,
        name=provider_name,
        specialty="unknown",
        credential_status="active",
        credential_effective_date="2020-01-01",
        is_excluded=is_excluded,
        exclusion_source=exclusion_source,
        exclusion_effective_date=exclusion_date,
        billing_variance_score=0.5,
        created_at=now,
        updated_at=now,
    )
    db.add(provider)
    return org, provider


# ── Main endpoint ──────────────────────────────────────────────────────────────

@router.post("/835", response_model=CaseDetail)
async def analyze_835(
    body: Analyze835Request,
    db: AsyncSession = Depends(get_db),
) -> CaseDetail:
    # 1. Parse
    log.info("analyze_835 received %d chars | first_30=%r", len(body.raw_edi), body.raw_edi[:30])
    try:
        parsed: Parsed835 = parse_835(body.raw_edi)
    except ValueError as exc:
        log.warning("parse_835 failed: %s | raw_edi[:200]=%r", exc, body.raw_edi[:200])
        raise HTTPException(status_code=400, detail=f"EDI parse error: {exc}")

    if not parsed.claims:
        raise HTTPException(status_code=400, detail="No CLP claim segments found in this 835.")

    p_claim = parsed.claims[0]
    now = datetime.utcnow().isoformat()
    today = date.today()

    # 2. Resolve member + provider
    lob = _infer_lob(None, parsed.payer_name)
    member = await _get_or_create_member(db, p_claim, lob)
    lob = _infer_lob(member.lob, parsed.payer_name)
    org, provider = await _get_or_create_provider(db, p_claim)

    # 3. ERA transaction + payment lines
    era_txn = Transaction835(
        transaction_id=str(uuid.uuid4()),
        transaction_number=f"{parsed.era_number}-{uuid.uuid4().hex[:8]}",
        transaction_type="payment",
        payer_name=parsed.payer_name,
        provider_org_id=org.provider_org_id,
        transaction_date=parsed.payment_date,
        total_amount=parsed.payment_amount,
        claim_count=len(parsed.claims),
        raw_835_json=body.raw_edi[:4000],
        created_at=now,
    )
    db.add(era_txn)

    for svc in p_claim.svc_lines:
        db.add(ClaimPayment835(
            payment_id=str(uuid.uuid4()),
            transaction_id=era_txn.transaction_id,
            claim_icn=p_claim.payer_claim_number or p_claim.patient_control_number,
            cpt_code=svc.cpt_code,
            paid_amount=svc.paid_amount,
            adjustment_amount=svc.adjustment_amount,
            adjustment_reason_code=svc.adjustment_reason_code,
            check_number=None,
            payment_date=parsed.payment_date,
        ))

    # 4. Claim — derive totals from SVC lines if CLP amounts are missing/zero
    service_date = p_claim.service_date or parsed.payment_date
    svc_billed = sum(s.billed_amount for s in p_claim.svc_lines)
    svc_paid   = sum(s.paid_amount   for s in p_claim.svc_lines)
    total_billed = p_claim.billed if p_claim.billed > 0 else svc_billed
    total_paid   = p_claim.paid   if p_claim.paid   > 0 else svc_paid
    claim = Claim(
        claim_id=str(uuid.uuid4()),
        icn=f"ICN-{uuid.uuid4().hex[:12].upper()}",
        member_id=member.member_id,
        provider_org_id=org.provider_org_id,
        billing_provider_npi=provider.npi,
        rendering_provider_npi=provider.npi,
        lob=lob,
        service_from_date=service_date,
        service_to_date=service_date,
        claim_type="professional",
        submitted_member_number=p_claim.patient_id or None,
        submitted_patient_dob=None,   # DOB is not carried in 835 remittances
        claim_status="paid",
        total_billed=total_billed,
        total_paid=total_paid,
        paid_date=parsed.payment_date,
        submission_date=today.isoformat(),
        pos_code="11",
        primary_icd="Z99.9",
        era_transaction_id=era_txn.transaction_id,
        raw_claim_json="{}",
        created_at=now,
        updated_at=now,
    )
    db.add(claim)

    # 5. Claim lines
    for idx, svc in enumerate(p_claim.svc_lines, start=1):
        db.add(ClaimLine(
            claim_line_id=str(uuid.uuid4()),
            claim_id=claim.claim_id,
            line_number=idx,
            cpt_code=svc.cpt_code,
            icd_codes="[]",
            modifier_1=svc.modifier,
            units_billed=svc.units,
            units_paid=svc.units,
            billed_amount=svc.billed_amount,
            paid_amount=svc.paid_amount,
            allowed_amount=svc.paid_amount,
            pos_code="11",
        ))

    # 6. OPA case
    seq_result = await db.execute(select(func.max(OpaCase.case_sequence)))
    case_seq = (seq_result.scalar_one_or_none() or 0) + 1
    identified_date = today
    deadline_date = today + timedelta(days=60)
    case_uuid = str(uuid.uuid4())

    case = OpaCase(
        case_id=case_uuid,
        case_number=f"OPA-{today.year}-{case_seq:05d}",
        case_sequence=case_seq,
        claim_id=claim.claim_id,
        primary_detector_id="PENDING",
        lob=lob,
        provider_org_id=org.provider_org_id,
        member_id=member.member_id,
        status="new",
        is_active=True,
        priority="MEDIUM",
        priority_score=50.0,
        total_overpayment_amount=0.0,
        recommended_recovery_method="standard",
        identified_date=identified_date.isoformat(),
        deadline_date=deadline_date.isoformat(),
        deadline_breached=False,
        lookback_window_start=(today - timedelta(days=365)).isoformat(),
        is_sensitive_provider=org.is_sensitive,
        requires_supervisor_approval=False,
        evidence_bundle="{}",
        case_json="{}",
        created_at=now,
        updated_at=now,
    )
    db.add(case)

    # 7. Placeholder LikelihoodScore — composite_likelihood seeded from ML model output
    db.add(LikelihoodScore(
        score_id=str(uuid.uuid4()),
        case_id=case_uuid,
        provider_risk_score=provider.billing_variance_score,
        cpt_risk_score=0.0,
        dx_cpt_mismatch_score=0.0,
        claim_complexity_score=0.0,
        billing_variance_score=provider.billing_variance_score,
        composite_likelihood=provider.billing_variance_score,
        urgency_factor=0.5,
        urgency_override_applied=False,
        priority_score=50.0,
        score_json="{}",
        scored_at=now,
    ))

    await db.commit()

    # 8. Run detectors (commits internally)
    det_svc = DetectorService(db)
    await det_svc.run_for_case(case_seq)

    # 9. Recompute priority from real findings
    case_res = await db.execute(select(OpaCase).where(OpaCase.case_sequence == case_seq))
    fresh_case = case_res.scalar_one()

    ls_res = await db.execute(select(LikelihoodScore).where(LikelihoodScore.case_id == case_uuid))
    fresh_ls = ls_res.scalar_one()

    findings_res = await db.execute(
        select(Finding)
        .join(CaseFinding, Finding.finding_id == CaseFinding.finding_id)
        .where(CaseFinding.case_id == case_uuid)
    )
    findings = findings_res.scalars().all()

    # Per-line de-dup: each line attributed to its highest-priority finding.
    lines_res = await db.execute(select(ClaimLine).where(ClaimLine.claim_id == fresh_case.claim_id))
    claim_lines = list(lines_res.scalars().all())
    amount_at_risk, _line_breakdown = compute_at_risk_deduped(claim_lines, list(findings))
    if amount_at_risk <= 0:
        # Fall back to CLP difference, then SVC line difference
        clp_diff = max(p_claim.billed - p_claim.paid, 0.0)
        svc_diff = max(svc_billed - svc_paid, 0.0)
        amount_at_risk = clp_diff or svc_diff

    posterior = _compute_posterior(fresh_ls.composite_likelihood, list(findings))
    cfg = await get_priority_config(db)
    priority_score, priority_band = compute_priority_with_config(
        cfg,
        amount_at_risk=amount_at_risk,
        posterior=posterior,
        deadline=deadline_date,
    )

    fresh_case.total_overpayment_amount = amount_at_risk
    fresh_case.priority_score = priority_score
    fresh_case.priority = priority_band
    if findings:
        fresh_case.primary_detector_id = max(findings, key=lambda f: f.overpayment_amount).detector_id

    await db.commit()

    # LLM-assisted FWA pass (FWA-04 upcoding + FWA-07 diagnosis inflation).
    # Soft-fails on missing API key; never blocks case creation.
    try:
        from ..services import fwa_service
        await fwa_service.run(fresh_case.claim_id, db)
        await db.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception(
            "FWA LLM pass failed for case %s: %s", fresh_case.case_id, e
        )

    # 10. Return full CaseDetail
    return await CaseService(db).get_case_detail(case_seq)
