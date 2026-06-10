"""Restructure code reference tables

Revision ID: j8e1f0g5h726
Revises: i7d0e5f4a628
Create Date: 2026-06-04 00:05:00.000000

- Adds new columns to cpt_codes and icd_codes (code_type, clinical attributes,
  source provenance, data_confidence, rule_certainty)
- Creates drg_codes, modifier_codes, cpt_modifier_map, cpt_dx_coverage
- Drops cpt_icd_risks (replaced by cpt_dx_coverage)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'j8e1f0g5h726'
down_revision: Union[str, None] = 'i7d0e5f4a628'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SOURCE_COLS = [
    sa.Column('source_authority',       sa.String(100),  nullable=True),
    sa.Column('source_document',        sa.String(255),  nullable=True),
    sa.Column('source_url',             sa.String(500),  nullable=True),
    sa.Column('last_reviewed_at',       sa.String(10),   nullable=True),
    sa.Column('data_confidence',        sa.Float(),      nullable=False, server_default='0.5'),
    sa.Column('data_confidence_notes',  sa.Text(),       nullable=True),
    sa.Column('rule_certainty',         sa.String(20),   nullable=False, server_default='mandatory'),
]


def upgrade() -> None:
    # ── cpt_codes — add new columns ───────────────────────────────────────
    with op.batch_alter_table('cpt_codes') as b:
        b.add_column(sa.Column('code_type',        sa.String(10),  nullable=False, server_default='cpt'))
        b.add_column(sa.Column('is_add_on',        sa.Boolean(),   nullable=False, server_default='0'))
        b.add_column(sa.Column('global_period_days', sa.Integer(), nullable=True))
        b.add_column(sa.Column('effective_date',   sa.String(10),  nullable=True))
        b.add_column(sa.Column('termination_date', sa.String(10),  nullable=True))
        b.add_column(sa.Column('audit_notes',      sa.Text(),      nullable=True))
        for col in _SOURCE_COLS:
            b.add_column(col)

    # ── icd_codes — add new columns ───────────────────────────────────────
    with op.batch_alter_table('icd_codes') as b:
        b.add_column(sa.Column('code_type',        sa.String(10),  nullable=False, server_default='icd10_cm'))
        b.add_column(sa.Column('chapter',          sa.String(100), nullable=True))
        b.add_column(sa.Column('is_manifestation', sa.Boolean(),   nullable=False, server_default='0'))
        b.add_column(sa.Column('is_etiology',      sa.Boolean(),   nullable=False, server_default='0'))
        b.add_column(sa.Column('effective_date',   sa.String(10),  nullable=True))
        b.add_column(sa.Column('termination_date', sa.String(10),  nullable=True))
        b.add_column(sa.Column('audit_notes',      sa.Text(),      nullable=True))
        for col in _SOURCE_COLS:
            b.add_column(col)

    # ── drg_codes ─────────────────────────────────────────────────────────
    op.create_table(
        'drg_codes',
        sa.Column('drg_code_id',         sa.String(36),  primary_key=True),
        sa.Column('code',                sa.String(10),  unique=True, nullable=False),
        sa.Column('description',         sa.String(500), nullable=False),
        sa.Column('drg_type',            sa.String(20),  nullable=False),
        sa.Column('mdc',                 sa.String(10),  nullable=True),
        sa.Column('mdc_description',     sa.String(200), nullable=True),
        sa.Column('weight',              sa.Float(),     nullable=True),
        sa.Column('geometric_mean_los',  sa.Float(),     nullable=True),
        sa.Column('arithmetic_mean_los', sa.Float(),     nullable=True),
        sa.Column('is_surgical',         sa.Boolean(),   nullable=False, server_default='0'),
        sa.Column('effective_fy',        sa.String(10),  nullable=True),
        sa.Column('termination_fy',      sa.String(10),  nullable=True),
        sa.Column('clinical_criteria',   sa.Text(),      nullable=True),
        sa.Column('source_authority',    sa.String(100), nullable=True),
        sa.Column('source_document',     sa.String(255), nullable=True),
        sa.Column('source_url',          sa.String(500), nullable=True),
        sa.Column('last_reviewed_at',    sa.String(10),  nullable=True),
        sa.Column('data_confidence',     sa.Float(),     nullable=False, server_default='0.5'),
        sa.Column('data_confidence_notes', sa.Text(),    nullable=True),
        sa.Column('rule_certainty',      sa.String(20),  nullable=False, server_default='mandatory'),
        sa.Column('created_at',          sa.String(30),  nullable=False),
        sa.Column('updated_at',          sa.String(30),  nullable=False),
    )

    # ── modifier_codes ────────────────────────────────────────────────────
    op.create_table(
        'modifier_codes',
        sa.Column('modifier_code_id',       sa.String(36),  primary_key=True),
        sa.Column('code',                   sa.String(5),   unique=True, nullable=False),
        sa.Column('description',            sa.String(500), nullable=False),
        sa.Column('modifier_type',          sa.String(30),  nullable=False),
        sa.Column('applies_to',             sa.String(10),  nullable=False),
        sa.Column('payment_impact',         sa.String(20),  nullable=True),
        sa.Column('payment_factor',         sa.Float(),     nullable=True),
        sa.Column('ncci_override',          sa.Boolean(),   nullable=False, server_default='0'),
        sa.Column('requires_documentation', sa.Boolean(),   nullable=False, server_default='0'),
        sa.Column('audit_risk_score',       sa.Float(),     nullable=False, server_default='0'),
        sa.Column('valid_cpt_prefixes',     sa.Text(),      nullable=True),
        sa.Column('mutually_exclusive_with', sa.Text(),     nullable=True),
        sa.Column('audit_notes',            sa.Text(),      nullable=True),
        sa.Column('source_authority',       sa.String(100), nullable=True),
        sa.Column('source_document',        sa.String(255), nullable=True),
        sa.Column('source_url',             sa.String(500), nullable=True),
        sa.Column('last_reviewed_at',       sa.String(10),  nullable=True),
        sa.Column('data_confidence',        sa.Float(),     nullable=False, server_default='0.5'),
        sa.Column('data_confidence_notes',  sa.Text(),      nullable=True),
        sa.Column('rule_certainty',         sa.String(20),  nullable=False, server_default='mandatory'),
        sa.Column('created_at',             sa.String(30),  nullable=False),
        sa.Column('updated_at',             sa.String(30),  nullable=False),
    )

    # ── cpt_modifier_map ──────────────────────────────────────────────────
    op.create_table(
        'cpt_modifier_map',
        sa.Column('cpt_code',              sa.String(10), sa.ForeignKey('cpt_codes.code'),      nullable=False),
        sa.Column('modifier_code',         sa.String(5),  sa.ForeignKey('modifier_codes.code'), nullable=False),
        sa.Column('payment_factor',        sa.Float(),    nullable=True),
        sa.Column('ncci_override',         sa.Boolean(),  nullable=False, server_default='0'),
        sa.Column('notes',                 sa.Text(),     nullable=True),
        sa.Column('source_authority',      sa.String(100), nullable=True),
        sa.Column('source_document',       sa.String(255), nullable=True),
        sa.Column('source_url',            sa.String(500), nullable=True),
        sa.Column('last_reviewed_at',      sa.String(10),  nullable=True),
        sa.Column('data_confidence',       sa.Float(),    nullable=False, server_default='0.5'),
        sa.Column('data_confidence_notes', sa.Text(),     nullable=True),
        sa.Column('rule_certainty',        sa.String(20), nullable=False, server_default='mandatory'),
        sa.PrimaryKeyConstraint('cpt_code', 'modifier_code'),
    )

    # ── cpt_dx_coverage ───────────────────────────────────────────────────
    op.create_table(
        'cpt_dx_coverage',
        sa.Column('cpt_code',              sa.String(10), sa.ForeignKey('cpt_codes.code'),  nullable=False),
        sa.Column('icd_code',              sa.String(10), sa.ForeignKey('icd_codes.code'),  nullable=False),
        sa.Column('coverage_type',         sa.String(20), nullable=False),
        sa.Column('rationale',             sa.Text(),     nullable=True),
        sa.Column('source_authority',      sa.String(100), nullable=True),
        sa.Column('source_document',       sa.String(255), nullable=True),
        sa.Column('source_url',            sa.String(500), nullable=True),
        sa.Column('last_reviewed_at',      sa.String(10),  nullable=True),
        sa.Column('data_confidence',       sa.Float(),    nullable=False, server_default='0.5'),
        sa.Column('data_confidence_notes', sa.Text(),     nullable=True),
        sa.Column('rule_certainty',        sa.String(20), nullable=False, server_default='guideline'),
        sa.PrimaryKeyConstraint('cpt_code', 'icd_code'),
    )

    # ── drop obsolete table ───────────────────────────────────────────────
    op.drop_table('cpt_icd_risks')


def downgrade() -> None:
    op.drop_table('cpt_dx_coverage')
    op.drop_table('cpt_modifier_map')
    op.drop_table('modifier_codes')
    op.drop_table('drg_codes')

    with op.batch_alter_table('icd_codes') as b:
        for col in ['code_type', 'chapter', 'is_manifestation', 'is_etiology',
                    'effective_date', 'termination_date', 'audit_notes',
                    'source_authority', 'source_document', 'source_url',
                    'last_reviewed_at', 'data_confidence', 'data_confidence_notes', 'rule_certainty']:
            b.drop_column(col)

    with op.batch_alter_table('cpt_codes') as b:
        for col in ['code_type', 'is_add_on', 'global_period_days',
                    'effective_date', 'termination_date', 'audit_notes',
                    'source_authority', 'source_document', 'source_url',
                    'last_reviewed_at', 'data_confidence', 'data_confidence_notes', 'rule_certainty']:
            b.drop_column(col)

    op.create_table(
        'cpt_icd_risks',
        sa.Column('cpt_icd_risk_id', sa.String(36), primary_key=True),
        sa.Column('cpt_code',        sa.String(10), nullable=False),
        sa.Column('icd_code',        sa.String(10), nullable=False),
        sa.Column('mismatch_risk_score', sa.Float(), nullable=False),
        sa.Column('rationale',       sa.Text(),     nullable=False),
        sa.Column('created_at',      sa.String(30), nullable=False),
        sa.Column('updated_at',      sa.String(30), nullable=False),
    )
