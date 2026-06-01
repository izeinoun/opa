"""Pydantic schemas for generic LLM document templates + generation."""
from __future__ import annotations

from typing import Any, Optional, Union

from pydantic import BaseModel, Field

_APPS = ("payguard", "claimguard")


class DocumentTemplateRead(BaseModel):
    template_id: str
    app: str
    name: str
    description: Optional[str] = None
    task_prompt: str
    template_markdown: str
    version: int
    is_active: bool
    created_at: str
    updated_at: str


class DocumentTemplateCreate(BaseModel):
    app: str = Field(..., description="Owning application: 'payguard' | 'claimguard'")
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    task_prompt: str = Field(..., description="Default LLM instructions for this template")
    template_markdown: str = Field(..., description="Markdown template body")
    is_active: bool = True


class GenerateDocumentRequest(BaseModel):
    """Either `template_id` or `template_markdown` must be supplied.

    `content` is the information to render — an object or free text.
    `task_prompt` overrides the stored template's default instructions.
    """
    app: str = Field(..., description="Owning application: 'payguard' | 'claimguard'")
    content: Union[dict, str] = Field(..., description="Information to put in the document")
    template_id: Optional[str] = None
    template_markdown: Optional[str] = None
    task_prompt: Optional[str] = None


class GenerateDocumentResponse(BaseModel):
    """Returned by the JSON generation endpoint (PDF as base64).

    The streaming endpoint returns the raw PDF instead.
    """
    markdown: str
    pdf_base64: str
    template_id: Optional[str] = None
