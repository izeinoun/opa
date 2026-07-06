from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import APP_DOMAIN
from ..database import get_db
from ..middleware.auth import get_current_user, require_app
from ..models.workflow import OpaUser
from ..services.delivery_service import DeliveryService, DeliveryError
from ..schemas.playbook_schemas import PlaybookRead
from ..schemas.case_schemas import CaseDetail

router = APIRouter(prefix="/api/cases", tags=["delivery"])


@router.get("/delivery-queue", dependencies=[Depends(require_app("payguard"))])
async def get_delivery_queue(
    mode: Optional[str] = Query(None, description="Filter by email|portal"),
    current_user: OpaUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all cases ready for delivery.

    Returns complete self-contained payload: case summary + full playbook embedded.
    Sorted by deadline ascending.
    """
    service = DeliveryService(db)
    queue = await service.get_delivery_queue(mode=mode, db_session=db)
    return queue


@router.post("/{case_id}/send-notice", dependencies=[Depends(require_app("payguard"))])
async def send_notice(
    case_id: str,
    app_domain: str = APP_DOMAIN,
    current_user: OpaUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send secure download link to provider via email.

    Only works for email-delivery playbooks. Returns the generated token.
    """
    service = DeliveryService(db)
    try:
        token, case = await service.send_email_notice(
            case_id,
            acting_user_id=current_user.user_id,
            app_domain=app_domain,
        )
        await db.commit()
    except DeliveryError as e:
        await db.rollback()
        raise HTTPException(status_code=502, detail=str(e))

    return {
        "token": token,
        "case_id": case.case_id,
        "status": case.status,
        "message": "Secure download link sent to provider",
    }


@router.patch("/{case_id}/delivery-result", dependencies=[Depends(require_app("payguard"))])
async def record_delivery_result(
    case_id: str,
    status: str,
    delivery_confirmation_ref: Optional[str] = None,
    last_delivery_attempt_at: Optional[str] = None,
    notes: Optional[str] = None,
    current_user: OpaUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Agent writes back delivery result from portal delivery attempt.

    Validates status transition from ready_to_send.
    """
    service = DeliveryService(db)
    try:
        case = await service.write_delivery_result(
            case_id,
            status,
            delivery_confirmation_ref=delivery_confirmation_ref,
            last_delivery_attempt_at=last_delivery_attempt_at,
            notes=notes,
            acting_user_id=current_user.user_id,
        )
        await db.commit()
    except DeliveryError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "case_id": case.case_id,
        "status": case.status,
        "delivery_confirmation_ref": case.delivery_confirmation_ref,
        "message": f"Case status updated to {status}",
    }
