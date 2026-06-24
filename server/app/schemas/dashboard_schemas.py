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


class PersonalStats(BaseModel):
    cases_closed: int
    dollars_recovered: float
    current_workload_count: int
    avg_handle_time_days: Optional[float] = None


class TrendComparison(BaseModel):
    current: Union[int, float]
    previous: Union[int, float]
    percent_change: float


class TrendsData(BaseModel):
    cases_closed_vs_previous: TrendComparison
    dollars_recovered_vs_previous: TrendComparison
    handle_time_vs_previous: TrendComparison


class TeamComparison(BaseModel):
    your_cases_closed: int
    team_avg_cases_closed: float
    your_dollars_recovered: float
    team_avg_dollars_recovered: float
    your_handle_time: float
    team_avg_handle_time: float


class UserRef(BaseModel):
    id: str
    full_name: str


class MemberRef(BaseModel):
    name: Optional[str] = None


class ProviderRef(BaseModel):
    name: Optional[str] = None


class ClaimRef(BaseModel):
    member: Optional[MemberRef] = None
    rendering_provider: Optional[ProviderRef] = None


class HighValueCase(BaseModel):
    case_id: str
    case_number: str
    priority_score: float
    amount_at_risk: Optional[float] = None
    status: str
    assignee: Optional[UserRef] = None
    claim: Optional[ClaimRef] = None


class DailyBriefing(BaseModel):
    personal_stats: PersonalStats
    trends: TrendsData
    team_comparison: TeamComparison
    high_value_cases: List[HighValueCase]
