"""Authentication routes for login and token management."""
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.workflow import OpaUser
from ..services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE_NAME = "opa_token"
COOKIE_MAX_AGE = 12 * 60 * 60  # 12 hours in seconds


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    role: str
    full_name: str


class CurrentUserResponse(BaseModel):
    user_id: str
    username: str
    full_name: str
    role: str
    email: str


def _set_auth_cookie(response: Response, token: str) -> None:
    """Set httpOnly cookie with JWT token for cross-app sharing."""
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Login with username and password. Sets httpOnly cookie + returns token."""
    user = await AuthService.authenticate_user(db, req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = AuthService.create_access_token(user.user_id)
    _set_auth_cookie(response, token)

    return TokenResponse(
        access_token=token,
        user_id=user.user_id,
        role=user.role,
        full_name=user.full_name,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: OpaUser = Depends(get_current_user),
) -> TokenResponse:
    """Refresh the JWT token. Called periodically by frontend to keep session alive."""
    token = AuthService.create_access_token(user.user_id)
    _set_auth_cookie(response, token)

    return TokenResponse(
        access_token=token,
        user_id=user.user_id,
        role=user.role,
        full_name=user.full_name,
    )


@router.get("/me", response_model=CurrentUserResponse)
async def get_current_user_info(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: OpaUser = Depends(get_current_user),
) -> CurrentUserResponse:
    """Get current authenticated user info. Apps use this to verify session.
    Returns 401 if no valid token is present (prevents system user fallback)."""
    # Check if user is authenticated (not the system fallback user)
    token = None
    authorization = request.headers.get("authorization")
    x_user_id = request.headers.get("x-user-id")

    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    elif not x_user_id:
        token = request.cookies.get("opa_token")

    # If no token/header found and user is system user, they're not authenticated
    if not token and not x_user_id and user.role == "system":
        raise HTTPException(status_code=401, detail="Not authenticated")

    return CurrentUserResponse(
        user_id=user.user_id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        email=user.email,
    )


@router.post("/logout")
async def logout(response: Response) -> dict:
    """Logout by clearing the auth cookie."""
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        samesite="lax",
        httponly=True,
    )
    return {"status": "logged_out"}
