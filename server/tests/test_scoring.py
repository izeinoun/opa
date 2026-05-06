import pytest
from app.services.scoring_service import ScoringService
from datetime import date, timedelta


def test_likelihood_formula():
    svc = ScoringService()
    score = svc.compute_likelihood(
        cpt_risk_score=0.8,
        provider_risk_tier=4,
        dx_cpt_mismatch_score=0.5,
        claim_complexity_score=0.3,
        billing_variance_score=0.6,
    )
    expected = 0.8 * 0.30 + (4 / 5) * 0.25 + 0.5 * 0.20 + 0.3 * 0.15 + 0.6 * 0.10
    assert abs(score - expected) < 1e-9


def test_priority_high_override():
    svc = ScoringService()
    deadline = date.today() + timedelta(days=3)
    score, band = svc.compute_priority(10_000, 0.3, deadline)
    assert band == "HIGH"  # forced by <= 5 days to deadline


def test_priority_bands():
    svc = ScoringService()
    _, band = svc.compute_priority(50_000, 0.9, None)
    assert band == "HIGH"
    _, band = svc.compute_priority(1_000, 0.1, None)
    assert band == "LOW"
