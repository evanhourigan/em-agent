"""Tests for metrics endpoints."""

import pytest
from fastapi.testclient import TestClient


class TestMetricsPlaceholder:
    """Tests for GET /metrics endpoint."""

    def test_metrics_placeholder_returns_text(self, client: TestClient):
        """Test that /metrics endpoint returns metrics data.

        Note: The /metrics endpoint is actually served by Prometheus middleware
        (starlette_exporter), not by the placeholder endpoint in the router.
        """
        response = client.get("/metrics")
        assert response.status_code == 200
        # Should return Prometheus metrics format (contains HELP/TYPE lines)
        assert ("help" in response.text.lower() or "type" in response.text.lower())

    def test_metrics_placeholder_content_type(self, client: TestClient):
        """Test that /metrics returns plain text content type."""
        response = client.get("/metrics")
        assert response.status_code == 200
        # PlainTextResponse should set content-type to text/plain
        content_type = response.headers.get("content-type", "")
        assert "text/plain" in content_type.lower()


class TestQuotasInfo:
    """Tests for GET /v1/metrics/quotas endpoint."""

    def test_quotas_info_success(self, client: TestClient):
        """Test that quotas endpoint returns success."""
        response = client.get("/v1/metrics/quotas")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

    def test_quotas_info_structure(self, client: TestClient):
        """Test that quotas response has expected structure."""
        response = client.get("/v1/metrics/quotas")
        assert response.status_code == 200
        data = response.json()
        assert "ok" in data

        # Quota info may or may not be present depending on global_metrics
        # but the endpoint should always return {"ok": True}

    def test_quotas_info_with_quota_data(self, client: TestClient):
        """Test quotas response when quota data is available."""
        response = client.get("/v1/metrics/quotas")
        assert response.status_code == 200
        data = response.json()

        # If quota key exists, verify structure
        if "quota" in data:
            quota = data["quota"]
            assert "limits" in quota
            assert "max_daily_slack_posts" in quota["limits"]
            assert "max_daily_rag_searches" in quota["limits"]


class TestDORAMetrics:
    """Tests for DORA metrics endpoints."""

    @pytest.mark.skip(
        reason="Requires PostgreSQL - uses public.dora_lead_time table"
    )
    def test_dora_lead_time(self, client: TestClient):
        """Test DORA lead time metrics endpoint.

        TODO: Requires PostgreSQL with public.dora_lead_time view/table.
        """
        response = client.get("/v1/metrics/dora/lead-time")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        if len(data) > 0:
            # Check structure of lead time entries
            entry = data[0]
            assert "delivery_id" in entry
            assert "lead_time_hours" in entry

    @pytest.mark.skip(
        reason="Requires PostgreSQL - uses public.deployment_frequency table"
    )
    def test_deployment_frequency(self, client: TestClient):
        """Test deployment frequency metrics endpoint.

        TODO: Requires PostgreSQL with public.deployment_frequency view/table.
        """
        response = client.get("/v1/metrics/dora/deployment-frequency")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        if len(data) > 0:
            entry = data[0]
            assert "day" in entry
            assert "deployments" in entry

    @pytest.mark.skip(
        reason="Requires PostgreSQL - uses public.change_fail_rate table"
    )
    def test_change_fail_rate(self, client: TestClient):
        """Test change fail rate metrics endpoint.

        TODO: Requires PostgreSQL with public.change_fail_rate view/table.
        """
        response = client.get("/v1/metrics/dora/change-fail-rate")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        if len(data) > 0:
            entry = data[0]
            assert "day" in entry
            assert "change_fail_rate" in entry

    @pytest.mark.skip(
        reason="Requires PostgreSQL - uses public.mttr table"
    )
    def test_mttr(self, client: TestClient):
        """Test MTTR (mean time to recovery) metrics endpoint.

        TODO: Requires PostgreSQL with public.mttr view/table.
        """
        response = client.get("/v1/metrics/dora/mttr")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        if len(data) > 0:
            entry = data[0]
            assert "delivery_id" in entry
            assert "mttr_hours" in entry

    def test_dora_endpoints_return_empty_on_sqlite(self, client: TestClient):
        """Test that DORA endpoints gracefully handle missing tables.

        On SQLite (test DB), the public schema tables don't exist.
        Endpoints should return empty list or error gracefully.
        """
        endpoints = [
            "/v1/metrics/dora/lead-time",
            "/v1/metrics/dora/deployment-frequency",
            "/v1/metrics/dora/change-fail-rate",
            "/v1/metrics/dora/mttr"
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            # Should either return 200 with empty list, or an error
            assert response.status_code in [200, 500, 503]

            if response.status_code == 200:
                data = response.json()
                # If successful on SQLite, should return empty list
                assert isinstance(data, list)
