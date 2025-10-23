"""Tests for configuration validation."""

import pytest
import os
from services.gateway.app.core.config import Settings, validate_settings


class TestSettingsValidation:
    """Tests for validate_settings function."""

    def test_validate_settings_missing_database_url(self):
        """Test that missing DATABASE_URL raises ValueError."""
        settings = Settings(database_url="")

        with pytest.raises(ValueError) as exc_info:
            validate_settings(settings)

        assert "DATABASE_URL is required" in str(exc_info.value)

    def test_validate_settings_whitespace_only_database_url(self):
        """Test that whitespace-only DATABASE_URL raises ValueError."""
        settings = Settings(database_url="   ")

        with pytest.raises(ValueError) as exc_info:
            validate_settings(settings)

        assert "DATABASE_URL is required" in str(exc_info.value)

    def test_validate_settings_slack_signing_without_secret(self):
        """Test that SLACK_SIGNING_REQUIRED without secret raises ValueError."""
        settings = Settings(
            database_url="sqlite:///:memory:",
            slack_signing_required=True,
            slack_signing_secret=""
        )

        with pytest.raises(ValueError) as exc_info:
            validate_settings(settings)

        assert "SLACK_SIGNING_SECRET is not set" in str(exc_info.value)

    def test_validate_settings_auth_enabled_without_jwt_secret(self):
        """Test that AUTH_ENABLED without JWT_SECRET_KEY raises ValueError."""
        settings = Settings(
            database_url="sqlite:///:memory:",
            auth_enabled=True,
            jwt_secret_key=""
        )

        with pytest.raises(ValueError) as exc_info:
            validate_settings(settings)

        assert "JWT_SECRET_KEY is not set" in str(exc_info.value)

    def test_validate_settings_auth_enabled_with_short_jwt_secret(self):
        """Test that AUTH_ENABLED with short JWT_SECRET_KEY raises ValueError."""
        settings = Settings(
            database_url="sqlite:///:memory:",
            auth_enabled=True,
            jwt_secret_key="short"  # Less than 32 characters
        )

        with pytest.raises(ValueError) as exc_info:
            validate_settings(settings)

        assert "must be at least 32 characters" in str(exc_info.value)

    def test_validate_settings_otel_enabled_without_endpoint(self, capsys):
        """Test that OTEL_ENABLED without endpoint prints warning."""
        settings = Settings(
            database_url="sqlite:///:memory:",
            otel_enabled=True,
            otel_exporter_otlp_endpoint=""
        )

        # Should not raise, but should print warning
        validate_settings(settings)

        captured = capsys.readouterr()
        assert "OTEL_ENABLED=true but OTEL_EXPORTER_OTLP_ENDPOINT is not set" in captured.out

    def test_validate_settings_invalid_rag_url(self, capsys):
        """Test that non-http RAG_URL prints warning."""
        settings = Settings(
            database_url="sqlite:///:memory:",
            rag_url="not-a-url"
        )

        # Should not raise, but should print warning
        validate_settings(settings)

        captured = capsys.readouterr()
        assert "RAG_URL does not look like an http URL" in captured.out

    def test_validate_settings_cors_wildcard_in_production(self, capsys):
        """Test that CORS wildcard in production prints security warning."""
        settings = Settings(
            database_url="sqlite:///:memory:",
            env="production",
            cors_allow_origins=["*"]
        )

        # Should not raise, but should print warning
        validate_settings(settings)

        captured = capsys.readouterr()
        assert "SECURITY WARNING" in captured.out
        assert "CORS allows all origins" in captured.out

    def test_validate_settings_valid_configuration(self):
        """Test that valid configuration passes validation."""
        settings = Settings(
            database_url="sqlite:///:memory:",
            slack_signing_required=False,
            auth_enabled=False,
            otel_enabled=False,
            rag_url="http://localhost:8000",
            env="development",
            cors_allow_origins=["http://localhost:3000"]
        )

        # Should not raise
        validate_settings(settings)
