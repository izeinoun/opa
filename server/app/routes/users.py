"""User picker + RBAC read endpoints.

Read-only for now. Role-assignment mutations (POST /users/{id}/roles) will
land alongside an admin UI in a follow-up.
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.workflow import App, OpaUser, Role, RoleApp
from ..schemas.prepay_schemas import AppOut, RoleOut, UserOut
from ..services.rbac_service import RBACService

router = APIRouter(prefix="/api/users", tags=["users"])


async def _user_to_out(rbac: RBACService, u: OpaUser, db: AsyncSession) -> UserOut:
    roles = await rbac.get_roles_for_user(u.user_id)
    apps = await rbac.get_apps_for_user(u.user_id)
    default_app_name = None
    if u.default_app_id:
        res = await db.execute(select(App).where(App.app_id == u.default_app_id))
        a = res.scalar_one_or_none()
        if a:
            default_app_name = a.app_name
    return UserOut(
        id=u.user_id,
        name=u.full_name,
        role=u.role,
        initials=u.initials,
        color_hex=u.color_hex,
        specialty=u.specialty,
        supervisor_id=u.supervisor_id,
        roles=[r.role_name for r in roles],
        apps=[a.app_name for a in apps],
        default_app=default_app_name,
    )


@router.get("", response_model=List[UserOut])
async def list_users(db: AsyncSession = Depends(get_db)) -> List[UserOut]:
    res = await db.execute(
        select(OpaUser).where(OpaUser.is_active == True).order_by(OpaUser.full_name)  # noqa: E712
    )
    rbac = RBACService(db)
    return [await _user_to_out(rbac, u, db) for u in res.scalars().all()]


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: str, db: AsyncSession = Depends(get_db)) -> UserOut:
    res = await db.execute(select(OpaUser).where(OpaUser.user_id == user_id))
    u = res.scalar_one_or_none()
    if u is None:
        raise HTTPException(status_code=404, detail="User not found")
    rbac = RBACService(db)
    return await _user_to_out(rbac, u, db)


# ── RBAC reference endpoints ──────────────────────────────────────────────

apps_router = APIRouter(prefix="/api/apps", tags=["rbac"])
roles_router = APIRouter(prefix="/api/roles", tags=["rbac"])


@apps_router.get("", response_model=List[AppOut])
async def list_apps(db: AsyncSession = Depends(get_db)) -> List[AppOut]:
    rbac = RBACService(db)
    return [
        AppOut(id=a.app_id, name=a.app_name, description=a.description, is_active=a.is_active)
        for a in await rbac.list_apps()
    ]


@roles_router.get("", response_model=List[RoleOut])
async def list_roles(db: AsyncSession = Depends(get_db)) -> List[RoleOut]:
    # Build role→app_names map from role_apps + apps in one shot.
    role_res = await db.execute(select(Role).order_by(Role.role_name))
    roles = list(role_res.scalars().all())
    ra_res = await db.execute(
        select(RoleApp.role_id, App.app_name)
        .join(App, App.app_id == RoleApp.app_id)
    )
    apps_by_role: dict[str, list[str]] = {}
    for role_id, app_name in ra_res.all():
        apps_by_role.setdefault(role_id, []).append(app_name)
    return [
        RoleOut(
            id=r.role_id, name=r.role_name, description=r.description,
            apps=sorted(apps_by_role.get(r.role_id, [])),
        )
        for r in roles
    ]
