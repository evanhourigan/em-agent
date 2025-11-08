"""
JWT Authentication utilities.

Provides functions for creating and verifying JWT tokens for API authentication.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import get_settings
from .logging import get_logger

logger = get_logger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password for storing."""
    return pwd_context.hash(password)


def create_access_token(
    data: dict[str, Any], expires_delta: timedelta | None = None
) -> str:
    """
    Create a JWT access token.

    Args:
        data: Payload to encode in the token (should include 'sub' for subject/user ID)
        expires_delta: Optional custom expiration time, defaults to settings value

    Returns:
        Encoded JWT token string

    Example:
        token = create_access_token({"sub": "user@example.com", "role": "admin"})
    """
    settings = get_settings()
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(
            minutes=settings.jwt_access_token_expire_minutes
        )

    to_encode.update({"exp": expire, "iat": datetime.now(UTC)})

    encoded_jwt = jwt.encode(
        to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )

    logger.info(
        "auth.token_created", sub=data.get("sub"), expires_at=expire.isoformat()
    )
    return encoded_jwt


def create_refresh_token(data: dict[str, Any]) -> str:
    """
    Create a JWT refresh token with longer expiration.

    Args:
        data: Payload to encode in the token

    Returns:
        Encoded JWT refresh token string
    """
    settings = get_settings()
    to_encode = data.copy()

    expire = datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days)
    to_encode.update({"exp": expire, "iat": datetime.now(UTC), "type": "refresh"})

    encoded_jwt = jwt.encode(
        to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )

    logger.info(
        "auth.refresh_token_created", sub=data.get("sub"), expires_at=expire.isoformat()
    )
    return encoded_jwt


def decode_token(token: str) -> dict[str, Any] | None:
    """
    Decode and verify a JWT token.

    Args:
        token: JWT token string to decode

    Returns:
        Decoded payload dict if valid, None if invalid/expired

    Raises:
        JWTError: If token is invalid or expired
    """
    settings = get_settings()

    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError as e:
        logger.warning("auth.token_decode_failed", error=str(e))
        raise


def verify_token(token: str) -> dict[str, Any]:
    """
    Verify a JWT token and return the payload.

    Args:
        token: JWT token string to verify

    Returns:
        Decoded payload dict

    Raises:
        JWTError: If token is invalid, expired, or missing required fields
    """
    try:
        payload = decode_token(token)

        # Verify required fields
        subject: str = payload.get("sub")
        if subject is None:
            logger.warning("auth.token_missing_subject")
            raise JWTError("Token missing 'sub' claim")

        logger.debug("auth.token_verified", sub=subject)
        return payload

    except JWTError as e:
        logger.warning("auth.token_verification_failed", error=str(e))
        raise
