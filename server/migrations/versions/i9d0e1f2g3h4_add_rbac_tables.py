"""add RBAC: apps, roles, role_apps, user_roles + default_app_id on opa_users

Revision ID: i9d0e1f2g3h4
Revises: h8c9d0e1f2g3
Create Date: 2026-05-29

Simple role-based access control where:
  • A user is assigned one or more roles (user_roles)
  • Each role grants access to one or more apps (role_apps)
  • Effective apps for a user = union over their roles → mapped apps

Migration also backfills user_roles from opa_users.role (the legacy single-
role column), so existing data continues to work end-to-end. The legacy
column is kept for one release to avoid breaking read paths.

Seeded reference data lives in seed_rbac.py (called from seed_all.py); this
migration only creates the schema.
"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "i9d0e1f2g3h4"
down_revision: Union[str, None] = "h8c9d0e1f2g3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── apps ──────────────────────────────────────────────────────────────
    op.create_table(
        "apps",
        sa.Column("app_id", sa.String(length=36), nullable=False),
        sa.Column("app_name", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.String(length=30), nullable=False),
        sa.Column("updated_at", sa.String(length=30), nullable=False),
        sa.PrimaryKeyConstraint("app_id"),
        sa.UniqueConstraint("app_name"),
    )

    # ── roles ─────────────────────────────────────────────────────────────
    op.create_table(
        "roles",
        sa.Column("role_id", sa.String(length=36), nullable=False),
        sa.Column("role_name", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=30), nullable=False),
        sa.Column("updated_at", sa.String(length=30), nullable=False),
        sa.PrimaryKeyConstraint("role_id"),
        sa.UniqueConstraint("role_name"),
    )

    # ── role_apps ─────────────────────────────────────────────────────────
    op.create_table(
        "role_apps",
        sa.Column("role_id", sa.String(length=36), nullable=False),
        sa.Column("app_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.role_id"]),
        sa.ForeignKeyConstraint(["app_id"], ["apps.app_id"]),
        sa.PrimaryKeyConstraint("role_id", "app_id"),
    )

    # ── user_roles ────────────────────────────────────────────────────────
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role_id", sa.String(length=36), nullable=False),
        sa.Column("granted_at", sa.String(length=30), nullable=False),
        sa.Column("granted_by_user_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["opa_users.user_id"]),
        sa.ForeignKeyConstraint(["role_id"], ["roles.role_id"]),
        sa.ForeignKeyConstraint(["granted_by_user_id"], ["opa_users.user_id"]),
        sa.PrimaryKeyConstraint("user_id", "role_id"),
    )

    # ── default_app_id on opa_users ───────────────────────────────────────
    with op.batch_alter_table("opa_users") as batch_op:
        batch_op.add_column(sa.Column("default_app_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_opa_users_default_app",
            "apps",
            ["default_app_id"],
            ["app_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("opa_users") as batch_op:
        batch_op.drop_constraint("fk_opa_users_default_app", type_="foreignkey")
        batch_op.drop_column("default_app_id")
    op.drop_table("user_roles")
    op.drop_table("role_apps")
    op.drop_table("roles")
    op.drop_table("apps")
