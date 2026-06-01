"""add ml_training_config table and metric/param columns on ml_model_versions

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-29

- Adds 7 columns to ml_model_versions to hold the metrics computed by
  train_model() that were previously discarded or squatted in `notes`
  (precision_score, recall_score, f1_score, f2_score, auc_roc,
  decision_threshold) plus a training_params JSON column for lineage.
- Adds ml_training_config singleton holding admin-editable RandomForest
  hyperparameters that the trainer reads on every run.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ml_model_versions") as batch_op:
        batch_op.add_column(sa.Column(
            "training_params", sa.Text(), nullable=False, server_default="{}"
        ))
        batch_op.add_column(sa.Column("precision_score", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("recall_score", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("f1_score", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("f2_score", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("auc_roc", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("decision_threshold", sa.Float(), nullable=True))

    op.create_table(
        "ml_training_config",
        sa.Column("config_id", sa.String(length=20), nullable=False),
        sa.Column("n_estimators", sa.Integer(), nullable=False, server_default="200"),
        sa.Column("max_depth", sa.Integer(), nullable=True),
        sa.Column("min_samples_leaf", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("decision_threshold_mode", sa.String(length=20), nullable=False,
                  server_default="auto_f2"),
        sa.Column("manual_threshold", sa.Float(), nullable=True),
        sa.Column("min_auc_to_promote", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.String(length=30), nullable=False),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["opa_users.user_id"]),
        sa.PrimaryKeyConstraint("config_id"),
    )


def downgrade() -> None:
    op.drop_table("ml_training_config")
    with op.batch_alter_table("ml_model_versions") as batch_op:
        batch_op.drop_column("decision_threshold")
        batch_op.drop_column("auc_roc")
        batch_op.drop_column("f2_score")
        batch_op.drop_column("f1_score")
        batch_op.drop_column("recall_score")
        batch_op.drop_column("precision_score")
        batch_op.drop_column("training_params")
