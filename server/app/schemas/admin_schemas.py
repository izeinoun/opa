"""Pydantic schemas for ML-model + training-config admin endpoints.

Moved out of routes/admin.py so multiple routes / services share the
same public contract.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ── ML model versions ─────────────────────────────────────────────────────

class MLModelSummary(BaseModel):
    """Shape consumed by the Admin → ML Model screen (active model)."""
    version: str
    trained_at: str
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    f2_score: Optional[float] = None
    auc_roc: float
    decision_threshold: Optional[float] = None
    training_samples: int
    feature_importance: dict = {}


class MLModelVersionRead(BaseModel):
    """Full row read for the ML versions list/history."""
    version_id: str
    model_name: str
    version: str
    trained_at: str
    training_rows: int
    training_params: dict = {}
    accuracy: float
    precision_score: Optional[float] = None
    recall_score: Optional[float] = None
    f1_score: Optional[float] = None
    f2_score: Optional[float] = None
    auc_roc: Optional[float] = None
    decision_threshold: Optional[float] = None
    positive_rate: float
    feature_importance: dict = {}
    is_active: bool
    notes: str = ""


# ── ML training config (admin-editable hyperparameters) ──────────────────

class MLTrainingConfigRead(BaseModel):
    n_estimators: int
    max_depth: Optional[int] = None
    min_samples_leaf: int
    decision_threshold_mode: str
    manual_threshold: Optional[float] = None
    min_auc_to_promote: Optional[float] = None
    updated_at: str


class MLTrainingConfigUpdate(BaseModel):
    n_estimators: int = Field(ge=10, le=2000)
    max_depth: Optional[int] = Field(default=None, ge=1, le=100)
    min_samples_leaf: int = Field(ge=1, le=200)
    decision_threshold_mode: str = Field(pattern="^(auto_f2|manual)$")
    manual_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    min_auc_to_promote: Optional[float] = Field(default=None, ge=0.0, le=1.0)
