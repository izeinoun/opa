"""Generic LLM-driven document generation, shared by both apps.

Contract: a caller supplies
  • `content`        — the information to put in the document (dict or text),
  • `task_prompt`    — instructions describing the document to produce,
  • `template`       — a Markdown template (resolved from a stored
                       DocumentTemplate, or passed inline).

The LLM fills/expands the template from the content per the task prompt and
returns the final document **as Markdown**. We then render that Markdown to a
PDF (utils.markdown_pdf). Both the Markdown and the PDF bytes are returned so
callers can store/preview the text and stream the PDF.

The Anthropic client + model are reused from ai_service so all LLM calls in
the codebase share one configuration point.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..dao.document_template_dao import DocumentTemplateDAO
from ..services.ai_service import MODEL, _client
from ..utils.markdown_pdf import markdown_to_pdf

logger = logging.getLogger(__name__)

GENERATION_SYSTEM_PROMPT = (
    "You are a document-generation assistant. You are given a task "
    "description, a body of source content, and a Markdown template. "
    "Produce the finished document by filling and, where the task asks for it, "
    "expanding the template using ONLY facts present in the supplied content. "
    "Rules:\n"
    "- Output valid GitHub-flavored Markdown and NOTHING else — no preamble, "
    "no code fences around the whole document, no explanations.\n"
    "- Preserve the template's structure and headings unless the task says "
    "otherwise.\n"
    "- Never invent facts (names, dates, amounts, citations) that are not in "
    "the content. If a required value is missing, write '[NOT PROVIDED]'.\n"
    "- Keep tone professional and appropriate for an official letter/notice."
)

# Hard ceiling on a single generation; long letters comfortably fit.
_MAX_TOKENS = 4096


class DocumentGenerationError(RuntimeError):
    """Raised when generation cannot proceed (bad input, LLM failure)."""


class GeneratedDocument:
    """Lightweight result holder (not an ORM/Pydantic type)."""

    def __init__(self, markdown: str, pdf_bytes: bytes, template_id: Optional[str]):
        self.markdown = markdown
        self.pdf_bytes = pdf_bytes
        self.template_id = template_id


class DocumentGenerationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.templates = DocumentTemplateDAO(db)

    async def generate(
        self,
        *,
        app: str,
        content: Any,
        template_id: Optional[str] = None,
        template_markdown: Optional[str] = None,
        task_prompt: Optional[str] = None,
    ) -> GeneratedDocument:
        """Generate a document for `app`.

        Provide either `template_id` (resolved from storage, scoped to `app`)
        or an inline `template_markdown`. `task_prompt` overrides the stored
        template's default instructions when supplied.
        """
        resolved_template = template_markdown
        resolved_prompt = task_prompt
        resolved_id: Optional[str] = None

        if template_id:
            tmpl = await self.templates.get_by_id(template_id, app=app)
            if tmpl is None:
                raise DocumentGenerationError(
                    f"No template '{template_id}' for app '{app}'"
                )
            resolved_id = tmpl.template_id
            resolved_template = template_markdown or tmpl.template_markdown
            resolved_prompt = task_prompt or tmpl.task_prompt

        if not resolved_template:
            raise DocumentGenerationError(
                "Provide either template_id or template_markdown"
            )
        if not resolved_prompt:
            raise DocumentGenerationError(
                "Provide a task_prompt (inline, or via the stored template)"
            )

        markdown = await self._call_llm(
            task_prompt=resolved_prompt,
            template=resolved_template,
            content=content,
        )
        try:
            pdf_bytes = markdown_to_pdf(markdown, title=resolved_id or app)
        except Exception as e:  # pragma: no cover - depends on optional deps
            logger.exception("markdown_to_pdf failed")
            raise DocumentGenerationError(f"PDF rendering failed: {e}") from e

        return GeneratedDocument(markdown, pdf_bytes, resolved_id)

    async def _call_llm(self, *, task_prompt: str, template: str, content: Any) -> str:
        if isinstance(content, str):
            content_block = content
        else:
            content_block = json.dumps(content, indent=2, default=str)

        user_msg = (
            f"## Task\n{task_prompt}\n\n"
            f"## Source content\n{content_block}\n\n"
            f"## Markdown template\n{template}\n\n"
            "Return the finished document as Markdown only."
        )

        try:
            client = _client()
            resp = await client.messages.create(
                model=MODEL,
                max_tokens=_MAX_TOKENS,
                system=GENERATION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
        except Exception as e:
            logger.exception("LLM generation call failed")
            raise DocumentGenerationError(f"LLM call failed: {e}") from e

        text = "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        ).strip()
        if not text:
            raise DocumentGenerationError("LLM returned empty content")
        return _strip_outer_fence(text)


def _strip_outer_fence(text: str) -> str:
    """Remove a wrapping ```markdown ... ``` fence if the model added one."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1]).strip()
    return stripped
