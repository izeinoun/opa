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
