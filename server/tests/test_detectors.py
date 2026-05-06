import pytest
from app.detectors.base_detector import DetectorResult, BaseDetector
from app.utils.scoring_utils import normalize_tier, amount_norm


def test_normalize_tier():
    assert normalize_tier(1) == 0.0
    assert normalize_tier(5) == 1.0
    assert normalize_tier(3) == 0.5


def test_amount_norm():
    assert amount_norm(0) == 0.0
    assert amount_norm(50_000) == 1.0
    assert amount_norm(100_000) == 1.0  # clamped


def test_detector_result_fields():
    r = DetectorResult(
        detector_code="DET-01",
        finding_type="DUPLICATE_CLAIM",
        description="test",
        overpayment_amount=1000.0,
        confidence_score=0.95,
        evidence={"key": "val"},
    )
    assert r.detector_code == "DET-01"
    assert r.finding_type == "DUPLICATE_CLAIM"
    assert r.overpayment_amount == 1000.0
    assert r.confidence_score == 0.95
    assert r.evidence == {"key": "val"}
