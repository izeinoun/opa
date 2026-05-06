from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List


@dataclass
class DetectorResult:
    detector_code: str
    finding_type: str
    description: str
    overpayment_amount: float
    confidence_score: float
    evidence: dict


class BaseDetector(ABC):
    code: str
    name: str

    @abstractmethod
    async def run(self, claim, db_session) -> List[DetectorResult]:
        ...
