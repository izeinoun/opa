# `server/app/detectors/base_detector.py`

A tiny (33-line) module that defines the **two foundational contracts every detector in the pipeline shares**.

## `DetectorResult` (dataclass)

The standard output shape a detector emits for each finding:

- `detector_code`, `finding_type`, `description`
- `overpayment_amount`, `confidence_score` (confidence is expected on `[0,1]`)
- `evidence` (dict)
- `fwa_indicator` / `fwa_rule_code` — optional Fraud-Waste-Abuse markers, so a single finding can also carry an FWA flag without a separate table. Per-detector code sets these, or the orchestrator stamps them.

## `BaseDetector` (ABC)

The abstract base class all detectors subclass:

- Class attributes `code`, `name`, and an optional `fwa_rule_code` (for detectors whose entire output category is an FWA signal).
- One abstract async method: `run(self, claim, db_session) -> List[DetectorResult]`.

In short: it's the **interface / data-contract layer** for the detector pipeline — no business logic of its own.

## Where it's referenced

**Orchestrator** (the central consumer) — `orchestrator.py:4`: imports both symbols, types its detector registry as `List[BaseDetector]` / `Dict[str, BaseDetector]`, returns `List[DetectorResult]`, and stamps `fwa_rule_code` onto results.

**Concrete detectors** — every detector module subclasses `BaseDetector` and constructs `DetectorResult`s. ~14 files including:

- `det_01_duplicate.py`, `det_16_modifier_integrity.py`, `det_18_medical_necessity.py`
- the `fwa_*` family (`fwa_02_credential_mismatch.py`, `fwa_03_pos_mismatch.py`)
- the `str_*` structural-edit family (`str_003`, `str_010`, `str_013`, `str_014`, …)
- `coverage_gap.py` (uses `DetectorResult` for an informational, confidence-0 result; it's a standalone function, not a `BaseDetector` subclass)

**Downstream of the orchestrator:**

- `services/case_service.py` — consumes `DetectorResult`s to build `Finding` rows and feed the posterior.
- `schemas/case_schemas.py:199` — has its own Pydantic `DetectorResultRead` (a separate API-response model, named similarly but unrelated to this dataclass).

> Note: the CLAUDE.md table lists six "core" detectors (DET-01/02/04/06/08/09), but the directory now holds the additional `det_16`, `det_18`, `fwa_*`, and `str_*` detectors shown above — all built on this same base.
