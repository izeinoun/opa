from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from uuid import uuid4

from sqlalchemy import Boolean, Float, ForeignKey, Integer, PrimaryKeyConstraint, String, Text, func, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


def _uuid() -> str:
    return str(uuid4())


def _now() -> str:
    return datetime.utcnow().isoformat()


class ProviderOrg(Base):
    __tablename__ = "provider_orgs"

    provider_org_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    npi: Mapped[str] = mapped_column(String(20), unique=True)
    tin: Mapped[str] = mapped_column(String(20))
    org_type: Mapped[str] = mapped_column(String(50))
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)

    providers: Mapped[List["Provider"]] = relationship(
        "Provider", back_populates="org", lazy="selectin"
    )
    fee_schedules: Mapped[List["FeeSchedule"]] = relationship(
        "FeeSchedule", back_populates="org", lazy="selectin"
    )
    contract_limitations: Mapped[List["ContractLimitation"]] = relationship(
        "ContractLimitation", back_populates="org", lazy="selectin"
    )
    playbook: Mapped[Optional["ProviderDeliveryPlaybook"]] = relationship(
        "ProviderDeliveryPlaybook", back_populates="org", uselist=False, lazy="selectin"
    )


class Provider(Base):
    __tablename__ = "providers"

    provider_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    provider_org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("provider_orgs.provider_org_id")
    )
    npi: Mapped[str] = mapped_column(String(20), unique=True)
    tin: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(255))
    specialty: Mapped[str] = mapped_column(String(100))
    credential_status: Mapped[str] = mapped_column(String(50))
    credential_effective_date: Mapped[str] = mapped_column(String(10))
    credential_lapse_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    is_excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    exclusion_effective_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    exclusion_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    billing_variance_score: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)

    org: Mapped["ProviderOrg"] = relationship(
        "ProviderOrg", back_populates="providers", lazy="selectin"
    )


class ExcludedProvider(Base):
    """OIG LEIE (List of Excluded Individuals/Entities) reference data.

    Imported from the CMS/OIG exclusion file. DET-08 screens each claim's
    rendering provider NPI against this table by `npi`. This is external
    reference data — it is NOT the payer's own provider roster (see Provider).
    Only NPI-bearing LEIE rows are imported, since `npi` is the deterministic
    join key DET-08 acts on; name+DOB-only individuals are out of scope.
    """

    __tablename__ = "excluded_providers"

    excluded_provider_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    npi: Mapped[str] = mapped_column(String(20), index=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    middle_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    business_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    general_category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    specialty: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    upin: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    dob: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    zip_code: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    # OIG exclusion statute code (e.g. 1128a1, 1128b4)
    exclusion_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    exclusion_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    reinstate_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    waiver_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    waiver_state: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    source: Mapped[str] = mapped_column(
        String(100), server_default="OIG LEIE", default="OIG LEIE"
    )
    created_at: Mapped[str] = mapped_column(
        String(30), server_default=func.now(), default=_now
    )


class Member(Base):
    __tablename__ = "members"

    member_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    member_number: Mapped[str] = mapped_column(String(50), unique=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    date_of_birth: Mapped[str] = mapped_column(String(10))
    date_of_death: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    lob: Mapped[str] = mapped_column(String(50))
    coverage_effective_date: Mapped[str] = mapped_column(String(10))
    coverage_termination_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    retro_termination_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)


class CptCode(Base):
    __tablename__ = "cpt_codes"

    cpt_code_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(10), unique=True)
    description: Mapped[str] = mapped_column(String(500))
    code_type: Mapped[str] = mapped_column(String(10), default="cpt", server_default="cpt")  # cpt | hcpcs
    value_tier: Mapped[str] = mapped_column(String(20))
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    typical_units_max: Mapped[int] = mapped_column(Integer, default=1)
    requires_auth: Mapped[bool] = mapped_column(Boolean, default=False)
    specialty_typical: Mapped[str] = mapped_column(String(100))
    typical_setting: Mapped[str] = mapped_column(
        String(20), default="professional", server_default="professional"
    )
    applicable_settings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    is_add_on: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    global_period_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)    # 0 | 10 | 90
    effective_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    termination_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    audit_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_authority: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_document: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    last_reviewed_at: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    data_confidence: Mapped[float] = mapped_column(Float, default=0.5, server_default="0.5")
    data_confidence_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rule_certainty: Mapped[str] = mapped_column(String(20), default="mandatory", server_default="mandatory")
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)


class IcdCode(Base):
    __tablename__ = "icd_codes"

    icd_code_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(10), unique=True)
    description: Mapped[str] = mapped_column(String(500))
    code_type: Mapped[str] = mapped_column(String(10), default="icd10_cm", server_default="icd10_cm")
    value_tier: Mapped[str] = mapped_column(String(20))
    chapter: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_manifestation: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    is_etiology: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    effective_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    termination_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    # Setting applicability — guides detectors and LLM reasoning.
    # typical_setting: primary/representative setting for filtering and display.
    # applicable_settings: full JSON array of all settings where this code
    #   meaningfully appears (inpatient, outpatient, professional, snf, irf,
    #   home_health, sleep_inlab, sleep_home, ed).
    # valid_as_primary_dx: False for codes that are inherently secondary
    #   (history codes, causative-organism codes, status codes, symptom codes
    #   that should be replaced by a confirmed diagnosis). Applies across settings.
    typical_setting: Mapped[str] = mapped_column(
        String(20), default="both", server_default="both"
    )
    applicable_settings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Soft reference to drg_codes.code — the DRG this code most commonly groups
    # to when it is the principal inpatient diagnosis. NULL for outpatient-only
    # codes, secondary/CC-MCC-only codes, and codes where DRG depends heavily
    # on the presence of CC/MCC (use the most common tier in that case).
    typical_drg: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    valid_as_primary_dx: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1"
    )
    audit_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_authority: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_document: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    last_reviewed_at: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    data_confidence: Mapped[float] = mapped_column(Float, default=0.5, server_default="0.5")
    data_confidence_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rule_certainty: Mapped[str] = mapped_column(String(20), default="mandatory", server_default="mandatory")
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)


class DrgCode(Base):
    __tablename__ = "drg_codes"

    drg_code_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(10), unique=True)
    description: Mapped[str] = mapped_column(String(500))
    drg_type: Mapped[str] = mapped_column(String(20))                                   # ms_drg | apr_drg | apc
    mdc: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    mdc_description: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    geometric_mean_los: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    arithmetic_mean_los: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_surgical: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    effective_fy: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    termination_fy: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    # Triplet links — soft references to other drg_codes.code values.
    # mcc_drg: the DRG this becomes when an MCC is present.
    # base_drg: the lowest-tier DRG in this triplet (without CC/MCC).
    mcc_drg: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    base_drg: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    # Representative ICD-10-CM/PCS codes — JSON arrays; LLM context only.
    typical_principal_dx: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    typical_procedures: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    clinical_criteria: Mapped[Optional[str]] = mapped_column(Text, nullable=True)       # LLM grouper context
    audit_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)             # audit-specific guidance
    source_authority: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_document: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    last_reviewed_at: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    data_confidence: Mapped[float] = mapped_column(Float, default=0.5, server_default="0.5")
    data_confidence_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rule_certainty: Mapped[str] = mapped_column(String(20), default="mandatory", server_default="mandatory")
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)


class ModifierCode(Base):
    __tablename__ = "modifier_codes"

    modifier_code_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(5), unique=True)
    description: Mapped[str] = mapped_column(String(500))
    modifier_type: Mapped[str] = mapped_column(String(30))    # informational | payment | pricing | location | service
    applies_to: Mapped[str] = mapped_column(String(10))       # cpt | hcpcs | both
    payment_impact: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)   # none | reduce | increase | bypass_edit
    payment_factor: Mapped[Optional[float]] = mapped_column(Float, nullable=True)      # e.g. 0.50 for mod-51
    ncci_override: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    requires_documentation: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    audit_risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    valid_cpt_prefixes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)     # JSON array of CPT prefixes
    mutually_exclusive_with: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # JSON array of modifier codes
    audit_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_authority: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_document: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    last_reviewed_at: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    data_confidence: Mapped[float] = mapped_column(Float, default=0.5, server_default="0.5")
    data_confidence_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rule_certainty: Mapped[str] = mapped_column(String(20), default="mandatory", server_default="mandatory")
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)


class CptModifierMap(Base):
    """Valid CPT + modifier combinations. Composite PK — no UUID needed."""
    __tablename__ = "cpt_modifier_map"
    __table_args__ = (PrimaryKeyConstraint("cpt_code", "modifier_code"),)

    cpt_code: Mapped[str] = mapped_column(String(10), ForeignKey("cpt_codes.code"))
    modifier_code: Mapped[str] = mapped_column(String(5), ForeignKey("modifier_codes.code"))
    payment_factor: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ncci_override: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_authority: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_document: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    last_reviewed_at: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    data_confidence: Mapped[float] = mapped_column(Float, default=0.5, server_default="0.5")
    data_confidence_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rule_certainty: Mapped[str] = mapped_column(String(20), default="mandatory", server_default="mandatory")


class CptDxCoverage(Base):
    """CPT → ICD-10 clinical coverage rules. Replaces cpt_icd_risks.
    coverage_type: required (ICD must be present), supporting (justifies CPT),
    excluded (ICD indicates CPT is not medically necessary).
    """
    __tablename__ = "cpt_dx_coverage"
    __table_args__ = (PrimaryKeyConstraint("cpt_code", "icd_code"),)

    cpt_code: Mapped[str] = mapped_column(String(10), ForeignKey("cpt_codes.code"))
    icd_code: Mapped[str] = mapped_column(String(10), ForeignKey("icd_codes.code"))
    coverage_type: Mapped[str] = mapped_column(String(20))    # required | supporting | excluded
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_authority: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_document: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    last_reviewed_at: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    data_confidence: Mapped[float] = mapped_column(Float, default=0.5, server_default="0.5")
    data_confidence_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rule_certainty: Mapped[str] = mapped_column(String(20), default="guideline", server_default="guideline")


class FeeSchedule(Base):
    __tablename__ = "fee_schedules"

    fee_schedule_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    provider_org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("provider_orgs.provider_org_id")
    )
    lob: Mapped[str] = mapped_column(String(50))
    cpt_code: Mapped[str] = mapped_column(String(10))
    effective_date: Mapped[str] = mapped_column(String(10))
    termination_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    base_rate: Mapped[float] = mapped_column(Float)
    rate_basis: Mapped[str] = mapped_column(String(50))
    modifier_applicable: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)

    org: Mapped["ProviderOrg"] = relationship(
        "ProviderOrg", back_populates="fee_schedules", lazy="selectin"
    )


class ContractLimitation(Base):
    __tablename__ = "contract_limitations"

    limitation_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    provider_org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("provider_orgs.provider_org_id")
    )
    cpt_code: Mapped[str] = mapped_column(String(10))
    limitation_type: Mapped[str] = mapped_column(String(50))
    limitation_value: Mapped[str] = mapped_column(String(100))
    effective_date: Mapped[str] = mapped_column(String(10))
    description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)

    org: Mapped["ProviderOrg"] = relationship(
        "ProviderOrg", back_populates="contract_limitations", lazy="selectin"
    )


class ReferenceDataFreshness(Base):
    __tablename__ = "reference_data_freshness"

    # Natural PK — not a UUID
    source_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    last_refreshed_at: Mapped[str] = mapped_column(String(30))
    next_scheduled_refresh: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20))          # fresh / stale / critical
    affected_detectors: Mapped[str] = mapped_column(Text)    # JSON array of detector IDs
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)


class EvidenceRequirement(Base):
    """Deterministic 'what evidence does this code require' reference table.

    Used by the AI evidence-validation pass (ai_service.validate_evidence) to
    enrich the prompt with auditable, citation-backed rules instead of relying
    purely on freeform model inference.

    Multiple rows per code are allowed (e.g. modifier-25 needs both documented
    E/M and documented separately-identifiable service — two rules).
    Global reference data (not tenant-scoped) — same convention as cpt_codes
    and icd_codes.
    """
    __tablename__ = "evidence_requirements"

    requirement_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code_type: Mapped[str] = mapped_column(String(20))            # cpt | hcpcs | icd10 | drg | modifier
    code: Mapped[str] = mapped_column(String(20))                 # e.g. '27447' or '25' or 'I25.10'
    required_evidence: Mapped[str] = mapped_column(Text)          # what the chart must show
    policy_reference: Mapped[str] = mapped_column(String(255))    # citation (LCD/NCD, NCCI, MS-DRG, etc.)
    severity_if_missing: Mapped[str] = mapped_column(String(20), default="warning")  # critical | warning
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)


class BillTypeCode(Base):
    """UB-04 bill type codes. Institutional claims only (care_setting=Inpatient/Outpatient or claim_form_type=UB-04)."""
    __tablename__ = "bill_type_codes"

    bill_type_code_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(4), unique=True)           # e.g. "111", "131"
    description: Mapped[str] = mapped_column(String(255))
    facility_type: Mapped[str] = mapped_column(String(50))              # e.g. "hospital", "snf", "home_health"
    bill_classification: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)   # inpatient | outpatient | other
    frequency: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)             # admit_discharge | interim | final
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    audit_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_authority: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)


class RevenueCode(Base):
    """UB-04 revenue codes applied at the claim line level on institutional claims."""
    __tablename__ = "revenue_codes"

    revenue_code_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(4), unique=True)           # e.g. "0360", "0250"
    description: Mapped[str] = mapped_column(String(255))
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)             # room_board | ancillary | pharmacy | therapy | etc.
    typical_setting: Mapped[str] = mapped_column(String(20), default="both", server_default="both")  # inpatient | outpatient | both
    requires_units: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    audit_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_authority: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)


class MLModelVersion(Base):
    __tablename__ = "ml_model_versions"

    version_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    model_name: Mapped[str] = mapped_column(String(100))
    model_artifact_id: Mapped[str] = mapped_column(String(255))
    trained_at: Mapped[str] = mapped_column(String(30))
    training_rows: Mapped[int] = mapped_column(Integer)
    training_window: Mapped[str] = mapped_column(String(50))
    # Lineage: hyperparameters used for this training run (JSON).
    # Pinned at training time — edits to ml_training_config never mutate this.
    training_params: Mapped[str] = mapped_column(Text, default="{}")
    accuracy: Mapped[float] = mapped_column(Float)
    precision_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recall_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    f1_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    f2_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    auc_roc: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    decision_threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    positive_rate: Mapped[float] = mapped_column(Float)
    feature_importance: Mapped[str] = mapped_column(Text)    # JSON
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(30), default=_now)


class CptCoverageGap(Base):
    """Registry of CPT codes that appear on claims but have no entries in
    cpt_dx_coverage. One row per CPT code — seen_count accumulates across
    claims so ops can prioritise which gaps to fill first.

    Populated automatically by DET-18 at detector run time.
    Reviewed and cleared by an admin once coverage rules are added.
    """
    __tablename__ = "cpt_coverage_gaps"

    cpt_code: Mapped[str] = mapped_column(String(10), primary_key=True)
    first_seen_at: Mapped[str] = mapped_column(String(30))
    last_seen_at: Mapped[str] = mapped_column(String(30))
    seen_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    last_seen_claim_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    reviewed_at: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ProviderDeliveryPlaybook(Base):
    """Delivery playbook for a provider organization.

    One-to-one with ProviderOrg. Configures how recovery letters are delivered:
    - email: secure time-limited download link sent to provider contact
    - portal: external agent navigates provider portal and uploads letter
    """
    __tablename__ = "provider_delivery_playbooks"

    playbook_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    provider_org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("provider_orgs.provider_org_id"), unique=True
    )
    delivery_type: Mapped[str] = mapped_column(String(20))  # "email" | "portal"
    status: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft")
    target_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email_template_ref: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    auth_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    preflight_checks: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    navigation_steps: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    confirmation_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    failure_signals: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    post_run_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    last_validated_at: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    created_by_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("opa_users.user_id"), nullable=True)
    updated_by_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("opa_users.user_id"), nullable=True)
    created_at: Mapped[str] = mapped_column(String(30), default=_now, server_default=func.now())
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now, server_default=func.now())

    org: Mapped["ProviderOrg"] = relationship(
        "ProviderOrg", back_populates="playbook", lazy="selectin"
    )

