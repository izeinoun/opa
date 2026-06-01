"""add connectors + connector_runs

Revision ID: k1f2g3h4i5j6
Revises: j0e1f2g3h4i5
Create Date: 2026-05-30

Connector registry for platform-wide integrations (HTTP APIs, SFTP, in-
process functions, future outbound webhooks). Adapted from clearlink's
agent_tools / agent_tool_calls pattern, simplified for OPA's needs.

The connectors UI lives as a tab in the IAM admin app (admin-only).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "k1f2g3h4i5j6"
down_revision: Union[str, None] = "j0e1f2g3h4i5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "connectors",
        sa.Column("connector_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False, server_default="outbound"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("secret_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("input_schema_json", sa.Text(), nullable=True),
        sa.Column("mock_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("mock_response_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=30), nullable=False),
        sa.Column("updated_at", sa.String(length=30), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["opa_users.user_id"]),
        sa.PrimaryKeyConstraint("connector_id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_connectors_kind", "connectors", ["kind"])
    op.create_index("ix_connectors_is_active", "connectors", ["is_active"])

    op.create_table(
        "connector_runs",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("connector_id", sa.String(length=36), nullable=False),
        sa.Column("triggered_at", sa.String(length=30), nullable=False),
        sa.Column("triggered_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("input_json", sa.Text(), nullable=True),
        sa.Column("output_json", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(["connector_id"], ["connectors.connector_id"]),
        sa.ForeignKeyConstraint(["triggered_by_user_id"], ["opa_users.user_id"]),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index("ix_connector_runs_connector",
                    "connector_runs", ["connector_id"])
    op.create_index("ix_connector_runs_triggered_at",
                    "connector_runs", ["triggered_at"])


def downgrade() -> None:
    op.drop_index("ix_connector_runs_triggered_at", table_name="connector_runs")
    op.drop_index("ix_connector_runs_connector", table_name="connector_runs")
    op.drop_table("connector_runs")
    op.drop_index("ix_connectors_is_active", table_name="connectors")
    op.drop_index("ix_connectors_kind", table_name="connectors")
    op.drop_table("connectors")
