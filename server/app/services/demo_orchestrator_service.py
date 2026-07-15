"""Demo orchestrator — drive one uploaded 835 file through the full post-pay
pipeline as a sequence of visible *stages*, emitting a progress event at each so
a live UI can animate a per-file lane.

For a high-confidence, under-gate case the orchestrator runs end-to-end with no
human: accept-for-recoup (which generates the deterministic recoupment letter)
then a *simulated* provider-portal upload + secure-email send. Everything else
stops at the DECISION stage with a plain-language reason for the human.

This reuses the real services (`create_case_from_835`, `CaseService.transition`,
the recoupment letter) — the only simulated parts are the two external
deliveries (portal, email), per the demo's scope.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Awaitable, Callable, Optional

from sqlalchemy import select, text

from ..config import APP_DOMAIN, settings
from ..database import AsyncSessionLocal, Base
from ..models.reference import ProviderDeliveryPlaybook, ProviderOrg
from ..models.workflow import AuditLog, CaseFinding, Finding, OpaCase
from ..schemas.case_schemas import CaseTransition
from .case_creation_service import create_case_from_835
from .case_service import AUTO_RECOUP_CONF, CaseService, _compute_evidence_score
from .delivery_service import DeliveryService

log = logging.getLogger(__name__)

# Ordered stations shown in the UI, with the friendly "5th-grader" labels the
# demo leads with. Single source of truth — the SSE `init` event ships this to
# the frontend so backend and UI can never drift.
STAGE_META = [
    {"key": "getting_file", "label": "Getting the file",   "emoji": "📥"},
    {"key": "reading",      "label": "Reading it",         "emoji": "👀"},
    {"key": "parsing",      "label": "Sorting the pieces", "emoji": "🧩"},
    {"key": "scoring",      "label": "Scoring the provider","emoji": "🧮"},
    {"key": "rules",        "label": "Running the checks", "emoji": "🔍"},
    {"key": "decision",     "label": "Making the call",    "emoji": "⚖️"},
    {"key": "letter",       "label": "Writing the letter", "emoji": "✉️"},
    {"key": "portal",       "label": "Posting to portal",  "emoji": "⬆️"},
    {"key": "email",        "label": "Sending secure link","emoji": "📧"},
]
STAGES = [s["key"] for s in STAGE_META]

# Every case the demo creates is stamped with this audit action so `reset_demo`
# can find and tear down exactly the demo-created rows — nothing seeded — and the
# "Run again" split reproduces from a clean slate. See reset_demo() below.
DEMO_MARKER_ACTION = "DEMO_CREATED"

# Fallback delivery inbox — matches the seeded delivery-playbook email. Used only
# when a case's provider org has no playbook (e.g. an org minted on-the-fly during
# 835 intake for an excluded/unknown provider), so every auto-recouped lane can
# still show a concrete "notice sent to …" address.
_DEFAULT_DELIVERY_EMAIL = "issam@penguinai.co"

# Emit(file_id, stage, status, detail) — status is "active" | "done" | "review" | "error".
Emit = Callable[[str, str, str, str], Awaitable[None]]

# SQLite has no row-level write concurrency and case numbers are minted from
# max(case_sequence)+1, so parallel case creation collides on opa_cases.case_number
# / "database is locked". Serialize just the DB-write moments; the staged pacing
# and event emits stay parallel, so every lane still animates concurrently.
_DB_LOCK = asyncio.Lock()


@dataclass
class FileResult:
    file_id: str
    filename: str
    outcome: str = "pending"          # AUTO_RECOUP | REVIEW | CLEAN | ERROR
    case_number: Optional[str] = None
    case_sequence: Optional[int] = None
    evidence: float = 0.0
    amount: float = 0.0
    reason: str = ""
    findings: list[str] = field(default_factory=list)
    letter_document_id: Optional[str] = None
    # Where the recoupment notice was delivered (from the provider's delivery
    # playbook). Populated only on the AUTO_RECOUP path, after the simulated send.
    delivery_email: Optional[str] = None
    delivery_contact: Optional[str] = None
    delivery_ref: Optional[str] = None
    delivery_sent: bool = False       # True = real EmailJS send; False = simulated
    error: Optional[str] = None


async def _findings_for(db, case_id: str) -> list[Finding]:
    res = await db.execute(
        select(Finding)
        .join(CaseFinding, Finding.finding_id == CaseFinding.finding_id)
        .where(CaseFinding.case_id == case_id)
    )
    return list(res.scalars().all())


def _headline(findings: list[Finding]) -> str:
    """The single detector we lead with in the UI (compliance > highest-conf)."""
    if not findings:
        return "no issue"
    det8 = [f for f in findings if (f.detector_id or "").startswith("DET-08")]
    if det8:
        return "DET-08 excluded provider"
    top = max(findings, key=lambda f: (f.confidence or 0.0))
    return f"{top.detector_id} ({round((top.confidence or 0) * 100)}%)"


async def process_file(
    *,
    file_id: str,
    filename: str,
    raw_edi: str,
    emit: Emit,
    user_id: str = "system",
    pace: float = 0.55,
) -> FileResult:
    """Run one 835 through the staged pipeline, emitting progress as it goes."""
    result = FileResult(file_id=file_id, filename=filename)
    gate = settings.high_dollar_threshold or 2000.0

    async def stage(name: str, detail: str = "", status: str = "done") -> None:
        await emit(file_id, name, status, detail)

    try:
        # 1–2. Intake
        await stage("getting_file", "active", status="active")
        await asyncio.sleep(pace)
        await stage("getting_file", f"received {filename}")
        await stage("reading", "active", status="active")
        await asyncio.sleep(pace)
        await stage("reading", f"read {len(raw_edi):,} bytes of X12")

        # 3. Parse (real) — surface the human-readable shape
        from .edi_parser import parse_835
        await stage("parsing", "active", status="active")
        parsed = parse_835(raw_edi)
        await asyncio.sleep(pace)
        if not parsed.claims:
            await stage("parsing", "no claim segments", status="error")
            result.outcome, result.reason = "ERROR", "No CLP claim in 835"
            return result
        pc = parsed.claims[0]
        lines = len(pc.svc_lines)
        await stage("parsing", f"{pc.patient_first} {pc.patient_last} · NPI {pc.rendering_npi} · {lines} line(s)")

        # 4–5. Score + run detectors (create_case_from_835 does both)
        await stage("scoring", "active", status="active")
        await asyncio.sleep(pace)
        await stage("scoring", "provider risk + likelihood prior")
        await stage("rules", "active", status="active")
        async with _DB_LOCK:
            async with AsyncSessionLocal() as db:
                created = await create_case_from_835(db, raw_edi)
            case = created[0]
            async with AsyncSessionLocal() as db:
                findings = await _findings_for(db, case.case_id)
                row = (await db.execute(select(OpaCase).where(OpaCase.case_id == case.case_id))).scalar_one()
                amount = row.total_overpayment_amount or 0.0
        result.case_number = case.case_number
        result.case_sequence = case.case_sequence
        result.amount = amount
        result.evidence = _compute_evidence_score(findings)
        result.findings = [f"{f.detector_id}:{(f.confidence or 0):.2f}" for f in findings]
        await _mark_demo_case(case.case_id)  # tag for reset_demo() teardown
        await asyncio.sleep(pace)
        await stage("rules", f"{len(findings)} finding(s) · lead: {_headline(findings)}")

        # 6. Decision — the fork
        await stage("decision", "active", status="active")
        await asyncio.sleep(pace)
        conf_pct = round(result.evidence * 100)
        if not findings:
            result.outcome = "CLEAN"
            result.reason = "No issue found — nothing to recoup"
            await stage("decision", f"{conf_pct}% · clean — no action", status="done")
            return result
        if result.evidence >= AUTO_RECOUP_CONF and result.amount < gate:
            result.outcome = "AUTO_RECOUP"
            await stage("decision", f"{conf_pct}% confidence → AUTO-RECOUP", status="done")
        else:
            result.outcome = "REVIEW"
            if result.evidence >= AUTO_RECOUP_CONF:
                result.reason = f"${result.amount:,.0f} over ${gate:,.0f} — needs supervisor sign-off"
            else:
                result.reason = f"{conf_pct}% confidence — needs analyst review"
            await stage("decision", result.reason, status="review")
            return result

        # 7. Accept-for-recoup → generates the recoupment letter (real, deterministic)
        await stage("letter", "active", status="active")
        async with _DB_LOCK:
            async with AsyncSessionLocal() as db:
                svc = CaseService(db)
                await svc.transition(
                    result.case_sequence,
                    CaseTransition(to_status="notice_sent", reason="Auto-recoup: high-confidence, under supervisor gate"),
                    acting_user_id=user_id,
                )
                await db.commit()
                doc = await _latest_letter(db, case.case_id)
                result.letter_document_id = doc
        await asyncio.sleep(pace)
        await stage("letter", f"recoupment letter generated ({result.case_number})")

        # 8–9. Simulated delivery: portal upload + secure email. The recipient
        # comes from the provider org's real delivery playbook (seeded), so the
        # UI can show exactly who the notice went to.
        email_addr, contact = await _delivery_target(case.case_id)
        result.delivery_email = email_addr
        result.delivery_contact = contact
        to_txt = email_addr or "provider"
        await stage("portal", "active", status="active")
        await asyncio.sleep(pace)
        await _simulate_delivery(case.case_id, result.case_sequence, user_id, stage_email=False)
        await stage("portal", "uploaded to provider portal (simulated)")
        await stage("email", "active", status="active")
        await asyncio.sleep(pace)
        sent_real, ref, _note = await _deliver_email(case.case_id, user_id)
        result.delivery_ref = ref
        result.delivery_sent = sent_real
        detail = f"secure link emailed to {to_txt}" + (" ✓" if sent_real else " (simulated)")
        await stage("email", detail)
        result.reason = f"Recouped ${result.amount:,.0f} — notice sent to {to_txt}"
        return result

    except Exception as exc:  # noqa: BLE001 — one bad file must not kill the run
        log.exception("demo orchestrator failed on %s", filename)
        result.outcome, result.error = "ERROR", f"{type(exc).__name__}: {exc}"
        try:
            await emit(file_id, "decision", "error", str(exc)[:120])
        except Exception:
            pass
        return result


async def _mark_demo_case(case_id: str) -> None:
    """Stamp a demo-created case with the DEMO_MARKER_ACTION audit row so a later
    reset can find and delete exactly the rows this demo created. Best-effort: a
    failed stamp must not fail the run (the case is still valid), it just leaves
    that one case for a manual reseed."""
    try:
        async with _DB_LOCK, AsyncSessionLocal() as db:
            db.add(AuditLog(
                audit_id=str(uuid.uuid4()),
                case_id=case_id,
                actor_user_id="system",
                action=DEMO_MARKER_ACTION,
                from_state=None,
                to_state="awaiting_837",
                reason="Created by Claims Control Room demo run",
                meta_json="{}",
                created_at=datetime.utcnow().isoformat(),
            ))
            await db.commit()
    except Exception:  # noqa: BLE001
        log.exception("failed to stamp demo marker on case %s", case_id)


def _in_clause(column: str, values: list[str], prefix: str) -> tuple[str, dict]:
    """Build a parameterized `col IN (:p0, :p1, …)` clause + bind params."""
    keys = [f"{prefix}{i}" for i in range(len(values))]
    clause = f"{column} IN ({', '.join(':' + k for k in keys)})"
    return clause, dict(zip(keys, values))


async def reset_demo() -> dict:
    """Tear down every case the Claims Control Room demo created (and only those),
    so the next run reproduces the locked 5-auto / 5-review split from a clean
    slate. Identified via the DEMO_MARKER_ACTION audit stamp; nothing seeded is
    touched.

    FK enforcement is OFF in this SQLite setup (no `PRAGMA foreign_keys=ON`), so
    delete order is irrelevant. We sweep every mapped table carrying a `case_id`
    or `claim_id` column for the demo ids, plus the ERA transaction / payment /
    adjustment tables (which key off the transaction, not the case).
    """
    async with _DB_LOCK, AsyncSessionLocal() as db:
        case_ids = [r[0] for r in (await db.execute(text(
            "SELECT DISTINCT case_id FROM audit_logs "
            "WHERE action = :a AND case_id IS NOT NULL"
        ), {"a": DEMO_MARKER_ACTION})).all()]
        if not case_ids:
            return {"cases_deleted": 0, "claims_deleted": 0}

        c_clause, c_params = _in_clause("case_id", case_ids, "c")
        claim_ids = [r[0] for r in (await db.execute(text(
            f"SELECT claim_id FROM opa_cases WHERE {c_clause}"
        ), c_params)).all() if r[0]]

        txn_ids: list[str] = []
        payment_ids: list[str] = []
        if claim_ids:
            cl_clause, cl_params = _in_clause("claim_id", claim_ids, "k")
            txn_ids = [r[0] for r in (await db.execute(text(
                f"SELECT era_transaction_id FROM claims "
                f"WHERE {cl_clause} AND era_transaction_id IS NOT NULL"
            ), cl_params)).all() if r[0]]
        if txn_ids:
            t_clause, t_params = _in_clause("transaction_id", txn_ids, "t")
            payment_ids = [r[0] for r in (await db.execute(text(
                f"SELECT payment_id FROM claim_payments_835 WHERE {t_clause}"
            ), t_params)).all() if r[0]]

        # Sweep every mapped table that references a case or a claim directly.
        for tbl in Base.metadata.tables.values():
            if "case_id" in tbl.c:
                clause, params = _in_clause("case_id", case_ids, "c")
                await db.execute(text(f"DELETE FROM {tbl.name} WHERE {clause}"), params)
            if "claim_id" in tbl.c and claim_ids:
                clause, params = _in_clause("claim_id", claim_ids, "k")
                await db.execute(text(f"DELETE FROM {tbl.name} WHERE {clause}"), params)

        # ERA remittance chain (keyed off the transaction, not the case/claim).
        if payment_ids:
            clause, params = _in_clause("payment_id", payment_ids, "p")
            await db.execute(text(f"DELETE FROM era_adjustment_codes WHERE {clause}"), params)
        if txn_ids:
            clause, params = _in_clause("transaction_id", txn_ids, "t")
            await db.execute(text(f"DELETE FROM claim_payments_835 WHERE {clause}"), params)
            await db.execute(text(f"DELETE FROM transactions_835 WHERE {clause}"), params)

        await db.commit()
        log.info("reset_demo cleared %d case(s), %d claim(s)", len(case_ids), len(claim_ids))
        return {"cases_deleted": len(case_ids), "claims_deleted": len(claim_ids)}


async def _latest_letter(db, case_id: str) -> Optional[str]:
    from ..models.workflow import Document
    res = await db.execute(
        select(Document).where(Document.case_id == case_id, Document.kind == "recoupment_letter")
    )
    docs = list(res.scalars().all())
    return docs[-1].document_id if docs else None


async def _delivery_target(case_id: str) -> tuple[Optional[str], Optional[str]]:
    """(contact_email, contact_name) the recoupment notice is delivered to, read
    from the case's provider-org delivery playbook (seeded active email playbook).
    Falls back to the default demo inbox (named after the provider org) if the org
    has no playbook, so every auto-recouped lane shows a concrete address."""
    async with _DB_LOCK, AsyncSessionLocal() as db:
        row = (await db.execute(select(OpaCase).where(OpaCase.case_id == case_id))).scalar_one()
        pb = (await db.execute(
            select(ProviderDeliveryPlaybook)
            .where(ProviderDeliveryPlaybook.provider_org_id == row.provider_org_id)
        )).scalars().first()
        if pb and pb.contact_email:
            return pb.contact_email, pb.contact_name
        org = (await db.execute(
            select(ProviderOrg).where(ProviderOrg.provider_org_id == row.provider_org_id)
        )).scalars().first()
        name = f"{org.name} Billing" if org and org.name else "Provider Billing"
        return _DEFAULT_DELIVERY_EMAIL, name


async def _deliver_email(case_id: str, user_id: str) -> tuple[bool, Optional[str], Optional[str]]:
    """Attempt a REAL secure-link email to the provider via DeliveryService/EmailJS.

    Returns (sent_for_real, confirmation_ref, note). Falls back to the simulated
    delivery on ANY failure — EmailJS creds not configured, org has no email
    playbook, missing NPI, network error — so a demo run is never broken by an
    unconfigured mailer. `note` carries the reason we simulated (for logs/UI).

    Real emails only leave the box when EMAILJS_SERVICE_ID / _PUBLIC_KEY /
    _PRIVATE_KEY / _TEMPLATE_ID_SECURE_LINK are set in the environment.
    """
    try:
        async with _DB_LOCK, AsyncSessionLocal() as db:
            svc = DeliveryService(db)
            token, _case = await svc.send_email_notice(case_id, user_id, APP_DOMAIN)
            await db.commit()
        return True, token, None
    except Exception as exc:  # noqa: BLE001 — degrade to simulation, never abort
        note = f"{type(exc).__name__}: {exc}"
        log.info("real email unavailable for %s (%s) — simulating", case_id, note)
    # Lock released above (the async-with exits as the exception unwinds), so the
    # simulated path can safely re-acquire it. Kept outside the except body's lock.
    ref = await _simulate_delivery(case_id, 0, user_id, stage_email=True)
    return False, ref, note


async def _simulate_delivery(case_id: str, case_sequence: int, user_id: str, *, stage_email: bool) -> Optional[str]:
    """Mark the case as portal-uploaded / emailed without hitting external services.
    Returns the delivery confirmation ref on the email leg (else None)."""
    async with _DB_LOCK, AsyncSessionLocal() as db:
        row = (await db.execute(select(OpaCase).where(OpaCase.case_id == case_id))).scalar_one()
        prior = row.status
        ref: Optional[str] = None
        if stage_email:
            ref = f"demo-{uuid.uuid4().hex[:16]}"
            row.delivery_confirmation_ref = ref
            row.last_delivery_attempt_at = datetime.utcnow().isoformat()
            row.status = "notice_sent"
            action, reason = "EMAIL_SENT_SIMULATED", "Secure download link emailed to provider (demo simulation)"
        else:
            action, reason = "PORTAL_UPLOAD_SIMULATED", "Recoupment letter uploaded to provider portal (demo simulation)"
        db.add(AuditLog(
            audit_id=str(uuid.uuid4()),
            case_id=case_id,
            actor_user_id=user_id,
            action=action,
            from_state=prior,
            to_state=row.status,
            reason=reason,
            meta_json="{}",
            created_at=datetime.utcnow().isoformat(),
        ))
        await db.commit()
        return ref
