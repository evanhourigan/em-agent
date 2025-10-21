"""
Authentication router.

Provides endpoints for login, token refresh, and user info.
"""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status

from ....core.auth import create_access_token, create_refresh_token, verify_token
from ....core.config import get_settings
from ....core.logging import get_logger
from ....schemas.auth import LoginRequest, TokenResponse, RefreshTokenRequest, UserInfo
from ...deps import get_current_user

router = APIRouter(prefix="/v1/auth", tags=["authentication"])
logger = get_logger(__name__)


@router.post("/login", response_model=TokenResponse)
def login(credentials: LoginRequest) -> TokenResponse:
    """
    Authenticate user and return JWT tokens.

    This is a simplified implementation for demonstration.
    In production, you would:
    1. Query user from database by username
    2. Verify password hash using verify_password()
    3. Check user is active/not banned
    4. Add user roles/permissions to token payload

    For now, this accepts any credentials when auth is enabled and returns a token.
    """
    settings = get_settings()

    if not settings.auth_enabled:
        logger.warning("auth.login_attempt_when_disabled")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not enabled"
        )

    # TODO: Replace with actual database user lookup and password verification
    # For demonstration purposes, we create a token with the provided username
    logger.info("auth.login_attempt", username=credentials.username)

    # In production, verify credentials here:
    # user = db.query(User).filter(User.username == credentials.username).first()
    # if not user or not verify_password(credentials.password, user.hashed_password):
    #     raise HTTPException(status_code=401, detail="Incorrect username or password")

    # Create token payload
    token_data = {
        "sub": credentials.username,
        "email": credentials.username,  # Assuming username is email
        "role": "user"  # Default role
    }

    # Generate tokens
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token({"sub": credentials.username})

    logger.info("auth.login_success", username=credentials.username)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_access_token(request: RefreshTokenRequest) -> TokenResponse:
    """
    Refresh an access token using a valid refresh token.

    Validates the refresh token and issues a new access token.
    """
    settings = get_settings()

    if not settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not enabled"
        )

    try:
        # Verify refresh token
        payload = verify_token(request.refresh_token)

        # Check token type
        if payload.get("type") != "refresh":
            logger.warning("auth.refresh_with_access_token", sub=payload.get("sub"))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token type. Refresh token required."
            )

        # Create new access token
        token_data = {"sub": payload.get("sub")}
        access_token = create_access_token(token_data)

        logger.info("auth.token_refreshed", sub=payload.get("sub"))

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.jwt_access_token_expire_minutes * 60
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("auth.refresh_failed", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )


@router.get("/me", response_model=UserInfo)
def get_current_user_info(current_user: dict = Depends(get_current_user)) -> UserInfo:
    """
    Get current authenticated user information.

    Returns user details from the JWT token.
    If authentication is disabled, returns anonymous user.
    """
    logger.info("auth.get_user_info", sub=current_user.get("sub"))

    return UserInfo(
        sub=current_user.get("sub"),
        email=current_user.get("email"),
        role=current_user.get("role"),
        auth_disabled=current_user.get("auth_disabled")
    )
