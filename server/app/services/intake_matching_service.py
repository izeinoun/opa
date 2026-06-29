"""Match an inbound 837 / medical-record document to an existing ERA-based case.

Cases stay ERA-driven (created from 835s). An 837 or clinical PDF is *linked*
to an existing case, resolved on:
  1. Member — by payer member number, falling back to name (+ DOB).
  2. Service date — among that member's post-pay cases, matched at the LINE
     level: the case whose claim has a line whose service_date equals one of
     the document's dates of service. One matching line is sufficient. (Claims
     with no per-line DoS fall back to the claim-level service window.)

Ambiguity (0 or >1 line-level matches) → status 'unmatched', with the member's
cases returned as candidates for the admin's radio picker.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.claims import Claim, ClaimLine
from ..models.reference import Member
from ..models.workflow import OpaCase

logger = logging.getLogger(__name__)

# Clinic-note and claim dates legitimately drift by a day (timezone rendering,
# note written the day after service, admit-vs-procedure date). Treat dates this
# far apart as the same date of service. The CPT must still match exactly in
# pairing mode, so widening the date window barely affects specificity.
_DOS_TOLERANCE_DAYS = 1


def _dates_close(a: Optional[str], b: Optional[str]) -> bool:
    """True if two YYYY-MM-DD dates are within _DOS_TOLERANCE_DAYS of each other."""
    if not a or not b:
        return False
    try:
        return abs((date.fromisoformat(a) - date.fromisoformat(b)).days) <= _DOS_TOLERANCE_DAYS
    except ValueError:
        return a == b  # non-ISO strings: fall back to exact equality


@dataclass
class MatchResult:
    status: str                                   # 'matched' | 'unmatched'
    reason: str = ""
    member_id: Optional[str] = None
    case_id: Optional[str] = None
    claim_id: Optional[str] = None
    candidate_case_ids: List[str] = field(default_factory=list)


async def _resolve_member(
    db: AsyncSession,
    *,
    member_number: Optional[str],
    member_first: Optional[str] = None,
    member_last: Optional[str] = None,
    dob: Optional[str],
) -> Optional[Member]:
    """Resolve a member by number first, then by first+last name (+ DOB if available)."""
    if member_number:
        res = await db.execute(
            select(Member).where(Member.member_number == member_number)
        )
        m = res.scalar_one_or_none()
        if m:
            return m

    first = (member_first or "").strip()
    last = (member_last or "").strip()
    if first:
        stmt = select(Member).where(Member.first_name.ilike(first))
        if last:
            stmt = stmt.where(Member.last_name.ilike(last))
        if dob:
            stmt = stmt.where(Member.date_of_birth == dob)
        res = await db.execute(stmt.order_by(Member.member_id))
        members = list(res.scalars().all())
        if len(members) == 1:
            return members[0]
        if len(members) > 1:
            logger.info("Member name '%s' matched %d members — ambiguous", name, len(members))
    return None


def _window_contains(claim: Claim, service_dates: List[str]) -> bool:
    """True if any of the document's service dates falls within the claim's
    service window (YYYY-MM-DD strings compare lexicographically), or within
    _DOS_TOLERANCE_DAYS of either window edge."""
    lo = claim.service_from_date or ""
    hi = claim.service_to_date or claim.service_from_date or ""
    for sd in service_dates:
        if lo and hi and lo <= sd <= hi:
            return True
        if _dates_close(sd, lo) or _dates_close(sd, hi):
            return True
    return False


def _claim_dos_match(
    claim: Claim, line_dates: set[str], service_dates: List[str]
) -> bool:
    """True if the document shares a date of service with this claim, compared
    AT THE LINE LEVEL: one of the document's DoS is within _DOS_TOLERANCE_DAYS of
    one of the claim's per-line service dates. A single matching line is enough.

    Falls back to the claim-level service window only when the claim has no
    line-level DoS recorded (legacy rows), so we never regress old data.
    """
    if not service_dates:
        return False
    if line_dates:
        return any(_dates_close(sd, ld) for sd in service_dates for ld in line_dates)
    return _window_contains(claim, service_dates)


async def _line_dos_by_claim(
    db: AsyncSession, claim_ids: List[str]
) -> dict[str, set[str]]:
    """Map claim_id → set of its non-null per-line service dates."""
    out: dict[str, set[str]] = {}
    if not claim_ids:
        return out
    rows = (await db.execute(
        select(ClaimLine.claim_id, ClaimLine.service_date)
        .where(ClaimLine.claim_id.in_(claim_ids))
        .where(ClaimLine.service_date.is_not(None))
    )).all()
    for cid, sd in rows:
        if sd:
            out.setdefault(cid, set()).add(sd)
    return out


async def _line_pairs_by_claim(
    db: AsyncSession, claim_ids: List[str]
) -> dict[str, set[tuple[str, str]]]:
    """Map claim_id → set of (cpt_code, service_date) pairs for its lines."""
    out: dict[str, set[tuple[str, str]]] = {}
    if not claim_ids:
        return out
    rows = (await db.execute(
        select(ClaimLine.claim_id, ClaimLine.cpt_code, ClaimLine.service_date)
        .where(ClaimLine.claim_id.in_(claim_ids))
        .where(ClaimLine.service_date.is_not(None))
    )).all()
    for cid, cpt, sd in rows:
        if cpt and sd:
            out.setdefault(cid, set()).add((cpt, sd))
    return out


def _pairs_match(
    doc_pairs: set[tuple[str, str]], claim_pairs: set[tuple[str, str]]
) -> bool:
    """True if any document (cpt, dos) pair shares a claim line with the SAME cpt
    and a date of service within _DOS_TOLERANCE_DAYS. One matching line is enough."""
    for dcpt, ddos in doc_pairs:
        for ccpt, cdos in claim_pairs:
            if dcpt == ccpt and _dates_close(ddos, cdos):
                return True
    return False


async def match_to_case(
    db: AsyncSession,
    *,
    member_number: Optional[str] = None,
    member_first: Optional[str] = None,
    member_last: Optional[str] = None,
    dob: Optional[str] = None,
    service_dates: Optional[List[str]] = None,
    service_lines: Optional[List[tuple[Optional[str], Optional[str]]]] = None,
) -> MatchResult:
    """Resolve the existing post-pay case an 837 / medical record belongs to.

    service_lines carries the document's per-line (cpt, date) pairs. When the
    document yields usable pairs we match line-to-line — a claim is a candidate
    only if it shares a (cpt, service_date) line with the document — which is
    stricter (procedure *and* date must line up) than the date-only fallback.
    """
    service_dates = sorted({d for d in (service_dates or []) if d})
    doc_pairs = {(c, d) for c, d in (service_lines or []) if c and d}

    member = await _resolve_member(
        db, member_number=member_number, member_first=member_first, member_last=member_last, dob=dob
    )
    if member is None:
        return MatchResult(status="unmatched", reason="Member could not be resolved")

    # All post-pay (ERA-based) cases for this member, with their claim window.
    rows = (await db.execute(
        select(OpaCase, Claim)
        .join(Claim, OpaCase.claim_id == Claim.claim_id)
        .where(OpaCase.member_id == member.member_id)
        .where(Claim.pipeline_mode == "post_pay")
        .order_by(OpaCase.case_sequence.desc())
    )).all()

    if not rows:
        return MatchResult(
            status="unmatched",
            reason="Member resolved but has no ERA-based cases",
            member_id=member.member_id,
        )

    all_case_ids = [case.case_id for case, _ in rows]
    claim_ids = [cl.claim_id for _, cl in rows]

    # Match at the LINE level. When the document gives us (cpt, date) pairs we
    # pair line-to-line: a claim matches only if it shares a (cpt, service_date)
    # line. Otherwise we fall back to date-of-service alone. One matching line
    # is sufficient either way.
    if doc_pairs:
        pair_by_claim = await _line_pairs_by_claim(db, claim_ids)
        matches = [
            (c, cl) for c, cl in rows
            if _pairs_match(doc_pairs, pair_by_claim.get(cl.claim_id, set()))
        ]
        matched_reason = "Matched on member + line (CPT + service date)"
        no_match_reason = "No claim line matched the document's procedure + date of service"
    else:
        line_dos = await _line_dos_by_claim(db, claim_ids)
        matches = [
            (c, cl) for c, cl in rows
            if _claim_dos_match(cl, line_dos.get(cl.claim_id, set()), service_dates)
        ]
        matched_reason = "Matched on member + line-level service date"
        no_match_reason = "No claim line matched the document's date of service"

    if len(matches) == 1:
        case, claim = matches[0]
        return MatchResult(
            status="matched", reason=matched_reason,
            member_id=member.member_id, case_id=case.case_id, claim_id=claim.claim_id,
            candidate_case_ids=all_case_ids,
        )

    # No document dates/lines to compare, but a single case for the member →
    # link it (nothing to disambiguate on).
    if not service_dates and not doc_pairs and len(rows) == 1:
        case, claim = rows[0]
        return MatchResult(
            status="matched", reason="Single case for member (no DoS to compare)",
            member_id=member.member_id, case_id=case.case_id, claim_id=claim.claim_id,
            candidate_case_ids=all_case_ids,
        )

    # 0 or >1 line-level matches → needs a human.
    reason = no_match_reason if not matches else "Multiple cases matched the document at the line level"
    return MatchResult(
        status="unmatched",
        reason=reason,
        member_id=member.member_id,
        candidate_case_ids=all_case_ids,
    )
