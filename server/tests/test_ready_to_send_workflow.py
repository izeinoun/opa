"""Regression tests for the split recoup workflow (decision vs. delivery).

Old flow: "Recoup it" jumped the case straight to notice_sent even though
nothing had been delivered, so the provider-portal upload warned about a
duplicate notice on the very first send.

New flow:
  1. Decision  — transition(to_status="notice_sent") from a pre-delivery state
     LANDS on ready_for_notice ("Ready to Send"): letter staged, final check.
  2. Delivery  — secure email or provider-portal upload advances
     ready_for_notice → notice_sent.
  3. An explicit ready_for_notice → notice_sent transition (manual mark-sent /
     composer) still passes through unchanged.
Supervisor approval of a stashed recoup decision also lands on
ready_for_notice.
"""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.database import Base
from app.models.workflow import OpaCase
from app.schemas.case_schemas import CaseTransition
from app.services.case_service import CaseService

CASE_SEQ = 7001


def _case(status: str, amount: float = 500.0) -> OpaCase:
    return OpaCase(
        case_id="case-rts-1",
        case_number="OPA-TEST-7001",
        case_sequence=CASE_SEQ,
        claim_id="claim-1",
        primary_detector_id="DET-01",
        lob="commercial",
        provider_org_id="prov-1",
        member_id="mem-1",
        status=status,
        priority="high",
        priority_score=80.0,
        total_overpayment_amount=amount,  # < $2K → no supervisor gate
        recommended_recovery_method="recoupment",
        identified_date="2026-01-01",
        deadline_date="2026-03-01",
        lookback_window_start="2025-01-01",
        evidence_bundle="{}",
        case_json="{}",
    )


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_recoup_decision_lands_on_ready_for_notice(session):
    session.add(_case("in_review"))
    await session.flush()

    svc = CaseService(session)
    await svc.transition(
        CASE_SEQ, CaseTransition(to_status="notice_sent", reason="recoup"), None
    )

    case = await session.get(OpaCase, "case-rts-1")
    assert case.status == "ready_for_notice"


@pytest.mark.asyncio
async def test_manual_send_from_ready_passes_through(session):
    session.add(_case("ready_for_notice"))
    await session.flush()

    svc = CaseService(session)
    await svc.transition(
        CASE_SEQ, CaseTransition(to_status="notice_sent", reason="sent"), None
    )

    case = await session.get(OpaCase, "case-rts-1")
    assert case.status == "notice_sent"


@pytest.mark.asyncio
async def test_not_for_recoup_still_closes(session):
    session.add(_case("in_review"))
    await session.flush()

    svc = CaseService(session)
    await svc.transition(
        CASE_SEQ,
        CaseTransition(to_status="closed_not_for_recoup", reason="no overpayment"),
        None,
    )

    case = await session.get(OpaCase, "case-rts-1")
    assert case.status == "closed_not_for_recoup"


@pytest.mark.asyncio
async def test_supervisor_approval_lands_on_ready_for_notice(session):
    import json

    case = _case("pending_supervisor", amount=5000.0)
    case.decision_metadata = json.dumps(
        {"disposition": "notice_sent", "reason": "recoup", "submitted_by_user_id": None}
    )
    session.add(case)
    await session.flush()

    svc = CaseService(session)
    await svc.approve_pending(CASE_SEQ, supervisor_id=None, reason="approved")

    refreshed = await session.get(OpaCase, "case-rts-1")
    assert refreshed.status == "ready_for_notice"


@pytest.mark.asyncio
async def test_high_dollar_decision_still_routes_to_supervisor(session):
    session.add(_case("in_review", amount=5000.0))
    await session.flush()

    svc = CaseService(session)
    await svc.transition(
        CASE_SEQ, CaseTransition(to_status="notice_sent", reason="recoup"), None
    )

    case = await session.get(OpaCase, "case-rts-1")
    assert case.status == "pending_supervisor"
    assert case.decision_metadata is not None
