"""Regression tests for the in_review -> forward transition gate and the
orphaned-disposition bug.

Bug: detector re-runs delete a case's findings + case_finding links but used to
leave the `finding_dispositions` rows behind. A stale `needs_review` orphan
(its finding gone, no card in the UI) kept `case_has_blocking_findings` True,
permanently blocking the case with nothing for the analyst to accept/reject.

Two guards prevent this:
  1. FindingDao.delete_by_case also deletes the dispositions.
  2. case_has_blocking_findings only counts dispositions for findings still
     linked to the case (joins case_findings), so any orphan is ignored.
"""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.database import Base
from app.models.workflow import Finding, CaseFinding, FindingDisposition
from app.dao.finding_dao import FindingDAO
from app.services.disposition_service import case_has_blocking_findings

CASE_ID = "case-1"


def _finding(fid: str) -> Finding:
    return Finding(
        finding_id=fid,
        claim_id="claim-1",
        detector_version="v1",
        fired_at="2026-01-01",
        severity="MEDIUM",
        rationale="test",
        evidence="{}",
    )


def _disposition(fid: str, status: str) -> FindingDisposition:
    return FindingDisposition(
        disposition_id=f"disp-{fid}",
        finding_id=fid,
        case_id=CASE_ID,
        status=status,
        original_amount=100.0,
    )


@pytest_asyncio.fixture
async def session():
    # In-memory SQLite; FK enforcement is off by default so we can insert
    # dispositions/links without building the full reference graph.
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_orphan_disposition_does_not_block(session):
    # Live finding linked to the case, plus an orphan disposition whose finding
    # is NOT linked (simulates a leftover from a prior detector run).
    session.add(_finding("F1"))
    session.add(CaseFinding(case_id=CASE_ID, finding_id="F1"))
    session.add(_disposition("F1", "needs_review"))
    session.add(_disposition("ORPHAN", "needs_review"))  # no CaseFinding link
    await session.flush()

    # Live needs_review finding blocks.
    assert await case_has_blocking_findings(session, CASE_ID) is True

    # Resolve the live finding; the orphan must NOT keep the case blocked.
    live = await session.get(FindingDisposition, "disp-F1")
    live.status = "accepted"
    await session.flush()
    assert await case_has_blocking_findings(session, CASE_ID) is False


@pytest.mark.asyncio
async def test_delete_by_case_clears_dispositions(session):
    session.add(_finding("F1"))
    session.add(CaseFinding(case_id=CASE_ID, finding_id="F1"))
    session.add(_disposition("F1", "needs_review"))
    # A disposition already orphaned (finding gone) but still scoped to the case.
    session.add(_disposition("GHOST", "needs_review"))
    await session.flush()

    await FindingDAO(session).delete_by_case(CASE_ID)

    remaining = (await session.execute(
        FindingDisposition.__table__.select().where(
            FindingDisposition.case_id == CASE_ID
        )
    )).all()
    assert remaining == []
    assert await case_has_blocking_findings(session, CASE_ID) is False
