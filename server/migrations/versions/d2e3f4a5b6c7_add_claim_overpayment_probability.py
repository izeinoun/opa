"""add claims.overpayment_probability (Stage 2 claim predictor output)

Plain add → native ALTER (no batch rebuild). Nullable, no server_default — the
claim-scoring pass populates it; unscored claims stay NULL and the EV funnel
falls back to the provider RF score.

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-09-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd2e3f4a5b6c7'
down_revision: Union[str, None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("claims", sa.Column("overpayment_probability", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("claims", "overpayment_probability")
