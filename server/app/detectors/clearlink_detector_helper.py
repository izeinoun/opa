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


async def search_clearlink_for_prior_auth(
    member_id: str, cpt_code: str, service_date: Optional[str] = None
) -> bool:
    """Search ClearLink for prior authorization matching the given CPT code.

    Returns True if prior auth found for this CPT code.
    Returns False if not found, unavailable, or ClearLink is not configured.
    """
    if not member_id or not cpt_code:
        return False

    # ClearLink exposes prior auths via `list_prior_authorizations`. The member_id
    # input is resolved against members.member_number, so callers pass member_number.
    success, response = await call_clearlink_tool(
        "list_prior_authorizations",
        {"member_id": member_id},
    )

    if not success:
        logger.debug(f"[ClearLink] Failed to fetch authorizations for member {member_id}")
        return False

    try:
        data = json.loads(response)
        logger.debug(f"[ClearLink] Retrieved authorizations for member {member_id}")

        # Search for the specific CPT code in authorizations
        response_text = json.dumps(data).upper()
        cpt_pattern = re.compile(rf'\b{cpt_code}\b', re.IGNORECASE)

        if cpt_pattern.search(response_text):
            logger.info(f"[ClearLink] Found prior auth in ClearLink for CPT {cpt_code}")
            return True

        logger.debug(f"[ClearLink] No prior auth found in ClearLink for CPT {cpt_code}")
        return False

    except json.JSONDecodeError:
        logger.warning(f"[ClearLink] Invalid JSON response for authorizations")
        return False
    except Exception as e:
        logger.warning(f"[ClearLink] Error parsing authorizations: {e}")
        return False


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
