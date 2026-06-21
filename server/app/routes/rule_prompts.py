"""CRUD API for rule prompts (versioned LLM prompt management).

GET  /api/rule-prompts              — list all prompts (filterable by rule_id)
GET  /api/rule-prompts/active       — active prompt per rule (cache view)
GET  /api/rule-prompts/{id}         — single prompt by UUID
POST /api/rule-prompts              — create new version (auto-increments version)
POST /api/rule-prompts/{id}/activate — make this version active, deactivate others
PUT  /api/rule-prompts/{id}         — edit non-structural fields (notes, eval_score)
DELETE /api/rule-prompts/{id}       — soft-delete (deactivate only; history kept)
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..middleware.auth import get_current_user, require_app
from ..models.workflow import OpaUser, RulePrompt
from ..services.rule_prompt_cache import rule_prompt_cache

router = APIRouter(
    prefix="/api/rule-prompts",
    tags=["rule-prompts"],
    dependencies=[Depends(require_app("payguard"))],
)

_NOW = lambda: datetime.utcnow().isoformat()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class RulePromptRead(BaseModel):
    id: str
    rule_id: str
    prompt_type: str
    version: int
    prompt_template: str
    output_schema: Optional[str] = None
    active: bool
    model: str
    temperature: float
    last_edited_by: Optional[str] = None
    last_edited_at: str
    notes: Optional[str] = None
    eval_score: Optional[float] = None


class RulePromptCreate(BaseModel):
    rule_id: str
    prompt_type: str = "evaluation"
    prompt_template: str
    output_schema: Optional[str] = None
    model: str = Field(default_factory=lambda: settings.llm_model)
    temperature: float = 0.0
    notes: Optional[str] = None
    activate: bool = True   # immediately activate the new version


class RulePromptPatch(BaseModel):
    notes: Optional[str] = None
    eval_score: Optional[float] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_read(r: RulePrompt) -> RulePromptRead:
    return RulePromptRead(
        id=r.id,
        rule_id=r.rule_id,
        prompt_type=r.prompt_type,
        version=r.version,
        prompt_template=r.prompt_template,
        output_schema=r.output_schema,
        active=r.active,
        model=r.model,
        temperature=r.temperature,
        last_edited_by=r.last_edited_by,
        last_edited_at=r.last_edited_at,
        notes=r.notes,
        eval_score=r.eval_score,
    )


async def _next_version(db: AsyncSession, rule_id: str, prompt_type: str) -> int:
    """Next version number scoped to (rule_id, prompt_type)."""
    result = await db.execute(
        select(RulePrompt.version)
        .where(RulePrompt.rule_id == rule_id, RulePrompt.prompt_type == prompt_type)
        .order_by(RulePrompt.version.desc())
        .limit(1)
    )
    current = result.scalar_one_or_none()
    return (current or 0) + 1


async def _deactivate_rule(db: AsyncSession, rule_id: str, prompt_type: str) -> None:
    """Deactivate all active versions for a (rule_id, prompt_type) pair."""
    await db.execute(
        update(RulePrompt)
        .where(
            RulePrompt.rule_id == rule_id,
            RulePrompt.prompt_type == prompt_type,
            RulePrompt.active == True,
        )
        .values(active=False)
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[RulePromptRead])
async def list_prompts(
    rule_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> List[RulePromptRead]:
    stmt = select(RulePrompt).order_by(RulePrompt.rule_id, RulePrompt.version.desc())
    if rule_id:
        stmt = stmt.where(RulePrompt.rule_id == rule_id)
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_read(r) for r in rows]


@router.get("/active", response_model=List[RulePromptRead])
async def list_active_prompts(db: AsyncSession = Depends(get_db)) -> List[RulePromptRead]:
    """Returns the currently active prompt per rule — reflects the live cache state."""
    rows = (await db.execute(
        select(RulePrompt).where(RulePrompt.active == True).order_by(RulePrompt.rule_id)
    )).scalars().all()
    return [_to_read(r) for r in rows]


@router.get("/{prompt_id}", response_model=RulePromptRead)
async def get_prompt(prompt_id: str, db: AsyncSession = Depends(get_db)) -> RulePromptRead:
    row = (await db.execute(select(RulePrompt).where(RulePrompt.id == prompt_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return _to_read(row)


@router.post("", response_model=RulePromptRead, status_code=201)
async def create_prompt(
    body: RulePromptCreate,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> RulePromptRead:
    """Create a new version of a rule prompt. If activate=True (default), the new
    version becomes active and the previous active version is deactivated."""
    from uuid import uuid4

    version = await _next_version(db, body.rule_id, body.prompt_type)

    if body.activate:
        await _deactivate_rule(db, body.rule_id, body.prompt_type)

    row = RulePrompt(
        id=str(uuid4()),
        rule_id=body.rule_id,
        prompt_type=body.prompt_type,
        version=version,
        prompt_template=body.prompt_template,
        output_schema=body.output_schema,
        active=body.activate,
        model=body.model,
        temperature=body.temperature,
        last_edited_by=current_user.username,
        last_edited_at=_NOW(),
        notes=body.notes,
        eval_score=None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    # Reload the cache so the new prompt is available immediately.
    await rule_prompt_cache.load(db)

    return _to_read(row)


@router.post("/{prompt_id}/activate", response_model=RulePromptRead)
async def activate_prompt(
    prompt_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> RulePromptRead:
    """Make a specific version the active prompt for its rule, deactivating others."""
    row = (await db.execute(select(RulePrompt).where(RulePrompt.id == prompt_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Prompt not found")

    await _deactivate_rule(db, row.rule_id, row.prompt_type)
    row.active = True
    row.last_edited_by = current_user.username
    row.last_edited_at = _NOW()
    await db.commit()
    await db.refresh(row)

    await rule_prompt_cache.load(db)
    return _to_read(row)


@router.put("/{prompt_id}", response_model=RulePromptRead)
async def patch_prompt(
    prompt_id: str,
    body: RulePromptPatch,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> RulePromptRead:
    """Update notes or eval_score on an existing prompt version."""
    row = (await db.execute(select(RulePrompt).where(RulePrompt.id == prompt_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Prompt not found")

    if body.notes is not None:
        row.notes = body.notes
    if body.eval_score is not None:
        row.eval_score = body.eval_score
    row.last_edited_by = current_user.username
    row.last_edited_at = _NOW()
    await db.commit()
    await db.refresh(row)

    if row.active:
        await rule_prompt_cache.load(db)
    return _to_read(row)


@router.delete("/{prompt_id}", status_code=204)
async def deactivate_prompt(
    prompt_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> None:
    """Deactivate a prompt version (history is preserved; not a hard delete)."""
    row = (await db.execute(select(RulePrompt).where(RulePrompt.id == prompt_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Prompt not found")
    row.active = False
    row.last_edited_by = current_user.username
    row.last_edited_at = _NOW()
    await db.commit()
    await rule_prompt_cache.load(db)
