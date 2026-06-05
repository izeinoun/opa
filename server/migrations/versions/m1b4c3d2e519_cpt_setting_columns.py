"""Add typical_setting and applicable_settings to cpt_codes

Revision ID: m1b4c3d2e519
Revises: l0a3b1c2d948
Create Date: 2026-06-04 00:08:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'm1b4c3d2e519'
down_revision: Union[str, None] = 'l0a3b1c2d948'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('cpt_codes') as b:
        b.add_column(sa.Column('typical_setting',    sa.String(20), nullable=False, server_default='professional'))
        b.add_column(sa.Column('applicable_settings', sa.Text(),    nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('cpt_codes') as b:
        b.drop_column('applicable_settings')
        b.drop_column('typical_setting')
