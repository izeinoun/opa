"""Provider messaging routes — send notices and inquiries to providers."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user, require_app
from ..models.workflow import OpaUser
from ..services.delivery_service import DeliveryService, DeliveryError

router = APIRouter(prefix="/api/cases", tags=["messaging"])


class SendProviderInquiryRequest(BaseModel):
    inquiry_text: str


@router.post("/{case_id}/send-notice-to-provider", dependencies=[Depends(require_app("payguard"))])
async def send_notice_to_provider(
    case_id: str,
    current_user: OpaUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send case notice/letter to provider via secure encrypted link.

    The notice must already exist (created in prior steps). Provider receives email
    with secure link; they verify NPI to access the letter and attachments.
    """
    service = DeliveryService(db)
    try:
        result = await service.send_notice_to_provider(
            case_id=case_id,
            acting_user_id=current_user.user_id,
        )
        await db.commit()
        return result
    except DeliveryError as e:
        await db.rollback()
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to send notice: {str(e)}")


@router.post("/{case_id}/send-provider-inquiry", dependencies=[Depends(require_app("payguard"))])
async def send_provider_inquiry(
    case_id: str,
    req: SendProviderInquiryRequest,
    current_user: OpaUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send custom inquiry/message to provider via secure encrypted link.

    Content is user-provided (e.g., from assistant or analyst). No attachment.
    Provider receives email with secure link; they verify NPI to access the message.
    """
    service = DeliveryService(db)
    try:
        result = await service.send_provider_inquiry(
            case_id=case_id,
            inquiry_text=req.inquiry_text,
            acting_user_id=current_user.user_id,
        )
        await db.commit()
        return result
    except DeliveryError as e:
        await db.rollback()
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to send inquiry: {str(e)}")
