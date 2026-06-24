from fastapi import Header, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.workflow import OpaUser


async def get_current_user_role(x_user_role: str = Header(default="analyst")) -> str:
    """Dev-mode: reads X-User-Role header. Returns role string.

    DEPRECATED in favor of get_current_user + RBAC dependencies below. Kept
    for routes that still gate on the single legacy role; new routes should
    use require_app() / require_role() which consult user_roles + role_apps."""
    if x_user_role not in ("analyst", "supervisor", "admin", "specialist"):
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
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> OpaUser:
    """Resolves the current user from the JWT Bearer token in Authorization header.

    Returns the OpaUser row. Falls back to the system bot if no token is sent,
    so existing endpoints / background jobs that don't pass auth still work.
    """
    from ..services.auth_service import AuthService

    if authorization:
        # Extract Bearer token from "Bearer <token>"
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid authorization header format")

        token = parts[1]
        payload = AuthService.verify_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        result = await db.execute(select(OpaUser).where(OpaUser.user_id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=401, detail=f"Unknown user_id: {user_id}")
        return user

    # Fallback for unauthenticated callers (system jobs, legacy endpoints)
    result = await db.execute(select(OpaUser).where(OpaUser.role == "system").limit(1))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=500, detail="No system user configured")
    return user


# ── RBAC dependencies (multi-role + app-scoped) ──────────────────────────
# Opt-in: routes that want enforcement add `Depends(require_app("payguard"))`
# or `Depends(require_role("admin"))`. Routes that don't add the dep continue
# to work for any authenticated caller — same behavior as today. This lets
# us roll out enforcement gradually.


def require_app(app_name: str):
    """Dependency: caller must have at least one role granting access to
    `app_name`. Uses user_roles + role_apps via RBACService."""
    from ..services.rbac_service import RBACService

    async def _dep(
        user: OpaUser = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> OpaUser:
        rbac = RBACService(db)
        if not await rbac.user_can_access_app(user.user_id, app_name):
            raise HTTPException(
                status_code=403,
                detail=f"User does not have access to app '{app_name}'",
            )
        return user
    return _dep


def require_any_app(*app_names: str):
    """Dependency: caller must have access to at least one of the listed apps.
    Useful for pipeline-agnostic endpoints (documents, evidence) that any
    app can hit."""
    from ..services.rbac_service import RBACService

    async def _dep(
        user: OpaUser = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> OpaUser:
        rbac = RBACService(db)
        user_apps = await rbac.get_app_names_for_user(user.user_id)
        if user_apps.isdisjoint(app_names):
            raise HTTPException(
                status_code=403,
                detail=f"Requires access to one of: {sorted(app_names)}; "
                       f"user has: {sorted(user_apps) or '[]'}",
            )
        return user
    return _dep


def require_role(role_name: str, *allow_also: str):
    """Dependency: caller must have `role_name` (or any of the additional
    allow-also roles). Multiple usages: `require_role('admin')`,
    `require_role('admin', 'supervisor')`."""
    from ..services.rbac_service import RBACService
    allowed = {role_name, *allow_also}

    async def _dep(
        user: OpaUser = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> OpaUser:
        rbac = RBACService(db)
        names = await rbac.get_role_names_for_user(user.user_id)
        if names.isdisjoint(allowed):
            raise HTTPException(
                status_code=403,
                detail=f"Requires one of: {sorted(allowed)}; user has: {sorted(names) or '[]'}",
            )
        return user
    return _dep


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
