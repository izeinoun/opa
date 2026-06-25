"""API key management endpoints for external service integration."""
from datetime import datetime
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user, require_role
from ..models.workflow import OpaUser
from ..services.api_key_service import APIKeyService

router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])


class APIKeyCreateRequest(BaseModel):
    """Request to create a new API key."""
    name: str = "API Key"
    expires_in_days: int | None = None  # None = no expiry


class APIKeyResponse(BaseModel):
    """Response for API key (without the secret token)."""
    api_key_id: str
    name: str
    created_at: str
    expires_at: str | None
    last_used_at: str | None
    is_active: bool


class APIKeyWithTokenResponse(APIKeyResponse):
    """Response when creating an API key (includes the secret token, shown once)."""
    token: str


@router.post("/create", response_model=APIKeyWithTokenResponse)
async def create_api_key(
    req: APIKeyCreateRequest,
    user: OpaUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIKeyWithTokenResponse:
    """Create a new API key for the current user.

    The token is shown only once. Store it securely.
    Token is used as: Authorization: Bearer <token>
    """
    token, api_key = await APIKeyService.create_api_key(
        db,
        user.user_id,
        name=req.name,
        expires_in_days=req.expires_in_days,
    )

    return APIKeyWithTokenResponse(
        api_key_id=api_key.api_key_id,
        token=token,
        name=api_key.name,
        created_at=api_key.created_at,
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        is_active=api_key.is_active,
    )


@router.get("/list", response_model=list[APIKeyResponse])
async def list_api_keys(
    user: OpaUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[APIKeyResponse]:
    """List all API keys for the current user."""
    api_keys = await APIKeyService.list_api_keys(db, user.user_id)
    return [
        APIKeyResponse(
            api_key_id=ak.api_key_id,
            name=ak.name,
            created_at=ak.created_at,
            expires_at=ak.expires_at,
            last_used_at=ak.last_used_at,
            is_active=ak.is_active,
        )
        for ak in api_keys
    ]


@router.post("/revoke/{api_key_id}")
async def revoke_api_key(
    api_key_id: str,
    user: OpaUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Revoke an API key."""
    ok = await APIKeyService.revoke_api_key(db, api_key_id, user.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"status": "revoked"}
