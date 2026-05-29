-- ============================================================================
-- OPA — Overpayment Agent: data model
-- Generated from server/app/models/{reference,claims,workflow}.py
-- 34 tables across three domains: reference / claims / workflow
--   (ml_training_config added for admin-editable RF hyperparameters)
--
-- Conventions used throughout (preserved here so a rebuild matches behavior)
--   • PKs are UUID-as-TEXT (36 chars) generated in application code.
--     Exceptions: reference_data_freshness (source_name), letter_templates
--     (human-readable key), detector_rule_config (rule_code), prioritization_config
--     (singleton 'current'), case_findings (composite PK).
--   • Timestamps stored as ISO-8601 strings (TEXT 30), dates as 'YYYY-MM-DD'
--     strings (TEXT 10). This avoids SQLite type-coercion quirks but means
--     comparisons are lexicographic; keep the format strict if you re-implement.
--   • JSON columns stored as TEXT. Documented inline.
--   • Defaults shown match SQLAlchemy model defaults. Where the default is
--     set in Python (UUID, NOW), the DDL omits it — your app layer assigns it.
--   • Engine target: SQLite via aiosqlite. Postgres-friendly; swap TEXT/REAL
--     for VARCHAR/NUMERIC and add proper TIMESTAMP/DATE if migrating.
--   • Indexes: the running app relies on FK + unique constraints; no
--     additional indexes are declared in models. Add for production volume.
-- ============================================================================


-- ============================================================================
-- DOMAIN 1 / 3 — REFERENCE
-- Master / lookup data: providers, members, codes, fee schedules, ML metadata.
-- ============================================================================

CREATE TABLE provider_orgs (
    provider_org_id    TEXT PRIMARY KEY,
    name               TEXT NOT NULL,
    npi                TEXT NOT NULL UNIQUE,
    tin                TEXT NOT NULL,
    org_type           TEXT NOT NULL,
    is_sensitive       INTEGER NOT NULL DEFAULT 0,        -- boolean
    risk_score         REAL NOT NULL DEFAULT 0.0,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);

CREATE TABLE providers (
    provider_id                  TEXT PRIMARY KEY,
    provider_org_id              TEXT NOT NULL REFERENCES provider_orgs(provider_org_id),
    npi                          TEXT NOT NULL UNIQUE,
    tin                          TEXT NOT NULL,
    name                         TEXT NOT NULL,
    specialty                    TEXT NOT NULL,
    credential_status            TEXT NOT NULL,
    credential_effective_date    TEXT NOT NULL,
    credential_lapse_date        TEXT,
    is_excluded                  INTEGER NOT NULL DEFAULT 0,
    exclusion_effective_date     TEXT,
    exclusion_source             TEXT,
    -- Output of the AutoML billing-variance classifier.
    -- Seeded at 0.5, then overwritten by ML training during `make seed` step 8.
    -- Used as the *prior* in the case posterior calculation.
    billing_variance_score       REAL NOT NULL DEFAULT 0.5,
    created_at                   TEXT NOT NULL,
    updated_at                   TEXT NOT NULL
);

CREATE TABLE members (
    member_id                    TEXT PRIMARY KEY,
    member_number                TEXT NOT NULL UNIQUE,
    first_name                   TEXT NOT NULL,
    last_name                    TEXT NOT NULL,
    date_of_birth                TEXT NOT NULL,
    date_of_death                TEXT,
    lob                          TEXT NOT NULL,            -- line of business
    coverage_effective_date      TEXT NOT NULL,
    coverage_termination_date    TEXT,
    -- Retro-termination flagged by DET-02 (eligibility paid in error).
    retro_termination_date       TEXT,
    created_at                   TEXT NOT NULL,
    updated_at                   TEXT NOT NULL
);

CREATE TABLE cpt_codes (
    cpt_code_id          TEXT PRIMARY KEY,
    code                 TEXT NOT NULL UNIQUE,
    description          TEXT NOT NULL,
    value_tier           TEXT NOT NULL,
    risk_score           REAL NOT NULL DEFAULT 0.0,
    typical_units_max    INTEGER NOT NULL DEFAULT 1,       -- feeds DET-06 MUE
    requires_auth        INTEGER NOT NULL DEFAULT 0,
    specialty_typical    TEXT NOT NULL,
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL
);

CREATE TABLE icd_codes (
    icd_code_id     TEXT PRIMARY KEY,
    code            TEXT NOT NULL UNIQUE,
    description     TEXT NOT NULL,
    value_tier      TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- DX/CPT pair risk lookup; feeds DET-09 coding-error detection.
CREATE TABLE cpt_icd_risks (
    cpt_icd_risk_id        TEXT PRIMARY KEY,
    cpt_code               TEXT NOT NULL,
    icd_code               TEXT NOT NULL,
    mismatch_risk_score    REAL NOT NULL DEFAULT 0.0,
    rationale              TEXT NOT NULL,
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL
);

CREATE TABLE fee_schedules (
    fee_schedule_id        TEXT PRIMARY KEY,
    provider_org_id        TEXT NOT NULL REFERENCES provider_orgs(provider_org_id),
    lob                    TEXT NOT NULL,
    cpt_code               TEXT NOT NULL,
    effective_date         TEXT NOT NULL,
    termination_date       TEXT,
    base_rate              REAL NOT NULL,
    rate_basis             TEXT NOT NULL,
    modifier_applicable    TEXT,
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL
);

CREATE TABLE contract_limitations (
    limitation_id      TEXT PRIMARY KEY,
    provider_org_id    TEXT NOT NULL REFERENCES provider_orgs(provider_org_id),
    cpt_code           TEXT NOT NULL,
    limitation_type    TEXT NOT NULL,
    limitation_value   TEXT NOT NULL,
    effective_date     TEXT NOT NULL,
    description        TEXT NOT NULL,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);

-- Tracks freshness of upstream reference data (NCCI/MUE, OIG, fee schedules).
-- Note: PK is the natural source_name, not a UUID.
CREATE TABLE reference_data_freshness (
    source_name              TEXT PRIMARY KEY,
    last_refreshed_at        TEXT NOT NULL,
    next_scheduled_refresh   TEXT NOT NULL,
    status                   TEXT NOT NULL,                -- fresh | stale | critical
    affected_detectors       TEXT NOT NULL,                -- JSON array of detector IDs
    updated_at               TEXT NOT NULL
);

-- Per-training-run record. Captures lineage (what hyperparameters trained
-- this version), validation metrics computed in train_model(), and the
-- F2-optimal decision threshold pinned in the saved artifact.
CREATE TABLE ml_model_versions (
    version_id            TEXT PRIMARY KEY,
    model_name            TEXT NOT NULL,
    model_artifact_id     TEXT NOT NULL,
    trained_at            TEXT NOT NULL,
    training_rows         INTEGER NOT NULL,
    training_window       TEXT NOT NULL,
    -- Lineage: snapshot of hyperparameters used for this training run.
    -- JSON object e.g. {"n_estimators":200,"max_depth":10,"min_samples_leaf":5,
    -- "random_state":42,"smote_strategy":"auto"}. Pinned at training time —
    -- changes to ml_training_config do NOT mutate historical rows.
    training_params       TEXT NOT NULL DEFAULT '{}',      -- JSON
    -- Validation metrics — all computed today in train_model() but previously
    -- discarded. Stored on [0.0, 1.0]. accuracy/precision/recall/f1/f2 are
    -- measured at the chosen decision_threshold; auc_roc is threshold-agnostic.
    accuracy              REAL NOT NULL,
    precision_score       REAL,                            -- 'precision' is SQL reserved-ish; use _score suffix
    recall_score          REAL,
    f1_score              REAL,
    f2_score              REAL,
    auc_roc               REAL,
    decision_threshold    REAL,                            -- F2-optimal cutoff stored in artifact
    positive_rate         REAL NOT NULL,
    feature_importance    TEXT NOT NULL,                   -- JSON
    is_active             INTEGER NOT NULL DEFAULT 1,
    notes                 TEXT NOT NULL DEFAULT '',
    created_at            TEXT NOT NULL
);


-- ============================================================================
-- DOMAIN 2 / 3 — CLAIMS
-- Inbound 837/835 EDI artifacts and the normalized claim + line model.
-- ============================================================================

-- Logical grouping of claims (same member + provider org + DOS window).
-- Used to surface DET-01 duplicate-billing candidates across multiple claims.
CREATE TABLE case_groups (
    case_group_id        TEXT PRIMARY KEY,
    group_number         TEXT NOT NULL UNIQUE,
    provider_org_id      TEXT NOT NULL REFERENCES provider_orgs(provider_org_id),
    member_id            TEXT NOT NULL REFERENCES members(member_id),
    dos_range_start      TEXT NOT NULL,
    dos_range_end        TEXT NOT NULL,
    group_reason         TEXT NOT NULL,
    duplicate_suspected  INTEGER NOT NULL DEFAULT 0,
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL
);

-- Raw 835 (remittance advice) at the transaction level.
CREATE TABLE transactions_835 (
    transaction_id       TEXT PRIMARY KEY,
    transaction_number   TEXT NOT NULL UNIQUE,
    transaction_type     TEXT NOT NULL,
    payer_name           TEXT NOT NULL,
    provider_org_id      TEXT NOT NULL REFERENCES provider_orgs(provider_org_id),
    transaction_date     TEXT NOT NULL,
    total_amount         REAL NOT NULL,
    claim_count          INTEGER NOT NULL,
    raw_835_json         TEXT NOT NULL,
    created_at           TEXT NOT NULL
);

-- Per-claim payment line within an 835 transaction.
CREATE TABLE claim_payments_835 (
    payment_id                TEXT PRIMARY KEY,
    transaction_id            TEXT NOT NULL REFERENCES transactions_835(transaction_id),
    claim_icn                 TEXT NOT NULL,
    cpt_code                  TEXT NOT NULL,
    paid_amount               REAL NOT NULL,
    adjustment_amount         REAL NOT NULL DEFAULT 0.0,
    adjustment_reason_code    TEXT,
    check_number              TEXT,
    payment_date              TEXT NOT NULL
);

-- Raw 837 (claim submission) header.
CREATE TABLE claim_headers_837 (
    header_id              TEXT PRIMARY KEY,
    claim_icn              TEXT NOT NULL UNIQUE,
    submitter_npi          TEXT NOT NULL,
    billing_provider_npi   TEXT NOT NULL,
    submission_date        TEXT NOT NULL,
    total_billed           REAL NOT NULL,
    claim_frequency_code   TEXT NOT NULL DEFAULT '1',
    raw_837_json           TEXT NOT NULL,
    created_at             TEXT NOT NULL
);

-- Normalized claim. Source of truth for detector runs.
CREATE TABLE claims (
    claim_id                  TEXT PRIMARY KEY,
    icn                       TEXT NOT NULL UNIQUE,
    case_group_id             TEXT REFERENCES case_groups(case_group_id),
    member_id                 TEXT NOT NULL REFERENCES members(member_id),
    provider_org_id           TEXT NOT NULL REFERENCES provider_orgs(provider_org_id),
    billing_provider_npi      TEXT NOT NULL,
    rendering_provider_npi    TEXT NOT NULL,
    lob                       TEXT NOT NULL,
    service_from_date         TEXT NOT NULL,
    service_to_date           TEXT NOT NULL,
    claim_type                TEXT NOT NULL DEFAULT 'professional',
    claim_status              TEXT NOT NULL,
    total_billed              REAL NOT NULL,
    total_paid                REAL NOT NULL,
    paid_date                 TEXT NOT NULL,
    authorization_number      TEXT,
    submission_date           TEXT NOT NULL,
    pos_code                  TEXT NOT NULL,
    primary_icd               TEXT NOT NULL,
    era_transaction_id        TEXT REFERENCES transactions_835(transaction_id),
    raw_claim_json            TEXT NOT NULL,
    created_at                TEXT NOT NULL,
    updated_at                TEXT NOT NULL
);

-- Service line. Detectors operate at this grain; findings can be line-level.
CREATE TABLE claim_lines (
    claim_line_id     TEXT PRIMARY KEY,
    claim_id          TEXT NOT NULL REFERENCES claims(claim_id),
    line_number       INTEGER NOT NULL,
    cpt_code          TEXT NOT NULL,
    icd_codes         TEXT NOT NULL,                       -- JSON array
    modifier_1        TEXT,
    modifier_2        TEXT,
    units_billed      INTEGER NOT NULL,
    units_paid        INTEGER NOT NULL,
    billed_amount     REAL NOT NULL,
    paid_amount       REAL NOT NULL,
    allowed_amount    REAL NOT NULL,
    pos_code          TEXT NOT NULL,
    revenue_code      TEXT
);


-- ============================================================================
-- DOMAIN 3 / 3 — WORKFLOW
-- Users, findings, cases, scoring, audit, letters, recoupment, reconciliation.
-- ============================================================================

CREATE TABLE opa_users (
    user_id      TEXT PRIMARY KEY,
    username     TEXT NOT NULL UNIQUE,
    full_name    TEXT NOT NULL,
    email        TEXT NOT NULL,
    role         TEXT NOT NULL,                            -- analyst | supervisor | admin
    is_active    INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

-- One row per detector fire. Findings are the unit of evidence.
-- detector_id is the rule code (e.g. DET-01) or a versioned legacy ID
-- (DUPLICATE_CLAIM_V1, UPCODING_V1, ...). Normalize through _DET_CODE_MAP.
CREATE TABLE findings (
    finding_id            TEXT PRIMARY KEY,
    claim_id              TEXT NOT NULL REFERENCES claims(claim_id),
    claim_line_id         TEXT REFERENCES claim_lines(claim_line_id),
    detector_id           TEXT NOT NULL,
    detector_version      TEXT NOT NULL,
    fired_at              TEXT NOT NULL,
    overpayment_amount    REAL NOT NULL,
    severity              TEXT NOT NULL,                   -- low | medium | high
    confidence            REAL NOT NULL,                   -- [0.0, 1.0]
    rationale             TEXT NOT NULL,
    evidence              TEXT NOT NULL,                   -- JSON
    rule_version          TEXT NOT NULL,
    status                TEXT NOT NULL DEFAULT 'active'
);

-- Case = workflowed grouping of findings on a single claim.
-- One active case per claim, enforced in CaseService (not DB constraint —
-- SQLite partial unique indexes are version-unreliable).
CREATE TABLE opa_cases (
    case_id                          TEXT PRIMARY KEY,
    case_number                      TEXT NOT NULL UNIQUE,
    case_sequence                    INTEGER NOT NULL DEFAULT 1,
    claim_id                         TEXT NOT NULL REFERENCES claims(claim_id),
    case_group_id                    TEXT REFERENCES case_groups(case_group_id),
    primary_detector_id              TEXT NOT NULL,
    lob                              TEXT NOT NULL,
    provider_org_id                  TEXT NOT NULL REFERENCES provider_orgs(provider_org_id),
    member_id                        TEXT NOT NULL REFERENCES members(member_id),
    assigned_analyst_id              TEXT REFERENCES opa_users(user_id),
    status                           TEXT NOT NULL DEFAULT 'new',
    is_active                        INTEGER NOT NULL DEFAULT 1,
    priority                         TEXT NOT NULL,        -- HIGH | MEDIUM | LOW (band)
    priority_score                   REAL NOT NULL,        -- 0..100
    total_overpayment_amount         REAL NOT NULL,
    recommended_recovery_method      TEXT NOT NULL,
    identified_date                  TEXT NOT NULL,
    deadline_date                    TEXT NOT NULL,
    deadline_breached                INTEGER NOT NULL DEFAULT 0,
    lookback_window_start            TEXT NOT NULL,
    provider_response_due_date       TEXT,
    is_sensitive_provider            INTEGER NOT NULL DEFAULT 0,
    requires_supervisor_approval     INTEGER NOT NULL DEFAULT 0,
    evidence_bundle                  TEXT NOT NULL,        -- JSON
    case_json                        TEXT NOT NULL,        -- JSON
    -- Closure decision held here while case is in pending_supervisor status:
    -- {disposition, reason, recovered_amount, submitted_by_user_id, submitted_at}
    decision_metadata                TEXT,
    created_at                       TEXT NOT NULL,
    updated_at                       TEXT NOT NULL
);

-- Human commentary on a case. Distinct from audit_logs (which are
-- system-generated state-change records and immutable).
CREATE TABLE case_notes (
    note_id           TEXT PRIMARY KEY,
    case_id           TEXT NOT NULL REFERENCES opa_cases(case_id),
    author_user_id    TEXT NOT NULL REFERENCES opa_users(user_id),
    body              TEXT NOT NULL,
    created_at        TEXT NOT NULL
);

-- In-app notification feed.
-- kinds: case_assigned | approval_requested | approval_decided |
--        case_reopened | note_mention (future)
CREATE TABLE notifications (
    notification_id      TEXT PRIMARY KEY,
    recipient_user_id    TEXT NOT NULL REFERENCES opa_users(user_id),
    kind                 TEXT NOT NULL,
    case_id              TEXT REFERENCES opa_cases(case_id),
    actor_user_id        TEXT REFERENCES opa_users(user_id),
    title                TEXT NOT NULL,
    body                 TEXT,
    link                 TEXT,
    is_read              INTEGER NOT NULL DEFAULT 0,
    created_at           TEXT NOT NULL
);

-- Structured analyst↔provider contact log.
CREATE TABLE contact_logs (
    contact_id           TEXT PRIMARY KEY,
    case_id              TEXT NOT NULL REFERENCES opa_cases(case_id),
    logged_by_user_id    TEXT NOT NULL REFERENCES opa_users(user_id),
    contact_date         TEXT NOT NULL,
    method               TEXT NOT NULL,                    -- phone|email|letter|in_person|portal
    direction            TEXT NOT NULL,                    -- outbound|inbound
    participant_name     TEXT,
    summary              TEXT NOT NULL,
    created_at           TEXT NOT NULL
);

-- Per-finding accept/reject/adjust. One row per finding (unique).
-- Default disposition seeded at detector run:
--   • DET-01/02/04/06/08 (deterministic)        → accepted
--   • DET-09 (AI-assisted) conf >= 0.85         → accepted
--   • DET-09 0.65 <= conf < 0.85                → needs_review
--   • DET-09 conf < 0.65                        → rejected
CREATE TABLE finding_dispositions (
    disposition_id        TEXT PRIMARY KEY,
    finding_id            TEXT NOT NULL UNIQUE REFERENCES findings(finding_id),
    case_id               TEXT NOT NULL REFERENCES opa_cases(case_id),
    status                TEXT NOT NULL,                   -- accepted|rejected|needs_review|adjusted
    original_amount       REAL NOT NULL,
    adjusted_amount       REAL,
    reason                TEXT,
    decided_by_user_id    TEXT REFERENCES opa_users(user_id),
    decided_at            TEXT,
    created_at            TEXT NOT NULL
);

-- Many-to-many: case ↔ findings. Composite PK.
CREATE TABLE case_findings (
    case_id      TEXT NOT NULL REFERENCES opa_cases(case_id),
    finding_id   TEXT NOT NULL REFERENCES findings(finding_id),
    PRIMARY KEY (case_id, finding_id)
);

-- One row per case (unique). Stores both the raw factor scores and the
-- composite/posterior used in priority. Note: in the live pipeline,
-- cpt_risk_score / dx_cpt_mismatch_score / claim_complexity_score are
-- written as 0.0 — the real likelihood is computed as a Bayesian posterior
-- over findings; composite_likelihood is seeded from provider.billing_variance_score.
CREATE TABLE likelihood_scores (
    score_id                    TEXT PRIMARY KEY,
    case_id                     TEXT NOT NULL UNIQUE REFERENCES opa_cases(case_id),
    provider_risk_score         REAL NOT NULL,
    cpt_risk_score              REAL NOT NULL,
    dx_cpt_mismatch_score       REAL NOT NULL,
    claim_complexity_score      REAL NOT NULL,
    billing_variance_score      REAL NOT NULL,
    composite_likelihood        REAL NOT NULL,             -- prior, then Bayesian-updated
    urgency_factor              REAL NOT NULL,
    urgency_override_applied    INTEGER NOT NULL DEFAULT 0,
    priority_score              REAL NOT NULL,             -- 0..100
    score_json                  TEXT NOT NULL,             -- JSON
    scored_at                   TEXT NOT NULL
);

-- Immutable audit trail. No updated_at by design.
-- meta_json is required (use '{}' for empty) — column name avoids the
-- SQLAlchemy-reserved 'metadata'.
CREATE TABLE audit_logs (
    audit_id         TEXT PRIMARY KEY,
    case_id          TEXT REFERENCES opa_cases(case_id),
    actor_user_id    TEXT NOT NULL REFERENCES opa_users(user_id),
    action           TEXT NOT NULL,
    from_state       TEXT,
    to_state         TEXT,
    reason           TEXT,
    meta_json        TEXT NOT NULL,                        -- JSON, never null
    created_at       TEXT NOT NULL
);

-- Provider dispute against a case.
CREATE TABLE disputes (
    dispute_id                 TEXT PRIMARY KEY,
    case_id                    TEXT NOT NULL REFERENCES opa_cases(case_id),
    received_date              TEXT NOT NULL,
    submitted_by_name          TEXT NOT NULL,
    channel                    TEXT NOT NULL,
    dispute_reason_code        TEXT NOT NULL,
    dispute_reason_text        TEXT NOT NULL,
    supporting_evidence_ref    TEXT,
    status                     TEXT NOT NULL,
    resolution_date            TEXT,
    resolution_notes           TEXT,
    resolved_by_user_id        TEXT REFERENCES opa_users(user_id),
    created_at                 TEXT NOT NULL,
    updated_at                 TEXT NOT NULL
);

-- Letter templates. template_id is a human-readable key, e.g. 'INIT-NOTICE-MA'.
CREATE TABLE letter_templates (
    template_id              TEXT PRIMARY KEY,
    lob                      TEXT NOT NULL,
    template_name            TEXT NOT NULL,
    regulatory_reference     TEXT NOT NULL,
    template_content         TEXT NOT NULL,
    version                  TEXT NOT NULL,
    is_active                INTEGER NOT NULL DEFAULT 1,
    created_by_user_id       TEXT NOT NULL REFERENCES opa_users(user_id),
    created_at               TEXT NOT NULL,
    updated_at               TEXT NOT NULL
);

-- A letter rendered and sent (or queued) for a case.
CREATE TABLE provider_notices (
    notice_id             TEXT PRIMARY KEY,
    case_id               TEXT NOT NULL REFERENCES opa_cases(case_id),
    template_id           TEXT NOT NULL REFERENCES letter_templates(template_id),
    lob                   TEXT NOT NULL,
    generated_at          TEXT NOT NULL,
    letter_content        TEXT NOT NULL,
    status                TEXT NOT NULL,
    approved_by_user_id   TEXT REFERENCES opa_users(user_id),
    approved_at           TEXT,
    sent_at               TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);

-- Recoupment action against a case. recovery_835_transaction_id links the
-- inbound 835 that confirms recovery (closes the loop with reconciliations).
CREATE TABLE recoupment_actions (
    recoupment_id                 TEXT PRIMARY KEY,
    case_id                       TEXT NOT NULL REFERENCES opa_cases(case_id),
    method                        TEXT NOT NULL,           -- offset|invoice|treasury|...
    requested_amount              REAL NOT NULL,
    status                        TEXT NOT NULL,
    submitted_at                  TEXT,
    confirmed_at                  TEXT,
    recovery_835_transaction_id   TEXT REFERENCES transactions_835(transaction_id),
    staging_output_json           TEXT NOT NULL,           -- JSON
    staging_status                TEXT NOT NULL DEFAULT 'pending',
    staging_exported_at           TEXT,
    created_at                    TEXT NOT NULL,
    updated_at                    TEXT NOT NULL
);

-- One row per detector. Enable/disable + score multiplier.
-- rule_code is the natural PK (DET-01, DET-02, ...).
CREATE TABLE detector_rule_config (
    rule_code            TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    description          TEXT NOT NULL,
    enabled              INTEGER NOT NULL DEFAULT 1,
    score                REAL NOT NULL DEFAULT 1.0,       -- confidence multiplier
    updated_at           TEXT NOT NULL,
    updated_by_user_id   TEXT REFERENCES opa_users(user_id)
);

-- Singleton (config_id='current'). Operator-tunable priority-formula knobs.
-- Defaults reflect the live formula:
--   priority = (amount_norm * 0.60 + posterior * 0.35 + urgency * 0.05) * 100
--   amount_norm = min(amount / 5000, 1)
--   urgency linear 0->1 over the last 30 days to deadline
--   HIGH >= 75, MEDIUM 50..74, LOW < 50
CREATE TABLE prioritization_config (
    config_id              TEXT PRIMARY KEY DEFAULT 'current',
    amount_weight          REAL NOT NULL DEFAULT 0.60,
    likelihood_weight      REAL NOT NULL DEFAULT 0.35,
    urgency_weight         REAL NOT NULL DEFAULT 0.05,
    amount_cap             REAL NOT NULL DEFAULT 5000.0,
    urgency_window_days    INTEGER NOT NULL DEFAULT 30,
    high_threshold         REAL NOT NULL DEFAULT 75.0,
    medium_threshold       REAL NOT NULL DEFAULT 50.0,
    updated_at             TEXT NOT NULL,
    updated_by_user_id     TEXT REFERENCES opa_users(user_id)
);

-- Singleton (config_id='current'). Operator-editable knobs that govern
-- the next training run of billing_variance_classifier (RandomForest).
-- Resolution rules (applied in train_model()):
--   • Any column whose value is NULL → use sklearn default for that param.
--   • The resolved config is persisted to ml_model_versions.training_params
--     when training completes, so historical lineage is immutable even
--     if this row is later edited.
--   • decision_threshold_mode:
--       'auto_f2' → keep the existing F2-optimal sweep; ignore manual_threshold
--       'manual'  → use manual_threshold verbatim (skip the sweep)
-- Default values below preserve current production behavior:
--   n_estimators=200 (matches the hardcoded value in train_billing_variance.py)
--   max_depth=NULL, min_samples_leaf=1 (sklearn defaults — trees grow until pure)
CREATE TABLE ml_training_config (
    config_id                  TEXT PRIMARY KEY DEFAULT 'current',
    -- The 3 admin-editable RandomForest hyperparameters.
    n_estimators               INTEGER NOT NULL DEFAULT 200,
    max_depth                  INTEGER,                    -- NULL → unlimited (sklearn default)
    min_samples_leaf           INTEGER NOT NULL DEFAULT 1,
    -- Decision threshold control. Lets ops override the F2-tuned cutoff
    -- without retraining when business priorities shift (recall vs precision).
    decision_threshold_mode    TEXT NOT NULL DEFAULT 'auto_f2',  -- auto_f2 | manual
    manual_threshold           REAL,                       -- [0.0, 1.0]; only honored when mode='manual'
    -- Promotion gate (optional, applied at end of training):
    -- if NULL, candidate is auto-activated; if set, candidate stays inactive
    -- until its auc_roc clears this floor.
    min_auc_to_promote         REAL,
    updated_at                 TEXT NOT NULL,
    updated_by_user_id         TEXT REFERENCES opa_users(user_id)
);


-- Reconciles expected recovery against the inbound 835 that actually paid.
-- match_type: exact|partial|unmatched|exception|pending
CREATE TABLE reconciliations (
    reconciliation_id             TEXT PRIMARY KEY,
    case_id                       TEXT NOT NULL REFERENCES opa_cases(case_id),
    expected_amount               REAL NOT NULL,
    actual_amount                 REAL,
    match_type                    TEXT NOT NULL DEFAULT 'pending',
    recovery_835_transaction_id   TEXT REFERENCES transactions_835(transaction_id),
    recovery_835_payment_id       TEXT REFERENCES claim_payments_835(payment_id),
    plb_reference                 TEXT,
    treasury_reference            TEXT,
    exception_reason              TEXT,
    reconciled_at                 TEXT,
    created_at                    TEXT NOT NULL,
    updated_at                    TEXT NOT NULL
);


-- ============================================================================
-- KEY RELATIONSHIPS (cheat sheet)
-- ============================================================================
--
-- provider_orgs 1─* providers
-- provider_orgs 1─* fee_schedules
-- provider_orgs 1─* contract_limitations
-- provider_orgs 1─* claims
-- provider_orgs 1─* transactions_835
--
-- members       1─* claims
-- case_groups   1─* claims                    (optional grouping)
-- claims        1─* claim_lines
-- claims        1─* findings
-- claim_lines   1─* findings                  (line-level findings)
--
-- transactions_835 1─* claim_payments_835
-- transactions_835 1─* claims                 (via era_transaction_id)
-- transactions_835 1─* recoupment_actions     (recovery 835 link)
-- transactions_835 1─* reconciliations
--
-- opa_cases   1─1 claims                      (one active case per claim,
--                                              enforced at service layer)
-- opa_cases   1─1 likelihood_scores
-- opa_cases   1─* case_findings *─1 findings  (M:N)
-- opa_cases   1─* finding_dispositions
-- opa_cases   1─* case_notes
-- opa_cases   1─* audit_logs
-- opa_cases   1─* contact_logs
-- opa_cases   1─* disputes
-- opa_cases   1─* provider_notices
-- opa_cases   1─* recoupment_actions
-- opa_cases   1─* reconciliations
-- opa_cases   1─* notifications               (when kind references a case)
--
-- letter_templates 1─* provider_notices
-- opa_users        1─* (case_notes, audit_logs, contact_logs,
--                       notifications, finding_dispositions, provider_notices,
--                       disputes, letter_templates, opa_cases.assigned_analyst,
--                       detector_rule_config, prioritization_config,
--                       ml_training_config)
--
-- ml_training_config   (singleton) ──drives──> next training run, which
--                                              persists its resolved config
--                                              into ml_model_versions.training_params
