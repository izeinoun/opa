"""Walkthrough (new-user tour) endpoint.

GET /api/walkthrough?app=payguard → the role-tailored spotlight tour for the
current user in that app. Content + ordering live in `walkthrough_service`;
this route only resolves *who* is asking (their RBAC roles + accessible apps)
and hands off to the composer.

Open to any authenticated caller — a tour is guidance, not data, and the
composer already scopes cross-app links to what the caller can reach.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.workflow import OpaUser
from ..schemas.walkthrough import Tour
from ..services.rbac_service import RBACService
from ..services.walkthrough_service import build_tour

router = APIRouter(prefix="/api/walkthrough", tags=["walkthrough"])

# Apps the composer knows how to tour. Requests for anything else still return
# a minimal intro/outro shell rather than 404, so a new SPA works day one.
_KNOWN_APPS = ("payguard", "claimguard", "siu", "intake", "assistant", "iam")


@router.get("", response_model=Tour)
async def get_walkthrough(
    app: str = Query("payguard", description="Which app's tour to return"),
    user: OpaUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Tour:
    rbac = RBACService(db)
    role_names = await rbac.get_role_names_for_user(user.user_id)
    accessible_apps = await rbac.get_app_names_for_user(user.user_id)

    # Fall back to the legacy single-role column if RBAC tables are empty
    # (e.g. a partially-seeded DB) so the tour still tailors sensibly.
    if not role_names and user.role:
        role_names = {user.role}

    return build_tour(app=app, role_names=role_names, accessible_apps=accessible_apps)
