from fastapi import Header, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.workflow import OpaUser


async def get_current_user_role(x_user_role: str = Header(default="analyst")) -> str:
    """Dev-mode: reads X-User-Role header. Returns role string."""
    if x_user_role not in ("analyst", "supervisor", "admin"):
        raise HTTPException(status_code=403, detail="Invalid role")
    return x_user_role


def require_supervisor(role: str = Depends(get_current_user_role)) -> str:
    if role not in ("supervisor", "admin"):
        raise HTTPException(status_code=403, detail="Supervisor access required")
    return role


def require_admin(role: str = Depends(get_current_user_role)) -> str:
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return role


async def get_current_user(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
) -> OpaUser:
    """Dev-mode: resolves the current user from the X-User-Id header.

    Returns the OpaUser row. Falls back to the system bot if no header is sent,
    so existing endpoints / background jobs that don't pass the header still
    work. Front-end is expected to set the header on every authenticated call.
    """
    if x_user_id:
        result = await db.execute(select(OpaUser).where(OpaUser.user_id == x_user_id))
        user = result.scalar_one_or_none()
        if user:
            return user
        raise HTTPException(status_code=401, detail=f"Unknown user_id: {x_user_id}")

    # Fallback for unauthenticated callers (system jobs, legacy endpoints)
    result = await db.execute(select(OpaUser).where(OpaUser.role == "system").limit(1))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=500, detail="No system user configured")
    return user


def assert_case_writable_by(case, user: OpaUser) -> None:
    """Raises 403 if `user` cannot perform writes on `case` in its current state.

    Lock rule: when case.status == 'pending_supervisor', only supervisors and
    admins may write. Analysts are read-only (notes remain writable via a
    dedicated path that does NOT call this guard).
    """
    if case.status == "pending_supervisor" and user.role not in ("supervisor", "admin"):
        raise HTTPException(
            status_code=403,
            detail=(
                "Case is awaiting supervisor approval and is read-only for analysts. "
                "Notes can still be added."
            ),
        )
