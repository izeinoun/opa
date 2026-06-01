"""Tests for the generic LLM document-generation feature.

The LLM call is mocked, so these run offline. The markdown→PDF path is
exercised for real (no network), validating the fpdf2 pipeline end to end.
"""
import asyncio
import types

import pytest

from app.services import document_generation_service as dgs
from app.services.document_generation_service import (
    DocumentGenerationError,
    DocumentGenerationService,
    _strip_outer_fence,
)
from app.utils.markdown_pdf import markdown_to_html, markdown_to_pdf


# ── markdown → PDF ────────────────────────────────────────────────────────

def test_markdown_to_pdf_produces_valid_pdf():
    pdf = markdown_to_pdf("# Title\n\nHello **world**.\n\n- a\n- b\n", title="t")
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF")  # PDF magic header
    assert len(pdf) > 200


def test_markdown_to_html_renders_table():
    html = markdown_to_html("| a | b |\n|---|---|\n| 1 | 2 |\n")
    assert "<table>" in html


# ── fence stripping ───────────────────────────────────────────────────────

def test_strip_outer_fence_removes_wrapper():
    assert _strip_outer_fence("```markdown\n# Hi\n```") == "# Hi"
    assert _strip_outer_fence("# Hi\n\nbody") == "# Hi\n\nbody"


# ── service generation (LLM mocked) ───────────────────────────────────────

def _fake_client(returned_text: str):
    """Build a stub mimicking AsyncAnthropic with .messages.create()."""
    block = types.SimpleNamespace(type="text", text=returned_text)
    resp = types.SimpleNamespace(content=[block])

    class _Messages:
        async def create(self, **kwargs):
            return resp

    return types.SimpleNamespace(messages=_Messages())


def test_generate_inline_template(monkeypatch):
    monkeypatch.setattr(dgs, "_client", lambda: _fake_client("# Letter\n\nDear X."))
    svc = DocumentGenerationService(db=None)  # DB unused for inline templates
    doc = asyncio.run(
        svc.generate(
            app="payguard",
            content={"name": "X"},
            template_markdown="# Letter\n\nDear {name}.",
            task_prompt="Write a letter.",
        )
    )
    assert "Dear X" in doc.markdown
    assert doc.pdf_bytes.startswith(b"%PDF")
    assert doc.template_id is None


def test_generate_requires_template():
    svc = DocumentGenerationService(db=None)
    with pytest.raises(DocumentGenerationError):
        asyncio.run(svc.generate(app="payguard", content={}, task_prompt="x"))


def test_generate_requires_prompt():
    svc = DocumentGenerationService(db=None)
    with pytest.raises(DocumentGenerationError):
        asyncio.run(
            svc.generate(app="payguard", content={}, template_markdown="# x")
        )


def test_generate_empty_llm_output_errors(monkeypatch):
    monkeypatch.setattr(dgs, "_client", lambda: _fake_client("   "))
    svc = DocumentGenerationService(db=None)
    with pytest.raises(DocumentGenerationError):
        asyncio.run(
            svc.generate(
                app="payguard",
                content={},
                template_markdown="# x",
                task_prompt="go",
            )
        )
