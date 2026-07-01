"""ClearLink MCP integration for detectors.

Provides helper functions for detectors to query member clinical data from ClearLink
(medical records, diagnoses, prior authorizations, etc.) when attached documents
are insufficient or unavailable.

Works for both PayGuard (post-pay) and ClaimGuard (pre-pay) pipelines.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from ..models.claims import Claim
from ..services.assistant.clearlink_integration import call_clearlink_tool

logger = logging.getLogger(__name__)


async def search_clearlink_for_diagnoses(member_id: str) -> set[str]:
    """Search ClearLink for member's clinical diagnoses.

    Returns a set of ICD-10 diagnosis codes found in member's ClearLink records.
    Returns empty set if ClearLink unavailable or member not found.
    """
    if not member_id:
        return set()

    # ClearLink exposes member diagnoses via the `list_diagnoses` tool. It resolves
    # the `member_id` input against `members.member_number`, so callers MUST pass the
    # member_number business key (NOT OPA's internal UUID member_id).
    success, response = await call_clearlink_tool(
        "list_diagnoses",
        {"member_id": member_id},
    )

    if not success:
        logger.debug(f"[ClearLink] Failed to fetch diagnoses for member {member_id}")
        return set()

    try:
        data = json.loads(response)
        logger.debug(f"[ClearLink] Retrieved medical records for member {member_id}")

        # Extract ICD codes from records using regex pattern
        icd_pattern = re.compile(r'\b([A-Z]\d{2}(?:\.\d{1,2})?)\b')
        diagnoses = set()

        # Search through medical records content
        records_text = json.dumps(data)  # Convert to string for regex search
        matches = icd_pattern.findall(records_text)
        for icd in matches:
            icd_normalized = icd.rstrip('.').upper()
            diagnoses.add(icd_normalized)

        if diagnoses:
            logger.info(f"[ClearLink] Found {len(diagnoses)} diagnoses for member {member_id}: {diagnoses}")

        return diagnoses

    except json.JSONDecodeError:
        logger.warning(f"[ClearLink] Invalid JSON response for member {member_id}")
        return set()
    except Exception as e:
        logger.warning(f"[ClearLink] Error parsing medical records for member {member_id}: {e}")
        return set()


_APPROVED_STATUSES = {"approved", "auto_approved"}
_PENDING_STATUSES  = {"pending", "pended_review"}
_DENIED_STATUSES   = {"denied", "auto_denied", "cancelled"}


async def search_clearlink_for_prior_auth(
    member_id: str, cpt_code: str, service_date: Optional[str] = None
) -> dict:
    """Search ClearLink for a prior authorization matching the given CPT code.

    Returns a dict:
        {
            "found": bool,          # any record matched this CPT
            "approved": bool,       # status is approved/auto_approved
            "auth_id": str | None,  # ClearLink PA record ID
            "status": str | None,   # raw status string
            "cpt_codes": list,      # CPT codes on the matching auth
            "service_date": str | None,
            "provider_name": str | None,
            "decided_at": str | None,
        }

    CPT matching uses JSON parsing of the cpt_codes field, not a substring search,
    so "27447" won't spuriously match "274470". Returns found=False on any error.
    """
    empty = {
        "found": False, "approved": False, "auth_id": None, "status": None,
        "cpt_codes": [], "service_date": None, "provider_name": None, "decided_at": None,
    }

    if not member_id or not cpt_code:
        return empty

    success, response = await call_clearlink_tool(
        "list_prior_authorizations",
        {"member_id": member_id, "cpt_code": cpt_code},
    )

    if not success:
        logger.debug(f"[ClearLink] Failed to fetch authorizations for member {member_id}")
        return empty

    try:
        data = json.loads(response)
        records = data if isinstance(data, list) else data.get("data", data.get("rows", []))

        for rec in records:
            # cpt_codes is stored as a JSON array string e.g. '["27447","27448"]'
            raw_cpts = rec.get("cpt_codes", "[]")
            try:
                rec_cpts = json.loads(raw_cpts) if isinstance(raw_cpts, str) else raw_cpts
            except (json.JSONDecodeError, TypeError):
                rec_cpts = []

            # Exact CPT match (case-insensitive)
            if cpt_code.upper() not in [c.upper() for c in rec_cpts]:
                # Fallback: regex whole-word match on raw string in case format differs
                if not re.search(rf'\b{re.escape(cpt_code)}\b', raw_cpts if isinstance(raw_cpts, str) else "", re.IGNORECASE):
                    continue

            status = (rec.get("status") or "").lower()
            result = {
                "found": True,
                "approved": status in _APPROVED_STATUSES,
                "auth_id": str(rec.get("id", "")),
                "status": status,
                "cpt_codes": rec_cpts,
                "service_date": rec.get("service_date"),
                "provider_name": rec.get("requesting_provider_name"),
                "decided_at": rec.get("decided_at"),
            }
            logger.info(
                f"[ClearLink] Prior auth found for member={member_id} CPT={cpt_code}: "
                f"id={result['auth_id']} status={status} approved={result['approved']}"
            )
            return result

        logger.debug(f"[ClearLink] No prior auth found in ClearLink for CPT {cpt_code}")
        return empty

    except json.JSONDecodeError:
        logger.warning("[ClearLink] Invalid JSON response for authorizations")
        return empty
    except Exception as e:
        logger.warning(f"[ClearLink] Error parsing authorizations for CPT {cpt_code}: {e}")
        return empty


async def search_clearlink_for_clinical_notes(member_id: str, keywords: list[str]) -> bool:
    """Search ClearLink member clinical notes for specific keywords.

    Returns True if any of the keywords found in clinical notes.
    Useful for finding medical justification for procedures.
    """
    if not member_id or not keywords:
        return False

    # ClearLink exposes no dedicated clinical-notes tool, so aggregate the
    # narrative-bearing data it does provide and keyword-match across all of it.
    # `member_id` must be the member_number business key.
    texts: list[str] = []
    for tool in ("list_diagnoses", "get_provider_messages"):
        success, response = await call_clearlink_tool(tool, {"member_id": member_id})
        if success and response:
            texts.append(response)

    if not texts:
        return False

    haystack = " ".join(texts).lower()
    for keyword in keywords:
        if re.search(keyword, haystack, re.IGNORECASE):
            logger.info(f"[ClearLink] Found justification keyword '{keyword}' in member clinical data")
            return True

    logger.debug("[ClearLink] No justification keywords found in member clinical data")
    return False
