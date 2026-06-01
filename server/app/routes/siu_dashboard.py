"""SIU dashboard endpoint — team performance, case metrics, dollars
saved, volumes, FWA-rule breakdown.

Mounted at /api/siu/dashboard. Read-only; gated by require_app('siu').

The dashboard is intentionally a single endpoint that returns the full
rollup in one round-trip so the UI doesn't have to choreograph N parallel
queries. SIU's data volume is bounded (investigations are rare and
high-touch) so this stays cheap.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import require_app
from ..models.claims import Claim
from ..models.workflow import (
    Finding,
    InvestigationCase,
    OpaCase,
    OpaUser,
    SIUInvestigation,
)


router = APIRouter(
    prefix="/api/siu/dashboard",
    tags=["siu-dashboard"],
    dependencies=[Depends(require_app("siu"))],
)


# ── response shapes ────────────────────────────────────────────────────────

class KPICard(BaseModel):
    label: str
    value: float
    unit: str                 # "investigations" | "$" | "days" | "%"
    sub: Optional[str] = None


class StatusCount(BaseModel):
    status: str
    count: int


class TypeCount(BaseModel):
    investigation_type: str
    count: int


class PipelineCount(BaseModel):
    pipeline_mode: str        # 'post_pay' | 'pre_pay' | 'mixed' | 'unknown'
    count: int


class WeekVolume(BaseModel):
    week_start: str           # YYYY-MM-DD (Monday)
    opened: int
    closed: int


class OutcomeCount(BaseModel):
    outcome: str
    count: int


class InvestigatorWorkload(BaseModel):
    investigator_id: str
    investigator_name: str
    open_count: int
    closed_30d_count: int
    fraud_confirmed_amount: float


class FWARuleStat(BaseModel):
    fwa_rule_code: str
    finding_count: int
    distinct_investigations: int
    total_at_risk: float


class SIUDashboard(BaseModel):
    kpis: list[KPICard]
    status_distribution: list[StatusCount]
    type_distribution: list[TypeCount]
    pipeline_distribution: list[PipelineCount]
    weekly_volumes: list[WeekVolume]
    outcomes_breakdown: list[OutcomeCount]
    investigator_workload: list[InvestigatorWorkload]
    fwa_rule_breakdown: list[FWARuleStat]


# ── helpers ────────────────────────────────────────────────────────────────


def _safe_date(iso: Optional[str]) -> Optional[date]:
    if not iso:
        return None
    try:
        return date.fromisoformat(iso[:10])
    except Exception:
        return None


async def _cases_for_invs(
    db: AsyncSession,
) -> dict[str, list[str]]:
    """Map investigation_id → list[case_id]. One query for all links."""
    rows = (await db.execute(select(InvestigationCase))).scalars().all()
    out: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        out[r.investigation_id].append(r.case_id)
    return out


async def _build_dashboard(db: AsyncSession) -> SIUDashboard:
    today = date.today()
    month_start = today.replace(day=1)
    ytd_start = today.replace(month=1, day=1)
    monday_today = today - timedelta(days=today.weekday())
    eight_weeks_back = monday_today - timedelta(weeks=7)

    # All investigations in scope. SIU data is small; pull and aggregate
    # in Python — keeps the rule logic readable.
    invs = (await db.execute(select(SIUInvestigation))).scalars().all()
    inv_by_id = {i.investigation_id: i for i in invs}

    inv_to_cases = await _cases_for_invs(db)

    # Index linked OpaCases (for at-risk dollars + claim_id link)
    all_case_ids: set[str] = set()
    for case_list in inv_to_cases.values():
        all_case_ids.update(case_list)
    case_by_id: dict[str, OpaCase] = {}
    case_pipeline: dict[str, str] = {}
    if all_case_ids:
        case_rows = (await db.execute(
            select(OpaCase).where(OpaCase.case_id.in_(all_case_ids))
        )).scalars().all()
        case_by_id = {c.case_id: c for c in case_rows}
        # Resolve pipeline_mode per case via claim
        claim_ids = {c.claim_id for c in case_rows if c.claim_id}
        if claim_ids:
            claim_rows = (await db.execute(
                select(Claim.claim_id, Claim.pipeline_mode).where(
                    Claim.claim_id.in_(claim_ids)
                )
            )).all()
            claim_pipeline = {cid: pm or "post_pay" for cid, pm in claim_rows}
            for c in case_rows:
                case_pipeline[c.case_id] = claim_pipeline.get(c.claim_id, "post_pay")

    def inv_pipeline(inv_id: str) -> str:
        case_ids = inv_to_cases.get(inv_id, [])
        modes = {case_pipeline.get(cid) for cid in case_ids if case_pipeline.get(cid)}
        if not modes:
            return "unknown"
        if len(modes) > 1:
            return "mixed"
        return next(iter(modes))

    def inv_total_at_risk(inv_id: str) -> float:
        total = 0.0
        for cid in inv_to_cases.get(inv_id, []):
            c = case_by_id.get(cid)
            if c and c.total_overpayment_amount:
                total += float(c.total_overpayment_amount)
        return round(total, 2)

    # ── KPIs ────────────────────────────────────────────────────────────
    open_invs = [i for i in invs if i.status != "CLOSED"]
    pending_le = [i for i in open_invs if i.status == "PENDING_LAW_ENFORCEMENT"]
    closed_invs = [i for i in invs if i.status == "CLOSED"]

    fraud_confirmed_mtd = 0.0
    fraud_confirmed_ytd = 0.0
    days_to_close: list[int] = []
    for inv in closed_invs:
        closed = _safe_date(inv.closed_at)
        if not closed:
            continue
        amount = inv_total_at_risk(inv.investigation_id)
        if inv.outcome == "FRAUD_CONFIRMED":
            if closed >= ytd_start:
                fraud_confirmed_ytd += amount
            if closed >= month_start:
                fraud_confirmed_mtd += amount
        opened = _safe_date(inv.escalated_at)
        if opened:
            days_to_close.append((closed - opened).days)
    avg_days_to_close = round(sum(days_to_close) / len(days_to_close), 1) if days_to_close else 0.0

    kpis = [
        KPICard(label="Open Investigations", value=len(open_invs),
                unit="investigations"),
        KPICard(label="Pending Law Enforcement", value=len(pending_le),
                unit="investigations",
                sub="Awaiting agency response"),
        KPICard(label="Dollars Confirmed (MTD)", value=round(fraud_confirmed_mtd, 2),
                unit="$",
                sub=f"YTD: ${fraud_confirmed_ytd:,.0f}"),
        KPICard(label="Avg Days to Close", value=avg_days_to_close,
                unit="days",
                sub=f"{len(closed_invs)} closed lifetime"),
    ]

    # ── Status / type / pipeline distributions ──────────────────────────
    status_counts: dict[str, int] = defaultdict(int)
    type_counts:   dict[str, int] = defaultdict(int)
    pipeline_counts: dict[str, int] = defaultdict(int)
    for i in invs:
        status_counts[i.status or "UNKNOWN"] += 1
        type_counts[i.investigation_type or "OTHER"] += 1
        pipeline_counts[inv_pipeline(i.investigation_id)] += 1

    # ── Weekly volumes (last 8 weeks, Monday-anchored) ──────────────────
    weeks: dict[str, dict[str, int]] = {
        (eight_weeks_back + timedelta(weeks=i)).isoformat(): {"opened": 0, "closed": 0}
        for i in range(8)
    }
    for i in invs:
        opened = _safe_date(i.escalated_at)
        if opened and opened >= eight_weeks_back:
            wk = (opened - timedelta(days=opened.weekday())).isoformat()
            if wk in weeks:
                weeks[wk]["opened"] += 1
        closed = _safe_date(i.closed_at)
        if closed and closed >= eight_weeks_back:
            wk = (closed - timedelta(days=closed.weekday())).isoformat()
            if wk in weeks:
                weeks[wk]["closed"] += 1
    weekly_volumes = [
        WeekVolume(week_start=k, opened=v["opened"], closed=v["closed"])
        for k, v in sorted(weeks.items())
    ]

    # ── Outcomes breakdown (closed investigations only) ─────────────────
    outcome_counts: dict[str, int] = defaultdict(int)
    for i in closed_invs:
        outcome_counts[i.outcome or "UNKNOWN"] += 1

    # ── Investigator workload ───────────────────────────────────────────
    cutoff_30d = today - timedelta(days=30)
    user_open: dict[str, int] = defaultdict(int)
    user_closed_30d: dict[str, int] = defaultdict(int)
    user_fraud_amount: dict[str, float] = defaultdict(float)
    for inv in invs:
        uid = inv.investigator_assigned_user_id
        if not uid:
            continue
        if inv.status != "CLOSED":
            user_open[uid] += 1
        else:
            closed = _safe_date(inv.closed_at)
            if closed and closed >= cutoff_30d:
                user_closed_30d[uid] += 1
            if inv.outcome == "FRAUD_CONFIRMED":
                user_fraud_amount[uid] += inv_total_at_risk(inv.investigation_id)

    user_ids = set(user_open) | set(user_closed_30d) | set(user_fraud_amount)
    user_lookup: dict[str, str] = {}
    if user_ids:
        urs = (await db.execute(
            select(OpaUser.user_id, OpaUser.full_name).where(OpaUser.user_id.in_(user_ids))
        )).all()
        user_lookup = {uid: name for uid, name in urs}

    investigator_workload = [
        InvestigatorWorkload(
            investigator_id=uid,
            investigator_name=user_lookup.get(uid, "Unknown"),
            open_count=user_open.get(uid, 0),
            closed_30d_count=user_closed_30d.get(uid, 0),
            fraud_confirmed_amount=round(user_fraud_amount.get(uid, 0.0), 2),
        )
        for uid in sorted(user_ids,
                          key=lambda u: -(user_open.get(u, 0) + user_closed_30d.get(u, 0)))
    ]

    # ── FWA rule breakdown ──────────────────────────────────────────────
    # All findings linked to claims that are part of SIU investigations,
    # grouped by FWA rule. Distinct-investigation count handles cases
    # where the same FWA rule fires on multiple claims in one
    # investigation.
    fwa_stats: dict[str, dict[str, Any]] = {}
    if all_case_ids:
        case_claim_ids = [c.claim_id for c in case_by_id.values() if c.claim_id]
        # Reverse map claim_id → investigation_ids (one claim → one case →
        # potentially many investigations)
        case_to_invs: dict[str, list[str]] = defaultdict(list)
        for inv_id, case_ids in inv_to_cases.items():
            for cid in case_ids:
                case_to_invs[cid].append(inv_id)
        claim_to_invs: dict[str, set[str]] = defaultdict(set)
        for cid, c in case_by_id.items():
            if c.claim_id:
                for iid in case_to_invs.get(cid, []):
                    claim_to_invs[c.claim_id].add(iid)

        if case_claim_ids:
            f_rows = (await db.execute(
                select(Finding).where(
                    Finding.claim_id.in_(case_claim_ids),
                    Finding.fwa_indicator == True,  # noqa: E712
                )
            )).scalars().all()
            for f in f_rows:
                rule = f.fwa_rule_code or "UNKNOWN"
                slot = fwa_stats.setdefault(rule, {
                    "finding_count": 0,
                    "investigations": set(),
                    "total_at_risk": 0.0,
                })
                slot["finding_count"] += 1
                slot["investigations"].update(claim_to_invs.get(f.claim_id, set()))
                if f.overpayment_amount:
                    slot["total_at_risk"] += float(f.overpayment_amount)

    fwa_rule_breakdown = [
        FWARuleStat(
            fwa_rule_code=rule,
            finding_count=v["finding_count"],
            distinct_investigations=len(v["investigations"]),
            total_at_risk=round(v["total_at_risk"], 2),
        )
        for rule, v in sorted(fwa_stats.items())
    ]

    return SIUDashboard(
        kpis=kpis,
        status_distribution=[
            StatusCount(status=k, count=v) for k, v in sorted(
                status_counts.items(), key=lambda x: -x[1],
            )
        ],
        type_distribution=[
            TypeCount(investigation_type=k, count=v) for k, v in sorted(
                type_counts.items(), key=lambda x: -x[1],
            )
        ],
        pipeline_distribution=[
            PipelineCount(pipeline_mode=k, count=v) for k, v in sorted(
                pipeline_counts.items(), key=lambda x: -x[1],
            )
        ],
        weekly_volumes=weekly_volumes,
        outcomes_breakdown=[
            OutcomeCount(outcome=k, count=v) for k, v in sorted(
                outcome_counts.items(), key=lambda x: -x[1],
            )
        ],
        investigator_workload=investigator_workload,
        fwa_rule_breakdown=fwa_rule_breakdown,
    )


@router.get("", response_model=SIUDashboard)
async def get_dashboard(db: AsyncSession = Depends(get_db)) -> SIUDashboard:
    return await _build_dashboard(db)
