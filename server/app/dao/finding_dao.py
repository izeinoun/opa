from typing import List, Optional
from datetime import datetime
import json
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base_dao import BaseDAO
from ..models.workflow import Finding, CaseFinding


def _severity_band(confidence_score: float) -> str:
    """3-band severity mapping. >= 0.85 HIGH, 0.65-0.84 MEDIUM, < 0.65 LOW."""
    if confidence_score >= 0.85:
        return "HIGH"
    if confidence_score >= 0.65:
        return "MEDIUM"
    return "LOW"


class FindingDAO(BaseDAO[Finding]):
    model = Finding

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_claim(self, claim_id: str) -> List[Finding]:
        stmt = select(Finding).where(Finding.claim_id == claim_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_case(self, case_id: str) -> None:
        """Remove case_finding links, their orphaned findings, and any
        dispositions for those findings before re-running detectors.

        Dispositions must be cleared too: a stale ``needs_review`` disposition
        left behind by a prior run keeps ``case_has_blocking_findings`` True even
        though its finding no longer exists, permanently blocking the case from
        advancing with no card in the UI to act on.
        """
        from sqlalchemy import delete as sa_delete
        from ..models.workflow import FindingDisposition

        links_res = await self.session.execute(
            select(CaseFinding).where(CaseFinding.case_id == case_id)
        )
        finding_ids = [cf.finding_id for cf in links_res.scalars().all()]

        await self.session.execute(
            sa_delete(CaseFinding).where(CaseFinding.case_id == case_id)
        )
        # Drop dispositions scoped to this case (covers any whose finding is
        # already gone), plus any keyed to the findings we're about to delete.
        await self.session.execute(
            sa_delete(FindingDisposition).where(FindingDisposition.case_id == case_id)
        )
        if finding_ids:
            await self.session.execute(
                sa_delete(FindingDisposition).where(
                    FindingDisposition.finding_id.in_(finding_ids)
                )
            )
            await self.session.execute(
                sa_delete(Finding).where(Finding.finding_id.in_(finding_ids))
            )
        await self.session.flush()

    async def create_finding(
        self,
        claim_id: str,
        case_id: str,
        detector_code: str,
        finding_type: str,
        description: str,
        overpayment_amount: float,
        confidence_score: float,
        evidence_json: dict,
        fwa_indicator: bool = False,
        fwa_rule_code: Optional[str] = None,
    ) -> Finding:
        finding = Finding(
            finding_id=str(uuid4()),
            claim_id=claim_id,
            claim_line_id=None,
            detector_id=detector_code,
            detector_version="1.0.0",
            fired_at=datetime.utcnow().isoformat(),
            overpayment_amount=overpayment_amount,
            severity=_severity_band(confidence_score),
            confidence=confidence_score,
            rationale=description,
            evidence=json.dumps(evidence_json),
            rule_version="1.0.0",
            status="open",
            fwa_indicator=fwa_indicator,
            fwa_rule_code=fwa_rule_code,
        )
        self.session.add(finding)
        await self.session.flush()

        link = CaseFinding(case_id=case_id, finding_id=finding.finding_id)
        self.session.add(link)
        await self.session.flush()

        return finding
