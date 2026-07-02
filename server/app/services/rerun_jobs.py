"""In-memory progress registry for background detector re-runs.

The rerun-detectors endpoint returns immediately (202) and does the slow work
(ClearLink round-trips + LLM calls) in a background task. The frontend polls a
status endpoint to drive a progress modal. Because the app runs as a single
uvicorn worker, a plain in-process dict is sufficient shared state — no external
store needed. State is intentionally ephemeral: a deploy/restart drops in-flight
jobs, which is fine (the user just re-runs).
"""
from __future__ import annotations

import time
from typing import Optional
from uuid import uuid4

# job_id -> job dict. Insertion-ordered; we prune the oldest past a soft cap so
# a long-lived process can't accumulate jobs without bound.
_JOBS: dict[str, dict] = {}
_MAX_JOBS = 200


def create_job(case_sequence: int) -> dict:
    job_id = uuid4().hex
    job = {
        "job_id": job_id,
        "case_sequence": case_sequence,
        "status": "running",       # running | done | error
        "total": None,             # filled in on first progress tick
        "completed": 0,
        "current": None,           # human label of the detector in flight
        "findings_created": None,
        "error": None,
        "started_at": time.time(),
        "updated_at": time.time(),
    }
    _JOBS[job_id] = job
    if len(_JOBS) > _MAX_JOBS:
        # Drop the oldest entries (dict preserves insertion order).
        for stale in list(_JOBS.keys())[: len(_JOBS) - _MAX_JOBS]:
            _JOBS.pop(stale, None)
    return job


def get_job(job_id: str) -> Optional[dict]:
    return _JOBS.get(job_id)


def update_job(job_id: str, **fields) -> None:
    job = _JOBS.get(job_id)
    if job is None:
        return
    job.update(fields)
    job["updated_at"] = time.time()
