from typing import List
from datetime import datetime, timedelta, date
from fastapi import APIRouter, Depends
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
)
from ..models.workflow import OpaCase, OpaUser, Finding, LikelihoodScore

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


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
        select(func.count()).select_from(OpaCase).where(OpaCase.is_active == True)
    )).scalar_one() or 0

    total_at_risk = float((await db.execute(
        select(func.coalesce(func.sum(OpaCase.total_overpayment_amount), 0.0))
        .where(OpaCase.is_active == True)
    )).scalar_one() or 0.0)

    total_recovered = float((await db.execute(
        select(func.coalesce(func.sum(OpaCase.total_overpayment_amount), 0.0))
        .where(OpaCase.status == "closed_recovered")
    )).scalar_one() or 0.0)

    high_priority = (await db.execute(
        select(func.count()).select_from(OpaCase).where(
            OpaCase.is_active == True, OpaCase.priority == "HIGH"
        )
    )).scalar_one() or 0

    return [
        KPICard(label="Open Cases",           value=open_count,      unit="cases", delta=None),
        KPICard(label="High Priority",         value=high_priority,   unit="cases", delta=None),
        KPICard(label="Total at Risk",         value=total_at_risk,   unit="$",     delta=None),
        KPICard(label="Total Recovered",       value=total_recovered, unit="$",     delta=None),
    ]


async def _compute_aging(db: AsyncSession) -> List[AgingBucket]:
    result = await db.execute(
        select(OpaCase.identified_date, OpaCase.total_overpayment_amount)
        .where(OpaCase.is_active == True)
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
        .where(OpaCase.is_active == True)
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
            select(func.coalesce(func.sum(OpaCase.total_overpayment_amount), 0.0))
            .where(OpaCase.status == "closed_recovered",
                   OpaCase.identified_date >= ms, OpaCase.identified_date < me)
        )).scalar_one() or 0.0)

        written_off = float((await db.execute(
            select(func.coalesce(func.sum(OpaCase.total_overpayment_amount), 0.0))
            .where(OpaCase.status == "closed_written_off",
                   OpaCase.identified_date >= ms, OpaCase.identified_date < me)
        )).scalar_one() or 0.0)

        pending = float((await db.execute(
            select(func.coalesce(func.sum(OpaCase.total_overpayment_amount), 0.0))
            .where(OpaCase.is_active == True,
                   OpaCase.identified_date >= ms, OpaCase.identified_date < me)
        )).scalar_one() or 0.0)

        points.append(RecoveryPoint(month=label, recovered=recovered,
                                    written_off=written_off, pending=pending))
    return points


async def _compute_detector_stats(db: AsyncSession) -> List[DetectorStat]:
    result = await db.execute(
        select(
            Finding.detector_id,
            func.count(Finding.finding_id).label("total_findings"),
            func.coalesce(func.sum(Finding.overpayment_amount), 0.0).label("confirmed_overpayment"),
            func.avg(Finding.confidence).label("avg_confidence"),
        )
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
        select(OpaCase.status, func.count(OpaCase.case_id).label("count"))
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
