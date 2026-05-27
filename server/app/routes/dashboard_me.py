"""Per-user analyst performance dashboard endpoint."""
from datetime import date, timedelta
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.workflow import OpaCase, OpaUser, AuditLog, RecoupmentAction


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


_CLOSED_STATUSES = {
    "closed_recovered", "closed_written_off",
    "closed_overturned", "closed_no_overpayment",
    "closed_unrecoverable",
}


class WeekBucket(BaseModel):
    week_start: str  # YYYY-MM-DD
    count: int


class StatusBucket(BaseModel):
    status: str
    count: int


class DispositionBucket(BaseModel):
    disposition: str
    count: int


class MyDashboard(BaseModel):
    period: Literal["week", "month", "quarter"]
    period_start: str
    period_end: str
    cases_closed: int
    dollars_recovered: float
    dollars_written_off: float
    avg_handle_time_days: Optional[float] = None
    disposition_breakdown: List[DispositionBucket]
    pipeline_snapshot: List[StatusBucket]
    cases_closed_by_week: List[WeekBucket]
    pipeline_total_active: int


def _window(period: str) -> tuple[date, date]:
    today = date.today()
    if period == "week":
        return today - timedelta(days=7), today
    if period == "quarter":
        return today - timedelta(days=90), today
    # default: month
    return today - timedelta(days=30), today


async def _compute_dashboard(
    db: AsyncSession,
    period: str,
    *,
    user_id_filter: Optional[str],  # None = team-wide (no analyst filter)
) -> MyDashboard:
    start, end = _window(period)

    # For closure date, walk the audit log: most recent STATUS_TRANSITION /
    # SUPERVISOR_APPROVED where to_state is a closed status, for cases this
    # analyst owns. The audit log is the only reliable source — updated_at
    # can change for unrelated reasons after closure.
    closure_rows = (await db.execute(
        select(
            AuditLog.case_id,
            AuditLog.to_state,
            AuditLog.created_at,
        )
        .where(AuditLog.to_state.in_(_CLOSED_STATUSES))
        .where(AuditLog.action.in_(("STATUS_TRANSITION", "SUPERVISOR_APPROVED")))
        .order_by(AuditLog.created_at.desc())
    )).all()

    # Keep most recent closure per case_id
    latest_closure_by_case: dict = {}
    for r in closure_rows:
        if r.case_id not in latest_closure_by_case:
            latest_closure_by_case[r.case_id] = (r.to_state, r.created_at)

    # Pull closed cases (scoped to user_id_filter when set, else team-wide)
    closed_stmt = select(OpaCase).where(OpaCase.is_active == False)  # noqa: E712
    if user_id_filter:
        closed_stmt = closed_stmt.where(OpaCase.assigned_analyst_id == user_id_filter)
    closed_cases = (await db.execute(closed_stmt)).scalars().all()

    in_window_cases = []
    disposition_counts: dict = {}
    handle_times: list = []
    week_buckets: dict = {}
    dollars_recovered = 0.0
    dollars_written_off = 0.0

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
        if closed_date < start or closed_date > end:
            continue
        in_window_cases.append(c)
        disposition_counts[to_state] = disposition_counts.get(to_state, 0) + 1
        if to_state == "closed_recovered":
            dollars_recovered += c.total_overpayment_amount or 0.0
        elif to_state == "closed_written_off":
            dollars_written_off += c.total_overpayment_amount or 0.0

        # Handle time: identified_date → closed_date in calendar days
        try:
            opened = date.fromisoformat(c.identified_date)
            handle_times.append((closed_date - opened).days)
        except Exception:
            pass

        # Week bucket (Monday-anchored)
        wk_start = closed_date - timedelta(days=closed_date.weekday())
        week_buckets[wk_start.isoformat()] = week_buckets.get(wk_start.isoformat(), 0) + 1

    # Use actual recoupments (P4-2) for "dollars_recovered" if any exist — more
    # accurate than the case total since partial recoveries are possible.
    user_case_ids = [c.case_id for c in closed_cases]
    recoup_rows = (await db.execute(
        select(RecoupmentAction.requested_amount, RecoupmentAction.confirmed_at)
        .where(RecoupmentAction.case_id.in_(user_case_ids))
    )).all() if user_case_ids else []
    actual_recovered = 0.0
    for amt, conf_at in recoup_rows:
        if not conf_at:
            continue
        try:
            d = date.fromisoformat((conf_at or "")[:10])
        except Exception:
            continue
        if start <= d <= end:
            actual_recovered += float(amt or 0)
    if actual_recovered > 0:
        dollars_recovered = actual_recovered

    # Pipeline snapshot (current state, NOT period-bound)
    pipeline_stmt = (
        select(OpaCase.status, func.count(OpaCase.case_id))
        .where(OpaCase.is_active == True)  # noqa: E712
        .group_by(OpaCase.status)
    )
    if user_id_filter:
        pipeline_stmt = pipeline_stmt.where(OpaCase.assigned_analyst_id == user_id_filter)
    pipeline_rows = (await db.execute(pipeline_stmt)).all()
    pipeline = [StatusBucket(status=s, count=n) for s, n in pipeline_rows]
    pipeline_total = sum(b.count for b in pipeline)

    # Build week buckets covering the whole window even if zero
    week_arr: List[WeekBucket] = []
    cursor = start - timedelta(days=start.weekday())
    while cursor <= end:
        key = cursor.isoformat()
        week_arr.append(WeekBucket(week_start=key, count=week_buckets.get(key, 0)))
        cursor += timedelta(days=7)

    avg_handle = round(sum(handle_times) / len(handle_times), 1) if handle_times else None

    return MyDashboard(
        period=period,
        period_start=start.isoformat(),
        period_end=end.isoformat(),
        cases_closed=len(in_window_cases),
        dollars_recovered=round(dollars_recovered, 2),
        dollars_written_off=round(dollars_written_off, 2),
        avg_handle_time_days=avg_handle,
        disposition_breakdown=[
            DispositionBucket(disposition=k, count=v)
            for k, v in sorted(disposition_counts.items(), key=lambda x: -x[1])
        ],
        pipeline_snapshot=pipeline,
        cases_closed_by_week=week_arr,
        pipeline_total_active=pipeline_total,
    )


@router.get("/me", response_model=MyDashboard)
async def my_dashboard(
    period: Literal["week", "month", "quarter"] = Query("month"),
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> MyDashboard:
    return await _compute_dashboard(db, period, user_id_filter=current_user.user_id)


@router.get("/team", response_model=MyDashboard)
async def team_dashboard(
    period: Literal["week", "month", "quarter"] = Query("month"),
    analyst_id: Optional[str] = Query(None, description="Scope to a single analyst; None = team aggregate"),
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> MyDashboard:
    """Supervisor/admin view. Returns the same shape as /me, aggregated across
    the team (or scoped to a specific analyst via ?analyst_id=)."""
    if current_user.role not in ("supervisor", "admin"):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Supervisor role required")
    return await _compute_dashboard(db, period, user_id_filter=analyst_id)
