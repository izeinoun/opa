"""remove catalog rules superseded by implemented DET detectors

Revision ID: c1d4e8f2a037
Revises: b8e2a4f1c039
Create Date: 2026-06-03 00:02:00.000000

Removed rules and their DET equivalents:
  DUP-001/002/003/004  → DET-01 (duplicate billing)
  ELG-001/002          → DET-02 (retro eligibility)
  CHG-001              → DET-04 (fee schedule mispricing)
  BND-001/002/004/005/009 + MUE-001/002/003 → DET-06 (NCCI/MUE)
  PRV-006              → DET-08 (excluded provider)
  COD-006 + MED-001 + PRV-004 → DET-09 / FWA-02 (coding errors / credential mismatch)
  STR-011              → FWA-03 (POS mismatch)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1d4e8f2a037'
down_revision: Union[str, None] = 'b8e2a4f1c039'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_REMOVED = (
    'DUP-001', 'DUP-002', 'DUP-003', 'DUP-004',
    'ELG-001', 'ELG-002',
    'CHG-001',
    'BND-001', 'BND-002', 'BND-004', 'BND-005', 'BND-009',
    'MUE-001', 'MUE-002', 'MUE-003',
    'PRV-006',
    'COD-006',
    'MED-001',
    'PRV-004',
    'STR-011',
)


def upgrade() -> None:
    placeholders = ', '.join(f"'{code}'" for code in _REMOVED)
    op.execute(f"DELETE FROM detector_rule_config WHERE rule_code IN ({placeholders})")


def downgrade() -> None:
    # Rows are re-inserted by seed_defaults on next startup if codes are
    # added back to _RULE_DEFAULTS; no data to restore here.
    pass
