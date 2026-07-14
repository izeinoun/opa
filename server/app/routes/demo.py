"""Demo run — server-sent-events endpoint that drives the locked 10-file 835 set
through the REAL post-pay pipeline in parallel, streaming a progress event for
every stage so the "Claims Control Room" swim-lane UI can animate ten lanes at
once.

Story: we "uploaded 10 claims"; 5 clear end-to-end with no human (accept →
recoupment letter → simulated portal upload → simulated secure email), the other
5 stop at the Decision station for a person. The split is engineered into the
curated files (see docs / seed), not faked here — every event is real pipeline
output. Only the two external deliveries (portal, email) are simulated.

`GET|POST /api/demo/run` → `text/event-stream` of `data: {json}\n\n` frames:
  init   — {stages:[{key,label,emoji}], files:[{file_id,label}]}  (sent once, first)
  stage  — {file_id, stage, status: active|done|review|error, detail}
  result — one per file when it finishes (outcome, case_number, amount, …)
  done   — {auto, review, clean, error, recovered}                 (sent once, last)

The endpoint has no auth dependency on purpose (it's a stage demo); writes are
attributed to `system`. Do NOT expose publicly as-is.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from ..services.demo_orchestrator_service import STAGE_META, process_file, reset_demo

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/demo", tags=["demo"])

# repo_root/tools/sample_x12 — this file is server/app/routes/demo.py
_SAMPLE_DIR = Path(__file__).resolve().parents[3] / "tools" / "sample_x12"

# The locked set (empirically verified 5-auto / 5-review). 03 precedes 04 so the
# duplicate has its predecessor in the DB; 835_10 combo is intentionally dropped.
_ORDER = [
    "835_01_det08_excluded", "835_02_det04_feeschedule", "835_03_det01_dup_a",
    "835_04_det01_dup_b", "835_05_det02_retro", "835_06_det06_ncci",
    "835_07_det06_mue", "835_08_det18_llm_fallback", "835_09_det19_upcoding",
    "835_11_inst_ub04_det09",
]


def _sse(event: dict) -> str:
    return "data: " + json.dumps(event) + "\n\n"


def _load() -> list[tuple[str, str, str]]:
    """(file_id, friendly lane label, raw EDI) for each file in the locked order."""
    out: list[tuple[str, str, str]] = []
    for i, name in enumerate(_ORDER, start=1):
        raw = (_SAMPLE_DIR / f"{name}.x12").read_text()
        out.append((name, f"Claim {i:02d}", raw))
    return out


async def _run(pace: float, stagger: float):
    """Async generator of SSE frames: init → live stage/result events → done."""
    files = _load()

    yield _sse({
        "type": "init",
        "stages": STAGE_META,
        "files": [{"file_id": fid, "label": label} for fid, label, _ in files],
    })

    queue: asyncio.Queue = asyncio.Queue()

    async def emit(file_id: str, stage: str, status: str, detail: str) -> None:
        await queue.put({"type": "stage", "file_id": file_id, "stage": stage,
                         "status": status, "detail": detail})

    async def run_one(index: int, file_id: str, raw: str):
        await asyncio.sleep(index * stagger)  # staggered starts → visibly parallel
        res = await process_file(
            file_id=file_id, filename=f"{file_id}.x12", raw_edi=raw,
            emit=emit, user_id="system", pace=pace,
        )
        await queue.put({
            "type": "result",
            "file_id": res.file_id,
            "outcome": res.outcome,
            "case_number": res.case_number,
            "case_sequence": res.case_sequence,
            "amount": res.amount,
            "evidence": res.evidence,
            "reason": res.reason,
            "findings": res.findings,
            "letter_document_id": res.letter_document_id,
            "error": res.error,
        })
        return res

    async def driver():
        results = await asyncio.gather(
            *(run_one(i, fid, raw) for i, (fid, _, raw) in enumerate(files)),
            return_exceptions=True,
        )
        auto = review = clean = error = 0
        recovered = 0.0
        for r in results:
            if isinstance(r, BaseException) or r is None:
                error += 1
                continue
            if r.outcome == "AUTO_RECOUP":
                auto += 1
                recovered += r.amount or 0.0
            elif r.outcome == "REVIEW":
                review += 1
            elif r.outcome == "CLEAN":
                clean += 1
            else:
                error += 1
        await queue.put({"type": "done", "auto": auto, "review": review,
                         "clean": clean, "error": error, "recovered": recovered})
        await queue.put(None)  # sentinel

    task = asyncio.create_task(driver())
    try:
        while True:
            evt = await queue.get()
            if evt is None:
                break
            yield _sse(evt)
    finally:
        if not task.done():
            task.cancel()
        # surface a driver crash rather than swallowing it
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass


@router.api_route("/run", methods=["GET", "POST"])
async def run_demo(
    pace: float = Query(0.55, ge=0.05, le=3.0, description="Seconds per stage dwell"),
    stagger: float = Query(0.35, ge=0.0, le=2.0, description="Seconds between lane starts"),
) -> StreamingResponse:
    """Stream the full parallel demo run as server-sent events."""
    return StreamingResponse(
        _run(pace, stagger),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.post("/reset")
async def reset_demo_run() -> dict:
    """Delete every case (and its claim / ERA / findings / letter) the demo
    created, so a re-run reproduces the 5-auto / 5-review split from scratch —
    no reseed or backend restart needed. Only demo-stamped rows are removed;
    seeded data is untouched. Like /run, no auth on purpose (stage demo)."""
    result = await reset_demo()
    return {"ok": True, **result}
