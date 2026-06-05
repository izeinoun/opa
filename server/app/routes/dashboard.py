from typing import List
from datetime import datetime, timedelta, date
from fastapi import APIRouter, Depends
from ..middleware.auth import require_app
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case as sa_case

from ..database import get_db
from ..schemas.dashboard_schemas import (
    DashboardResponse,
    KPICard,
    AgingBucket,
    WorkloadItem,
    RecoveryPoint,
    DetectorStat,
    StatusCount,
    DxCoverageRate,
    DetectorAcceptanceRate,
    LayerCoverage,
)
from ..models.workflow import OpaCase, OpaUser, Finding, LikelihoodScore, FindingDisposition, DetectorRuleConfig
from ..models.claims import Claim, ClaimLine
from ..models.reference import CptDxCoverage

# PayGuard is post-pay only. All dashboard aggregates join through claims so
# pre-pay (ClaimGuard) cases/findings don't inflate the numbers.
_POST_PAY = Claim.pipeline_mode == "post_pay"


def _case_join(stmt):
    return stmt.join(Claim, OpaCase.claim_id == Claim.claim_id)


def _finding_join(stmt):
    return stmt.join(Claim, Finding.claim_id == Claim.claim_id)


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"], dependencies=[Depends(require_app("payguard"))])


def _aging_bucket_label(identified_date: str) -> str:
    try:
        d = date.fromisoformat(identified_date[:10])
    except Exception:
        return "60+d"
    days = (date.today() - d).days
    if days <= 15:
        return "0-15d"
    elif days <= 30:
        return "16-30d"
    elif days <= 45:
        return "31-45d"
    elif days <= 60:
        return "46-60d"
    return "60+d"


async def _compute_kpis(db: AsyncSession) -> List[KPICard]:
    open_count = (await db.execute(
        _case_join(select(func.count(OpaCase.case_id)))
        .where(OpaCase.is_active == True, _POST_PAY)
    )).scalar_one() or 0

    total_at_risk = float((await db.execute(
        _case_join(select(func.coalesce(func.sum(OpaCase.total_overpayment_amount), 0.0)))
        .where(OpaCase.is_active == True, _POST_PAY)
    )).scalar_one() or 0.0)

    total_recovered = float((await db.execute(
        _case_join(select(func.coalesce(func.sum(OpaCase.total_overpayment_amount), 0.0)))
        .where(OpaCase.status == "closed_recovered", _POST_PAY)
    )).scalar_one() or 0.0)

    high_priority = (await db.execute(
        _case_join(select(func.count(OpaCase.case_id)))
        .where(OpaCase.is_active == True, OpaCase.priority == "HIGH", _POST_PAY)
    )).scalar_one() or 0

    return [
        KPICard(label="Open Cases",           value=open_count,      unit="cases", delta=None),
        KPICard(label="High Priority",         value=high_priority,   unit="cases", delta=None),
        KPICard(label="Total at Risk",         value=total_at_risk,   unit="$",     delta=None),
        KPICard(label="Total Recovered",       value=total_recovered, unit="$",     delta=None),
    ]


async def _compute_aging(db: AsyncSession) -> List[AgingBucket]:
    result = await db.execute(
        _case_join(select(OpaCase.identified_date, OpaCase.total_overpayment_amount))
        .where(OpaCase.is_active == True, _POST_PAY)
    )
    rows = result.all()

    buckets: dict = {k: {"count": 0, "amount": 0.0} for k in
                     ["0-15d", "16-30d", "31-45d", "46-60d", "60+d"]}
    for (identified_date, amount) in rows:
        label = _aging_bucket_label(identified_date or "")
        buckets[label]["count"] += 1
        buckets[label]["amount"] += float(amount or 0.0)

    return [AgingBucket(label=k, count=v["count"], amount=v["amount"]) for k, v in buckets.items()]


async def _compute_workload(db: AsyncSession) -> List[WorkloadItem]:
    result = await db.execute(
        select(
            OpaUser.full_name,
            func.count(OpaCase.case_id).label("open_cases"),
            func.sum(sa_case((OpaCase.priority == "HIGH", 1), else_=0)).label("high_priority"),
            func.coalesce(func.sum(OpaCase.total_overpayment_amount), 0.0).label("total_at_risk"),
        )
        .join(OpaCase, OpaCase.assigned_analyst_id == OpaUser.user_id)
        .join(Claim, OpaCase.claim_id == Claim.claim_id)
        .where(OpaCase.is_active == True, _POST_PAY)
        .group_by(OpaUser.full_name)
    )
    return [
        WorkloadItem(
            assignee=row.full_name,
            open_cases=row.open_cases,
            high_priority=int(row.high_priority or 0),
            total_at_risk=float(row.total_at_risk or 0.0),
        )
        for row in result.all()
    ]


async def _compute_recovery(db: AsyncSession) -> List[RecoveryPoint]:
    today = date.today()
    points = []
    for i in range(5, -1, -1):
        month_start = (today.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
        next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        label = month_start.strftime("%Y-%m")

        ms = month_start.isoformat()
        me = next_month.isoformat()

        recovered = float((await db.execute(
            _case_join(select(func.coalesce(func.sum(OpaCase.total_overpayment_amount), 0.0)))
            .where(OpaCase.status == "closed_recovered",
                   OpaCase.identified_date >= ms, OpaCase.identified_date < me, _POST_PAY)
        )).scalar_one() or 0.0)

        written_off = float((await db.execute(
            _case_join(select(func.coalesce(func.sum(OpaCase.total_overpayment_amount), 0.0)))
            .where(OpaCase.status == "closed_written_off",
                   OpaCase.identified_date >= ms, OpaCase.identified_date < me, _POST_PAY)
        )).scalar_one() or 0.0)

        pending = float((await db.execute(
            _case_join(select(func.coalesce(func.sum(OpaCase.total_overpayment_amount), 0.0)))
            .where(OpaCase.is_active == True,
                   OpaCase.identified_date >= ms, OpaCase.identified_date < me, _POST_PAY)
        )).scalar_one() or 0.0)

        points.append(RecoveryPoint(month=label, recovered=recovered,
                                    written_off=written_off, pending=pending))
    return points


async def _compute_detector_stats(db: AsyncSession) -> List[DetectorStat]:
    result = await db.execute(
        _finding_join(select(
            Finding.detector_id,
            func.count(Finding.finding_id).label("total_findings"),
            func.coalesce(func.sum(Finding.overpayment_amount), 0.0).label("confirmed_overpayment"),
            func.avg(Finding.confidence).label("avg_confidence"),
        ))
        .where(_POST_PAY)
        .group_by(Finding.detector_id)
    )
    return [
        DetectorStat(
            detector_code=row.detector_id,
            total_findings=row.total_findings,
            confirmed_overpayment=float(row.confirmed_overpayment or 0.0),
            avg_confidence=float(row.avg_confidence or 0.0),
        )
        for row in result.all()
    ]


async def _compute_status_distribution(db: AsyncSession) -> List[StatusCount]:
    result = await db.execute(
        _case_join(select(OpaCase.status, func.count(OpaCase.case_id).label("count")))
        .where(_POST_PAY)
        .group_by(OpaCase.status)
    )
    return [StatusCount(status=row.status, count=row.count) for row in result.all()]


@router.get("", response_model=DashboardResponse)
async def get_dashboard(db: AsyncSession = Depends(get_db)) -> DashboardResponse:
    kpis = await _compute_kpis(db)
    aging = await _compute_aging(db)
    workload = await _compute_workload(db)
    recovery = await _compute_recovery(db)
    detectors = await _compute_detector_stats(db)
    status_distribution = await _compute_status_distribution(db)
    return DashboardResponse(
        kpis=kpis, aging=aging, workload=workload, recovery=recovery,
        detectors=detectors, status_distribution=status_distribution,
    )


@router.get("/summary", response_model=DashboardResponse)
async def get_summary(db: AsyncSession = Depends(get_db)) -> DashboardResponse:
    return await get_dashboard(db)


@router.get("/kpis", response_model=List[KPICard])
async def get_kpis(db: AsyncSession = Depends(get_db)) -> List[KPICard]:
    return await _compute_kpis(db)


@router.get("/aging", response_model=List[AgingBucket])
async def get_aging(db: AsyncSession = Depends(get_db)) -> List[AgingBucket]:
    return await _compute_aging(db)


@router.get("/workload", response_model=List[WorkloadItem])
async def get_workload(db: AsyncSession = Depends(get_db)) -> List[WorkloadItem]:
    return await _compute_workload(db)


@router.get("/recovery", response_model=List[RecoveryPoint])
async def get_recovery(db: AsyncSession = Depends(get_db)) -> List[RecoveryPoint]:
    return await _compute_recovery(db)


@router.get("/detectors", response_model=List[DetectorStat])
async def get_detector_stats(db: AsyncSession = Depends(get_db)) -> List[DetectorStat]:
    return await _compute_detector_stats(db)


@router.get("/dx-coverage", response_model=DxCoverageRate)
async def get_dx_coverage(db: AsyncSession = Depends(get_db)) -> DxCoverageRate:
    """Metric 1 — DX coverage rate.

    Measures what fraction of post-pay claim lines have their CPT catalogued
    in cpt_dx_coverage (i.e. DET-18 can actually evaluate them). The
    uncatalogued_cpts list is the priority queue for catalogue expansion.
    """
    # All distinct CPTs that have at least one coverage rule.
    catalogued_res = await db.execute(select(CptDxCoverage.cpt_code).distinct())
    catalogued: set[str] = {r for (r,) in catalogued_res.all()}

    # Every post-pay claim line with its CPT.
    lines_res = await db.execute(
        select(ClaimLine.cpt_code)
        .join(Claim, ClaimLine.claim_id == Claim.claim_id)
        .where(Claim.pipeline_mode == "post_pay")
    )
    all_line_cpts = [r for (r,) in lines_res.all()]

    total_lines = len(all_line_cpts)
    covered_lines = sum(1 for cpt in all_line_cpts if cpt in catalogued)

    # Distinct CPTs billed on post-pay claims that have NO coverage rules.
    billed_cpts: set[str] = set(all_line_cpts)
    uncatalogued = sorted(billed_cpts - catalogued)

    return DxCoverageRate(
        total_lines=total_lines,
        covered_lines=covered_lines,
        coverage_rate=round(covered_lines / total_lines, 4) if total_lines else 0.0,
        uncatalogued_cpts=uncatalogued,
    )


@router.get("/finding-acceptance", response_model=List[DetectorAcceptanceRate])
async def get_finding_acceptance(db: AsyncSession = Depends(get_db)) -> List[DetectorAcceptanceRate]:
    """Metric 2 — Finding acceptance / override rate by detector.

    Acceptance rate = analyst-confirmed findings / total findings.
    Override rate   = analyst-rejected findings / total findings.
    A falling acceptance rate on a detector signals calibration drift or
    catalogue quality issues (especially relevant for DET-18).
    """
    result = await db.execute(
        select(
            Finding.detector_id,
            func.count(Finding.finding_id).label("total"),
            func.sum(
                sa_case((FindingDisposition.status == "accepted", 1), else_=0)
            ).label("accepted"),
            func.sum(
                sa_case((FindingDisposition.status == "rejected", 1), else_=0)
            ).label("rejected"),
            func.sum(
                sa_case((FindingDisposition.status == "needs_review", 1), else_=0)
            ).label("needs_review"),
            func.sum(
                sa_case((FindingDisposition.status == "adjusted", 1), else_=0)
            ).label("adjusted"),
        )
        .join(FindingDisposition, Finding.finding_id == FindingDisposition.finding_id)
        .join(Claim, Finding.claim_id == Claim.claim_id)
        .where(Claim.pipeline_mode == "post_pay")
        .group_by(Finding.detector_id)
        .order_by(func.count(Finding.finding_id).desc())
    )
    rows = result.all()
    out = []
    for row in rows:
        total = row.total or 0
        accepted = int(row.accepted or 0)
        rejected = int(row.rejected or 0)
        out.append(DetectorAcceptanceRate(
            detector_code=row.detector_id,
            total=total,
            accepted=accepted,
            rejected=rejected,
            needs_review=int(row.needs_review or 0),
            adjusted=int(row.adjusted or 0),
            acceptance_rate=round(accepted / total, 4) if total else 0.0,
            override_rate=round(rejected / total, 4) if total else 0.0,
        ))
    return out


@router.get("/rule-coverage", response_model=List[LayerCoverage])
async def get_rule_coverage(db: AsyncSession = Depends(get_db)) -> List[LayerCoverage]:
    """Metric 3 — Rule implementation coverage by layer.

    Shows implemented vs pending rules for each detection layer so engineering
    and product can see where the biggest detection gaps are.
    """
    result = await db.execute(
        select(
            DetectorRuleConfig.layer,
            DetectorRuleConfig.layer_order,
            func.count(DetectorRuleConfig.rule_code).label("total_rules"),
            func.sum(
                sa_case((DetectorRuleConfig.has_implementation == True, 1), else_=0)
            ).label("implemented"),
        )
        .where(DetectorRuleConfig.layer.is_not(None))
        .group_by(DetectorRuleConfig.layer, DetectorRuleConfig.layer_order)
        .order_by(DetectorRuleConfig.layer_order)
    )
    out = []
    for row in result.all():
        total = row.total_rules or 0
        impl = int(row.implemented or 0)
        out.append(LayerCoverage(
            layer=row.layer,
            layer_order=row.layer_order or 0,
            total_rules=total,
            implemented=impl,
            pending=total - impl,
            coverage_pct=round(impl / total * 100, 1) if total else 0.0,
        ))
    return out
