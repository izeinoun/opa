"""add_unique_rule_prompts_rule_type_version

Revision ID: 57b24d8e3916
Revises: f58cbaa3480c
Create Date: 2026-06-05 10:36:07.516878

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '57b24d8e3916'
down_revision: Union[str, None] = 'f58cbaa3480c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('rule_prompts', schema=None) as batch_op:
        batch_op.create_unique_constraint(
            'uq_rule_prompts_rule_type_ver',
            ['rule_id', 'prompt_type', 'version'],
        )


def downgrade() -> None:
    with op.batch_alter_table('rule_prompts', schema=None) as batch_op:
        batch_op.drop_constraint('uq_rule_prompts_rule_type_ver', type_='unique')
