"""Pre-pay reports — summary across all pre-pay claims + per-specialist
drill-in. Ported from ClaimGuard's routers/admin.py reports endpoints."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.claims import Claim
from ..models.workflow import OpaCase, OpaUser
from ..schemas.prepay_schemas import PrepayClaimOut, UserOut

router = APIRouter(prefix="/api/prepay/reports", tags=["prepay-reports"])


_CLINICAL_DENIAL_STATUSES = {"denied"}
_TECHNICAL_DENIAL_STATUSES = {"correction", "pend"}
_OPEN_STATUSES = {"pending", "review", "escalated", "correction", "pend"}


# ── Response shapes (mirror ClaimGuard's for UI parity) ──────────────────

class AgingBuckets(BaseModel):
    bucket_0_7: int = 0
    bucket_8_14: int = 0
    bucket_15_30: int = 0
    bucket_30_plus: int = 0


class ReportSummary(BaseModel):
    total_claims: int
    approved_count: int
    approved_amount: float
    denied_count: int
    denied_amount: float
    technical_denial_rate: float
    clinical_denial_rate: float
    avg_review_time_by_specialist: Dict[str, float]
    aging_buckets: AgingBuckets
    dollar_by_specialty: Dict[str, float]


class SpecialistReport(BaseModel):
    user: UserOut
    total_claims: int
    by_status: Dict[str, int]
    total_billed: float
    avg_review_time_minutes: float
    claims: List[PrepayClaimOut]


# ── Helpers ──────────────────────────────────────────────────────────────

def _user_to_out(u: OpaUser) -> UserOut:
    return UserOut(
        id=u.user_id, name=u.full_name, role=u.role,
        initials=u.initials, color_hex=u.color_hex,
        specialty=u.specialty, supervisor_id=u.supervisor_id,
    )


async def _claim_to_out(db: AsyncSession, c: Claim) -> PrepayClaimOut:
    # Reuse the prepay_claims._build_detail-style assembly without the inline
    # joins overhead; reports only need surface fields, not findings.
    from ..models.claims import ClaimLine
    from ..models.reference import Member, ProviderOrg
    l_res = await db.execute(select(ClaimLine).where(ClaimLine.claim_id == c.claim_id))
    cpts = [ln.cpt_code for ln in l_res.scalars().all() if ln.cpt_code]
    m = (await db.execute(select(Member).where(Member.member_id == c.member_id))).scalar_one_or_none()
    o = (await db.execute(select(ProviderOrg).where(ProviderOrg.provider_org_id == c.provider_org_id))).scalar_one_or_none()
    return PrepayClaimOut(
        claim_id=c.claim_id, icn=c.icn, pipeline_mode=c.pipeline_mode,
        claim_form_type=c.claim_form_type, care_setting=c.care_setting,
        drg=c.drg, cpts=cpts,
        icd10=[c.primary_icd] if c.primary_icd else [],
        provider_name=o.name if o else None,
        patient_name=f"{m.first_name} {m.last_name}" if m else None,
        dob=m.date_of_birth if m else None,
        dos=c.service_from_date, billed_amount=float(c.total_billed or 0),
        status=c.claim_status, specialty=c.specialty,
        description=c.description, summary=c.claim_summary,
        code_descriptions=None,
        created_at=c.created_at, updated_at=c.updated_at,
    )


async def _assigned_analyst_map(db: AsyncSession) -> Dict[str, Optional[str]]:
    """Map claim_id → assigned_analyst_id (via opa_cases.claim_id)."""
    res = await db.execute(select(OpaCase.claim_id, OpaCase.assigned_analyst_id))
    return {row[0]: row[1] for row in res.all()}


async def _review_time_map(db: AsyncSession) -> Dict[str, int]:
    res = await db.execute(select(OpaCase.claim_id, OpaCase.review_time_minutes))
    return {row[0]: row[1] or 0 for row in res.all()}


# ── Routes ───────────────────────────────────────────────────────────────

@router.get("/summary", response_model=ReportSummary)
async def report_summary(db: AsyncSession = Depends(get_db)) -> ReportSummary:
    # Pull all pre-pay claims (the report is scoped to the pre-pay pipeline).
    c_res = await db.execute(
        select(Claim).where(Claim.pipeline_mode == "pre_pay")
    )
    claims = list(c_res.scalars().all())
    u_res = await db.execute(select(OpaUser))
    user_by_id = {u.user_id: u for u in u_res.scalars().all()}

    assigned = await _assigned_analyst_map(db)
    review_times = await _review_time_map(db)

    total = len(claims)
    approved = [c for c in claims if c.claim_status == "approved"]
    denied = [c for c in claims if c.claim_status == "denied"]
    clinical = sum(1 for c in claims if c.claim_status in _CLINICAL_DENIAL_STATUSES)
    technical = sum(1 for c in claims if c.claim_status in _TECHNICAL_DENIAL_STATUSES)

    review_time_by_user: Dict[str, List[int]] = defaultdict(list)
    for c in claims:
        uid = assigned.get(c.claim_id)
        rt = review_times.get(c.claim_id, 0)
        if uid is None or rt <= 0:
            continue
        u = user_by_id.get(uid)
        name = u.full_name if u else f"user#{uid[:8]}"
        review_time_by_user[name].append(rt)
    avg_review_time = {
        name: round(sum(times) / len(times), 1)
        for name, times in review_time_by_user.items()
    }

    now = datetime.utcnow()
    buckets = AgingBuckets()
    for c in claims:
        if c.claim_status not in _OPEN_STATUSES:
            continue
        try:
            created = datetime.fromisoformat(c.created_at)
        except Exception:
            continue
        age = (now - created).days
        if age <= 7:
            buckets.bucket_0_7 += 1
        elif age <= 14:
            buckets.bucket_8_14 += 1
        elif age <= 30:
            buckets.bucket_15_30 += 1
        else:
            buckets.bucket_30_plus += 1

    dollar_by_specialty: Dict[str, float] = defaultdict(float)
    for c in claims:
        dollar_by_specialty[c.specialty or "Other"] += float(c.total_billed or 0)

    return ReportSummary(
        total_claims=total,
        approved_count=len(approved),
        approved_amount=round(sum(float(c.total_billed or 0) for c in approved), 2),
        denied_count=len(denied),
        denied_amount=round(sum(float(c.total_billed or 0) for c in denied), 2),
        technical_denial_rate=round(technical / total, 4) if total else 0.0,
        clinical_denial_rate=round(clinical / total, 4) if total else 0.0,
        avg_review_time_by_specialist=avg_review_time,
        aging_buckets=buckets,
        dollar_by_specialty={k: round(v, 2) for k, v in dollar_by_specialty.items()},
    )


@router.get("/specialist/{user_id}", response_model=SpecialistReport)
async def report_specialist(
    user_id: str, db: AsyncSession = Depends(get_db)
) -> SpecialistReport:
    user = (await db.execute(
        select(OpaUser).where(OpaUser.user_id == user_id)
    )).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Claims assigned to this user via opa_cases.
    case_res = await db.execute(
        select(OpaCase).where(OpaCase.assigned_analyst_id == user_id)
    )
    case_rows = list(case_res.scalars().all())
    claim_ids = [r.claim_id for r in case_rows if r.claim_id]
    if not claim_ids:
        return SpecialistReport(
            user=_user_to_out(user),
            total_claims=0, by_status={}, total_billed=0.0,
            avg_review_time_minutes=0.0, claims=[],
        )

    c_res = await db.execute(
        select(Claim).where(Claim.claim_id.in_(claim_ids))
        .where(Claim.pipeline_mode == "pre_pay")
    )
    claims = list(c_res.scalars().all())

    by_status: Dict[str, int] = defaultdict(int)
    for c in claims:
        by_status[c.claim_status] += 1

    review_times = [r.review_time_minutes for r in case_rows if (r.review_time_minutes or 0) > 0]
    avg_time = round(sum(review_times) / len(review_times), 1) if review_times else 0.0

    outs = [await _claim_to_out(db, c) for c in claims]
    return SpecialistReport(
        user=_user_to_out(user),
        total_claims=len(claims),
        by_status=dict(by_status),
        total_billed=round(sum(float(c.total_billed or 0) for c in claims), 2),
        avg_review_time_minutes=avg_time,
        claims=outs,
    )
