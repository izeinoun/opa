"""User picker + RBAC read + mutation endpoints.

Powers both the per-app user pickers (read paths) and the central IAM
admin UI (mutation paths: create/update user, assign/revoke roles).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.workflow import App, OpaUser, Role, RoleApp, UserRole
from ..schemas.prepay_schemas import (
    AppCreate,
    AppOut,
    AppUpdate,
    RoleCreate,
    RoleOut,
    RoleUpdate,
    UserCreate,
    UserOut,
    UserUpdate,
)
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
        username=u.username,
        email=u.email,
        role=u.role,
        is_active=u.is_active,
        initials=u.initials,
        color_hex=u.color_hex,
        specialty=u.specialty,
        supervisor_id=u.supervisor_id,
        roles=[r.role_name for r in roles],
        apps=[a.app_name for a in apps],
        default_app=default_app_name,
        default_app_id=u.default_app_id,
    )


@router.get("", response_model=List[UserOut])
async def list_users(
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
) -> List[UserOut]:
    stmt = select(OpaUser).order_by(OpaUser.full_name)
    if not include_inactive:
        stmt = stmt.where(OpaUser.is_active == True)  # noqa: E712
    res = await db.execute(stmt)
    rbac = RBACService(db)
    return [await _user_to_out(rbac, u, db) for u in res.scalars().all()]


@router.post("", response_model=UserOut, status_code=201)
async def create_user(
    body: UserCreate,
    actor_user_id: Optional[str] = Query(None, alias="actor_user_id"),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    # Username + email uniqueness
    dup = (await db.execute(
        select(OpaUser).where(OpaUser.username == body.username)
    )).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail="Username already exists")

    now = datetime.utcnow().isoformat()
    user = OpaUser(
        user_id=str(uuid.uuid4()),
        username=body.username,
        full_name=body.full_name,
        email=body.email,
        role=body.role,
        initials=body.initials,
        color_hex=body.color_hex,
        specialty=body.specialty,
        default_app_id=body.default_app_id,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    await db.flush()

    rbac = RBACService(db)
    for role_id in body.role_ids:
        await rbac.assign_role(user.user_id, role_id, granted_by_user_id=actor_user_id)

    await db.commit()
    return await _user_to_out(rbac, user, db)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    user = (await db.execute(
        select(OpaUser).where(OpaUser.user_id == user_id)
    )).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if body.full_name is not None:      user.full_name = body.full_name
    if body.email is not None:          user.email = body.email
    if body.initials is not None:       user.initials = body.initials
    if body.color_hex is not None:      user.color_hex = body.color_hex
    if body.specialty is not None:      user.specialty = body.specialty
    if body.is_active is not None:      user.is_active = body.is_active
    if body.default_app_id is not None: user.default_app_id = body.default_app_id
    user.updated_at = datetime.utcnow().isoformat()
    await db.commit()
    return await _user_to_out(RBACService(db), user, db)


# ── RBAC mutations on a user ─────────────────────────────────────────────

@router.get("/{user_id}/roles", response_model=List[RoleOut])
async def list_user_roles(
    user_id: str, db: AsyncSession = Depends(get_db)
) -> List[RoleOut]:
    user = (await db.execute(
        select(OpaUser).where(OpaUser.user_id == user_id)
    )).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    rbac = RBACService(db)
    roles = await rbac.get_roles_for_user(user_id)
    # Hydrate each role with its apps
    ra_res = await db.execute(
        select(RoleApp.role_id, App.app_name)
        .join(App, App.app_id == RoleApp.app_id)
    )
    apps_by_role: dict[str, list[str]] = {}
    for rid, name in ra_res.all():
        apps_by_role.setdefault(rid, []).append(name)
    return [
        RoleOut(id=r.role_id, name=r.role_name, description=r.description,
                apps=sorted(apps_by_role.get(r.role_id, [])))
        for r in roles
    ]


@router.post("/{user_id}/roles/{role_id}", response_model=UserOut, status_code=201)
async def assign_role_to_user(
    user_id: str,
    role_id: str,
    actor_user_id: Optional[str] = Query(None, alias="actor_user_id"),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    user = (await db.execute(
        select(OpaUser).where(OpaUser.user_id == user_id)
    )).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    role = (await db.execute(
        select(Role).where(Role.role_id == role_id)
    )).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    rbac = RBACService(db)
    await rbac.assign_role(user_id, role_id, granted_by_user_id=actor_user_id)
    await db.commit()
    return await _user_to_out(rbac, user, db)


@router.delete("/{user_id}/roles/{role_id}", response_model=UserOut)
async def revoke_role_from_user(
    user_id: str,
    role_id: str,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    user = (await db.execute(
        select(OpaUser).where(OpaUser.user_id == user_id)
    )).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    rbac = RBACService(db)
    removed = await rbac.revoke_role(user_id, role_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Role assignment not found")
    await db.commit()
    return await _user_to_out(rbac, user, db)


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


async def _hydrate_role(role: Role, db: AsyncSession) -> RoleOut:
    res = await db.execute(
        select(App.app_name)
        .join(RoleApp, RoleApp.app_id == App.app_id)
        .where(RoleApp.role_id == role.role_id)
        .order_by(App.app_name)
    )
    return RoleOut(
        id=role.role_id, name=role.role_name, description=role.description,
        apps=[row[0] for row in res.all()],
    )


# ── Apps CRUD ────────────────────────────────────────────────────────────

@apps_router.get("", response_model=List[AppOut])
async def list_apps(
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
) -> List[AppOut]:
    stmt = select(App).order_by(App.app_name)
    if not include_inactive:
        stmt = stmt.where(App.is_active == True)  # noqa: E712
    res = await db.execute(stmt)
    return [
        AppOut(id=a.app_id, name=a.app_name, description=a.description, is_active=a.is_active)
        for a in res.scalars().all()
    ]


@apps_router.post("", response_model=AppOut, status_code=201)
async def create_app(body: AppCreate, db: AsyncSession = Depends(get_db)) -> AppOut:
    dup = (await db.execute(
        select(App).where(App.app_name == body.name)
    )).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail="App name already exists")
    now = datetime.utcnow().isoformat()
    a = App(
        app_id=str(uuid.uuid4()),
        app_name=body.name,
        description=body.description,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(a)
    await db.commit()
    return AppOut(id=a.app_id, name=a.app_name, description=a.description, is_active=a.is_active)


@apps_router.patch("/{app_id}", response_model=AppOut)
async def update_app(
    app_id: str, body: AppUpdate, db: AsyncSession = Depends(get_db)
) -> AppOut:
    a = (await db.execute(
        select(App).where(App.app_id == app_id)
    )).scalar_one_or_none()
    if a is None:
        raise HTTPException(status_code=404, detail="App not found")
    if body.name is not None:        a.app_name = body.name
    if body.description is not None: a.description = body.description
    if body.is_active is not None:   a.is_active = body.is_active
    a.updated_at = datetime.utcnow().isoformat()
    await db.commit()
    return AppOut(id=a.app_id, name=a.app_name, description=a.description, is_active=a.is_active)


# ── Roles CRUD ───────────────────────────────────────────────────────────

@roles_router.get("", response_model=List[RoleOut])
async def list_roles(db: AsyncSession = Depends(get_db)) -> List[RoleOut]:
    role_res = await db.execute(select(Role).order_by(Role.role_name))
    return [await _hydrate_role(r, db) for r in role_res.scalars().all()]


@roles_router.post("", response_model=RoleOut, status_code=201)
async def create_role(body: RoleCreate, db: AsyncSession = Depends(get_db)) -> RoleOut:
    dup = (await db.execute(
        select(Role).where(Role.role_name == body.name)
    )).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail="Role name already exists")
    now = datetime.utcnow().isoformat()
    role = Role(
        role_id=str(uuid.uuid4()),
        role_name=body.name,
        description=body.description,
        created_at=now,
        updated_at=now,
    )
    db.add(role)
    await db.flush()
    # Optional initial app grants
    for app_id in body.app_ids:
        a = (await db.execute(
            select(App).where(App.app_id == app_id)
        )).scalar_one_or_none()
        if a is None:
            continue
        db.add(RoleApp(role_id=role.role_id, app_id=app_id))
    await db.commit()
    return await _hydrate_role(role, db)


@roles_router.patch("/{role_id}", response_model=RoleOut)
async def update_role(
    role_id: str, body: RoleUpdate, db: AsyncSession = Depends(get_db)
) -> RoleOut:
    role = (await db.execute(
        select(Role).where(Role.role_id == role_id)
    )).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    if body.name is not None:        role.role_name = body.name
    if body.description is not None: role.description = body.description
    role.updated_at = datetime.utcnow().isoformat()
    await db.commit()
    return await _hydrate_role(role, db)


@roles_router.post("/{role_id}/apps/{app_id}", response_model=RoleOut, status_code=201)
async def grant_app_to_role(
    role_id: str, app_id: str, db: AsyncSession = Depends(get_db)
) -> RoleOut:
    role = (await db.execute(
        select(Role).where(Role.role_id == role_id)
    )).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    app_row = (await db.execute(
        select(App).where(App.app_id == app_id)
    )).scalar_one_or_none()
    if app_row is None:
        raise HTTPException(status_code=404, detail="App not found")
    existing = (await db.execute(
        select(RoleApp).where(
            RoleApp.role_id == role_id,
            RoleApp.app_id == app_id,
        )
    )).scalar_one_or_none()
    if existing is None:
        db.add(RoleApp(role_id=role_id, app_id=app_id))
        await db.commit()
    return await _hydrate_role(role, db)


@roles_router.delete("/{role_id}/apps/{app_id}", response_model=RoleOut)
async def revoke_app_from_role(
    role_id: str, app_id: str, db: AsyncSession = Depends(get_db)
) -> RoleOut:
    role = (await db.execute(
        select(Role).where(Role.role_id == role_id)
    )).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    existing = (await db.execute(
        select(RoleApp).where(
            RoleApp.role_id == role_id,
            RoleApp.app_id == app_id,
        )
    )).scalar_one_or_none()
    if existing is None:
        raise HTTPException(status_code=404, detail="Role does not grant this app")
    await db.delete(existing)
    await db.commit()
    return await _hydrate_role(role, db)
