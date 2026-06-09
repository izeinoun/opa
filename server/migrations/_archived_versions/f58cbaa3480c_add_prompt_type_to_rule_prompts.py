"""add_prompt_type_to_rule_prompts

Revision ID: f58cbaa3480c
Revises: 18a3071f0e76
Create Date: 2026-06-05 10:30:01.171218

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f58cbaa3480c'
down_revision: Union[str, None] = '18a3071f0e76'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('rule_prompts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('prompt_type', sa.String(length=30), server_default='evaluation', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('rule_prompts', schema=None) as batch_op:
        batch_op.drop_column('prompt_type')
