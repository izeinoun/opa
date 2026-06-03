import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from ..middleware.auth import require_role
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field
from datetime import datetime, timedelta

from ..database import get_db
from ..dao.user_dao import UserDAO
from ..models.workflow import OpaUser, OpaCase, PrioritizationConfig, DetectorRuleConfig, AuditLog
from ..models.reference import ReferenceDataFreshness, CptCode, IcdCode
from ..schemas.case_schemas import UserRead, CPTCodeRead, ICDCodeRead
from ..schemas.admin_schemas import (
    MLModelSummary,
    MLModelVersionRead,
    MLTrainingConfigRead,
    MLTrainingConfigUpdate,
    MLTrialResult,
    MLCommitRequest,
)
from ..services.ml_model_service import MLModelService, params_from_config
from ..services.prioritization_service import (
    get_config as get_priority_config,
    recompute_open_cases,
)
from ..services import detector_rule_service

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_role("admin"))])


class UserCreate(BaseModel):
    username: str
    email: str
    full_name: str
    role: str


class ReferenceDataFreshnessRead(BaseModel):
    source_name: str
    last_updated: str
    next_due: str
    status: str
    affected_detectors: List[str] = []


def _user_to_read(u: OpaUser) -> UserRead:
    return UserRead(
        id=u.user_id,
        username=u.username,
        full_name=u.full_name,
        email=u.email,
        role=u.role,
        is_active=u.is_active,
    )


@router.get("/users", response_model=List[UserRead])
async def list_users(db: AsyncSession = Depends(get_db)) -> List[UserRead]:
    dao = UserDAO(db)
    users = await dao.get_all()
    return [_user_to_read(u) for u in users]


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_user(
    user_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> UserRead:
    result = await db.execute(select(OpaUser).where(OpaUser.user_id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if "is_active" in body:
        user.is_active = bool(body["is_active"])
    await db.flush()
    return _user_to_read(user)


@router.get("/reference-freshness", response_model=List[ReferenceDataFreshnessRead])
async def get_reference_freshness(db: AsyncSession = Depends(get_db)) -> List[ReferenceDataFreshnessRead]:
    result = await db.execute(select(ReferenceDataFreshness))
    records = result.scalars().all()
    out = []
    for r in records:
        try:
            detectors = json.loads(r.affected_detectors)
        except Exception:
            detectors = []
        out.append(ReferenceDataFreshnessRead(
            source_name=r.source_name,
            last_updated=r.last_refreshed_at,
            next_due=r.next_scheduled_refresh,
            status=r.status,
            affected_detectors=detectors,
        ))
    return out


@router.post("/reference-freshness/{source_name}/refresh", response_model=ReferenceDataFreshnessRead)
async def refresh_reference_source(
    source_name: str,
    db: AsyncSession = Depends(get_db),
) -> ReferenceDataFreshnessRead:
    result = await db.execute(
        select(ReferenceDataFreshness).where(ReferenceDataFreshness.source_name == source_name)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail=f"Source '{source_name}' not found")

    # Preserve the original refresh cadence
    try:
        last = datetime.fromisoformat(record.last_refreshed_at)
        nxt  = datetime.fromisoformat(record.next_scheduled_refresh)
        interval_days = max(7, (nxt - last).days)
    except Exception:
        interval_days = 30

    now = datetime.utcnow()
    record.last_refreshed_at      = now.isoformat()
    record.next_scheduled_refresh = (now + timedelta(days=interval_days)).isoformat()
    record.status                 = "fresh"
    await db.flush()

    try:
        detectors = json.loads(record.affected_detectors)
    except Exception:
        detectors = []

    return ReferenceDataFreshnessRead(
        source_name=record.source_name,
        last_updated=record.last_refreshed_at,
        next_due=record.next_scheduled_refresh,
        status=record.status,
        affected_detectors=detectors,
    )


@router.get("/model", response_model=MLModelSummary)
async def get_active_model(db: AsyncSession = Depends(get_db)) -> MLModelSummary:
    summary = await MLModelService(db).get_active_summary()
    if summary is None:
        raise HTTPException(status_code=404, detail="No active model found")
    return summary


@router.get("/ml-models", response_model=List[MLModelVersionRead])
async def list_ml_models(db: AsyncSession = Depends(get_db)) -> List[MLModelVersionRead]:
    return await MLModelService(db).list_versions()


@router.get("/training-config", response_model=MLTrainingConfigRead)
async def get_training_config(db: AsyncSession = Depends(get_db)) -> MLTrainingConfigRead:
    return await MLModelService(db).get_training_config()


@router.put("/training-config", response_model=MLTrainingConfigRead)
async def update_training_config(
    body: MLTrainingConfigUpdate,
    db: AsyncSession = Depends(get_db),
) -> MLTrainingConfigRead:
    try:
        return await MLModelService(db).update_training_config(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/model/retrain")
async def retrain_model(db: AsyncSession = Depends(get_db)) -> dict:
    """Run a synchronous retrain inside the request using the saved config.
    For larger datasets, prefer POST /api/ml/train (thread executor)."""
    from ..ml.seed_training_data import generate_training_data
    from ..ml.train_billing_variance import train_model

    svc = MLModelService(db)
    cfg = await svc.get_training_config()
    params = params_from_config(cfg)
    try:
        df = generate_training_data()
        result = train_model(df, params=params)
        await svc.write_provider_scores(result["provider_scores"])
        version_id = await svc.write_training_result(
            result,
            params,
            model_name=result.get("model_name", "billing_variance_classifier"),
        )
        return {"status": "success", "version_id": version_id, "metrics": {
            "accuracy": result["accuracy"],
            "precision": result.get("precision"),
            "recall": result.get("recall"),
            "f1_score": result.get("f1_score"),
            "f2_score": result.get("f2_score"),
            "auc_roc": result.get("auc_roc"),
            "decision_threshold": result.get("threshold"),
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")


@router.post("/model/trial", response_model=MLTrialResult)
async def trial_train(body: MLTrainingConfigUpdate) -> MLTrialResult:
    """Experimental training run with the supplied hyperparameters. Returns
    metrics + feature importances but persists NOTHING — no version row, no
    provider-score write, and the live model artifact is left untouched. The
    engineer can re-run this freely while tuning, then call /model/commit when
    satisfied. Same params produce the same model (fixed random_state)."""
    if body.decision_threshold_mode == "manual" and body.manual_threshold is None:
        raise HTTPException(status_code=400,
                            detail="manual_threshold is required when decision_threshold_mode='manual'")

    from ..ml.seed_training_data import generate_training_data
    from ..ml.train_billing_variance import train_model

    params = params_from_config(body)
    try:
        df = generate_training_data()
        result = train_model(df, params=params, persist_artifact=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Trial training failed: {str(e)}")

    return MLTrialResult(
        method=result.get("method", ""),
        params_used=result.get("params_used", params),
        accuracy=result["accuracy"],
        precision=result.get("precision"),
        recall=result.get("recall"),
        f1_score=result.get("f1_score"),
        f2_score=result.get("f2_score"),
        auc_roc=result.get("auc_roc"),
        decision_threshold=result.get("threshold"),
        positive_rate=result["positive_rate"],
        training_rows=result["training_rows"],
        feature_importance=result.get("feature_importance", {}),
    )


@router.post("/model/commit")
async def commit_model(body: MLCommitRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """Save the chosen hyperparameters as the current config, retrain for real
    (persisting the artifact + provider scores), and insert a new active model
    version. Honors the min_auc_to_promote gate. Call this once a trial run
    looks good."""
    if body.decision_threshold_mode == "manual" and body.manual_threshold is None:
        raise HTTPException(status_code=400,
                            detail="manual_threshold is required when decision_threshold_mode='manual'")

    from ..ml.seed_training_data import generate_training_data
    from ..ml.train_billing_variance import train_model

    svc = MLModelService(db)
    # Persist the approved config (everything except the commit-only `notes`).
    cfg_update = MLTrainingConfigUpdate(**body.model_dump(exclude={"notes"}))
    try:
        await svc.update_training_config(cfg_update)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    params = params_from_config(cfg_update)
    try:
        df = generate_training_data()
        result = train_model(df, params=params, persist_artifact=True)
        providers_updated = await svc.write_provider_scores(result["provider_scores"])
        version_id = await svc.write_training_result(
            result,
            params,
            model_name=result.get("model_name", "billing_variance_classifier"),
            notes=body.notes,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")

    return {
        "status": "success",
        "version_id": version_id,
        "providers_updated": providers_updated,
        "metrics": {
            "accuracy": result["accuracy"],
            "precision": result.get("precision"),
            "recall": result.get("recall"),
            "f1_score": result.get("f1_score"),
            "f2_score": result.get("f2_score"),
            "auc_roc": result.get("auc_roc"),
            "decision_threshold": result.get("threshold"),
        },
    }


@router.get("/cpt-codes", response_model=List[CPTCodeRead])
async def list_cpt_codes(db: AsyncSession = Depends(get_db)) -> List[CPTCodeRead]:
    result = await db.execute(select(CptCode))
    codes = result.scalars().all()
    return [
        CPTCodeRead(
            code=c.code,
            description=c.description,
            risk_level=c.value_tier[0].upper() if c.value_tier else "M",
            cms_rac_flag=c.requires_auth,
        )
        for c in codes
    ]


class PrioritizationConfigRead(BaseModel):
    amount_weight: float
    likelihood_weight: float
    urgency_weight: float
    amount_cap: float
    urgency_window_days: int
    high_threshold: float
    medium_threshold: float
    updated_at: str


class PrioritizationConfigUpdate(BaseModel):
    amount_weight: float = Field(ge=0.0, le=1.0)
    likelihood_weight: float = Field(ge=0.0, le=1.0)
    urgency_weight: float = Field(ge=0.0, le=1.0)
    amount_cap: float = Field(gt=0.0)
    urgency_window_days: int = Field(ge=1, le=365)
    high_threshold: float = Field(ge=0.0, le=100.0)
    medium_threshold: float = Field(ge=0.0, le=100.0)


def _cfg_to_read(c: PrioritizationConfig) -> PrioritizationConfigRead:
    return PrioritizationConfigRead(
        amount_weight=c.amount_weight,
        likelihood_weight=c.likelihood_weight,
        urgency_weight=c.urgency_weight,
        amount_cap=c.amount_cap,
        urgency_window_days=c.urgency_window_days,
        high_threshold=c.high_threshold,
        medium_threshold=c.medium_threshold,
        updated_at=c.updated_at,
    )


@router.get("/prioritization-config", response_model=PrioritizationConfigRead)
async def get_prioritization_config(db: AsyncSession = Depends(get_db)) -> PrioritizationConfigRead:
    cfg = await get_priority_config(db)
    return _cfg_to_read(cfg)


@router.put("/prioritization-config", response_model=PrioritizationConfigRead)
async def update_prioritization_config(
    body: PrioritizationConfigUpdate,
    db: AsyncSession = Depends(get_db),
) -> PrioritizationConfigRead:
    weight_sum = body.amount_weight + body.likelihood_weight + body.urgency_weight
    if abs(weight_sum - 1.0) > 0.001:
        raise HTTPException(
            status_code=400,
            detail=f"Weights must sum to 1.0 (got {weight_sum:.3f})",
        )
    if body.high_threshold <= body.medium_threshold:
        raise HTTPException(
            status_code=400,
            detail="HIGH threshold must be greater than MEDIUM threshold",
        )

    cfg = await get_priority_config(db)
    cfg.amount_weight       = body.amount_weight
    cfg.likelihood_weight   = body.likelihood_weight
    cfg.urgency_weight      = body.urgency_weight
    cfg.amount_cap          = body.amount_cap
    cfg.urgency_window_days = body.urgency_window_days
    cfg.high_threshold      = body.high_threshold
    cfg.medium_threshold    = body.medium_threshold
    await db.flush()
    return _cfg_to_read(cfg)


@router.get("/prioritization-config/affected-count")
async def get_affected_case_count(db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(
        select(func.count()).select_from(OpaCase).where(OpaCase.is_active == True)  # noqa: E712
    )
    return {"open_cases": int(result.scalar_one())}


@router.post("/prioritization-config/recompute")
async def recompute_priorities(db: AsyncSession = Depends(get_db)) -> dict:
    cfg = await get_priority_config(db)
    summary = await recompute_open_cases(db, cfg)
    return {"status": "success", **summary}


class DetectorRuleRead(BaseModel):
    rule_code: str
    name: str
    description: str
    enabled: bool
    score: float
    updated_at: str
    has_implementation: bool
    layer: Optional[str]
    layer_order: Optional[int]
    applies_to: Optional[str]
    prepay: bool
    postpay: bool
    rationale: Optional[str]


class DetectorRuleUpdate(BaseModel):
    enabled: Optional[bool] = None
    score: Optional[float] = Field(default=None, ge=0.0, le=1.0)


def _rule_to_read(r: DetectorRuleConfig) -> DetectorRuleRead:
    return DetectorRuleRead(
        rule_code=r.rule_code,
        name=r.name,
        description=r.description,
        enabled=r.enabled,
        score=r.score,
        updated_at=r.updated_at,
        has_implementation=r.has_implementation,
        layer=r.layer,
        layer_order=r.layer_order,
        applies_to=r.applies_to,
        prepay=r.prepay,
        postpay=r.postpay,
        rationale=r.rationale,
    )


async def _resolve_actor(request: Request, db: AsyncSession) -> str:
    """Return a real opa_users.user_id. Falls back to system.bot if header is missing/invalid."""
    header_id = request.headers.get("X-User-Id")
    if header_id:
        result = await db.execute(select(OpaUser.user_id).where(OpaUser.user_id == header_id))
        if result.scalar_one_or_none() is not None:
            return header_id
    result = await db.execute(select(OpaUser.user_id).where(OpaUser.username == "system.bot"))
    sys_id = result.scalar_one_or_none()
    if sys_id is not None:
        return sys_id
    # Last resort: any active user
    result = await db.execute(select(OpaUser.user_id).limit(1))
    return result.scalar_one()


@router.get("/detector-rules", response_model=List[DetectorRuleRead])
async def list_detector_rules(db: AsyncSession = Depends(get_db)) -> List[DetectorRuleRead]:
    rules = await detector_rule_service.get_all(db)
    return [_rule_to_read(r) for r in rules]


@router.put("/detector-rules/{rule_code}", response_model=DetectorRuleRead)
async def update_detector_rule(
    rule_code: str,
    body: DetectorRuleUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> DetectorRuleRead:
    rule = await detector_rule_service.get_by_code(db, rule_code)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_code}' not found")

    changes: dict = {}
    if body.enabled is not None and body.enabled != rule.enabled:
        changes["enabled"] = {"from": rule.enabled, "to": body.enabled}
        rule.enabled = body.enabled
    if body.score is not None and body.score != rule.score:
        changes["score"] = {"from": rule.score, "to": body.score}
        rule.score = body.score

    if not changes:
        return _rule_to_read(rule)

    actor_id = await _resolve_actor(request, db)
    rule.updated_by_user_id = actor_id

    db.add(AuditLog(
        case_id=None,
        actor_user_id=actor_id,
        action="rule_config_updated",
        from_state=None,
        to_state=None,
        reason=None,
        meta_json=json.dumps({"rule_code": rule_code, "changes": changes}),
    ))
    await db.flush()
    return _rule_to_read(rule)


@router.get("/icd-codes", response_model=List[ICDCodeRead])
async def list_icd_codes(db: AsyncSession = Depends(get_db)) -> List[ICDCodeRead]:
    result = await db.execute(select(IcdCode))
    codes = result.scalars().all()
    return [
        ICDCodeRead(
            code=c.code,
            description=c.description,
            category=c.value_tier or "general",
        )
        for c in codes
    ]
