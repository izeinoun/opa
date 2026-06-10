"""Add submitted_member_number and submitted_patient_dob to claims

Revision ID: i7d0e5f4a628
Revises: h6c9d4e3f517
Create Date: 2026-06-04 00:04:00.000000

Stores the raw values from the submitted document (PDF or X12) before member
resolution. STR-013 and STR-014 check these to detect missing data in the
actual submission rather than in the resolved member record.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'i7d0e5f4a628'
down_revision: Union[str, None] = 'h6c9d4e3f517'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('claims') as batch_op:
        batch_op.add_column(sa.Column('submitted_member_number', sa.String(50), nullable=True))
        batch_op.add_column(sa.Column('submitted_patient_dob', sa.String(10), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('claims') as batch_op:
        batch_op.drop_column('submitted_patient_dob')
        batch_op.drop_column('submitted_member_number')
