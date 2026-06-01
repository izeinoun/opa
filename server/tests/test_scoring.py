import types

from app.services.scoring_service import ScoringService
from datetime import date, timedelta


def _line(cpt_code, units, modifier=None):
    return types.SimpleNamespace(cpt_code=cpt_code, units=units, modifier=modifier)


def _finding(detector_code, confidence_score):
    return types.SimpleNamespace(
        detector_code=detector_code, confidence_score=confidence_score
    )


# NOTE: ScoringService has no `compute_likelihood`. The README's 5-factor
# weighted formula is intentionally not wired into the live path (see
# CLAUDE.md); the real likelihood comes from case_service._compute_posterior.
# These tests cover the scoring methods that actually exist.


def test_claim_complexity_formula():
    svc = ScoringService()
    lines = [_line("99214", 3, "25"), _line("93000", 2, None)]
    # line_score 0.2*0.35 + cpt_score 0.4*0.30 + unit_score 0.25*0.20 + mod 0.5*0.15
    expected = 0.2 * 0.35 + 0.4 * 0.30 + 0.25 * 0.20 + 0.5 * 0.15
    assert abs(svc.compute_claim_complexity(lines) - expected) < 1e-9


def test_claim_complexity_empty_is_zero():
    assert ScoringService().compute_claim_complexity([]) == 0.0


def test_dx_cpt_mismatch_uses_relevant_findings():
    svc = ScoringService()
    lines = [_line("99214", 1), _line("93000", 1)]
    findings = [
        _finding("DET-06", 0.8),
        _finding("DET-09", 0.6),
        _finding("DET-01", 0.9),  # irrelevant — ignored
    ]
    # avg_confidence 0.7 * 0.70 + count_factor 1.0 * 0.30
    expected = 0.7 * 0.70 + 1.0 * 0.30
    assert abs(svc.compute_dx_cpt_mismatch(lines, findings) - expected) < 1e-9


def test_dx_cpt_mismatch_no_relevant_findings_is_zero():
    svc = ScoringService()
    lines = [_line("99214", 1)]
    assert svc.compute_dx_cpt_mismatch(lines, []) == 0.0
    assert svc.compute_dx_cpt_mismatch(lines, [_finding("DET-01", 0.9)]) == 0.0


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
