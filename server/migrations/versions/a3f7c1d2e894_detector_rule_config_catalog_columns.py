"""add catalog columns to detector_rule_config

Revision ID: a3f7c1d2e894
Revises: 68c9293e51e1
Create Date: 2026-06-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3f7c1d2e894'
down_revision: Union[str, None] = '68c9293e51e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('detector_rule_config',
        sa.Column('layer', sa.String(length=60), nullable=True))
    op.add_column('detector_rule_config',
        sa.Column('layer_order', sa.Integer(), nullable=True))
    op.add_column('detector_rule_config',
        sa.Column('applies_to', sa.String(length=30), server_default='Both', nullable=True))
    op.add_column('detector_rule_config',
        sa.Column('default_disposition', sa.String(length=30), server_default='suspend_review', nullable=True))
    op.add_column('detector_rule_config',
        sa.Column('has_implementation', sa.Boolean(), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('detector_rule_config', 'has_implementation')
    op.drop_column('detector_rule_config', 'default_disposition')
    op.drop_column('detector_rule_config', 'applies_to')
    op.drop_column('detector_rule_config', 'layer_order')
    op.drop_column('detector_rule_config', 'layer')
