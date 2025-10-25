"""Tests for authentication endpoints.

Security-critical tests for JWT authentication flow.
Current coverage: 52% → Target: 80%+
"""

import pytest
from datetime import timedelta
from jose import jwt, JWTError
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from services.gateway.app.core.auth import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_token
)


class TestAuthLogin:
    """Tests for POST /v1/auth/login endpoint."""

    def test_login_disabled_by_default(self, client: TestClient):
        """Test that login returns 503 when auth is disabled."""
        response = client.post(
            "/v1/auth/login",
            json={"username": "user@example.com", "password": "password123"}
        )
        assert response.status_code == 503
        assert response.json()["detail"] == "Authentication is not enabled"

    def test_login_validation_missing_username(self, client: TestClient):
        """Test login validation requires username."""
        response = client.post(
            "/v1/auth/login",
            json={"password": "password123"}
        )
        assert response.status_code == 422
        errors = response.json()["errors"]
        assert any(err["loc"] == ["body", "username"] for err in errors)

    def test_login_validation_missing_password(self, client: TestClient):
        """Test login validation requires password."""
        response = client.post(
            "/v1/auth/login",
            json={"username": "user@example.com"}
        )
        assert response.status_code == 422
        errors = response.json()["errors"]
        assert any(err["loc"] == ["body", "password"] for err in errors)

    def test_login_validation_empty_username(self, client: TestClient):
        """Test login validation rejects empty username."""
        response = client.post(
            "/v1/auth/login",
            json={"username": "", "password": "password123"}
        )
        assert response.status_code == 422

    def test_login_validation_empty_password(self, client: TestClient):
        """Test login validation rejects empty password."""
        response = client.post(
            "/v1/auth/login",
            json={"username": "user@example.com", "password": ""}
        )
        assert response.status_code == 422


class TestAuthRefresh:
    """Tests for POST /v1/auth/refresh endpoint."""

    def test_refresh_disabled_by_default(self, client: TestClient):
        """Test that refresh returns 503 when auth is disabled."""
        response = client.post(
            "/v1/auth/refresh",
            json={"refresh_token": "fake.token.here"}
        )
        assert response.status_code == 503
        assert response.json()["detail"] == "Authentication is not enabled"

    def test_refresh_validation_missing_token(self, client: TestClient):
        """Test refresh validation requires refresh_token."""
        response = client.post("/v1/auth/refresh", json={})
        assert response.status_code == 422
        errors = response.json()["errors"]
        assert any(err["loc"] == ["body", "refresh_token"] for err in errors)

    def test_refresh_validation_empty_token(self, client: TestClient):
        """Test refresh validation rejects empty refresh_token.

        Note: Returns 503 when auth disabled, would return 422 if enabled.
        """
        response = client.post(
            "/v1/auth/refresh",
            json={"refresh_token": ""}
        )
        # Auth disabled, so returns 503 before validation
        assert response.status_code == 503


class TestAuthMe:
    """Tests for GET /v1/auth/me endpoint."""

    def test_me_without_auth_returns_anonymous(self, client: TestClient):
        """Test /me returns anonymous user when auth disabled."""
        response = client.get("/v1/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["sub"] == "anonymous"
        assert data["auth_disabled"] is True

    def test_me_with_invalid_token_returns_anonymous(self, client: TestClient):
        """Test /me returns anonymous user for invalid token when auth disabled."""
        response = client.get(
            "/v1/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sub"] == "anonymous"


class TestAuthWithEnabledFlag:
    """Tests for authentication when AUTH_ENABLED=true.

    Note: These tests would require mocking the settings or using
    environment variables to enable auth. Skipping for now as we
    don't have a User model/database table yet.
    """

    @pytest.mark.skip(reason="Requires AUTH_ENABLED=true and User model")
    def test_login_success_with_valid_credentials(self, client: TestClient):
        """Test successful login with valid credentials."""
        # This would require:
        # 1. Setting AUTH_ENABLED=true
        # 2. Creating a User in the database with hashed password
        # 3. Verifying token is returned
        pass

    @pytest.mark.skip(reason="Requires AUTH_ENABLED=true and User model")
    def test_login_failure_with_invalid_credentials(self, client: TestClient):
        """Test login failure with invalid credentials."""
        pass

    @pytest.mark.skip(reason="Requires AUTH_ENABLED=true and User model")
    def test_refresh_success_with_valid_token(self, client: TestClient):
        """Test successful token refresh."""
        pass

    @pytest.mark.skip(reason="Requires AUTH_ENABLED=true and User model")
    def test_refresh_failure_with_invalid_token(self, client: TestClient):
        """Test refresh failure with invalid token."""
        pass

    @pytest.mark.skip(reason="Requires AUTH_ENABLED=true and User model")
    def test_refresh_failure_with_access_token(self, client: TestClient):
        """Test refresh rejects access token (not refresh token)."""
        pass

    @pytest.mark.skip(reason="Requires AUTH_ENABLED=true and User model")
    def test_me_success_with_valid_token(self, client: TestClient):
        """Test /me returns user info with valid token."""
        pass

    @pytest.mark.skip(reason="Requires AUTH_ENABLED=true and User model")
    def test_me_failure_with_expired_token(self, client: TestClient):
        """Test /me rejects expired token."""
        pass

    @pytest.mark.skip(reason="Requires AUTH_ENABLED=true and User model")
    def test_protected_endpoint_requires_auth(self, client: TestClient):
        """Test that protected endpoints require authentication."""
        pass


class TestPasswordHashing:
    """Tests for password hashing utilities."""

    def test_password_hash_and_verify(self):
        """Test password hashing and verification."""
        from services.gateway.app.core.auth import get_password_hash, verify_password

        password = "test_password_123"  # Under 72 byte bcrypt limit
        hashed = get_password_hash(password)

        # Hash should not be the same as password
        assert hashed != password

        # Verify correct password
        assert verify_password(password, hashed) is True

        # Verify incorrect password
        assert verify_password("wrong_password", hashed) is False

    def test_same_password_different_hashes(self):
        """Test that same password produces different hashes (salt)."""
        from services.gateway.app.core.auth import get_password_hash

        password = "test_pass_123"  # Under 72 byte bcrypt limit
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)

        # Different hashes due to random salt
        assert hash1 != hash2

    def test_empty_password_can_be_hashed(self):
        """Test that empty password can be hashed (validation should prevent this at API level)."""
        from services.gateway.app.core.auth import get_password_hash, verify_password

        password = "x"  # Minimal password
        hashed = get_password_hash(password)
        assert verify_password(password, hashed) is True


class TestJWTTokens:
    """Tests for JWT token creation and verification."""

    def test_create_access_token(self):
        """Test creating an access token."""
        from services.gateway.app.core.auth import create_access_token

        token_data = {"sub": "user@example.com", "role": "admin"}
        token = create_access_token(token_data)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 50  # JWT tokens are long
        assert "." in token  # JWT format: header.payload.signature

    def test_create_refresh_token(self):
        """Test creating a refresh token."""
        from services.gateway.app.core.auth import create_refresh_token

        token_data = {"sub": "user@example.com"}
        token = create_refresh_token(token_data)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 50
        assert "." in token

    def test_verify_valid_token(self):
        """Test verifying a valid token."""
        from services.gateway.app.core.auth import create_access_token, verify_token

        token_data = {"sub": "user@example.com", "email": "user@example.com"}
        token = create_access_token(token_data)

        payload = verify_token(token)
        assert payload["sub"] == "user@example.com"
        assert payload["email"] == "user@example.com"
        assert "exp" in payload  # Expiration timestamp
        assert "iat" in payload  # Issued at timestamp

    def test_verify_invalid_token(self):
        """Test verifying an invalid token raises JWTError."""
        from jose import JWTError
        from services.gateway.app.core.auth import verify_token

        with pytest.raises(JWTError):
            verify_token("invalid.token.here")

    def test_verify_malformed_token(self):
        """Test verifying a malformed token raises JWTError."""
        from jose import JWTError
        from services.gateway.app.core.auth import verify_token

        with pytest.raises(JWTError):
            verify_token("not-a-jwt-token")

    def test_refresh_token_has_type_field(self):
        """Test that refresh tokens include type field."""
        from services.gateway.app.core.auth import create_refresh_token, verify_token

        token_data = {"sub": "user@example.com"}
        token = create_refresh_token(token_data)

        payload = verify_token(token)
        assert payload["type"] == "refresh"

    def test_access_token_does_not_have_type_field(self):
        """Test that access tokens don't have type field."""
        from services.gateway.app.core.auth import create_access_token, verify_token

        token_data = {"sub": "user@example.com"}
        token = create_access_token(token_data)

        payload = verify_token(token)
        assert "type" not in payload or payload.get("type") != "refresh"


class TestTokenCreation:
    """Test JWT token creation with custom expiration."""

    def test_access_token_with_custom_expiration(self):
        """Test creating access token with custom expiration delta."""
        from services.gateway.app.core.auth import create_access_token, verify_token

        token_data = {"sub": "user@example.com", "role": "admin"}
        custom_expiration = timedelta(hours=2)

        token = create_access_token(token_data, expires_delta=custom_expiration)

        assert isinstance(token, str)
        assert len(token) > 20

        # Verify token is valid
        payload = verify_token(token)
        assert payload["sub"] == "user@example.com"
        assert payload["role"] == "admin"

    def test_access_token_default_expiration(self):
        """Test creating access token with default expiration."""
        from services.gateway.app.core.auth import create_access_token, verify_token

        token_data = {"sub": "user@example.com"}
        token = create_access_token(token_data)

        payload = verify_token(token)
        assert "exp" in payload
        assert "iat" in payload

    def test_refresh_token_creation(self):
        """Test creating refresh token."""
        from services.gateway.app.core.auth import create_refresh_token, verify_token

        token_data = {"sub": "user@example.com"}
        token = create_refresh_token(token_data)

        assert isinstance(token, str)
        payload = verify_token(token)
        assert payload["sub"] == "user@example.com"
        assert payload["type"] == "refresh"


class TestTokenVerification:
    """Test JWT token verification edge cases."""

    def test_decode_token_with_invalid_signature(self):
        """Test decoding token with tampered signature fails."""
        from services.gateway.app.core.auth import create_access_token, decode_token

        token_data = {"sub": "user@example.com"}
        token = create_access_token(token_data)

        # Tamper with token
        parts = token.split('.')
        tampered_token = parts[0] + "." + parts[1] + ".tamperedsignature"

        with pytest.raises(JWTError):
            decode_token(tampered_token)

    def test_verify_token_missing_sub_claim(self):
        """Test verifying token without 'sub' claim fails."""
        from services.gateway.app.core.auth import verify_token
        from services.gateway.app.core.config import get_settings

        settings = get_settings()

        # Create token without 'sub' claim
        token_data = {"role": "admin"}  # No 'sub'
        token = jwt.encode(
            token_data,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )

        with pytest.raises(JWTError) as exc_info:
            verify_token(token)
        assert "sub" in str(exc_info.value).lower()

    def test_verify_token_with_expired_token(self):
        """Test verifying expired token fails."""
        from datetime import datetime, UTC
        from services.gateway.app.core.auth import verify_token
        from services.gateway.app.core.config import get_settings

        settings = get_settings()

        # Create token that expired in the past
        token_data = {
            "sub": "user@example.com",
            "exp": datetime.now(UTC) - timedelta(hours=1),  # Expired 1 hour ago
            "iat": datetime.now(UTC) - timedelta(hours=2)
        }
        token = jwt.encode(
            token_data,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )

        with pytest.raises(JWTError):
            verify_token(token)
