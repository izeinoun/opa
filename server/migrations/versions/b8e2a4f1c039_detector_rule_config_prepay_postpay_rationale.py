"""add prepay, postpay, rationale to detector_rule_config

Revision ID: b8e2a4f1c039
Revises: a3f7c1d2e894
Create Date: 2026-06-03 00:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8e2a4f1c039'
down_revision: Union[str, None] = 'a3f7c1d2e894'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('detector_rule_config',
        sa.Column('prepay', sa.Boolean(), server_default='0', nullable=False))
    op.add_column('detector_rule_config',
        sa.Column('postpay', sa.Boolean(), server_default='0', nullable=False))
    op.add_column('detector_rule_config',
        sa.Column('rationale', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('detector_rule_config', 'rationale')
    op.drop_column('detector_rule_config', 'postpay')
    op.drop_column('detector_rule_config', 'prepay')
