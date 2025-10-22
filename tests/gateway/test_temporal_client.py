"""
Tests for temporal_client service.

Tests the Temporal workflow client integration.
Current coverage: 39% → Target: 80%+
"""
import os
import pytest
from unittest.mock import Mock, patch, AsyncMock

from services.gateway.app.services.temporal_client import (
    TemporalGateway,
    get_temporal,
)


class TestTemporalGatewayInit:
    """Test TemporalGateway initialization."""

    def test_temporal_gateway_initialization(self):
        """Test TemporalGateway initializes correctly."""
        gateway = TemporalGateway()

        assert gateway._client is None
        assert gateway._addr == "temporal:7233"  # Default address
        assert gateway._namespace == "default"  # Default namespace

    def test_temporal_gateway_respects_address_env(self):
        """Test TemporalGateway respects TEMPORAL_ADDRESS environment variable."""
        with patch.dict(os.environ, {"TEMPORAL_ADDRESS": "localhost:7233"}):
            gateway = TemporalGateway()

            assert gateway._addr == "localhost:7233"

    def test_temporal_gateway_respects_namespace_env(self):
        """Test TemporalGateway respects TEMPORAL_NAMESPACE environment variable."""
        with patch.dict(os.environ, {"TEMPORAL_NAMESPACE": "production"}):
            gateway = TemporalGateway()

            assert gateway._namespace == "production"

    def test_temporal_gateway_respects_both_env_vars(self):
        """Test TemporalGateway respects both environment variables."""
        with patch.dict(os.environ, {
            "TEMPORAL_ADDRESS": "prod-temporal:7233",
            "TEMPORAL_NAMESPACE": "prod"
        }):
            gateway = TemporalGateway()

            assert gateway._addr == "prod-temporal:7233"
            assert gateway._namespace == "prod"


class TestTemporalGatewayEnsure:
    """Test TemporalGateway.ensure method."""

    @pytest.mark.asyncio
    async def test_ensure_when_temporal_not_available(self):
        """Test ensure() returns None when Temporal library not available."""
        gateway = TemporalGateway()

        # Mock _HAS_TEMPORAL to False
        with patch("services.gateway.app.services.temporal_client._HAS_TEMPORAL", False):
            gateway = TemporalGateway()
            result = await gateway.ensure()

            # Should return None
            assert result is None
            # Should not create client
            assert gateway._client is None

    @pytest.mark.asyncio
    async def test_ensure_when_temporal_available(self):
        """Test ensure() creates client when Temporal library available."""
        gateway = TemporalGateway()

        # Mock Temporal client
        mock_client = AsyncMock()

        with patch("services.gateway.app.services.temporal_client._HAS_TEMPORAL", True):
            with patch("services.gateway.app.services.temporal_client.Client") as mock_client_class:
                with patch("services.gateway.app.services.temporal_client.get_logger") as mock_logger:
                    mock_log_instance = Mock()
                    mock_logger.return_value = mock_log_instance

                    mock_client_class.connect = AsyncMock(return_value=mock_client)

                    gateway = TemporalGateway()
                    result = await gateway.ensure()

                    # Should create client and connect
                    mock_client_class.connect.assert_awaited_once_with(
                        "temporal:7233",
                        namespace="default"
                    )

                    # Should log connection
                    mock_log_instance.info.assert_called_with(
                        "temporal.connected",
                        address="temporal:7233",
                        namespace="default"
                    )

                    # Should return client
                    assert result == mock_client
                    # Should store client
                    assert gateway._client == mock_client

    @pytest.mark.asyncio
    async def test_ensure_already_connected(self):
        """Test ensure() returns existing client if already connected."""
        gateway = TemporalGateway()

        # Set up mock client that's already connected
        mock_existing_client = AsyncMock()
        gateway._client = mock_existing_client

        with patch("services.gateway.app.services.temporal_client._HAS_TEMPORAL", True):
            with patch("services.gateway.app.services.temporal_client.Client") as mock_client_class:
                mock_client_class.connect = AsyncMock()

                result = await gateway.ensure()

                # Should not create new client
                mock_client_class.connect.assert_not_awaited()
                # Should return existing client
                assert result == mock_existing_client
                # Should still have original client
                assert gateway._client == mock_existing_client

    @pytest.mark.asyncio
    async def test_ensure_custom_address_and_namespace(self):
        """Test ensure() uses custom address and namespace."""
        with patch.dict(os.environ, {
            "TEMPORAL_ADDRESS": "staging:7233",
            "TEMPORAL_NAMESPACE": "staging"
        }):
            gateway = TemporalGateway()

            mock_client = AsyncMock()

            with patch("services.gateway.app.services.temporal_client._HAS_TEMPORAL", True):
                with patch("services.gateway.app.services.temporal_client.Client") as mock_client_class:
                    mock_client_class.connect = AsyncMock(return_value=mock_client)

                    result = await gateway.ensure()

                    # Should connect to custom address and namespace
                    mock_client_class.connect.assert_awaited_once_with(
                        "staging:7233",
                        namespace="staging"
                    )


class TestGetTemporal:
    """Test get_temporal singleton function."""

    def test_get_temporal_creates_singleton(self):
        """Test get_temporal() creates and returns singleton."""
        # Clear the global singleton
        import services.gateway.app.services.temporal_client as temporal_module
        temporal_module._gw = None

        gw1 = get_temporal()
        gw2 = get_temporal()

        # Should return same instance
        assert gw1 is gw2
        assert isinstance(gw1, TemporalGateway)

    def test_get_temporal_reuses_existing(self):
        """Test get_temporal() reuses existing singleton."""
        import services.gateway.app.services.temporal_client as temporal_module

        # Create a specific instance
        existing_gw = TemporalGateway()
        temporal_module._gw = existing_gw

        gw = get_temporal()

        # Should return the existing instance
        assert gw is existing_gw

    def teardown_method(self):
        """Clean up singleton after each test."""
        import services.gateway.app.services.temporal_client as temporal_module
        temporal_module._gw = None
