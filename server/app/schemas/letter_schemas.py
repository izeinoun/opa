from pydantic import BaseModel
from typing import Optional


class LetterTemplateRead(BaseModel):
    id: str           # = template_id (e.g. "TMPL-MA-001")
    code: str         # = template_id (same value, alias for frontend compat)
    name: str
    template_type: str
    lob: str
    version: int
    is_active: bool
    created_at: str
    regulatory_reference: str = ""


class LetterTemplateDetail(LetterTemplateRead):
    content_html: str


class RecoveryNoticeCreate(BaseModel):
    case_id: int              # case_sequence integer (as user types it)
    template_id: str          # template_id string
    amount_demanded: float
    delivery_method: str
    response_due: Optional[str] = None


class RecoveryNoticeRead(BaseModel):
    id: str
    sent_date: str
    amount_demanded: float
    response_due: str
    delivery_method: str
    status: str


class RenderedLetter(BaseModel):
    case_id: int
    template_code: str
    html_content: str
    rendered_at: str
