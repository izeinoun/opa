"""Add typical_setting and valid_as_inpatient_pdx to icd_codes

Revision ID: k9f2g1h4i837
Revises: j8e1f0g5h726
Create Date: 2026-06-04 00:06:00.000000

typical_setting: inpatient | outpatient | both | ed
valid_as_inpatient_pdx: False for codes CMS MCE flags as unacceptable PDX
  (history/aftercare, causative-organism-only, wellness, manifestation-only)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'k9f2g1h4i837'
down_revision: Union[str, None] = 'j8e1f0g5h726'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('icd_codes') as b:
        b.add_column(sa.Column('typical_setting',        sa.String(20),  nullable=False, server_default='both'))
        b.add_column(sa.Column('valid_as_inpatient_pdx', sa.Boolean(),   nullable=False, server_default='1'))


def downgrade() -> None:
    with op.batch_alter_table('icd_codes') as b:
        b.drop_column('valid_as_inpatient_pdx')
        b.drop_column('typical_setting')
