"""ClaimGuard analyst dashboard.

Mirrors the shape of PayGuard's /api/dashboard where the metric makes sense
for pre-pay (KPIs, status distribution, aging, analyst workload) and adds
pipeline-unique aggregates:

  - decisions_trend     weekly approved vs denied counts/$ for the last 6 weeks
  - ai_coverage         AI-analysis coverage + finding-volume rollup
  - specialty_mix       claim counts by specialty (top 10)
  - top_providers       top submitters by claim count (top 8)

All queries hard-filter Claim.pipeline_mode = 'pre_pay'.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Optional, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, and_, case as sa_case
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user, require_app
from ..models.claims import Claim
from ..models.workflow import Finding, OpaCase, OpaUser


router = APIRouter(
    prefix="/api/prepay/dashboard",
    tags=["prepay-dashboard"],
    dependencies=[Depends(require_app("claimguard"))],
)

# All queries scoped to pre-pay.
_PRE_PAY = Claim.pipeline_mode == "pre_pay"

# Claim statuses considered "still in the analyst's pipeline".
_OPEN_CLAIM_STATUSES = ("pending", "review", "escalated", "pend", "correction")


# ── response shapes ────────────────────────────────────────────────────────

class KPICard(BaseModel):
    label: str
    value: float
    unit: str  # "claims" | "$" | "%"
    sub: Optional[str] = None


class StatusCount(BaseModel):
    status: str
    count: int


class AgingBucket(BaseModel):
    label: str
    count: int
    amount: float


class DecisionWeek(BaseModel):
    week_start: str           # YYYY-MM-DD (Monday)
    approved_count: int
    denied_count: int
    approved_amount: float
    denied_amount: float


class AICoverage(BaseModel):
    claims_total: int
    claims_with_ai_summary: int
    claims_with_findings: int
    findings_total: int
    findings_critical: int
    avg_findings_per_analyzed_claim: float
    coverage_pct: float       # 0..100, claims_with_ai_summary / claims_total


class SpecialtyCount(BaseModel):
    specialty: str
    count: int
    amount: float


class ProviderCount(BaseModel):
    provider_name: str
    count: int
    amount: float


class WorkloadItem(BaseModel):
    assignee: str
    open_claims: int
    in_review: int
    total_under_review_amount: float


class PrepayDashboard(BaseModel):
    kpis: List[KPICard]
    status_distribution: List[StatusCount]
    aging: List[AgingBucket]
    decisions_trend: List[DecisionWeek]
    ai_coverage: AICoverage
    specialty_mix: List[SpecialtyCount]
    top_providers: List[ProviderCount]
    workload: List[WorkloadItem]


# ── helpers ────────────────────────────────────────────────────────────────

def _aging_label(submitted_iso: Optional[str]) -> str:
    try:
        d = date.fromisoformat((submitted_iso or "")[:10])
    except Exception:
        return "30+d"
    days = (date.today() - d).days
    if days <= 1:
        return "0-1d"
    if days <= 3:
        return "2-3d"
    if days <= 7:
        return "4-7d"
    if days <= 14:
        return "8-14d"
    if days <= 30:
        return "15-30d"
    return "30+d"


_AGING_ORDER = ["0-1d", "2-3d", "4-7d", "8-14d", "15-30d", "30+d"]


# ── compute functions ──────────────────────────────────────────────────────

async def _compute_kpis(db: AsyncSession) -> List[KPICard]:
    # Open (still in reviewer pipeline)
    open_count = (await db.execute(
        select(func.count(Claim.claim_id))
        .where(_PRE_PAY, Claim.claim_status.in_(_OPEN_CLAIM_STATUSES))
    )).scalar_one() or 0

    # Total billed for open claims
    total_at_risk = float((await db.execute(
        select(func.coalesce(func.sum(Claim.total_billed), 0.0))
        .where(_PRE_PAY, Claim.claim_status.in_(_OPEN_CLAIM_STATUSES))
    )).scalar_one() or 0.0)

    # High-priority count via the linked case
    high_priority = (await db.execute(
        select(func.count(OpaCase.case_id))
        .join(Claim, OpaCase.claim_id == Claim.claim_id)
        .where(_PRE_PAY, OpaCase.priority == "HIGH", OpaCase.is_active == True)  # noqa: E712
    )).scalar_one() or 0

    # Prevented overpayment MTD = $ sum of denied claims this month
    today = date.today()
    month_start = today.replace(day=1).isoformat()
    prevented_mtd = float((await db.execute(
        select(func.coalesce(func.sum(Claim.total_billed), 0.0))
        .where(_PRE_PAY, Claim.claim_status == "denied",
               Claim.updated_at >= month_start)
    )).scalar_one() or 0.0)

    return [
        KPICard(label="Claims Under Review", value=open_count, unit="claims"),
        KPICard(label="High Priority", value=high_priority, unit="claims"),
        KPICard(label="$ Billed Under Review", value=round(total_at_risk, 2), unit="$"),
        KPICard(label="Prevented Overpayment (MTD)", value=round(prevented_mtd, 2),
                unit="$", sub="Denied claims this month"),
    ]


async def _compute_status_distribution(db: AsyncSession) -> List[StatusCount]:
    rows = (await db.execute(
        select(Claim.claim_status, func.count(Claim.claim_id).label("count"))
        .where(_PRE_PAY)
        .group_by(Claim.claim_status)
    )).all()
    return [StatusCount(status=r.claim_status or "unknown", count=r.count) for r in rows]


async def _compute_aging(db: AsyncSession) -> List[AgingBucket]:
    # Aging is meaningful only for open (under-review) claims
    rows = (await db.execute(
        select(Claim.submission_date, Claim.total_billed)
        .where(_PRE_PAY, Claim.claim_status.in_(_OPEN_CLAIM_STATUSES))
    )).all()
    buckets = {k: {"count": 0, "amount": 0.0} for k in _AGING_ORDER}
    for submission_date, billed in rows:
        label = _aging_label(submission_date)
        buckets[label]["count"] += 1
        buckets[label]["amount"] += float(billed or 0.0)
    return [AgingBucket(label=k, count=v["count"], amount=v["amount"]) for k, v in buckets.items()]


async def _compute_decisions_trend(db: AsyncSession) -> List[DecisionWeek]:
    today = date.today()
    # Monday of the week 5 weeks ago through this week → 6 buckets
    start_monday = (today - timedelta(days=today.weekday())) - timedelta(weeks=5)
    rows = (await db.execute(
        select(Claim.claim_status, Claim.updated_at, Claim.total_billed)
        .where(_PRE_PAY, Claim.claim_status.in_(("approved", "denied")),
               Claim.updated_at >= start_monday.isoformat())
    )).all()

    buckets = {(start_monday + timedelta(weeks=i)).isoformat():
               {"approved_count": 0, "denied_count": 0,
                "approved_amount": 0.0, "denied_amount": 0.0}
               for i in range(6)}

    for status, updated_at, billed in rows:
        try:
            d = date.fromisoformat((updated_at or "")[:10])
        except Exception:
            continue
        wk = (d - timedelta(days=d.weekday())).isoformat()
        if wk not in buckets:
            continue
        if status == "approved":
            buckets[wk]["approved_count"] += 1
            buckets[wk]["approved_amount"] += float(billed or 0.0)
        elif status == "denied":
            buckets[wk]["denied_count"] += 1
            buckets[wk]["denied_amount"] += float(billed or 0.0)

    return [
        DecisionWeek(week_start=k, **v)  # type: ignore[arg-type]
        for k, v in sorted(buckets.items())
    ]


async def _compute_ai_coverage(db: AsyncSession) -> AICoverage:
    claims_total = (await db.execute(
        select(func.count(Claim.claim_id)).where(_PRE_PAY)
    )).scalar_one() or 0

    claims_with_summary = (await db.execute(
        select(func.count(Claim.claim_id))
        .where(_PRE_PAY, Claim.claim_summary.is_not(None), Claim.claim_summary != "")
    )).scalar_one() or 0

    # AI findings — Finding rows whose claim is pre-pay
    findings_total = (await db.execute(
        select(func.count(Finding.finding_id))
        .join(Claim, Finding.claim_id == Claim.claim_id)
        .where(_PRE_PAY)
    )).scalar_one() or 0

    findings_critical = (await db.execute(
        select(func.count(Finding.finding_id))
        .join(Claim, Finding.claim_id == Claim.claim_id)
        .where(_PRE_PAY, Finding.severity == "critical")
    )).scalar_one() or 0

    claims_with_findings = (await db.execute(
        select(func.count(func.distinct(Finding.claim_id)))
        .join(Claim, Finding.claim_id == Claim.claim_id)
        .where(_PRE_PAY)
    )).scalar_one() or 0

    avg_findings = round(findings_total / claims_with_findings, 2) if claims_with_findings else 0.0
    coverage = round(100.0 * claims_with_summary / claims_total, 1) if claims_total else 0.0

    return AICoverage(
        claims_total=int(claims_total),
        claims_with_ai_summary=int(claims_with_summary),
        claims_with_findings=int(claims_with_findings),
        findings_total=int(findings_total),
        findings_critical=int(findings_critical),
        avg_findings_per_analyzed_claim=avg_findings,
        coverage_pct=coverage,
    )


async def _compute_specialty_mix(db: AsyncSession) -> List[SpecialtyCount]:
    rows = (await db.execute(
        select(
            func.coalesce(Claim.specialty, "Unspecified").label("specialty"),
            func.count(Claim.claim_id).label("count"),
            func.coalesce(func.sum(Claim.total_billed), 0.0).label("amount"),
        )
        .where(_PRE_PAY)
        .group_by(Claim.specialty)
        .order_by(func.count(Claim.claim_id).desc())
        .limit(10)
    )).all()
    return [SpecialtyCount(specialty=r.specialty, count=r.count, amount=float(r.amount or 0))
            for r in rows]


async def _compute_top_providers(db: AsyncSession) -> List[ProviderCount]:
    # Display name via the case's denormalized provider_org join.
    from ..models.reference import ProviderOrg

    rows = (await db.execute(
        select(
            func.coalesce(ProviderOrg.name, "Unknown").label("provider_name"),
            func.count(Claim.claim_id).label("count"),
            func.coalesce(func.sum(Claim.total_billed), 0.0).label("amount"),
        )
        .join(ProviderOrg, Claim.provider_org_id == ProviderOrg.provider_org_id, isouter=True)
        .where(_PRE_PAY)
        .group_by(ProviderOrg.name)
        .order_by(func.count(Claim.claim_id).desc())
        .limit(8)
    )).all()
    return [ProviderCount(provider_name=r.provider_name, count=r.count, amount=float(r.amount or 0))
            for r in rows]


async def _compute_workload(db: AsyncSession) -> List[WorkloadItem]:
    rows = (await db.execute(
        select(
            OpaUser.full_name,
            func.count(Claim.claim_id).label("open_claims"),
            func.sum(sa_case((Claim.claim_status == "review", 1), else_=0)).label("in_review"),
            func.coalesce(func.sum(Claim.total_billed), 0.0).label("total_amount"),
        )
        .join(OpaCase, OpaCase.assigned_analyst_id == OpaUser.user_id)
        .join(Claim, OpaCase.claim_id == Claim.claim_id)
        .where(_PRE_PAY, Claim.claim_status.in_(_OPEN_CLAIM_STATUSES))
        .group_by(OpaUser.full_name)
        .order_by(func.count(Claim.claim_id).desc())
    )).all()
    return [
        WorkloadItem(
            assignee=r.full_name,
            open_claims=int(r.open_claims or 0),
            in_review=int(r.in_review or 0),
            total_under_review_amount=float(r.total_amount or 0),
        )
        for r in rows
    ]


# ── routes ─────────────────────────────────────────────────────────────────

@router.get("", response_model=PrepayDashboard)
async def get_dashboard(db: AsyncSession = Depends(get_db)) -> PrepayDashboard:
    return PrepayDashboard(
        kpis=await _compute_kpis(db),
        status_distribution=await _compute_status_distribution(db),
        aging=await _compute_aging(db),
        decisions_trend=await _compute_decisions_trend(db),
        ai_coverage=await _compute_ai_coverage(db),
        specialty_mix=await _compute_specialty_mix(db),
        top_providers=await _compute_top_providers(db),
        workload=await _compute_workload(db),
    )


# Per-analyst variant — drops top_providers/specialty (team-level) and scopes
# the other queries to claims whose linked case is assigned to current_user.
class MyPrepayDashboard(BaseModel):
    kpis: List[KPICard]
    status_distribution: List[StatusCount]
    aging: List[AgingBucket]
    decisions_trend: List[DecisionWeek]


@router.get("/me", response_model=MyPrepayDashboard)
async def get_my_dashboard(
    period: Literal["week", "month", "quarter"] = Query("month"),
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> MyPrepayDashboard:
    """Per-user view: same shape as team dashboard's first four sections,
    but only for claims whose linked case is assigned to current_user."""
    uid = current_user.user_id

    # Open count for this user
    open_count = (await db.execute(
        select(func.count(Claim.claim_id))
        .join(OpaCase, OpaCase.claim_id == Claim.claim_id)
        .where(_PRE_PAY,
               Claim.claim_status.in_(_OPEN_CLAIM_STATUSES),
               OpaCase.assigned_analyst_id == uid)
    )).scalar_one() or 0

    today = date.today()
    if period == "week":
        start = today - timedelta(days=7)
    elif period == "quarter":
        start = today - timedelta(days=90)
    else:
        start = today - timedelta(days=30)

    # Decisions this user made in the period
    approved_ct = (await db.execute(
        select(func.count(Claim.claim_id))
        .join(OpaCase, OpaCase.claim_id == Claim.claim_id)
        .where(_PRE_PAY, Claim.claim_status == "approved",
               OpaCase.assigned_analyst_id == uid,
               Claim.updated_at >= start.isoformat())
    )).scalar_one() or 0

    denied_ct = (await db.execute(
        select(func.count(Claim.claim_id))
        .join(OpaCase, OpaCase.claim_id == Claim.claim_id)
        .where(_PRE_PAY, Claim.claim_status == "denied",
               OpaCase.assigned_analyst_id == uid,
               Claim.updated_at >= start.isoformat())
    )).scalar_one() or 0

    denied_amt = float((await db.execute(
        select(func.coalesce(func.sum(Claim.total_billed), 0.0))
        .join(OpaCase, OpaCase.claim_id == Claim.claim_id)
        .where(_PRE_PAY, Claim.claim_status == "denied",
               OpaCase.assigned_analyst_id == uid,
               Claim.updated_at >= start.isoformat())
    )).scalar_one() or 0.0)

    kpis = [
        KPICard(label="My Open Claims", value=int(open_count), unit="claims"),
        KPICard(label="My Approvals", value=int(approved_ct), unit="claims",
                sub=f"Last {period}"),
        KPICard(label="My Denials", value=int(denied_ct), unit="claims",
                sub=f"Last {period}"),
        KPICard(label="$ I Prevented", value=round(denied_amt, 2), unit="$",
                sub=f"Last {period}"),
    ]

    # Status distribution for this user's claims
    sd_rows = (await db.execute(
        select(Claim.claim_status, func.count(Claim.claim_id).label("count"))
        .join(OpaCase, OpaCase.claim_id == Claim.claim_id)
        .where(_PRE_PAY, OpaCase.assigned_analyst_id == uid)
        .group_by(Claim.claim_status)
    )).all()
    status_dist = [StatusCount(status=r.claim_status or "unknown", count=r.count) for r in sd_rows]

    # Aging on this user's open claims
    aging_rows = (await db.execute(
        select(Claim.submission_date, Claim.total_billed)
        .join(OpaCase, OpaCase.claim_id == Claim.claim_id)
        .where(_PRE_PAY, Claim.claim_status.in_(_OPEN_CLAIM_STATUSES),
               OpaCase.assigned_analyst_id == uid)
    )).all()
    aging_buckets = {k: {"count": 0, "amount": 0.0} for k in _AGING_ORDER}
    for sd, billed in aging_rows:
        label = _aging_label(sd)
        aging_buckets[label]["count"] += 1
        aging_buckets[label]["amount"] += float(billed or 0)
    aging = [AgingBucket(label=k, count=v["count"], amount=v["amount"])
             for k, v in aging_buckets.items()]

    # Decisions trend for this user (last 6 weeks regardless of `period`,
    # to keep the chart sparkline-like even on short periods)
    start_monday = (today - timedelta(days=today.weekday())) - timedelta(weeks=5)
    dt_rows = (await db.execute(
        select(Claim.claim_status, Claim.updated_at, Claim.total_billed)
        .join(OpaCase, OpaCase.claim_id == Claim.claim_id)
        .where(_PRE_PAY,
               Claim.claim_status.in_(("approved", "denied")),
               OpaCase.assigned_analyst_id == uid,
               Claim.updated_at >= start_monday.isoformat())
    )).all()
    dt_buckets = {(start_monday + timedelta(weeks=i)).isoformat():
                  {"approved_count": 0, "denied_count": 0,
                   "approved_amount": 0.0, "denied_amount": 0.0}
                  for i in range(6)}
    for status, ua, billed in dt_rows:
        try:
            d = date.fromisoformat((ua or "")[:10])
        except Exception:
            continue
        wk = (d - timedelta(days=d.weekday())).isoformat()
        if wk not in dt_buckets:
            continue
        key_ct = "approved_count" if status == "approved" else "denied_count"
        key_amt = "approved_amount" if status == "approved" else "denied_amount"
        dt_buckets[wk][key_ct] += 1
        dt_buckets[wk][key_amt] += float(billed or 0)
    decisions = [DecisionWeek(week_start=k, **v)  # type: ignore[arg-type]
                 for k, v in sorted(dt_buckets.items())]

    return MyPrepayDashboard(
        kpis=kpis,
        status_distribution=status_dist,
        aging=aging,
        decisions_trend=decisions,
    )
