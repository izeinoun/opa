"""add capacity knobs to ml_training_config

Adds evaluation_population_size + team_audit_capacity to ml_training_config,
backing the 'capacity_bounded_f2' decision-threshold mode and the operational
capacity metrics returned on every trial run.

Plain adds → native ALTER (no batch rebuild). Both carry a server_default so
existing singleton rows and raw-SQL seeds that omit them satisfy NOT NULL.

Revision ID: c1d2e3f4a5b6
Revises: eb3909b62b39
Create Date: 2026-09-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, None] = 'eb3909b62b39'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ml_training_config",
        sa.Column(
            "evaluation_population_size",
            sa.Integer(),
            nullable=False,
            server_default="1000",
        ),
    )
    op.add_column(
        "ml_training_config",
        sa.Column(
            "team_audit_capacity",
            sa.Integer(),
            nullable=False,
            server_default="50",
        ),
    )


def downgrade() -> None:
    op.drop_column("ml_training_config", "team_audit_capacity")
    op.drop_column("ml_training_config", "evaluation_population_size")
