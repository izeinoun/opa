"""Enable STR-008 for pre-pay pipeline

Revision ID: g5b8c3d2e406
Revises: f4a7b2c1d395
Create Date: 2026-06-04 00:02:00.000000

STR-008 (Missing Date of Service) now has a live handler.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'g5b8c3d2e406'
down_revision: Union[str, None] = 'f4a7b2c1d395'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE detector_rule_config "
        "SET has_implementation = 1, enabled_prepay = 1 "
        "WHERE rule_code = 'STR-008'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE detector_rule_config "
        "SET has_implementation = 0, enabled_prepay = 0 "
        "WHERE rule_code = 'STR-008'"
    )
