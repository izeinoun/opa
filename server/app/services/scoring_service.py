from datetime import date
from typing import Optional, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..models.claims import ClaimLine, ClaimFinding


class ScoringService:
    """Computes likelihood and priority scores for cases."""

    def compute_likelihood(
        self,
        cpt_risk_score: float,
        provider_risk_tier: int,
        dx_cpt_mismatch_score: float,
        claim_complexity_score: float,
        billing_variance_score: float,
    ) -> float:
        """
        Weighted likelihood score formula:
          cpt_risk_score          × 0.30
          (provider_risk_tier/5)  × 0.25
          dx_cpt_mismatch_score   × 0.20
          claim_complexity_score  × 0.15
          billing_variance_score  × 0.10
        """
        tier_normalized = provider_risk_tier / 5.0
        score = (
            cpt_risk_score * 0.30
            + tier_normalized * 0.25
            + dx_cpt_mismatch_score * 0.20
            + claim_complexity_score * 0.15
            + billing_variance_score * 0.10
        )
        return score

    def compute_priority(
        self,
        amount_at_risk: float,
        likelihood: float,
        deadline: Optional[date],
    ) -> Tuple[float, str]:
        """
        Returns (priority_score, band).
        Band: >=75 -> HIGH, 50-74 -> MEDIUM, <50 -> LOW
        Override: if deadline and days_to_deadline <= 5 -> force HIGH
        """
        today = date.today()
        amount_norm = min(amount_at_risk / 50_000.0, 1.0)

        if deadline is not None:
            days_to_deadline = (deadline - today).days
            urgency = max(0.0, 1.0 - (days_to_deadline / 90.0))
        else:
            days_to_deadline = None
            urgency = 0.5

        score = (amount_norm * 0.40 + likelihood * 0.40 + urgency * 0.20) * 100.0

        # Override for imminent deadlines (0–5 days remaining; excludes already-breached)
        if deadline is not None and days_to_deadline is not None and 0 <= days_to_deadline <= 5:
            return score, "HIGH"

        if score >= 75:
            band = "HIGH"
        elif score >= 50:
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
