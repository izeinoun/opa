"""Add typical_drg to icd_codes

Revision ID: n2c5d4e3f629
Revises: m1b4c3d2e519
Create Date: 2026-06-04 00:09:00.000000

Soft reference to drg_codes.code — the DRG an ICD-10 code most commonly
groups to when it is the inpatient principal diagnosis. NULL for secondary,
outpatient-only, and ambiguous codes.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'n2c5d4e3f629'
down_revision: Union[str, None] = 'm1b4c3d2e519'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('icd_codes') as b:
        b.add_column(sa.Column('typical_drg', sa.String(10), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('icd_codes') as b:
        b.drop_column('typical_drg')
