"""API key management for external service-to-service authentication."""
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.workflow import APIKey, OpaUser


class APIKeyService:
    """Manage API keys for external services and MCP server integration."""

    @staticmethod
    def _hash_token(token: str) -> str:
        """Hash a token for safe storage."""
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    def generate_token(length: int = 32) -> str:
        """Generate a random API token (URL-safe base64)."""
        return secrets.token_urlsafe(length)

    @staticmethod
    async def create_api_key(
        db: AsyncSession,
        user_id: str,
        name: str = "API Key",
        expires_in_days: Optional[int] = None,
    ) -> tuple[str, APIKey]:
        """Create a new API key for a user.

        Returns (token, api_key_row). Token is shown only once; store it securely.
        """
        token = APIKeyService.generate_token()
        token_hash = APIKeyService._hash_token(token)

        expires_at = None
        if expires_in_days:
            expires_at = (datetime.utcnow() + timedelta(days=expires_in_days)).isoformat()

        api_key = APIKey(
            user_id=user_id,
            name=name,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        db.add(api_key)
        await db.flush()
        return token, api_key

    @staticmethod
    async def verify_api_key(token: str, db: AsyncSession) -> Optional[str]:
        """Verify an API key token. Returns user_id if valid, None otherwise.
        Updates last_used_at on successful verification."""
        token_hash = APIKeyService._hash_token(token)
        now = datetime.utcnow().isoformat()

        result = await db.execute(
            select(APIKey).where(
                APIKey.token_hash == token_hash,
                APIKey.is_active == True,
            )
        )
        api_key = result.scalar_one_or_none()

        if not api_key:
            return None

        # Check expiry
        if api_key.expires_at and api_key.expires_at < now:
            return None

        # Update last_used_at
        await db.execute(
            update(APIKey)
            .where(APIKey.api_key_id == api_key.api_key_id)
            .values(last_used_at=now)
        )
        await db.flush()

        return api_key.user_id

    @staticmethod
    async def list_api_keys(db: AsyncSession, user_id: str) -> list[APIKey]:
        """List all API keys for a user (without the token)."""
        result = await db.execute(
            select(APIKey)
            .where(APIKey.user_id == user_id)
            .order_by(APIKey.created_at.desc())
        )
        return result.scalars().all()

    @staticmethod
    async def revoke_api_key(db: AsyncSession, api_key_id: str, user_id: str) -> bool:
        """Revoke an API key. Returns True if successful."""
        result = await db.execute(
            update(APIKey)
            .where(
                APIKey.api_key_id == api_key_id,
                APIKey.user_id == user_id,
            )
            .values(is_active=False)
        )
        await db.flush()
        return result.rowcount > 0
