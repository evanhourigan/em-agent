"""
Tests for event_bus service.

Tests the NATS event bus integration and publish/subscribe functionality.
Current coverage: 37% → Target: 70%+
"""
import os
import pytest
from unittest.mock import Mock, patch, AsyncMock
import asyncio
import json

from services.gateway.app.services.event_bus import (
    EventBus,
    get_event_bus,
)


class TestEventBusInit:
    """Test EventBus initialization."""

    def test_event_bus_initialization(self):
        """Test EventBus initializes correctly."""
        bus = EventBus()

        assert bus._nats is None
        assert bus._url == "nats://nats:4222"  # Default URL

    def test_event_bus_respects_nats_url_env(self):
        """Test EventBus respects NATS_URL environment variable."""
        with patch.dict(os.environ, {"NATS_URL": "nats://custom:4222"}):
            bus = EventBus()

            assert bus._url == "nats://custom:4222"


class TestEventBusConnect:
    """Test EventBus.connect method."""

    @pytest.mark.asyncio
    async def test_connect_when_nats_not_available(self):
        """Test connect() handles NATS library not being available."""
        bus = EventBus()

        # Mock _HAS_NATS to False
        with patch("services.gateway.app.services.event_bus._HAS_NATS", False):
            with patch("services.gateway.app.services.event_bus.get_logger") as mock_logger:
                mock_log_instance = Mock()
                mock_logger.return_value = mock_log_instance

                bus = EventBus()
                await bus.connect()

                # Should log that it's disabled
                mock_log_instance.info.assert_called_once_with(
                    "eventbus.disabled", reason="nats-py not installed"
                )
                # Should not create NATS client
                assert bus._nats is None

    @pytest.mark.asyncio
    async def test_connect_when_nats_available(self):
        """Test connect() creates NATS client when available."""
        bus = EventBus()

        # Mock NATS client
        mock_nats_client = AsyncMock()

        with patch("services.gateway.app.services.event_bus._HAS_NATS", True):
            with patch("services.gateway.app.services.event_bus.NATS") as mock_nats_class:
                with patch("services.gateway.app.services.event_bus.get_logger") as mock_logger:
                    mock_log_instance = Mock()
                    mock_logger.return_value = mock_log_instance

                    mock_nats_class.return_value = mock_nats_client

                    bus = EventBus()
                    await bus.connect()

                    # Should create NATS client and connect
                    mock_nats_class.assert_called_once()
                    mock_nats_client.connect.assert_awaited_once_with(servers=["nats://nats:4222"])

                    # Should log connection
                    mock_log_instance.info.assert_called_with(
                        "eventbus.connected", url="nats://nats:4222"
                    )

                    # Should store client
                    assert bus._nats == mock_nats_client

    @pytest.mark.asyncio
    async def test_connect_already_connected(self):
        """Test connect() skips if already connected."""
        bus = EventBus()

        # Set up mock NATS client that's already connected
        mock_existing_client = AsyncMock()
        bus._nats = mock_existing_client

        with patch("services.gateway.app.services.event_bus._HAS_NATS", True):
            with patch("services.gateway.app.services.event_bus.NATS") as mock_nats_class:
                await bus.connect()

                # Should not create new client
                mock_nats_class.assert_not_called()
                # Should still have original client
                assert bus._nats == mock_existing_client

    @pytest.mark.asyncio
    async def test_connect_custom_url(self):
        """Test connect() uses custom NATS URL."""
        with patch.dict(os.environ, {"NATS_URL": "nats://prod:4222"}):
            bus = EventBus()

            mock_nats_client = AsyncMock()

            with patch("services.gateway.app.services.event_bus._HAS_NATS", True):
                with patch("services.gateway.app.services.event_bus.NATS") as mock_nats_class:
                    mock_nats_class.return_value = mock_nats_client

                    await bus.connect()

                    # Should connect to custom URL
                    mock_nats_client.connect.assert_awaited_once_with(servers=["nats://prod:4222"])


class TestEventBusPublishJson:
    """Test EventBus.publish_json method."""

    @pytest.mark.asyncio
    async def test_publish_json_when_nats_not_available(self):
        """Test publish_json() handles NATS library not being available."""
        bus = EventBus()

        with patch("services.gateway.app.services.event_bus._HAS_NATS", False):
            bus = EventBus()
            # Should not raise
            await bus.publish_json("test.subject", {"key": "value"})

    @pytest.mark.asyncio
    async def test_publish_json_when_not_connected(self):
        """Test publish_json() handles not being connected."""
        bus = EventBus()

        with patch("services.gateway.app.services.event_bus._HAS_NATS", True):
            bus = EventBus()
            # bus._nats is None (not connected)

            # Should not raise
            await bus.publish_json("test.subject", {"key": "value"})

    @pytest.mark.asyncio
    async def test_publish_json_when_connected(self):
        """Test publish_json() publishes to NATS when connected."""
        bus = EventBus()

        mock_nats_client = AsyncMock()
        bus._nats = mock_nats_client

        with patch("services.gateway.app.services.event_bus._HAS_NATS", True):
            payload = {"event": "test", "data": 123}
            await bus.publish_json("events.test", payload)

            # Should serialize and publish
            expected_data = json.dumps(payload).encode("utf-8")
            mock_nats_client.publish.assert_awaited_once_with("events.test", expected_data)

    @pytest.mark.asyncio
    async def test_publish_json_complex_payload(self):
        """Test publish_json() handles complex payloads."""
        bus = EventBus()

        mock_nats_client = AsyncMock()
        bus._nats = mock_nats_client

        with patch("services.gateway.app.services.event_bus._HAS_NATS", True):
            payload = {
                "nested": {"key": "value"},
                "list": [1, 2, 3],
                "string": "test",
                "number": 42,
                "boolean": True,
                "null": None,
            }
            await bus.publish_json("complex.event", payload)

            # Should serialize complex payload
            expected_data = json.dumps(payload).encode("utf-8")
            mock_nats_client.publish.assert_awaited_once_with("complex.event", expected_data)


class TestGetEventBus:
    """Test get_event_bus singleton function."""

    def test_get_event_bus_creates_singleton(self):
        """Test get_event_bus() creates and returns singleton."""
        # Clear the global singleton
        import services.gateway.app.services.event_bus as event_bus_module
        event_bus_module._event_bus = None

        bus1 = get_event_bus()
        bus2 = get_event_bus()

        # Should return same instance
        assert bus1 is bus2
        assert isinstance(bus1, EventBus)

    def test_get_event_bus_reuses_existing(self):
        """Test get_event_bus() reuses existing singleton."""
        import services.gateway.app.services.event_bus as event_bus_module

        # Create a specific instance
        existing_bus = EventBus()
        event_bus_module._event_bus = existing_bus

        bus = get_event_bus()

        # Should return the existing instance
        assert bus is existing_bus

    def teardown_method(self):
        """Clean up singleton after each test."""
        import services.gateway.app.services.event_bus as event_bus_module
        event_bus_module._event_bus = None
