"""Email sending endpoint for MCP assistant and internal services."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.workflow import OpaUser
from ..services.delivery_service import DeliveryService, DeliveryError

router = APIRouter(prefix="/api/email", tags=["email"])


class EmailRequest(BaseModel):
    template: str  # 'secure_link', 'otp', 'notify_payer'
    to_email: str
    to_name: str | None = None
    template_params: dict | None = None


@router.post("/send")
async def send_email(
    req: EmailRequest,
    current_user: OpaUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a transactional email via EmailJS.

    Supports templates:
    - secure_link: Secure download link for provider
    - otp: One-time password verification
    - notify_payer: Payer notification
    """
    if not req.to_email:
        raise HTTPException(status_code=400, detail="to_email is required")

    service = DeliveryService(db)

    try:
        # Call the static email sending method
        await DeliveryService._send_email_emailjs(
            template=req.template,
            to_email=req.to_email,
            to_name=req.to_name,
            template_params=req.template_params or {},
        )
        return {"status": "success", "message": "Email sent successfully"}
    except DeliveryError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email send failed: {str(e)}")
