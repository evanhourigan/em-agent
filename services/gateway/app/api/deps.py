from collections.abc import Generator
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy.orm import Session

from ..core.auth import verify_token
from ..core.config import get_settings
from ..core.logging import get_logger
from ..db import get_sessionmaker

logger = get_logger(__name__)

# HTTP Bearer token scheme
security = HTTPBearer(auto_error=False)


def get_db_session() -> Generator[Session, None, None]:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        yield session


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> dict:
    """
    Dependency to get the current authenticated user from JWT token.

    Only enforced if AUTH_ENABLED=true in settings.
    Returns user payload from JWT token.

    Raises:
        HTTPException: 401 if authentication is enabled and token is invalid/missing
    """
    settings = get_settings()

    # If auth is disabled, return anonymous user
    if not settings.auth_enabled:
        return {"sub": "anonymous", "auth_disabled": True}

    # Auth is enabled - require valid token
    if not credentials:
        logger.warning("auth.missing_credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        token = credentials.credentials
        payload = verify_token(token)
        return payload

    except JWTError as e:
        logger.warning("auth.invalid_token", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[dict]:
    """
    Optional authentication dependency.

    Returns user payload if valid token provided, None otherwise.
    Does not raise exceptions for missing/invalid tokens.
    """
    settings = get_settings()

    if not settings.auth_enabled:
        return None

    if not credentials:
        return None

    try:
        token = credentials.credentials
        payload = verify_token(token)
        return payload
    except JWTError:
        return None
