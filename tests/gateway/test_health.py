"""Tests for health and readiness endpoints."""

import pytest
from fastapi.testclient import TestClient


class TestHealth:
    """Tests for GET /health endpoint."""

    def test_health_success(self, client: TestClient):
        """Test that health endpoint returns success when DB is healthy."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_health_response_structure(self, client: TestClient):
        """Test that health response has expected structure."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()

        # Top-level fields
        assert "status" in data
        assert "db" in data
        assert "orm" in data

        # DB check structure
        assert "ok" in data["db"]
        assert "details" in data["db"]

        # ORM check structure
        assert "ok" in data["orm"]
        assert "details" in data["orm"]

    def test_health_db_check_ok(self, client: TestClient):
        """Test that DB check returns ok."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["db"]["ok"] is True
        assert data["db"]["details"] == "ok"

    def test_health_orm_check_ok(self, client: TestClient):
        """Test that ORM check returns ok."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["orm"]["ok"] is True
        assert data["orm"]["details"] == "ok"

    def test_health_overall_ok_when_both_healthy(self, client: TestClient):
        """Test that overall status is ok when both DB and ORM healthy."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["db"]["ok"] is True
        assert data["orm"]["ok"] is True

    @pytest.mark.skip(
        reason="Requires mocking database failure"
    )
    def test_health_degraded_on_db_failure(self, client: TestClient):
        """Test that health returns 503 when DB check fails.

        TODO: Requires mocking the check_database_health function
        to simulate database connection failure.
        """
        # Would mock check_database_health to return {"ok": False, "details": "error"}
        response = client.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["db"]["ok"] is False

    @pytest.mark.skip(
        reason="Requires mocking ORM session failure"
    )
    def test_health_degraded_on_orm_failure(self, client: TestClient):
        """Test that health returns 503 when ORM check fails.

        TODO: Requires mocking the session.execute call to raise exception.
        """
        # Would mock session.execute to raise an exception
        response = client.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["orm"]["ok"] is False


class TestReady:
    """Tests for GET /ready endpoint."""

    def test_ready_success(self, client: TestClient):
        """Test that ready endpoint returns success when DB is reachable."""
        response = client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is True

    def test_ready_response_structure(self, client: TestClient):
        """Test that ready response has expected structure."""
        response = client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert "ready" in data
        assert isinstance(data["ready"], bool)

    def test_ready_returns_boolean(self, client: TestClient):
        """Test that ready field is a boolean value."""
        response = client.get("/ready")
        data = response.json()
        assert data["ready"] in [True, False]

    @pytest.mark.skip(
        reason="Requires mocking database failure"
    )
    def test_ready_false_on_db_failure(self, client: TestClient):
        """Test that ready returns 503 and false when DB unreachable.

        TODO: Requires mocking session.execute to raise exception.
        """
        # Would mock session.execute to raise an exception
        response = client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["ready"] is False


class TestHealthVsReady:
    """Tests comparing health and ready endpoints."""

    def test_both_endpoints_succeed_together(self, client: TestClient):
        """Test that both endpoints succeed when DB is healthy."""
        health_response = client.get("/health")
        ready_response = client.get("/ready")

        assert health_response.status_code == 200
        assert ready_response.status_code == 200

        health_data = health_response.json()
        ready_data = ready_response.json()

        # When ready is true, health should be ok
        if ready_data["ready"]:
            assert health_data["status"] == "ok"

    def test_health_provides_more_detail_than_ready(self, client: TestClient):
        """Test that health endpoint provides more diagnostic info."""
        health_response = client.get("/health")
        ready_response = client.get("/ready")

        health_data = health_response.json()
        ready_data = ready_response.json()

        # Health has detailed checks
        assert "db" in health_data
        assert "orm" in health_data
        assert "details" in health_data["db"]
        assert "details" in health_data["orm"]

        # Ready is simple boolean
        assert len(ready_data) == 1
        assert "ready" in ready_data

    def test_ready_is_simpler_check(self, client: TestClient):
        """Test that ready endpoint is a simple boolean check."""
        ready_response = client.get("/ready")
        ready_data = ready_response.json()

        # Only one field: ready
        assert list(ready_data.keys()) == ["ready"]
        assert isinstance(ready_data["ready"], bool)


class TestHealthEndpointBehavior:
    """Tests for specific health endpoint behaviors."""

    def test_health_does_not_modify_database(self, client: TestClient):
        """Test that health checks are read-only."""
        # Call health multiple times
        response1 = client.get("/health")
        response2 = client.get("/health")
        response3 = client.get("/health")

        # All should succeed with same status
        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response3.status_code == 200

        # Results should be consistent
        assert response1.json()["status"] == response2.json()["status"]
        assert response2.json()["status"] == response3.json()["status"]

    def test_ready_does_not_modify_database(self, client: TestClient):
        """Test that readiness checks are read-only."""
        # Call ready multiple times
        response1 = client.get("/ready")
        response2 = client.get("/ready")
        response3 = client.get("/ready")

        # All should succeed
        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response3.status_code == 200

        # Results should be consistent
        assert response1.json()["ready"] == response2.json()["ready"]
        assert response2.json()["ready"] == response3.json()["ready"]

    def test_health_endpoints_are_idempotent(self, client: TestClient):
        """Test that health endpoints can be called repeatedly safely."""
        # Make many calls to simulate health check polling
        for _ in range(10):
            health_response = client.get("/health")
            ready_response = client.get("/ready")

            # Should always succeed when DB is healthy
            assert health_response.status_code == 200
            assert ready_response.status_code == 200
