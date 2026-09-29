"""add brier_raw / brier_calibrated to ml_model_versions

Stage 1's output is a calibrated probability consumed as a feature, so calibration
quality (Brier) + AUC are its primary metrics. Persist Brier per version.

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-09-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e3f4a5b6c7d8'
down_revision: Union[str, None] = 'd2e3f4a5b6c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ml_model_versions", sa.Column("brier_raw", sa.Float(), nullable=True))
    op.add_column("ml_model_versions", sa.Column("brier_calibrated", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("ml_model_versions", "brier_calibrated")
    op.drop_column("ml_model_versions", "brier_raw")
