from typing import List, Literal, Optional
from datetime import datetime, timedelta, date
from fastapi import APIRouter, Depends, Query
from ..middleware.auth import require_app, get_current_user
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case as sa_case, and_

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
    DailyBriefing,
    PersonalStats,
    TrendsData,
    TrendComparison,
    TeamComparison,
    HighValueCase,
    UserRef,
    MemberRef,
    ProviderRef,
    ClaimRef,
)
from ..models.workflow import OpaCase, OpaUser, Finding, LikelihoodScore, FindingDisposition, DetectorRuleConfig, AuditLog
from ..models.claims import Claim, ClaimLine
from ..models.reference import CptDxCoverage, Member, ProviderOrg

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


# ─── Daily Briefing Endpoint ────────────────────────────────────────────────

_CLOSED_STATUSES = {
    "closed_recovered", "closed_written_off",
    "closed_overturned", "closed_no_overpayment",
    "closed_unrecoverable", "closed_not_for_recoup",
}


def _get_period_window(period: Literal["day", "week"]) -> tuple[date, date, date, date]:
    """Return (current_start, current_end, previous_start, previous_end)."""
    today = date.today()
    if period == "week":
        # Current week: Monday of this week to today
        current_start = today - timedelta(days=today.weekday())
        current_end = today
        # Previous week: Monday of last week to Sunday
        prev_week_start = current_start - timedelta(days=7)
        prev_week_end = prev_week_start + timedelta(days=6)
        return current_start, current_end, prev_week_start, prev_week_end
    else:
        # Current day: today
        # Previous day: yesterday
        return today, today, today - timedelta(days=1), today - timedelta(days=1)


async def _get_personal_stats(
    db: AsyncSession,
    analyst_id: str,
    period: Literal["day", "week"],
) -> PersonalStats:
    """Get personal stats for analyst in the given period."""
    current_start, current_end, _, _ = _get_period_window(period)

    # Get closed cases via audit log
    closure_rows = (await db.execute(
        select(AuditLog.case_id, AuditLog.to_state, AuditLog.created_at)
        .where(AuditLog.to_state.in_(_CLOSED_STATUSES))
        .where(AuditLog.action.in_(("STATUS_TRANSITION", "SUPERVISOR_APPROVED")))
        .order_by(AuditLog.created_at.desc())
    )).all()

    latest_closure_by_case: dict = {}
    for r in closure_rows:
        if r.case_id not in latest_closure_by_case:
            latest_closure_by_case[r.case_id] = (r.to_state, r.created_at)

    # Pull closed cases for this analyst
    closed_stmt = (
        select(OpaCase)
        .join(Claim, OpaCase.claim_id == Claim.claim_id)
        .where(OpaCase.is_active == False, _POST_PAY)
        .where(OpaCase.assigned_analyst_id == analyst_id)
    )
    closed_cases = (await db.execute(closed_stmt)).scalars().all()

    cases_closed = 0
    dollars_recovered = 0.0
    handle_times = []

    for c in closed_cases:
        closure = latest_closure_by_case.get(c.case_id)
        if not closure:
            continue
        to_state, closed_at = closure
        closed_date_str = (closed_at or "")[:10]
        try:
            closed_date = date.fromisoformat(closed_date_str)
        except Exception:
            continue
        if closed_date < current_start or closed_date > current_end:
            continue
        cases_closed += 1
        if to_state == "closed_recovered":
            dollars_recovered += c.total_overpayment_amount or 0.0
        try:
            opened = date.fromisoformat(c.identified_date)
            handle_times.append((closed_date - opened).days)
        except Exception:
            pass

    # Current workload: active cases assigned to analyst
    workload = (await db.execute(
        _case_join(select(func.count(OpaCase.case_id)))
        .where(OpaCase.is_active == True, OpaCase.assigned_analyst_id == analyst_id, _POST_PAY)
    )).scalar_one() or 0

    avg_handle = round(sum(handle_times) / len(handle_times), 1) if handle_times else None

    return PersonalStats(
        cases_closed=cases_closed,
        dollars_recovered=round(dollars_recovered, 2),
        current_workload_count=workload,
        avg_handle_time_days=avg_handle,
    )


async def _get_trends(
    db: AsyncSession,
    analyst_id: str,
    period: Literal["day", "week"],
) -> TrendsData:
    """Calculate trends vs previous period."""
    current_start, current_end, prev_start, prev_end = _get_period_window(period)

    current = await _get_personal_stats(db, analyst_id, period)

    # Get previous period stats (manually calculate since period is different)
    closure_rows = (await db.execute(
        select(AuditLog.case_id, AuditLog.to_state, AuditLog.created_at)
        .where(AuditLog.to_state.in_(_CLOSED_STATUSES))
        .where(AuditLog.action.in_(("STATUS_TRANSITION", "SUPERVISOR_APPROVED")))
        .order_by(AuditLog.created_at.desc())
    )).all()

    latest_closure_by_case: dict = {}
    for r in closure_rows:
        if r.case_id not in latest_closure_by_case:
            latest_closure_by_case[r.case_id] = (r.to_state, r.created_at)

    closed_stmt = (
        select(OpaCase)
        .join(Claim, OpaCase.claim_id == Claim.claim_id)
        .where(OpaCase.is_active == False, _POST_PAY)
        .where(OpaCase.assigned_analyst_id == analyst_id)
    )
    closed_cases = (await db.execute(closed_stmt)).scalars().all()

    prev_cases_closed = 0
    prev_dollars_recovered = 0.0
    prev_handle_times = []

    for c in closed_cases:
        closure = latest_closure_by_case.get(c.case_id)
        if not closure:
            continue
        to_state, closed_at = closure
        closed_date_str = (closed_at or "")[:10]
        try:
            closed_date = date.fromisoformat(closed_date_str)
        except Exception:
            continue
        if closed_date < prev_start or closed_date > prev_end:
            continue
        prev_cases_closed += 1
        if to_state == "closed_recovered":
            prev_dollars_recovered += c.total_overpayment_amount or 0.0
        try:
            opened = date.fromisoformat(c.identified_date)
            prev_handle_times.append((closed_date - opened).days)
        except Exception:
            pass

    prev_handle = sum(prev_handle_times) / len(prev_handle_times) if prev_handle_times else 1.0

    def calc_percent_change(curr, prev):
        if prev == 0:
            return 0.0 if curr == 0 else 100.0
        return round(((curr - prev) / prev) * 100, 1)

    return TrendsData(
        cases_closed_vs_previous=TrendComparison(
            current=current.cases_closed,
            previous=prev_cases_closed,
            percent_change=calc_percent_change(current.cases_closed, prev_cases_closed),
        ),
        dollars_recovered_vs_previous=TrendComparison(
            current=current.dollars_recovered,
            previous=round(prev_dollars_recovered, 2),
            percent_change=calc_percent_change(current.dollars_recovered, prev_dollars_recovered),
        ),
        handle_time_vs_previous=TrendComparison(
            current=current.avg_handle_time_days or 0.0,
            previous=prev_handle,
            percent_change=calc_percent_change(current.avg_handle_time_days or 0.0, prev_handle),
        ),
    )


async def _get_team_comparison(
    db: AsyncSession,
    analyst_id: str,
    period: Literal["day", "week"],
) -> TeamComparison:
    """Compare analyst to team average."""
    analyst_stats = await _get_personal_stats(db, analyst_id, period)

    # Get all analysts and their stats
    analysts = (await db.execute(
        select(OpaUser.user_id)
        .where(OpaUser.is_active == True)
    )).scalars().all()

    all_stats = []
    for aid in analysts:
        s = await _get_personal_stats(db, aid, period)
        all_stats.append(s)

    team_avg_cases = sum(s.cases_closed for s in all_stats) / len(all_stats) if all_stats else 0.0
    team_avg_dollars = sum(s.dollars_recovered for s in all_stats) / len(all_stats) if all_stats else 0.0
    team_avg_handle = sum((s.avg_handle_time_days or 0.0) for s in all_stats) / len(all_stats) if all_stats else 0.0

    return TeamComparison(
        your_cases_closed=analyst_stats.cases_closed,
        team_avg_cases_closed=round(team_avg_cases, 1),
        your_dollars_recovered=analyst_stats.dollars_recovered,
        team_avg_dollars_recovered=round(team_avg_dollars, 2),
        your_handle_time=analyst_stats.avg_handle_time_days or 0.0,
        team_avg_handle_time=round(team_avg_handle, 1),
    )


async def _get_high_value_cases(
    db: AsyncSession,
    analyst_id: str,
) -> List[HighValueCase]:
    """Get top 5 non-closed cases assigned to analyst (or unassigned), sorted by priority_score."""
    stmt = (
        select(OpaCase)
        .join(Claim, OpaCase.claim_id == Claim.claim_id)
        .where(OpaCase.is_active == True, _POST_PAY)
        .where(
            (OpaCase.assigned_analyst_id == analyst_id) | (OpaCase.assigned_analyst_id == None)
        )
        .order_by(OpaCase.priority_score.desc())
        .limit(5)
    )
    cases = (await db.execute(stmt)).scalars().all()

    result = []
    for c in cases:
        assignee = None
        if c.assigned_analyst_id:
            user = (await db.execute(
                select(OpaUser).where(OpaUser.user_id == c.assigned_analyst_id)
            )).scalar_one_or_none()
            if user:
                assignee = UserRef(id=user.user_id, full_name=user.full_name or "Unknown")

        claim_ref = None
        if c.claim_id:
            claim = (await db.execute(
                select(Claim).where(Claim.claim_id == c.claim_id)
            )).scalar_one_or_none()
            if claim:
                member_ref = None
                if claim.member_id:
                    member = (await db.execute(
                        select(Member).where(Member.member_id == claim.member_id)
                    )).scalar_one_or_none()
                    if member:
                        member_ref = MemberRef(name=f"{member.first_name} {member.last_name}".strip())

                provider_ref = None
                if claim.provider_org_id:
                    org = (await db.execute(
                        select(ProviderOrg).where(ProviderOrg.provider_org_id == claim.provider_org_id)
                    )).scalar_one_or_none()
                    if org:
                        provider_ref = ProviderRef(name=org.name)

                claim_ref = ClaimRef(member=member_ref, rendering_provider=provider_ref)

        result.append(HighValueCase(
            case_id=c.case_id,
            case_number=c.case_number,
            priority_score=c.priority_score,
            amount_at_risk=c.total_overpayment_amount,
            status=c.status,
            assignee=assignee,
            claim=claim_ref,
        ))

    return result


@router.get("/briefing", response_model=DailyBriefing)
async def daily_briefing(
    period: Literal["day", "week"] = Query("day"),
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> DailyBriefing:
    """Get personalized daily briefing for an analyst.

    Includes personal stats, trends vs previous period, team comparison, and top cases.
    """
    personal_stats = await _get_personal_stats(db, current_user.user_id, period)
    trends = await _get_trends(db, current_user.user_id, period)
    team_comp = await _get_team_comparison(db, current_user.user_id, period)
    high_value = await _get_high_value_cases(db, current_user.user_id)

    return DailyBriefing(
        personal_stats=personal_stats,
        trends=trends,
        team_comparison=team_comp,
        high_value_cases=high_value,
    )
