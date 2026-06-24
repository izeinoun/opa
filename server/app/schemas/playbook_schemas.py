from typing import Optional, List, Any
from pydantic import BaseModel, Field


class AuthConfigSchema(BaseModel):
    method: str = Field(..., description="username_password | sso | token")
    mfa: bool = False
    mfa_method: Optional[str] = Field(None, description="totp | sms | email | none")
    credential_ref: Optional[str] = None
    session_reuse: bool = False


class PreflightCheckSchema(BaseModel):
    field: str
    label: str
    required: bool


class NavigationStepSchema(BaseModel):
    step: int
    label: str
    action: str  # navigate | click | type | select | upload | wait | assert
    target: str
    value: Optional[str] = None
    timeout_ms: int
    on_failure: str  # retry | skip | abort | flag_for_review


class ConfirmationConfigSchema(BaseModel):
    type: str  # confirmation_number | banner_text | email | none
    capture_method: str  # selector | screenshot | email_parse | none
    selector: Optional[str] = None
    save_to_field: Optional[str] = None


class FailureSignalSchema(BaseModel):
    text: str
    action: str  # retry | skip | abort | flag_for_review
    note: str


class PostRunConfigSchema(BaseModel):
    success_status: str
    screenshot: bool = False
    notify_analyst: bool = False


class PlaybookCreate(BaseModel):
    delivery_type: str
    status: str = "draft"
    target_url: Optional[str] = None
    contact_email: Optional[str] = None
    contact_name: Optional[str] = None
    email_template_ref: Optional[str] = None
    notes: Optional[str] = None
    auth_config: Optional[dict] = None
    preflight_checks: Optional[List[dict]] = None
    navigation_steps: Optional[List[dict]] = None
    confirmation_config: Optional[dict] = None
    failure_signals: Optional[List[dict]] = None
    post_run_config: Optional[dict] = None


class PlaybookUpdate(BaseModel):
    delivery_type: Optional[str] = None
    status: Optional[str] = None
    target_url: Optional[str] = None
    contact_email: Optional[str] = None
    contact_name: Optional[str] = None
    email_template_ref: Optional[str] = None
    notes: Optional[str] = None
    auth_config: Optional[dict] = None
    preflight_checks: Optional[List[dict]] = None
    navigation_steps: Optional[List[dict]] = None
    confirmation_config: Optional[dict] = None
    failure_signals: Optional[List[dict]] = None
    post_run_config: Optional[dict] = None


class PlaybookRead(BaseModel):
    playbook_id: str
    provider_org_id: str
    delivery_type: str
    status: str
    target_url: Optional[str]
    contact_email: Optional[str]
    contact_name: Optional[str]
    email_template_ref: Optional[str]
    notes: Optional[str]
    auth_config: Optional[dict]
    preflight_checks: Optional[List[dict]]
    navigation_steps: Optional[List[dict]]
    confirmation_config: Optional[dict]
    failure_signals: Optional[List[dict]]
    post_run_config: Optional[dict]
    last_validated_at: Optional[str]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True
