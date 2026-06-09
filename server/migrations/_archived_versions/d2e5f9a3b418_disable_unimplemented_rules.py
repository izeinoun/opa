"""disable stub rules pending implementation

Revision ID: d2e5f9a3b418
Revises: c1d4e8f2a037
Create Date: 2026-06-03 00:03:00.000000

Only the 8 rules backed by a live detector remain enabled.
All catalog stubs are disabled until their detector is built.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'd2e5f9a3b418'
down_revision: Union[str, None] = 'c1d4e8f2a037'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ACTIVE = (
    'DET-01', 'DET-02', 'DET-04', 'DET-06',
    'DET-08', 'DET-09', 'FWA-02', 'FWA-03',
)


def upgrade() -> None:
    active = ', '.join(f"'{c}'" for c in _ACTIVE)
    op.execute(
        f"UPDATE detector_rule_config SET enabled = 0 WHERE rule_code NOT IN ({active})"
    )


def downgrade() -> None:
    op.execute("UPDATE detector_rule_config SET enabled = 1")
