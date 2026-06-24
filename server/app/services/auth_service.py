"""JWT authentication service for user login and token validation."""
from datetime import datetime, timedelta
import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..config import JWT_SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRY_MINUTES
from ..models.workflow import OpaUser


class AuthService:
    """Handle JWT token generation and user authentication."""

    @staticmethod
    def create_access_token(user_id: str) -> str:
        """Generate JWT access token for a user."""
        now = datetime.utcnow()
        exp = now + timedelta(minutes=JWT_EXPIRY_MINUTES)
        payload = {
            "sub": user_id,
            "iat": now,
            "exp": exp,
        }
        token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        return token

    @staticmethod
    def verify_token(token: str) -> dict | None:
        """Verify and decode JWT token. Returns payload if valid, None if invalid."""
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            return payload
        except (jwt.InvalidTokenError, jwt.ExpiredSignatureError):
            return None

    @staticmethod
    async def authenticate_user(db: AsyncSession, username: str, password: str) -> OpaUser | None:
        """Authenticate user by username and password. Returns user if valid, None if invalid."""
        # Find user by username
        user = (await db.execute(
            select(OpaUser).where(OpaUser.username == username)
        )).scalar_one_or_none()

        print(f"[AUTH] Attempting login for user: {username}, found: {user is not None}", flush=True)

        if not user:
            print(f"[AUTH] User {username} not found", flush=True)
            return None

        # Demo mode: password = username (simple for testing)
        # In production, use bcrypt or similar with proper password_hash column
        match = password == username
        print(f"[AUTH] Password check for {username}: {match} (password={password}, username={username})", flush=True)
        if not match:
            return None

        print(f"[AUTH] Authentication successful for {username}", flush=True)
        return user
