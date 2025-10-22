"""
Tests for API dependencies module.

Tests database session and authentication dependencies.
Current coverage: 38% → Target: 80%+
"""
import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jose import JWTError

from services.gateway.app.api.deps import (
    get_db_session,
    get_current_user,
    get_current_user_optional,
)


class TestGetDbSession:
    """Test get_db_session dependency."""

    def test_get_db_session_yields_session(self):
        """Test that get_db_session yields a database session."""
        with patch("services.gateway.app.api.deps.get_sessionmaker") as mock_get_sessionmaker:
            mock_session = Mock()

            # Create a proper context manager mock
            mock_context = MagicMock()
            mock_context.__enter__ = Mock(return_value=mock_session)
            mock_context.__exit__ = Mock(return_value=None)

            mock_sessionmaker = Mock()
            mock_sessionmaker.return_value = mock_context
            mock_get_sessionmaker.return_value = mock_sessionmaker

            # Get the generator
            gen = get_db_session()
            session = next(gen)

            # Should yield the session
            assert session == mock_session

            # Clean up generator
            try:
                next(gen)
            except StopIteration:
                pass

    def test_get_db_session_closes_session(self):
        """Test that get_db_session properly closes the session."""
        with patch("services.gateway.app.api.deps.get_sessionmaker") as mock_get_sessionmaker:
            mock_session = Mock()
            mock_context_manager = Mock()
            mock_context_manager.__enter__ = Mock(return_value=mock_session)
            mock_context_manager.__exit__ = Mock(return_value=None)

            mock_sessionmaker = Mock()
            mock_sessionmaker.return_value = mock_context_manager
            mock_get_sessionmaker.return_value = mock_sessionmaker

            # Use the generator
            gen = get_db_session()
            session = next(gen)

            # Complete the generator (triggers __exit__)
            try:
                gen.send(None)
            except StopIteration:
                pass

            # Should have called __exit__ to close session
            mock_context_manager.__exit__.assert_called_once()


class TestGetCurrentUser:
    """Test get_current_user dependency."""

    def test_get_current_user_auth_disabled_returns_anonymous(self):
        """Test that get_current_user returns anonymous when auth disabled."""
        with patch("services.gateway.app.api.deps.get_settings") as mock_settings:
            settings = Mock()
            settings.auth_enabled = False
            mock_settings.return_value = settings

            result = get_current_user(credentials=None)

            assert result == {"sub": "anonymous", "auth_disabled": True}

    def test_get_current_user_auth_enabled_missing_credentials_raises_401(self):
        """Test that missing credentials raises 401 when auth enabled."""
        with patch("services.gateway.app.api.deps.get_settings") as mock_settings:
            settings = Mock()
            settings.auth_enabled = True
            mock_settings.return_value = settings

            with pytest.raises(HTTPException) as exc_info:
                get_current_user(credentials=None)

            assert exc_info.value.status_code == 401
            assert "Authentication required" in exc_info.value.detail
            assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}

    def test_get_current_user_auth_enabled_valid_token_returns_payload(self):
        """Test that valid token returns user payload when auth enabled."""
        with patch("services.gateway.app.api.deps.get_settings") as mock_settings:
            with patch("services.gateway.app.api.deps.verify_token") as mock_verify:
                settings = Mock()
                settings.auth_enabled = True
                mock_settings.return_value = settings

                # Mock valid token verification
                mock_verify.return_value = {"sub": "user123", "email": "user@example.com"}

                credentials = HTTPAuthorizationCredentials(
                    scheme="Bearer",
                    credentials="valid.jwt.token"
                )

                result = get_current_user(credentials=credentials)

                assert result == {"sub": "user123", "email": "user@example.com"}
                mock_verify.assert_called_once_with("valid.jwt.token")

    def test_get_current_user_auth_enabled_invalid_token_raises_401(self):
        """Test that invalid token raises 401 when auth enabled."""
        with patch("services.gateway.app.api.deps.get_settings") as mock_settings:
            with patch("services.gateway.app.api.deps.verify_token") as mock_verify:
                settings = Mock()
                settings.auth_enabled = True
                mock_settings.return_value = settings

                # Mock token verification failure
                mock_verify.side_effect = JWTError("Invalid token")

                credentials = HTTPAuthorizationCredentials(
                    scheme="Bearer",
                    credentials="invalid.jwt.token"
                )

                with pytest.raises(HTTPException) as exc_info:
                    get_current_user(credentials=credentials)

                assert exc_info.value.status_code == 401
                assert "Invalid authentication credentials" in exc_info.value.detail
                assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}


class TestGetCurrentUserOptional:
    """Test get_current_user_optional dependency."""

    def test_get_current_user_optional_auth_disabled_returns_none(self):
        """Test that get_current_user_optional returns None when auth disabled."""
        with patch("services.gateway.app.api.deps.get_settings") as mock_settings:
            settings = Mock()
            settings.auth_enabled = False
            mock_settings.return_value = settings

            result = get_current_user_optional(credentials=None)

            assert result is None

    def test_get_current_user_optional_missing_credentials_returns_none(self):
        """Test that missing credentials returns None (no exception)."""
        with patch("services.gateway.app.api.deps.get_settings") as mock_settings:
            settings = Mock()
            settings.auth_enabled = True
            mock_settings.return_value = settings

            result = get_current_user_optional(credentials=None)

            assert result is None

    def test_get_current_user_optional_valid_token_returns_payload(self):
        """Test that valid token returns user payload."""
        with patch("services.gateway.app.api.deps.get_settings") as mock_settings:
            with patch("services.gateway.app.api.deps.verify_token") as mock_verify:
                settings = Mock()
                settings.auth_enabled = True
                mock_settings.return_value = settings

                # Mock valid token verification
                mock_verify.return_value = {"sub": "user456", "role": "admin"}

                credentials = HTTPAuthorizationCredentials(
                    scheme="Bearer",
                    credentials="valid.jwt.token"
                )

                result = get_current_user_optional(credentials=credentials)

                assert result == {"sub": "user456", "role": "admin"}
                mock_verify.assert_called_once_with("valid.jwt.token")

    def test_get_current_user_optional_invalid_token_returns_none(self):
        """Test that invalid token returns None (no exception)."""
        with patch("services.gateway.app.api.deps.get_settings") as mock_settings:
            with patch("services.gateway.app.api.deps.verify_token") as mock_verify:
                settings = Mock()
                settings.auth_enabled = True
                mock_settings.return_value = settings

                # Mock token verification failure
                mock_verify.side_effect = JWTError("Invalid token")

                credentials = HTTPAuthorizationCredentials(
                    scheme="Bearer",
                    credentials="invalid.jwt.token"
                )

                result = get_current_user_optional(credentials=credentials)

                # Should return None instead of raising
                assert result is None

    def test_get_current_user_optional_auth_disabled_with_credentials(self):
        """Test that credentials are ignored when auth disabled."""
        with patch("services.gateway.app.api.deps.get_settings") as mock_settings:
            settings = Mock()
            settings.auth_enabled = False
            mock_settings.return_value = settings

            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials="some.token"
            )

            result = get_current_user_optional(credentials=credentials)

            # Should return None without checking token
            assert result is None
