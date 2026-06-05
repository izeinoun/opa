"""Add triplet links, typical dx/procedures, and audit_notes to drg_codes

Revision ID: o3d6e5f4g740
Revises: n2c5d4e3f629
Create Date: 2026-06-04 00:10:00.000000

mcc_drg, base_drg    — soft triplet links (no FK)
typical_principal_dx — JSON array of representative PDX ICD codes
typical_procedures   — JSON array of ICD-10-PCS prefixes
audit_notes          — audit-specific guidance (separate from clinical_criteria)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'o3d6e5f4g740'
down_revision: Union[str, None] = 'n2c5d4e3f629'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('drg_codes') as b:
        b.add_column(sa.Column('mcc_drg',             sa.String(10), nullable=True))
        b.add_column(sa.Column('base_drg',            sa.String(10), nullable=True))
        b.add_column(sa.Column('typical_principal_dx', sa.Text(),    nullable=True))
        b.add_column(sa.Column('typical_procedures',   sa.Text(),    nullable=True))
        b.add_column(sa.Column('audit_notes',          sa.Text(),    nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('drg_codes') as b:
        b.drop_column('audit_notes')
        b.drop_column('typical_procedures')
        b.drop_column('typical_principal_dx')
        b.drop_column('base_drg')
        b.drop_column('mcc_drg')
