"""expand ml_training_config with the full RandomForest tuning surface

Revision ID: l2g3h4i5j6k7
Revises: k1f2g3h4i5j6
Create Date: 2026-05-30

Adds the hyperparameters engineers typically tune on a RandomForestClassifier
beyond the three already stored (n_estimators, max_depth, min_samples_leaf):

  - min_samples_split  : min samples required to split an internal node
  - max_features       : features considered per split ('sqrt'|'log2'|'none'|float-as-str)
  - max_leaf_nodes     : cap on leaves per tree (NULL = unlimited)
  - bootstrap          : sample-with-replacement per tree
  - class_weight       : NULL | 'balanced' | 'balanced_subsample'
  - criterion          : 'gini' | 'entropy' | 'log_loss'

Defaults mirror sklearn's RandomForestClassifier defaults so existing rows keep
their current behavior.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "l2g3h4i5j6k7"
down_revision: Union[str, None] = "k1f2g3h4i5j6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ml_training_config") as batch_op:
        batch_op.add_column(sa.Column(
            "min_samples_split", sa.Integer(), nullable=False, server_default="2"
        ))
        batch_op.add_column(sa.Column(
            "max_features", sa.String(length=20), nullable=True, server_default="sqrt"
        ))
        batch_op.add_column(sa.Column("max_leaf_nodes", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column(
            "bootstrap", sa.Boolean(), nullable=False, server_default=sa.true()
        ))
        batch_op.add_column(sa.Column("class_weight", sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column(
            "criterion", sa.String(length=20), nullable=False, server_default="gini"
        ))


def downgrade() -> None:
    with op.batch_alter_table("ml_training_config") as batch_op:
        batch_op.drop_column("criterion")
        batch_op.drop_column("class_weight")
        batch_op.drop_column("bootstrap")
        batch_op.drop_column("max_leaf_nodes")
        batch_op.drop_column("max_features")
        batch_op.drop_column("min_samples_split")
