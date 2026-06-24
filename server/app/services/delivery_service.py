import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from uuid import uuid4

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import SECRET_KEY, EMAILJS_SERVICE_ID, EMAILJS_PRIVATE_KEY, EMAILJS_PUBLIC_KEY
from ..config import EMAILJS_TEMPLATE_ID_SECURE_LINK, EMAILJS_TEMPLATE_ID_OTP, EMAILJS_TEMPLATE_ID_NOTIFY_PAYER
from ..models.reference import ProviderDeliveryPlaybook
from ..models.workflow import OpaCase, AuditLog
from ..dao.playbook_dao import PlaybookDAO
from ..dao.audit_log_dao import AuditLogDAO
from ..dao.case_dao import CaseDAO


class DeliveryError(Exception):
    """Raised when delivery operations fail."""
    pass


class SecureTokenError(Exception):
    """Raised when secure token operations fail."""
    pass


class DeliveryService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.playbook_dao = PlaybookDAO(session)
        self.audit_log_dao = AuditLogDAO(session)
        self.case_dao = CaseDAO(session)

    @staticmethod
    def _generate_secure_token(case_id: str, provider_npi: str, expiry_hours: int = 24) -> str:
        """Generate a signed token for secure letter download.

        Format: base64url(case_id:npi_sha256:exp_unix).signature
        Stateless — no DB storage needed.
        """
        npi_hash = hashlib.sha256(provider_npi.encode()).hexdigest()
        exp_unix = int((datetime.utcnow() + timedelta(hours=expiry_hours)).timestamp())
        payload = f"{case_id}:{npi_hash}:{exp_unix}"

        # Base64url encode the payload
        payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")

        # HMAC-SHA256 signature
        signature = hmac.new(
            SECRET_KEY.encode(),
            payload_b64.encode(),
            hashlib.sha256,
        ).digest()
        signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")

        return f"{payload_b64}.{signature_b64}"

    @staticmethod
    def _verify_secure_token(token: str) -> Dict[str, Any]:
        """Verify and decode a secure token.

        Returns: {case_id, npi_hash, exp_unix}
        Raises: SecureTokenError if invalid or expired.
        """
        try:
            payload_b64, signature_b64 = token.split(".")
        except ValueError:
            raise SecureTokenError("Invalid token format")

        # Verify signature
        expected_sig = hmac.new(
            SECRET_KEY.encode(),
            payload_b64.encode(),
            hashlib.sha256,
        ).digest()
        expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).decode().rstrip("=")

        if not hmac.compare_digest(signature_b64, expected_sig_b64):
            raise SecureTokenError("Token signature invalid")

        # Decode payload
        try:
            payload_decoded = base64.urlsafe_b64decode(payload_b64 + "==")
            case_id, npi_hash, exp_unix_str = payload_decoded.decode().split(":")
            exp_unix = int(exp_unix_str)
        except (ValueError, UnicodeDecodeError):
            raise SecureTokenError("Token decode failed")

        # Check expiry
        if datetime.utcnow().timestamp() > exp_unix:
            raise SecureTokenError("Token expired")

        return {"case_id": case_id, "npi_hash": npi_hash, "exp_unix": exp_unix}

    async def send_email_notice(
        self,
        case_id: str,
        acting_user_id: str,
        app_domain: str,
    ) -> tuple[str, OpaCase]:
        """Send secure download link to provider via email.

        Returns: (token, updated_case)
        Raises: DeliveryError on email failure.
        """
        case = await self.case_dao.get_by_id(case_id)
        if not case:
            raise DeliveryError(f"Case {case_id} not found")

        playbook = await self.playbook_dao.get_by_org(case.provider_org_id)
        if not playbook or playbook.delivery_type != "email":
            raise DeliveryError("No email playbook configured for provider")

        if not playbook.contact_email:
            raise DeliveryError("No contact email configured in playbook")

        # Generate token
        provider = case.claim.provider if case.claim else None
        if not provider:
            raise DeliveryError("Cannot determine provider NPI for case")

        token = self._generate_secure_token(case_id, provider.npi, expiry_hours=24)
        secure_url = f"{app_domain}/secure-download?token={token}"

        # Send email via EmailJS
        try:
            await self._send_email_emailjs(
                template="secure_link",
                to_email=playbook.contact_email,
                to_name=playbook.contact_name,
                template_params={
                    "secure_link": secure_url,
                    "provider_name": case.claim.provider_org.name if case.claim else "",
                    "case_id": case.case_number,
                    "expiry_hours": 24,
                    "payer_name": "PayGuard",  # Could be made configurable
                },
            )
        except Exception as e:
            raise DeliveryError(f"Email send failed: {str(e)}")

        # Update case
        case.delivery_confirmation_ref = token
        case.last_delivery_attempt_at = datetime.utcnow().isoformat()
        self.session.add(case)
        await self.session.flush()

        # Audit log
        await self.audit_log_dao.create_entry(
            case_id=case_id,
            actor_user_id=acting_user_id,
            action="EMAIL_SENT",
            from_status=None,
            to_status=None,
            reason=f"Secure link sent to {playbook.contact_email}",
        )

        return token, case

    async def verify_npi(
        self,
        token: str,
        entered_npi: str,
    ) -> bool:
        """Verify entered NPI against token hash.

        Returns: True if match, False otherwise.
        """
        try:
            token_data = self._verify_secure_token(token)
        except SecureTokenError:
            return False

        npi_hash = hashlib.sha256(entered_npi.encode()).hexdigest()
        return hmac.compare_digest(npi_hash, token_data["npi_hash"])

    async def record_letter_access(
        self,
        token: str,
        acting_user_id: Optional[str] = None,
    ) -> OpaCase:
        """Record that provider accessed the secure download link.

        Updates case status to letter_accessed and logs audit event.
        """
        try:
            token_data = self._verify_secure_token(token)
        except SecureTokenError as e:
            raise DeliveryError(f"Cannot verify token: {str(e)}")

        case_id = token_data["case_id"]
        case = await self.case_dao.get_by_id(case_id)
        if not case:
            raise DeliveryError(f"Case {case_id} not found")

        case.status = "letter_accessed"
        case.last_delivery_attempt_at = datetime.utcnow().isoformat()
        self.session.add(case)
        await self.session.flush()

        # Audit log
        await self.audit_log_dao.create_entry(
            case_id=case_id,
            actor_user_id=acting_user_id or "system",
            action="LETTER_ACCESSED",
            from_status="notice_sent",
            to_status="letter_accessed",
            reason="Provider accessed secure download link",
        )

        return case

    async def get_delivery_queue(
        self,
        mode: Optional[str] = None,
        db_session: Optional[AsyncSession] = None,
    ) -> List[Dict[str, Any]]:
        """Get all cases ready for delivery, optionally filtered by mode.

        Returns self-contained payload: case detail + full playbook embedded.
        Sorted by deadline ascending.
        """
        session = db_session or self.session

        # Query cases in ready_to_send status
        from sqlalchemy import select, asc
        stmt = select(OpaCase).where(OpaCase.status == "ready_to_send")
        result = await session.execute(stmt)
        cases = result.scalars().all()

        queue = []
        for case in cases:
            playbook = await self.playbook_dao.get_by_org(case.provider_org_id)
            if playbook and (mode is None or playbook.delivery_type == mode):
                queue.append(self._serialize_delivery_item(case, playbook))

        # Sort by deadline ascending
        queue.sort(key=lambda x: x["deadline_date"])
        return queue

    async def write_delivery_result(
        self,
        case_id: str,
        status: str,
        delivery_confirmation_ref: Optional[str] = None,
        last_delivery_attempt_at: Optional[str] = None,
        notes: Optional[str] = None,
        acting_user_id: str = "system",
    ) -> OpaCase:
        """Agent writes back delivery result.

        Validates status transition from ready_to_send.
        Updates case and logs audit event.
        """
        case = await self.case_dao.get_by_id(case_id)
        if not case:
            raise DeliveryError(f"Case {case_id} not found")

        if case.status != "ready_to_send":
            raise DeliveryError(
                f"Cannot transition from {case.status} to {status}. "
                "Only ready_to_send cases can accept delivery results."
            )

        # Validate status transition
        valid_transitions = {"letter_sent", "delivery_failed", "needs_review"}
        if status not in valid_transitions:
            raise DeliveryError(f"Invalid delivery status: {status}")

        from_state = case.status
        case.status = status
        case.last_delivery_attempt_at = last_delivery_attempt_at or datetime.utcnow().isoformat()
        if delivery_confirmation_ref:
            case.delivery_confirmation_ref = delivery_confirmation_ref
        self.session.add(case)
        await self.session.flush()

        # Audit log
        await self.audit_log_dao.create_entry(
            case_id=case_id,
            actor_user_id=acting_user_id,
            action="DELIVERY_RESULT_RECORDED",
            from_status=from_state,
            to_status=status,
            reason=notes or f"Delivery {status}",
        )

        return case

    @staticmethod
    def _serialize_delivery_item(case: OpaCase, playbook: ProviderDeliveryPlaybook) -> Dict[str, Any]:
        """Serialize case + playbook for delivery queue API response."""
        return {
            "case_id": case.case_id,
            "case_number": case.case_number,
            "claim_id": case.claim_id,
            "provider_name": case.claim.provider_org.name if case.claim else "",
            "provider_npi": case.claim.provider_org.npi if case.claim else "",
            "member_id": case.member_id,
            "lob": case.lob,
            "amount_at_risk": case.total_overpayment_amount,
            "deadline": case.deadline_date,
            "deadline_date": case.deadline_date,
            "status": case.status,
            "delivery_mode": playbook.delivery_type,
            "playbook": {
                "playbook_id": playbook.playbook_id,
                "delivery_type": playbook.delivery_type,
                "status": playbook.status,
                "target_url": playbook.target_url,
                "contact_email": playbook.contact_email,
                "contact_name": playbook.contact_name,
                "email_template_ref": playbook.email_template_ref,
                "notes": playbook.notes,
                "auth_config": playbook.auth_config,
                "preflight_checks": playbook.preflight_checks,
                "navigation_steps": playbook.navigation_steps,
                "confirmation_config": playbook.confirmation_config,
                "failure_signals": playbook.failure_signals,
                "post_run_config": playbook.post_run_config,
            },
        }

    @staticmethod
    async def _send_email_emailjs(
        template: str,
        to_email: str,
        to_name: Optional[str],
        template_params: Dict[str, Any],
    ) -> None:
        """Send email via EmailJS REST API.

        Raises: DeliveryError on failure.
        """
        if not all([EMAILJS_SERVICE_ID, EMAILJS_PUBLIC_KEY, EMAILJS_PRIVATE_KEY]):
            raise DeliveryError("EmailJS credentials not configured")

        # Map template name to EmailJS template ID
        template_id_map = {
            "secure_link": EMAILJS_TEMPLATE_ID_SECURE_LINK,
            "otp": EMAILJS_TEMPLATE_ID_OTP,
            "notify_payer": EMAILJS_TEMPLATE_ID_NOTIFY_PAYER,
        }
        template_id = template_id_map.get(template)
        if not template_id:
            raise DeliveryError(f"Unknown email template: {template}")

        payload = {
            "service_id": EMAILJS_SERVICE_ID,
            "template_id": template_id,
            "user_id": EMAILJS_PUBLIC_KEY,
            "accessToken": EMAILJS_PRIVATE_KEY,
            "template_params": {
                "to_email": to_email,
                "to_name": to_name or to_email,
                **template_params,
            },
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    "https://api.emailjs.com/api/v1.0/email/send",
                    json=payload,
                    timeout=30,
                )
                if response.status_code not in (200, 201):
                    raise DeliveryError(f"EmailJS error ({response.status_code}): {response.text}")
            except httpx.RequestError as e:
                raise DeliveryError(f"EmailJS request failed: {str(e)}")

    async def send_secure_message_to_provider(
        self,
        case_id: str,
        content: str,
        subject: str,
        file_path: Optional[str] = None,
        acting_user_id: Optional[str] = None,
        app_domain: str = "http://localhost:5174",
    ) -> Dict[str, Any]:
        """Send a secure message to provider with encrypted token.

        1. Fetches case and provider info
        2. Creates encrypted token with NPI hash and expiry
        3. Persists token metadata to audit log
        4. Sends email with secure download link
        5. Updates case delivery tracking

        Returns: {token, link, case_id, provider_email, audit_log_id}
        """
        # Fetch case (try as sequence number first, then as UUID)
        case = None
        try:
            seq_num = int(case_id)
            case = await self.case_dao.get_by_sequence(seq_num)
        except ValueError:
            # Not an integer, try as UUID
            case = await self.case_dao.get_by_id(case_id)

        if not case:
            raise DeliveryError(f"Case {case_id} not found")

        # Get provider org from case claim
        provider_org = case.claim.provider_org
        if not provider_org:
            raise DeliveryError("Provider org not found for case")

        # Fetch playbook for provider org
        playbook = await self.playbook_dao.get_by_org(provider_org.provider_org_id)
        if not playbook or not playbook.contact_email:
            raise DeliveryError("No email configured for provider org")

        # Generate secure token using the rendering provider's NPI (the provider who rendered the service)
        # Use case.case_id (UUID) not case_id (sequence number) for token storage
        rendering_npi = case.claim.rendering_provider_npi or provider_org.npi
        token = self._generate_secure_token(case.case_id, rendering_npi)
        secure_link = f"{app_domain}/secure-download?token={token}"

        # Create audit log entry for token generation
        audit_entry = await self.audit_log_dao.create_entry(
            case_id=case_id,
            actor_user_id=acting_user_id or "system",
            action="send_secure_message_to_provider",
            from_status=case.status,
            to_status=case.status,
            reason=f"Message sent to {playbook.contact_email} via secure link (token: {token[:8]}...)",
        )

        # Send email via EmailJS with secure link template
        await self._send_email_emailjs(
            template="secure_link",
            to_email=playbook.contact_email,
            to_name=playbook.contact_name or "Provider",
            template_params={
                "to_email": playbook.contact_email,
                "member_id": case.member_id,
                "provider_name": provider_org.name,
                "secure_link": secure_link,
            },
        )

        return {
            "token": token,
            "link": secure_link,
            "case_id": case_id,
            "provider_email": playbook.contact_email,
            "audit_log_id": audit_entry.audit_id,
            "message": "Message sent successfully",
        }

    async def send_notice_to_provider(
        self,
        case_id: str,
        acting_user_id: Optional[str] = None,
        app_domain: str = "http://localhost:5174",
    ) -> Dict[str, Any]:
        """Send case notice/letter to provider via secure link.

        Automatically fetches the case letter and sends it with secure download access.
        """
        # Fetch case (try as sequence number first, then as UUID)
        case = None
        try:
            seq_num = int(case_id)
            case = await self.case_dao.get_by_sequence(seq_num)
        except ValueError:
            case = await self.case_dao.get_by_id(case_id)

        if not case:
            raise DeliveryError(f"Case {case_id} not found")

        # Fetch the latest case notice
        from ..dao.letter_dao import LetterDAO
        letter_dao = LetterDAO(self.session)
        notices = await letter_dao.get_notices_by_case_id(case.case_id)
        if not notices:
            raise DeliveryError("No notice/letter found for case")

        notice = notices[0]  # Latest (ordered by generated_at DESC)

        # Send secure message with the notice as content
        return await self.send_secure_message_to_provider(
            case_id=case_id,
            content=notice.letter_content or "",
            subject=f"Case Notice - {case.case_number}",
            file_path=None,
            acting_user_id=acting_user_id,
            app_domain=app_domain,
        )

    async def send_provider_inquiry(
        self,
        case_id: str,
        inquiry_text: str,
        acting_user_id: Optional[str] = None,
        app_domain: str = "http://localhost:5174",
    ) -> Dict[str, Any]:
        """Send an inquiry/message to provider with secure access.

        Content is provided directly by the user (e.g., from assistant or case detail).
        """
        return await self.send_secure_message_to_provider(
            case_id=case_id,
            content=inquiry_text,
            subject=f"Case Inquiry - {case_id}",
            file_path=None,
            acting_user_id=acting_user_id,
            app_domain=app_domain,
        )
