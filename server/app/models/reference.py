from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from uuid import uuid4

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
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
    value_tier: Mapped[str] = mapped_column(String(20))
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    typical_units_max: Mapped[int] = mapped_column(Integer, default=1)
    requires_auth: Mapped[bool] = mapped_column(Boolean, default=False)
    specialty_typical: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)


class IcdCode(Base):
    __tablename__ = "icd_codes"

    icd_code_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(10), unique=True)
    description: Mapped[str] = mapped_column(String(500))
    value_tier: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)


class CptIcdRisk(Base):
    __tablename__ = "cpt_icd_risks"

    cpt_icd_risk_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    cpt_code: Mapped[str] = mapped_column(String(10))
    icd_code: Mapped[str] = mapped_column(String(10))
    mismatch_risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    rationale: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(30), default=_now)
    updated_at: Mapped[str] = mapped_column(String(30), default=_now, onupdate=_now)


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
