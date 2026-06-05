"""Add applicable_settings and rename valid_as_inpatient_pdx to valid_as_primary_dx

Revision ID: l0a3b1c2d948
Revises: k9f2g1h4i837
Create Date: 2026-06-04 00:07:00.000000

applicable_settings: JSON array of all care settings where this ICD code
  meaningfully appears (inpatient, outpatient, professional, snf, irf,
  home_health, sleep_inlab, sleep_home, ed).

valid_as_primary_dx replaces valid_as_inpatient_pdx — the concept applies
  across settings (outpatient first-listed, inpatient PDX, SNF primary, etc.).
  Existing data is migrated: valid_as_inpatient_pdx values carry over.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'l0a3b1c2d948'
down_revision: Union[str, None] = 'k9f2g1h4i837'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('icd_codes') as b:
        b.add_column(sa.Column('applicable_settings', sa.Text(), nullable=True))
        b.add_column(sa.Column('valid_as_primary_dx', sa.Boolean(), nullable=False, server_default='1'))
    # Carry over existing values
    op.execute("""
        UPDATE icd_codes
        SET valid_as_primary_dx = valid_as_inpatient_pdx
    """)
    with op.batch_alter_table('icd_codes') as b:
        b.drop_column('valid_as_inpatient_pdx')


def downgrade() -> None:
    with op.batch_alter_table('icd_codes') as b:
        b.add_column(sa.Column('valid_as_inpatient_pdx', sa.Boolean(), nullable=False, server_default='1'))
    op.execute("UPDATE icd_codes SET valid_as_inpatient_pdx = valid_as_primary_dx")
    with op.batch_alter_table('icd_codes') as b:
        b.drop_column('valid_as_primary_dx')
        b.drop_column('applicable_settings')
