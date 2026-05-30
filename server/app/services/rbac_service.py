"""RBAC helpers — compute roles + app access for a user.

This is purely the data layer. Service-layer enforcement (e.g. requiring an
'admin' role to mutate config, or rejecting requests when the user has no
role mapping to the calling app) is wired in separately, on top of this.
"""
from __future__ import annotations

from typing import List, Optional, Set
from uuid import uuid4
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.workflow import App, OpaUser, Role, RoleApp, UserRole


# Priority order for picking the "primary" role when a user has multiple
# (used to populate the legacy opa_users.role column — which is a cache of
# the user's effective primary role for backward compat with code that still
# reads .role directly).
_ROLE_PRIORITY = [
    "admin",
    "supervisor",
    "siu_investigator",
    "recoupment_specialist",
    "analyst",
    "specialist",
    "system",
]


def _pick_primary(role_names: set[str]) -> str:
    for r in _ROLE_PRIORITY:
        if r in role_names:
            return r
    if role_names:
        return sorted(role_names)[0]
    return ""


class RBACService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _sync_legacy_role_column(self, user_id: str) -> None:
        """Keep opa_users.role consistent with user_roles so the legacy
        single-role column reflects the user's highest-priority current role.
        Called on every assign/revoke. The column is no longer the source of
        truth; it's a denormalized cache for code that hasn't been migrated
        to user_roles yet."""
        names = await self.get_role_names_for_user(user_id)
        primary = _pick_primary(names)
        user = (await self.session.execute(
            select(OpaUser).where(OpaUser.user_id == user_id)
        )).scalar_one_or_none()
        if user is None:
            return
        if user.role != primary:
            user.role = primary
            user.updated_at = datetime.utcnow().isoformat()

    # ── Reads ─────────────────────────────────────────────────────────────

    async def get_roles_for_user(self, user_id: str) -> List[Role]:
        stmt = (
            select(Role)
            .join(UserRole, UserRole.role_id == Role.role_id)
            .where(UserRole.user_id == user_id)
            .order_by(Role.role_name)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_apps_for_user(self, user_id: str) -> List[App]:
        """The full set of apps a user has access to via any of their roles."""
        stmt = (
            select(App)
            .join(RoleApp, RoleApp.app_id == App.app_id)
            .join(UserRole, UserRole.role_id == RoleApp.role_id)
            .where(UserRole.user_id == user_id)
            .where(App.is_active == True)  # noqa: E712
            .distinct()
            .order_by(App.app_name)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_app_names_for_user(self, user_id: str) -> Set[str]:
        apps = await self.get_apps_for_user(user_id)
        return {a.app_name for a in apps}

    async def user_can_access_app(self, user_id: str, app_name: str) -> bool:
        names = await self.get_app_names_for_user(user_id)
        return app_name in names

    async def get_role_names_for_user(self, user_id: str) -> Set[str]:
        roles = await self.get_roles_for_user(user_id)
        return {r.role_name for r in roles}

    async def user_has_role(self, user_id: str, role_name: str) -> bool:
        return role_name in (await self.get_role_names_for_user(user_id))

    # ── Listing ──────────────────────────────────────────────────────────

    async def list_apps(self) -> List[App]:
        res = await self.session.execute(
            select(App).where(App.is_active == True).order_by(App.app_name)  # noqa: E712
        )
        return list(res.scalars().all())

    async def list_roles(self) -> List[Role]:
        res = await self.session.execute(select(Role).order_by(Role.role_name))
        return list(res.scalars().all())

    # ── Mutations ────────────────────────────────────────────────────────

    async def assign_role(
        self,
        user_id: str,
        role_id: str,
        granted_by_user_id: Optional[str] = None,
    ) -> UserRole:
        """Grant a role to a user. Idempotent — returns the existing row
        unchanged if the assignment already exists."""
        existing = await self.session.execute(
            select(UserRole).where(
                UserRole.user_id == user_id,
                UserRole.role_id == role_id,
            )
        )
        row = existing.scalar_one_or_none()
        if row is not None:
            return row
        row = UserRole(
            user_id=user_id,
            role_id=role_id,
            granted_at=datetime.utcnow().isoformat(),
            granted_by_user_id=granted_by_user_id,
        )
        self.session.add(row)
        await self.session.flush()
        await self._sync_legacy_role_column(user_id)
        return row

    async def revoke_role(self, user_id: str, role_id: str) -> bool:
        """Remove a role from a user. Returns True if a row was removed."""
        res = await self.session.execute(
            select(UserRole).where(
                UserRole.user_id == user_id,
                UserRole.role_id == role_id,
            )
        )
        row = res.scalar_one_or_none()
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.flush()
        await self._sync_legacy_role_column(user_id)
        return True
