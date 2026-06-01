"""ML model + training-config read/write service.

Fronts MLModelVersion + MLTrainingConfig so that routes / UI never depend
on column layout. Storage can move (DB, MLflow, external metrics store)
without changing the public response shape.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.reference import MLModelVersion, Provider
from ..models.workflow import MLTrainingConfig
from ..schemas.admin_schemas import (
    MLModelSummary,
    MLModelVersionRead,
    MLTrainingConfigRead,
    MLTrainingConfigUpdate,
)


# ── helpers ───────────────────────────────────────────────────────────────

def _parse_json(text: Optional[str], default):
    try:
        return json.loads(text) if text else default
    except Exception:
        return default


def _version_label(version_id: str) -> str:
    return f"v{version_id[:8]}"


def _to_summary(m: MLModelVersion) -> MLModelSummary:
    return MLModelSummary(
        version=_version_label(m.version_id),
        trained_at=m.trained_at,
        accuracy=m.accuracy,
        precision=m.precision_score if m.precision_score is not None else 0.0,
        recall=m.recall_score if m.recall_score is not None else 0.0,
        f1_score=m.f1_score if m.f1_score is not None else 0.0,
        f2_score=m.f2_score,
        auc_roc=m.auc_roc if m.auc_roc is not None else 0.0,
        decision_threshold=m.decision_threshold,
        training_samples=m.training_rows,
        feature_importance=_parse_json(m.feature_importance, {}),
    )


def _to_version_read(m: MLModelVersion) -> MLModelVersionRead:
    return MLModelVersionRead(
        version_id=m.version_id,
        model_name=m.model_name,
        version=_version_label(m.version_id),
        trained_at=m.trained_at,
        training_rows=m.training_rows,
        training_params=_parse_json(m.training_params, {}),
        accuracy=m.accuracy,
        precision_score=m.precision_score,
        recall_score=m.recall_score,
        f1_score=m.f1_score,
        f2_score=m.f2_score,
        auc_roc=m.auc_roc,
        decision_threshold=m.decision_threshold,
        positive_rate=m.positive_rate,
        feature_importance=_parse_json(m.feature_importance, {}),
        is_active=m.is_active,
        notes=m.notes or "",
    )


def _to_config_read(c: MLTrainingConfig) -> MLTrainingConfigRead:
    return MLTrainingConfigRead(
        n_estimators=c.n_estimators,
        max_depth=c.max_depth,
        min_samples_split=c.min_samples_split,
        min_samples_leaf=c.min_samples_leaf,
        max_features=c.max_features,
        max_leaf_nodes=c.max_leaf_nodes,
        bootstrap=c.bootstrap,
        class_weight=c.class_weight,
        criterion=c.criterion,
        decision_threshold_mode=c.decision_threshold_mode,
        manual_threshold=c.manual_threshold,
        min_auc_to_promote=c.min_auc_to_promote,
        updated_at=c.updated_at,
    )


# Hyperparameter keys passed to train_billing_variance.train_model(). Kept in
# one place so trial / commit / retrain all build identical param dicts.
_PARAM_KEYS = (
    "n_estimators", "max_depth", "min_samples_split", "min_samples_leaf",
    "max_features", "max_leaf_nodes", "bootstrap", "class_weight", "criterion",
    "decision_threshold_mode", "manual_threshold",
)


def params_from_config(c: MLTrainingConfigRead | MLTrainingConfig) -> dict:
    """Build a train_model() params dict from a config row/read model."""
    return {k: getattr(c, k) for k in _PARAM_KEYS}


# ── service ───────────────────────────────────────────────────────────────

class MLModelService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---- versions -------------------------------------------------------

    async def get_active_summary(self) -> Optional[MLModelSummary]:
        result = await self.session.execute(
            select(MLModelVersion).where(MLModelVersion.is_active == True).limit(1)  # noqa: E712
        )
        m = result.scalar_one_or_none()
        return _to_summary(m) if m else None

    async def list_versions(self) -> List[MLModelVersionRead]:
        result = await self.session.execute(
            select(MLModelVersion).order_by(MLModelVersion.trained_at.desc())
        )
        return [_to_version_read(m) for m in result.scalars().all()]

    async def write_training_result(
        self,
        result: dict,
        params: dict,
        *,
        model_name: str,
        training_window: str = "12_months",
        notes: str = "",
    ) -> str:
        """Insert a new ml_model_versions row from a trainer result dict.

        Honors the min_auc_to_promote gate on ml_training_config: if set
        and auc_roc < gate, the new row is inserted is_active=False and
        the currently-active model is left untouched.
        """
        cfg = await self._get_or_create_config()
        auc = result.get("auc_roc")
        promote = (
            cfg.min_auc_to_promote is None
            or auc is None
            or auc >= cfg.min_auc_to_promote
        )

        new_id = str(uuid4())
        if promote:
            await self.session.execute(
                update(MLModelVersion).values(is_active=False)
            )

        row = MLModelVersion(
            version_id=new_id,
            model_name=model_name,
            model_artifact_id=result.get("model_artifact_id", ""),
            trained_at=datetime.utcnow().isoformat(),
            training_rows=result.get("training_rows", 0),
            training_window=training_window,
            training_params=json.dumps(params),
            accuracy=result.get("accuracy", 0.0),
            precision_score=result.get("precision"),
            recall_score=result.get("recall"),
            f1_score=result.get("f1_score"),
            f2_score=result.get("f2_score"),
            auc_roc=auc,
            decision_threshold=result.get("threshold"),
            positive_rate=result.get("positive_rate", 0.0),
            feature_importance=json.dumps(result.get("feature_importance", {})),
            is_active=promote,
            notes=notes,
        )
        self.session.add(row)
        await self.session.flush()
        return new_id

    async def write_provider_scores(self, provider_scores: dict) -> int:
        """Write billing_variance_score for each provider via the request's
        async session (NOT a raw sqlite3 connection), so it shares the same
        transaction as the version write and never deadlocks on the DB lock.
        Keyed by NPI. Returns the number of rows updated."""
        updated = 0
        for npi, score in provider_scores.items():
            res = await self.session.execute(
                update(Provider)
                .where(Provider.npi == npi)
                .values(billing_variance_score=float(score))
            )
            updated += res.rowcount or 0
        return updated

    # ---- training config -----------------------------------------------

    async def _get_or_create_config(self) -> MLTrainingConfig:
        result = await self.session.execute(
            select(MLTrainingConfig).where(MLTrainingConfig.config_id == "current")
        )
        cfg = result.scalar_one_or_none()
        if cfg is None:
            cfg = MLTrainingConfig(config_id="current")
            self.session.add(cfg)
            await self.session.flush()
        return cfg

    async def get_training_config(self) -> MLTrainingConfigRead:
        cfg = await self._get_or_create_config()
        return _to_config_read(cfg)

    async def update_training_config(
        self,
        body: MLTrainingConfigUpdate,
        actor_user_id: Optional[str] = None,
    ) -> MLTrainingConfigRead:
        if body.decision_threshold_mode == "manual" and body.manual_threshold is None:
            raise ValueError("manual_threshold is required when decision_threshold_mode='manual'")

        cfg = await self._get_or_create_config()
        cfg.n_estimators            = body.n_estimators
        cfg.max_depth               = body.max_depth
        cfg.min_samples_split       = body.min_samples_split
        cfg.min_samples_leaf        = body.min_samples_leaf
        cfg.max_features            = body.max_features
        cfg.max_leaf_nodes          = body.max_leaf_nodes
        cfg.bootstrap               = body.bootstrap
        cfg.class_weight            = body.class_weight
        cfg.criterion               = body.criterion
        cfg.decision_threshold_mode = body.decision_threshold_mode
        cfg.manual_threshold        = body.manual_threshold
        cfg.min_auc_to_promote      = body.min_auc_to_promote
        cfg.updated_by_user_id      = actor_user_id
        await self.session.flush()
        return _to_config_read(cfg)
