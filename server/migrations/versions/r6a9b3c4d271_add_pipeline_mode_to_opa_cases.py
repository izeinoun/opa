"""add pipeline_mode to opa_cases

Closes real model<->migration drift: OpaCase.pipeline_mode exists in the model
(and on create_all-built DBs from the pre-squash era) but was never added by any
migration, so a fresh `alembic upgrade head` built opa_cases WITHOUT it and the
seed/detector path failed with "no such column: opa_cases.pipeline_mode".

After this revision a pure-migration build (i.e. a fresh deploy) produces a
complete, seedable schema. `alembic check` is then clean except for two
known SQLite reflection false-positives (phantom add_fk on claim_payments_835,
whose columns + model-side FKs already exist — SQLite reflection just can't see
them; they appear even against a create_all DB that definitely has them).

Revision ID: r6a9b3c4d271
Revises: q5f8a2b3c160
Create Date: 2026-06-09 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'r6a9b3c4d271'
down_revision: Union[str, None] = 'q5f8a2b3c160'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    # Idempotent: create_all-built DBs (pre-squash) already carry this column;
    # only a pure-migration build lacks it. Guard so both paths converge.
    #
    # Plain ADD COLUMN (not batch_alter_table): SQLite supports native
    # ALTER TABLE ADD COLUMN with a default, so this avoids rebuilding opa_cases.
    # A batch rebuild would silently drop the table's existing FK constraints
    # (SQLite reflection can't see them), introducing new phantom drift.
    if not _has_column(bind, "opa_cases", "pipeline_mode"):
        op.add_column(
            "opa_cases",
            sa.Column(
                "pipeline_mode",
                sa.String(length=20),
                server_default="post_pay",
                nullable=False,
            ),
        )


def downgrade() -> None:
    op.drop_column("opa_cases", "pipeline_mode")
