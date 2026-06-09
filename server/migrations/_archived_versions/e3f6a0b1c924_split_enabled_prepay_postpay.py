"""Split enabled into enabled_prepay + enabled_postpay

Revision ID: e3f6a0b1c924
Revises: d2e5f9a3b418
Create Date: 2026-06-04 00:00:00.000000

Replaces the single `enabled` column on detector_rule_config with two
per-pipeline operator toggles: enabled_prepay and enabled_postpay.

Migration logic:
  enabled_prepay  = old enabled AND prepay   (was on, and structurally capable)
  enabled_postpay = old enabled AND postpay
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'e3f6a0b1c924'
down_revision: Union[str, None] = 'd2e5f9a3b418'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'detector_rule_config',
        sa.Column('enabled_prepay', sa.Boolean(), nullable=False, server_default='0'),
    )
    op.add_column(
        'detector_rule_config',
        sa.Column('enabled_postpay', sa.Boolean(), nullable=False, server_default='0'),
    )
    op.execute("""
        UPDATE detector_rule_config
        SET
            enabled_prepay  = CASE WHEN enabled = 1 AND prepay  = 1 THEN 1 ELSE 0 END,
            enabled_postpay = CASE WHEN enabled = 1 AND postpay = 1 THEN 1 ELSE 0 END
    """)
    with op.batch_alter_table('detector_rule_config') as batch_op:
        batch_op.drop_column('enabled')


def downgrade() -> None:
    op.add_column(
        'detector_rule_config',
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='0'),
    )
    op.execute("""
        UPDATE detector_rule_config
        SET enabled = CASE WHEN enabled_prepay = 1 OR enabled_postpay = 1 THEN 1 ELSE 0 END
    """)
    with op.batch_alter_table('detector_rule_config') as batch_op:
        batch_op.drop_column('enabled_prepay')
        batch_op.drop_column('enabled_postpay')
