from pydantic import BaseModel
from typing import Optional, Union, List


class KPICard(BaseModel):
    label: str
    value: Union[float, int, str]
    delta: Optional[float] = None
    unit: Optional[str] = None


class AgingBucket(BaseModel):
    label: str  # "0-15d", "16-30d", etc.
    count: int
    amount: float


class WorkloadItem(BaseModel):
    assignee: str
    open_cases: int
    high_priority: int
    total_at_risk: float


class RecoveryPoint(BaseModel):
    month: str
    recovered: float
    written_off: float
    pending: float


class DetectorStat(BaseModel):
    detector_code: str
    total_findings: int
    confirmed_overpayment: float
    avg_confidence: float


class StatusCount(BaseModel):
    status: str
    count: int


class DashboardResponse(BaseModel):
    kpis: List[KPICard]
    aging: List[AgingBucket]
    workload: List[WorkloadItem]
    recovery: List[RecoveryPoint]
    detectors: List[DetectorStat]
    status_distribution: List[StatusCount]
