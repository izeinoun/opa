"""Enable STR-012 for pre-pay pipeline

Revision ID: f4a7b2c1d395
Revises: e3f6a0b1c924
Create Date: 2026-06-04 00:01:00.000000

STR-012 (Charge Total Mismatch) now has a live handler. Enable it for
pre-pay (postpay remains false — the rule is postpay=False in the catalog).
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'f4a7b2c1d395'
down_revision: Union[str, None] = 'e3f6a0b1c924'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE detector_rule_config "
        "SET has_implementation = 1, enabled_prepay = 1 "
        "WHERE rule_code = 'STR-012'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE detector_rule_config "
        "SET has_implementation = 0, enabled_prepay = 0 "
        "WHERE rule_code = 'STR-012'"
    )
