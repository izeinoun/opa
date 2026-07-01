from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DetectorResult:
    detector_code: str
    finding_type: str
    description: str
    overpayment_amount: float
    confidence_score: float
    evidence: dict
    # FWA marker — when a detector also represents an FWA rule, it declares
    # which FWA-XX rule fired here so the Finding row picks up the flag.
    # Cleanest way to express "this DCE finding is also an FWA signal"
    # without splitting findings into two tables.
    fwa_indicator: bool = False
    fwa_rule_code: Optional[str] = None
    # Optional explicit severity override. Normally severity is derived from
    # confidence_score (>=0.85 HIGH / >=0.65 MEDIUM / else LOW). A detector sets
    # this when confidence and severity must diverge — e.g. a high-confidence
    # informational warning that carries no financial impact and should read LOW.
    severity: Optional[str] = None


class BaseDetector(ABC):
    code: str
    name: str
    # FWA mapping for detectors whose entire output category is an FWA
    # signal (FWA-01 provider exclusion, FWA-05 unbundling, FWA-06 duplicate
    # billing). Subclasses set this; the orchestrator stamps every result.
    fwa_rule_code: Optional[str] = None

    @abstractmethod
    async def run(self, claim, db_session) -> List[DetectorResult]:
        ...

    async def resolve_member_number(self, member_id, db_session) -> Optional[str]:
        """Translate OPA's internal member_id (UUID PK) → member_number business key.

        Connected systems (ClearLink, etc.) resolve members by member_number, not
        OPA's internal UUID. Detectors that reach out to those systems must pass the
        member_number. Returns None when the member can't be resolved.
        """
        if not member_id:
            return None
        from sqlalchemy import select
        from ..models.reference import Member
        return (await db_session.execute(
            select(Member.member_number).where(Member.member_id == member_id)
        )).scalar_one_or_none()
