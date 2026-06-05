"""Enable STR-009/010/013/014 and CHG-002/003

Revision ID: h6c9d4e3f517
Revises: g5b8c3d2e406
Create Date: 2026-06-04 00:03:00.000000

New handlers implemented for:
  STR-009  DOS in Future
  STR-010  Missing Primary Diagnosis
  STR-013  Missing Patient DOB
  STR-014  Missing Member ID
  CHG-002  Uniform Line Charges
  CHG-003  Zero Dollar Line

All are prepay-only (postpay=0 in catalog), so only enabled_prepay is set.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'h6c9d4e3f517'
down_revision: Union[str, None] = 'g5b8c3d2e406'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CODES = ('STR-009', 'STR-010', 'STR-013', 'STR-014', 'CHG-002', 'CHG-003')


def upgrade() -> None:
    placeholders = ', '.join(f"'{c}'" for c in _CODES)
    op.execute(
        f"UPDATE detector_rule_config "
        f"SET has_implementation = 1, enabled_prepay = 1 "
        f"WHERE rule_code IN ({placeholders})"
    )


def downgrade() -> None:
    placeholders = ', '.join(f"'{c}'" for c in _CODES)
    op.execute(
        f"UPDATE detector_rule_config "
        f"SET has_implementation = 0, enabled_prepay = 0 "
        f"WHERE rule_code IN ({placeholders})"
    )
