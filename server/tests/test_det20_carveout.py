"""DET-20 carve-out violation detector — regression + behavior tests.

Guards against the bugs that made DET-20 dead/incorrect (all swallowed by the
orchestrator's try/except, so they produced wrong findings silently):
  1. AttributeError — class constant defined as `BEHAVIORAL_HEALTH_CPts` but
     referenced as `self.BEHAVIORAL_HEALTH_CPTS`.
  2. TypeError — DetectorResult built with non-existent fields (`detector_id`,
     `title`, `rationale`, `confidence`, `claim_line_id`) instead of the real
     dataclass fields (`detector_code`/`description`/`confidence_score`/`evidence`).
  3. Wrong data source — carve-out metadata was read from `claim.case_json`, but
     `case_json` is a field on OpaCase, not Claim. It now reads from the claim
     envelope `claim.raw_claim_json`.
  4. DME false positive — the vendor check defaulted to "violation" when no
     vendor metadata was present; it now returns no finding when the vendor is
     unknown.

Carve-out signals ride along in `raw_claim_json`:
{"provider_network": bool, "behavioral_health_preauth": bool,
 "bh_visit_count": int, "dme_vendor": str}.
"""
import asyncio
import json
import types

from app.detectors.det_20_carveout_violation import CarveoutViolationDetector


def _line(cpt, paid=100.0, line_id="L1"):
    return types.SimpleNamespace(cpt_code=cpt, paid_amount=paid, claim_line_id=line_id)


def _claim(lob="HMO", lines=None, raw_claim_json=None):
    c = types.SimpleNamespace(lob=lob, claim_lines=lines or [])
    if raw_claim_json is not None:
        c.raw_claim_json = raw_claim_json
    return c


def _run(claim):
    return asyncio.run(CarveoutViolationDetector().run(claim, None))


def test_det20_dme_unapproved_vendor_fires():
    raw = json.dumps({"dme_vendor": "MedSupply Plus (non-approved)"})
    results = _run(_claim(lines=[_line("E1390", paid=250.0, line_id="L-DME")], raw_claim_json=raw))
    assert len(results) == 1
    r = results[0]
    assert r.detector_code == "DET-20"
    assert r.finding_type == "CARVEOUT_UNAPPROVED_VENDOR"
    assert r.confidence_score == 0.90
    assert r.overpayment_amount == 250.0
    # Line attribution for amount-at-risk dedup.
    assert r.evidence["line_id"] == "L-DME"
    assert r.evidence["cpt_code"] == "E1390"


def test_det20_dme_approved_vendor_no_finding():
    raw = json.dumps({"dme_vendor": "Optimal Medical Supply Company"})
    results = _run(_claim(lines=[_line("E1390")], raw_claim_json=raw))
    assert results == []


def test_det20_dme_no_vendor_metadata_no_finding():
    # Regression for the false positive: unknown vendor → no violation asserted.
    results = _run(_claim(lines=[_line("E1390")]))  # no raw_claim_json
    assert results == []


def test_det20_behavioral_health_out_of_network_fires():
    raw = json.dumps({"provider_network": False})
    results = _run(_claim(lines=[_line("90834", paid=180.0, line_id="L-BH")], raw_claim_json=raw))
    assert len(results) == 1
    assert results[0].finding_type == "CARVEOUT_NO_NETWORK"
    assert results[0].confidence_score == 0.95
    assert results[0].evidence["line_id"] == "L-BH"


def test_det20_preauth_required_over_visit_limit():
    raw = json.dumps(
        {"provider_network": True, "behavioral_health_preauth": False, "bh_visit_count": 25}
    )
    results = _run(_claim(lines=[_line("90834", paid=180.0, line_id="L-BH2")], raw_claim_json=raw))
    assert len(results) == 1
    assert results[0].finding_type == "CARVEOUT_PREAUTH_REQUIRED"
    # 50% partial overpayment of the line's paid amount.
    assert results[0].overpayment_amount == 90.0


def test_det20_non_hmo_skipped():
    results = _run(_claim(lob="PPO", lines=[_line("E1390")]))
    assert results == []


def test_det20_runs_clean_without_metadata():
    # Regression: previously raised AttributeError + TypeError. Must not raise,
    # and with no carve-out metadata a BH CPT yields no finding.
    results = _run(_claim(lines=[_line("90834", paid=100.0)]))
    assert isinstance(results, list)
    assert results == []
