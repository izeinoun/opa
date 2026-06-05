"""In-memory cache for active rule prompts.

Loaded once at startup; reloaded whenever an admin writes a new active prompt.
Detectors call `rule_prompt_cache.get(rule_id, prompt_type)` with no DB round-trip.

Thread/async safety: asyncio.Lock serialises concurrent reloads. Individual
reads are lock-free (dict lookup on an immutable snapshot).
"""
import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.workflow import RulePrompt

logger = logging.getLogger(__name__)

_DEFAULT_PROMPT_TYPE = "evaluation"


@dataclass(frozen=True)
class ActivePrompt:
    rule_id: str
    prompt_type: str
    version: int
    prompt_template: str
    output_schema: Optional[str]   # raw JSON string or None
    model: str
    temperature: float
    notes: Optional[str]
    eval_score: Optional[float]


class RulePromptCache:
    """Singleton in-memory store for active rule prompts.

    Keyed by (rule_id, prompt_type) so a rule can have both an evaluation
    prompt and a verification prompt active simultaneously.
    """

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], ActivePrompt] = {}
        self._lock = asyncio.Lock()
        self._loaded = False

    async def load(self, db: AsyncSession) -> None:
        """(Re)load all active prompts from the DB into memory."""
        async with self._lock:
            rows = (await db.execute(
                select(RulePrompt).where(RulePrompt.active == True)
            )).scalars().all()

            self._cache = {
                (r.rule_id, r.prompt_type): ActivePrompt(
                    rule_id=r.rule_id,
                    prompt_type=r.prompt_type,
                    version=r.version,
                    prompt_template=r.prompt_template,
                    output_schema=r.output_schema,
                    model=r.model,
                    temperature=r.temperature,
                    notes=r.notes,
                    eval_score=r.eval_score,
                )
                for r in rows
            }
            self._loaded = True
            logger.info(
                "[rule_prompt_cache] loaded %d active prompt(s): %s",
                len(self._cache),
                sorted(f"{rule_id}:{pt}" for rule_id, pt in self._cache),
            )

    def get(
        self,
        rule_id: str,
        prompt_type: str = _DEFAULT_PROMPT_TYPE,
    ) -> Optional[ActivePrompt]:
        """Return the active prompt for (rule_id, prompt_type), or None."""
        return self._cache.get((rule_id, prompt_type))

    def get_evaluation(self, rule_id: str) -> Optional[ActivePrompt]:
        return self.get(rule_id, "evaluation")

    def get_verification(self, rule_id: str) -> Optional[ActivePrompt]:
        return self.get(rule_id, "verification")

    def all(self) -> dict[tuple[str, str], ActivePrompt]:
        return dict(self._cache)

    @property
    def loaded(self) -> bool:
        return self._loaded


# Module-level singleton — imported by detectors and routes.
rule_prompt_cache = RulePromptCache()
