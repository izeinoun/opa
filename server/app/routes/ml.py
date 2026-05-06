"""GET /api/ml/info  — model artifact status
   POST /api/ml/train — regenerate training data, retrain, write scores to DB
   POST /api/ml/upload — accept a CSV upload as custom training data, then retrain
"""
from __future__ import annotations

import asyncio
import io
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from ..ml.train_billing_variance import (
    FEATURE_COLS,
    MODEL_NAME,
    _ARTIFACT_PATH,
    train_model,
    write_scores_to_db,
)
from ..ml.seed_training_data import generate_training_data

router = APIRouter(prefix="/api/ml", tags=["ml"])


# ── Response schemas ──────────────────────────────────────────────────────────

class ModelInfo(BaseModel):
    model_name: str
    artifact_path: str
    exists: bool
    last_modified: Optional[str]
    size_kb: Optional[float]
    feature_cols: list[str]


class TrainResult(BaseModel):
    success: bool
    method: str
    accuracy: float
    positive_rate: float
    training_rows: int
    providers_updated: int
    feature_importance: dict[str, float]
    provider_scores: dict[str, float]
    trained_at: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _model_info() -> ModelInfo:
    exists = _ARTIFACT_PATH.exists()
    last_modified: Optional[str] = None
    size_kb: Optional[float] = None
    if exists:
        stat = _ARTIFACT_PATH.stat()
        last_modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        size_kb = round(stat.st_size / 1024, 1)
    return ModelInfo(
        model_name=MODEL_NAME,
        artifact_path=str(_ARTIFACT_PATH),
        exists=exists,
        last_modified=last_modified,
        size_kb=size_kb,
        feature_cols=FEATURE_COLS,
    )


def _run_training(df: pd.DataFrame) -> TrainResult:
    result: dict[str, Any] = train_model(df)
    n_updated = write_scores_to_db(result["provider_scores"])
    return TrainResult(
        success=result["success"],
        method=result["method"],
        accuracy=result["accuracy"],
        positive_rate=result["positive_rate"],
        training_rows=result["training_rows"],
        providers_updated=n_updated,
        feature_importance=result["feature_importance"],
        provider_scores=result["provider_scores"],
        trained_at=datetime.now(timezone.utc).isoformat(),
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/info", response_model=ModelInfo)
async def get_model_info() -> ModelInfo:
    return _model_info()


@router.post("/train", response_model=TrainResult)
async def train(use_seed_data: bool = True) -> TrainResult:
    """Regenerate synthetic seed data and retrain the model."""
    loop = asyncio.get_event_loop()
    try:
        df = await loop.run_in_executor(None, generate_training_data)
        result = await loop.run_in_executor(None, _run_training, df)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Training failed: {exc}") from exc
    return result


@router.post("/upload", response_model=TrainResult)
async def upload_and_train(file: UploadFile = File(...)) -> TrainResult:
    """Accept a CSV file with the required feature columns and retrain."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted.")

    content = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {exc}") from exc

    missing = [c for c in FEATURE_COLS + ["had_confirmed_overpayment"] if c not in df.columns]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"CSV is missing required columns: {missing}",
        )

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, _run_training, df)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Training failed: {exc}") from exc
    return result
