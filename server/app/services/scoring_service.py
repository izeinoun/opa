from datetime import date
from typing import Optional, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..models.claims import ClaimLine, ClaimFinding


class ScoringService:
    """Computes likelihood and priority scores for cases."""

    def compute_priority(
        self,
        amount_at_risk: float,
        posterior: float,
        deadline: Optional[date],
        max_amount: float = 5_000.0,
        amount_weight: float = 0.60,
        likelihood_weight: float = 0.35,
        urgency_weight: float = 0.05,
        urgency_window_days: int = 30,
        high_threshold: float = 75.0,
        medium_threshold: float = 50.0,
    ) -> Tuple[float, str]:
        """
        Returns (priority_score, band).
        priority = (w_amt×amount_norm + w_lik×posterior + w_urg×urgency) × 100
        amount_norm = amount / max_amount (capped at 1)
        urgency: 0 at urgency_window_days+ out, linear to 1 at deadline/overdue
        Band: >=high_threshold → HIGH, >=medium_threshold → MEDIUM, else LOW
        """
        today = date.today()
        amount_norm = min(amount_at_risk / max(max_amount, 1.0), 1.0)

        if deadline is not None:
            days_to_deadline = (deadline - today).days
            urgency = max(0.0, min(1.0, 1.0 - days_to_deadline / max(urgency_window_days, 1)))
        else:
            urgency = 0.5

        score = (
            amount_norm * amount_weight
            + posterior * likelihood_weight
            + urgency * urgency_weight
        ) * 100.0

        if score >= high_threshold:
            band = "HIGH"
        elif score >= medium_threshold:
            band = "MEDIUM"
        else:
            band = "LOW"

        return score, band

    def compute_claim_complexity(self, lines: List) -> float:
        """
        Compute complexity based on:
        - Line count
        - Unique CPT count
        - Total units
        - Lines with modifiers
        Returns a score in [0.0, 1.0].
        """
        if not lines:
            return 0.0

        line_count = len(lines)
        unique_cpts = len({line.cpt_code for line in lines})
        total_units = sum(line.units for line in lines)
        lines_with_modifiers = sum(1 for line in lines if line.modifier)

        # Normalize each component to 0-1 range
        line_score = min(line_count / 10.0, 1.0)
        cpt_score = min(unique_cpts / 5.0, 1.0)
        unit_score = min(total_units / 20.0, 1.0)
        modifier_score = lines_with_modifiers / max(line_count, 1)

        complexity = (
            line_score * 0.35
            + cpt_score * 0.30
            + unit_score * 0.20
            + modifier_score * 0.15
        )
        return min(complexity, 1.0)

    def compute_dx_cpt_mismatch(self, lines: List, findings: List) -> float:
        """
        Estimate DX-CPT mismatch score based on DET-06/DET-09 findings.
        Returns a score in [0.0, 1.0].
        """
        if not findings:
            return 0.0

        relevant_codes = {"DET-06", "DET-09"}
        relevant_findings = [f for f in findings if f.detector_code in relevant_codes]

        if not relevant_findings:
            return 0.0

        # Average confidence of relevant findings, clipped to [0,1]
        avg_confidence = sum(f.confidence_score for f in relevant_findings) / len(relevant_findings)
        count_factor = min(len(relevant_findings) / max(len(lines), 1), 1.0)

        return min(avg_confidence * 0.70 + count_factor * 0.30, 1.0)
