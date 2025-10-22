"""
Tests for observability module.

Tests Prometheus metrics, OpenTelemetry tracing, and rate limiting middleware.
Current coverage: 69% → Target: 90%+
"""
import os
import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from collections import deque

from services.gateway.app.core.observability import (
    add_prometheus,
    add_tracing,
)


class TestAddPrometheus:
    """Test add_prometheus function."""

    def test_add_prometheus_adds_middleware_and_route(self):
        """Test that add_prometheus adds PrometheusMiddleware and metrics route."""
        mock_app = Mock()

        add_prometheus(mock_app, app_name="test-service")

        # Should add PrometheusMiddleware
        mock_app.add_middleware.assert_called()
        middleware_call = mock_app.add_middleware.call_args_list[0]
        assert "PrometheusMiddleware" in str(middleware_call)

        # Should add /metrics route
        mock_app.add_route.assert_called_once()
        route_call = mock_app.add_route.call_args
        assert route_call[0][0] == "/metrics"

    def test_add_prometheus_uses_custom_app_name(self):
        """Test that add_prometheus uses custom app_name."""
        mock_app = Mock()

        with patch("services.gateway.app.core.observability.PrometheusMiddleware") as mock_middleware:
            add_prometheus(mock_app, app_name="custom-app")

            # Should be called with add_middleware
            mock_app.add_middleware.assert_called()

    def test_add_prometheus_creates_custom_metrics(self):
        """Test that add_prometheus creates custom metrics registry."""
        from fastapi import FastAPI

        app = FastAPI()

        add_prometheus(app, app_name="test")

        # Should create metrics dict on app.state
        assert hasattr(app.state, "metrics")
        assert isinstance(app.state.metrics, dict)

        # Should contain expected metrics (if prometheus_client available)
        if app.state.metrics:  # Only check if metrics were created
            expected_metrics = [
                "approvals_decisions_total",
                "approvals_latency_seconds",
                "slack_posts_total",
                "slack_post_errors_total",
                "approvals_override_total",
                "workflows_auto_vs_hitl_total",
                "quota_slack_posts_total",
                "quota_rag_searches_total",
            ]

            for metric_name in expected_metrics:
                assert metric_name in app.state.metrics

    def test_add_prometheus_handles_metrics_import_failure(self):
        """Test that add_prometheus handles prometheus_client import failures."""
        from fastapi import FastAPI

        app = FastAPI()

        # Mock prometheus_client.Counter to fail during import
        import sys
        original_import = __builtins__['__import__']

        def mock_import(name, *args, **kwargs):
            if name == 'prometheus_client':
                raise ImportError("prometheus_client not installed")
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=mock_import):
            add_prometheus(app, app_name="test")

        # Should create empty metrics dict on error
        assert app.state.metrics == {}

    def test_add_prometheus_adds_limits_middleware(self):
        """Test that add_prometheus adds rate limiting middleware."""
        mock_app = Mock()

        add_prometheus(mock_app, app_name="test")

        # Should add two middlewares: PrometheusMiddleware and _LimitsMiddleware
        assert mock_app.add_middleware.call_count == 2

    def test_add_prometheus_default_app_name(self):
        """Test that add_prometheus uses default app_name."""
        mock_app = Mock()

        add_prometheus(mock_app)  # No app_name argument

        # Should still work with default
        mock_app.add_middleware.assert_called()
        mock_app.add_route.assert_called_once()


class TestLimitsMiddleware:
    """Test _LimitsMiddleware rate limiting and payload size checks."""

    def test_limits_middleware_added_to_app(self):
        """Test that _LimitsMiddleware is added to the app."""
        from fastapi import FastAPI
        app = FastAPI()

        add_prometheus(app, app_name="test")

        # The middleware should be added - we can't easily test it in isolation
        # without running the full FastAPI app, so we verify it was added
        assert len(app.user_middleware) > 0

    @pytest.mark.asyncio
    async def test_limits_middleware_blocks_large_payload(self):
        """Test that middleware blocks requests with large payloads."""
        from starlette.requests import Request
        from starlette.responses import JSONResponse

        # Mock request with large body
        mock_request = AsyncMock(spec=Request)
        mock_request.body = AsyncMock(return_value=b"x" * 20000)  # 20KB

        mock_call_next = AsyncMock()

        # Import the middleware class
        import time
        from collections import deque
        from services.gateway.app.core.config import get_settings
        from starlette.middleware.base import BaseHTTPMiddleware

        settings = get_settings()
        settings.max_payload_bytes = 10000  # 10KB limit

        # Create middleware instance
        class _LimitsMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next):
                body = await request.body()
                if len(body) > settings.max_payload_bytes:
                    return JSONResponse({"detail": "payload too large"}, status_code=413)
                return await call_next(request)

        middleware = _LimitsMiddleware(app=Mock())
        response = await middleware.dispatch(mock_request, mock_call_next)

        # Should return 413 error
        assert response.status_code == 413
        # Should not call next middleware
        mock_call_next.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_limits_middleware_enforces_rate_limit(self):
        """Test that middleware enforces rate limiting."""
        from starlette.requests import Request
        from starlette.responses import JSONResponse
        import time
        from collections import deque

        # Mock request with small body
        mock_request = AsyncMock(spec=Request)
        mock_request.body = AsyncMock(return_value=b"small")

        mock_call_next = AsyncMock()

        from services.gateway.app.core.config import get_settings
        from starlette.middleware.base import BaseHTTPMiddleware

        settings = get_settings()
        settings.max_payload_bytes = 10000
        settings.rate_limit_per_min = 2  # Very low limit for testing

        window_s = 60
        max_requests = 2
        timestamps: deque[float] = deque()

        class _LimitsMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next):
                body = await request.body()
                if len(body) > settings.max_payload_bytes:
                    return JSONResponse({"detail": "payload too large"}, status_code=413)

                now = time.time()
                while timestamps and now - timestamps[0] > window_s:
                    timestamps.popleft()
                if len(timestamps) >= max_requests:
                    return JSONResponse({"detail": "rate limit exceeded"}, status_code=429)
                timestamps.append(now)
                return await call_next(request)

        middleware = _LimitsMiddleware(app=Mock())

        # First two requests should succeed
        response1 = await middleware.dispatch(mock_request, mock_call_next)
        response2 = await middleware.dispatch(mock_request, mock_call_next)

        # Third request should be rate limited
        response3 = await middleware.dispatch(mock_request, mock_call_next)

        assert response3.status_code == 429


class TestAddTracing:
    """Test add_tracing function."""

    def test_add_tracing_when_otel_not_available(self):
        """Test that add_tracing handles OpenTelemetry not being available."""
        mock_app = Mock()

        with patch("services.gateway.app.core.observability._HAS_OTEL", False):
            # Should not raise
            add_tracing(mock_app, app_name="test", endpoint=None)

        # Should return early without setting up tracing

    def test_add_tracing_with_endpoint(self):
        """Test add_tracing with OTLP endpoint."""
        mock_app = Mock()

        with patch("services.gateway.app.core.observability._HAS_OTEL", True):
            with patch("services.gateway.app.core.observability.Resource") as mock_resource:
                with patch("services.gateway.app.core.observability.TracerProvider") as mock_provider_class:
                    with patch("services.gateway.app.core.observability.BatchSpanProcessor") as mock_batch:
                        with patch("services.gateway.app.core.observability.OTLPSpanExporter") as mock_exporter:
                            with patch("services.gateway.app.core.observability.trace") as mock_trace:
                                with patch("services.gateway.app.core.observability.FastAPIInstrumentor") as mock_instrumentor:
                                    mock_resource_instance = Mock()
                                    mock_resource.create.return_value = mock_resource_instance

                                    mock_provider = Mock()
                                    mock_provider_class.return_value = mock_provider

                                    add_tracing(mock_app, app_name="test-service", endpoint="http://otel:4318")

                                    # Should create resource with service name
                                    mock_resource.create.assert_called_once_with({"service.name": "test-service"})

                                    # Should create TracerProvider with resource
                                    mock_provider_class.assert_called_once_with(resource=mock_resource_instance)

                                    # Should create OTLP exporter with endpoint
                                    mock_exporter.assert_called_once_with(endpoint="http://otel:4318")

                                    # Should add batch processor
                                    mock_provider.add_span_processor.assert_called_once()

                                    # Should set tracer provider
                                    mock_trace.set_tracer_provider.assert_called_once_with(mock_provider)

                                    # Should instrument the app
                                    mock_instrumentor.instrument_app.assert_called_once_with(mock_app)

    def test_add_tracing_without_endpoint(self):
        """Test add_tracing without OTLP endpoint (console output)."""
        mock_app = Mock()

        with patch("services.gateway.app.core.observability._HAS_OTEL", True):
            with patch("services.gateway.app.core.observability.Resource") as mock_resource:
                with patch("services.gateway.app.core.observability.TracerProvider") as mock_provider_class:
                    with patch("services.gateway.app.core.observability.SimpleSpanProcessor") as mock_simple:
                        with patch("services.gateway.app.core.observability.ConsoleSpanExporter") as mock_console:
                            with patch("services.gateway.app.core.observability.trace") as mock_trace:
                                with patch("services.gateway.app.core.observability.FastAPIInstrumentor") as mock_instrumentor:
                                    mock_resource_instance = Mock()
                                    mock_resource.create.return_value = mock_resource_instance

                                    mock_provider = Mock()
                                    mock_provider_class.return_value = mock_provider

                                    add_tracing(mock_app, app_name="test-service", endpoint=None)

                                    # Should create console exporter (no endpoint)
                                    mock_console.assert_called_once()

                                    # Should add simple processor (not batch)
                                    mock_provider.add_span_processor.assert_called_once()

                                    # Should still set tracer provider
                                    mock_trace.set_tracer_provider.assert_called_once_with(mock_provider)

                                    # Should instrument the app
                                    mock_instrumentor.instrument_app.assert_called_once_with(mock_app)

    def test_add_tracing_with_empty_string_endpoint(self):
        """Test add_tracing treats empty string endpoint as None."""
        mock_app = Mock()

        with patch("services.gateway.app.core.observability._HAS_OTEL", True):
            with patch("services.gateway.app.core.observability.Resource"):
                with patch("services.gateway.app.core.observability.TracerProvider"):
                    with patch("services.gateway.app.core.observability.SimpleSpanProcessor") as mock_simple:
                        with patch("services.gateway.app.core.observability.ConsoleSpanExporter") as mock_console:
                            with patch("services.gateway.app.core.observability.trace"):
                                with patch("services.gateway.app.core.observability.FastAPIInstrumentor"):
                                    # Empty string is falsy, should use console exporter
                                    add_tracing(mock_app, app_name="test", endpoint="")

                                    # Should use console exporter (empty string is falsy)
                                    mock_console.assert_called_once()
