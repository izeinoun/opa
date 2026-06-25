"""ClearLink proxy endpoints for diagnosis management and claim enrichment.

This router proxies requests to the ClearLink MCP server, which handles:
- add-diagnosis: Add/update diagnosis codes on a claim
- Audit logging for all ClearLink operations

Environment variables:
- CLEARLINK_MCP_URL: Base URL of ClearLink MCP server (default: http://localhost:8010)
- CLEARLINK_API_KEY: API key for ClearLink authentication
"""
import json
import logging
import os
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user, require_role
from ..models.workflow import AuditLog, OpaUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/clearlink", tags=["clearlink"])


class AddDiagnosisRequest(BaseModel):
    """Request body for adding a diagnosis to a claim."""
    claim_id: str
    icd_code: str
    description: Optional[str] = None
    severity: Optional[str] = None
    sequence: Optional[int] = None


class ClearLinkResponse(BaseModel):
    """Generic response wrapper from ClearLink."""
    success: bool
    message: Optional[str] = None
    data: Optional[Any] = None


async def _get_clearlink_url() -> str:
    """Get ClearLink MCP server base URL from environment or use default."""
    return (
        (os.getenv("CLEARLINK_MCP_URL") or "http://localhost:8010")
        .rstrip("/")
    )


async def _get_clearlink_api_key() -> str:
    """Get ClearLink API key from environment."""
    api_key = os.getenv("CLEARLINK_API_KEY", "")
    if not api_key:
        logger.warning("CLEARLINK_API_KEY not set; requests may be rejected")
    return api_key


async def _audit_log(
    db: AsyncSession,
    user: OpaUser,
    action: str,
    claim_id: Optional[str] = None,
    case_id: Optional[str] = None,
    reason: Optional[str] = None,
    meta_json: Optional[str] = None,
) -> None:
    """Create an audit log entry for ClearLink operations."""
    audit = AuditLog(
        audit_id=str(uuid4()),
        case_id=case_id,
        claim_id=claim_id,
        actor_user_id=user.user_id,
        action=action,
        from_state=None,
        to_state=None,
        reason=(reason or "")[:500],
        meta_json=meta_json or "{}",
        created_at=datetime.utcnow().isoformat(),
    )
    db.add(audit)
    await db.commit()
    logger.info(
        f"Audit logged: {action} by {user.user_id} on claim {claim_id}",
        extra={"audit_id": audit.audit_id},
    )


@router.post("/add-diagnosis", response_model=ClearLinkResponse, dependencies=[Depends(require_role("analyst", "admin"))])
async def add_diagnosis(
    req: AddDiagnosisRequest,
    db: AsyncSession = Depends(get_db),
    user: OpaUser = Depends(get_current_user),
) -> ClearLinkResponse:
    """Add or update a diagnosis code on a claim via ClearLink.

    Requires analyst or admin role. Logs the operation to audit_logs.
    Proxies the request to the ClearLink MCP server.

    Args:
        req: AddDiagnosisRequest with claim_id, icd_code, and optional metadata
        db: Database session
        user: Current authenticated user

    Returns:
        ClearLinkResponse with success status and optional data

    Raises:
        HTTPException: If ClearLink is unavailable or returns an error
    """
    clearlink_url = await _get_clearlink_url()
    clearlink_api_key = await _get_clearlink_api_key()

    # Prepare headers for ClearLink request
    headers = {
        "Authorization": f"Bearer {clearlink_api_key}",
        "Content-Type": "application/json",
    }

    # Build the payload for ClearLink
    payload = {
        "claim_id": req.claim_id,
        "icd_code": req.icd_code,
    }
    if req.description:
        payload["description"] = req.description
    if req.severity:
        payload["severity"] = req.severity
    if req.sequence is not None:
        payload["sequence"] = req.sequence

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Proxy to ClearLink endpoint
            response = await client.post(
                f"{clearlink_url}/api/clearlink/add-diagnosis",
                json=payload,
                headers=headers,
            )

            # Log the audit trail
            await _audit_log(
                db,
                user,
                action="clearlink_add_diagnosis",
                claim_id=req.claim_id,
                reason=f"Added diagnosis {req.icd_code}",
                meta_json=json.dumps({
                    "icd_code": req.icd_code,
                    "description": req.description,
                    "severity": req.severity,
                    "sequence": req.sequence,
                    "clearlink_status": response.status_code,
                }),
            )

            # Check for errors from ClearLink
            if response.status_code >= 400:
                logger.error(
                    f"ClearLink error: {response.status_code} {response.text}",
                    extra={"claim_id": req.claim_id, "user_id": user.user_id},
                )
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"ClearLink service error: {response.status_code}",
                )

            # Parse and return the response
            result = response.json()
            return ClearLinkResponse(
                success=result.get("success", True),
                message=result.get("message"),
                data=result.get("data"),
            )

    except httpx.ConnectError as e:
        logger.error(
            f"Failed to connect to ClearLink at {clearlink_url}",
            exc_info=e,
        )
        raise HTTPException(
            status_code=503,
            detail="ClearLink service unavailable",
        )
    except httpx.TimeoutException as e:
        logger.error(
            f"Timeout communicating with ClearLink",
            exc_info=e,
        )
        raise HTTPException(
            status_code=504,
            detail="ClearLink service timeout",
        )
    except json.JSONDecodeError as e:
        logger.error(
            f"Invalid JSON response from ClearLink: {response.text}",
            exc_info=e,
        )
        raise HTTPException(
            status_code=502,
            detail="ClearLink returned invalid response",
        )
    except Exception as e:
        logger.error(
            f"Unexpected error proxying to ClearLink: {str(e)}",
            exc_info=e,
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error proxying to ClearLink",
        )
