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


class DxCoverageRate(BaseModel):
    total_lines: int
    covered_lines: int        # lines whose CPT has ≥1 row in cpt_dx_coverage
    coverage_rate: float      # covered_lines / total_lines, 0–1
    uncatalogued_cpts: List[str]  # CPTs with no coverage rules (the gap to fill)


class DetectorAcceptanceRate(BaseModel):
    detector_code: str
    total: int
    accepted: int
    rejected: int
    needs_review: int
    adjusted: int
    acceptance_rate: float    # accepted / total
    override_rate: float      # rejected / total


class LayerCoverage(BaseModel):
    layer: str
    layer_order: int
    total_rules: int
    implemented: int
    pending: int
    coverage_pct: float       # implemented / total_rules, 0–100
