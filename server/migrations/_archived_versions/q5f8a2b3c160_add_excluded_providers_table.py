"""add_excluded_providers_table

Imports the CMS/OIG LEIE (List of Excluded Individuals/Entities) as a
reference table screened by DET-08. Only NPI-bearing rows are loaded by the
seed; `npi` is the deterministic join key and carries an index.

Revision ID: q5f8a2b3c160
Revises: 9c28676855fb
Create Date: 2026-06-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'q5f8a2b3c160'
down_revision: Union[str, None] = '9c28676855fb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'excluded_providers',
        sa.Column('excluded_provider_id', sa.String(length=36), nullable=False),
        sa.Column('npi', sa.String(length=20), nullable=False),
        sa.Column('last_name', sa.String(length=255), nullable=True),
        sa.Column('first_name', sa.String(length=255), nullable=True),
        sa.Column('middle_name', sa.String(length=255), nullable=True),
        sa.Column('business_name', sa.String(length=255), nullable=True),
        sa.Column('general_category', sa.String(length=100), nullable=True),
        sa.Column('specialty', sa.String(length=100), nullable=True),
        sa.Column('upin', sa.String(length=20), nullable=True),
        sa.Column('dob', sa.String(length=10), nullable=True),
        sa.Column('address', sa.String(length=255), nullable=True),
        sa.Column('city', sa.String(length=100), nullable=True),
        sa.Column('state', sa.String(length=10), nullable=True),
        sa.Column('zip_code', sa.String(length=15), nullable=True),
        sa.Column('exclusion_type', sa.String(length=20), nullable=True),
        sa.Column('exclusion_date', sa.String(length=10), nullable=True),
        sa.Column('reinstate_date', sa.String(length=10), nullable=True),
        sa.Column('waiver_date', sa.String(length=10), nullable=True),
        sa.Column('waiver_state', sa.String(length=10), nullable=True),
        sa.Column('source', sa.String(length=100), server_default='OIG LEIE', nullable=False),
        sa.Column('created_at', sa.String(length=30), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('excluded_provider_id'),
    )
    op.create_index(
        op.f('ix_excluded_providers_npi'), 'excluded_providers', ['npi'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_excluded_providers_npi'), table_name='excluded_providers')
    op.drop_table('excluded_providers')
