"""
Tests for workflows router.

Basic validation tests to ensure refactored endpoints work correctly.
Current coverage: 54% → Target: 70%+
"""
import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, OperationalError
import httpx

from services.gateway.app.models.action_log import ActionLog
from services.gateway.app.models.workflow_jobs import WorkflowJob
from services.gateway.app.models.approvals import Approval


class TestRunWorkflow:
    """Test workflow execution endpoint."""

    def test_run_workflow_success(self, client: TestClient, db_session: Session):
        """Test running a workflow successfully."""
        # Clean database
        db_session.query(ActionLog).delete()
        db_session.query(WorkflowJob).delete()
        db_session.commit()

        payload = {
            "rule": "deploy",
            "subject": "deploy:test-service",
            "action": "allow",
            "payload": {"version": "1.0.0"}
        }

        response = client.post("/v1/workflows/run", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert data["action"] == "allow"
        assert "id" in data

        # Verify job was created
        jobs = db_session.query(WorkflowJob).all()
        assert len(jobs) == 1
        assert jobs[0].status == "queued"
        assert jobs[0].rule_kind == "deploy"

    def test_run_workflow_minimal_payload(self, client: TestClient, db_session: Session):
        """Test running a workflow with minimal payload."""
        # Clean database
        db_session.query(ActionLog).delete()
        db_session.query(WorkflowJob).delete()
        db_session.commit()

        payload = {
            "action": "nudge"
        }

        response = client.post("/v1/workflows/run", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert data["action"] == "nudge"

    def test_run_workflow_with_block_creates_approval(self, client: TestClient, db_session: Session):
        """Test that blocked workflow creates approval request."""
        # Clean database
        db_session.query(Approval).delete()
        db_session.query(ActionLog).delete()
        db_session.query(WorkflowJob).delete()
        db_session.commit()

        payload = {
            "rule": "deploy",
            "subject": "deploy:production",
            "action": "block",
            "payload": {"environment": "production"}
        }

        response = client.post("/v1/workflows/run", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "awaiting_approval"
        assert "action_id" in data

        # Verify approval was created
        approvals = db_session.query(Approval).all()
        assert len(approvals) == 1
        assert approvals[0].status == "pending"
        assert approvals[0].subject == "deploy:production"

    def test_run_workflow_invalid_payload(self, client: TestClient, db_session: Session):
        """Test that invalid payload returns validation error."""
        payload = {
            "subject": "x" * 300,  # Exceeds max_length=255
            "action": "allow"
        }

        response = client.post("/v1/workflows/run", json=payload)

        # Pydantic validation returns 422
        assert response.status_code == 422


class TestListJobs:
    """Test workflow jobs listing endpoint."""

    def test_list_jobs_empty(self, client: TestClient, db_session: Session):
        """Test listing jobs when none exist."""
        # Clean database
        db_session.query(WorkflowJob).delete()
        db_session.commit()

        response = client.get("/v1/workflows/jobs")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_jobs_returns_jobs(self, client: TestClient, db_session: Session):
        """Test listing jobs returns all jobs."""
        # Clean database
        db_session.query(WorkflowJob).delete()
        db_session.commit()

        # Create test jobs
        job1 = WorkflowJob(status="queued", rule_kind="deploy", subject="deploy:service-a")
        job2 = WorkflowJob(status="done", rule_kind="merge", subject="pr:123")
        db_session.add_all([job1, job2])
        db_session.commit()

        response = client.get("/v1/workflows/jobs")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["status"] in ["queued", "done"]
        assert all("id" in job for job in data)
        assert all("rule_kind" in job for job in data)


class TestGetJob:
    """Test individual job retrieval endpoint."""

    def test_get_job_success(self, client: TestClient, db_session: Session):
        """Test getting a specific job."""
        # Clean database
        db_session.query(WorkflowJob).delete()
        db_session.commit()

        job = WorkflowJob(
            status="queued",
            rule_kind="deploy",
            subject="deploy:api-service"
        )
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)

        response = client.get(f"/v1/workflows/jobs/{job.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == job.id
        assert data["status"] == "queued"
        assert data["rule_kind"] == "deploy"
        assert data["subject"] == "deploy:api-service"

    def test_get_job_not_found(self, client: TestClient, db_session: Session):
        """Test getting a non-existent job returns 404."""
        response = client.get("/v1/workflows/jobs/99999")

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data


class TestWorkflowPolicyIntegration:
    """Test workflow policy integration (OPA and policy file fallback)."""

    def test_run_workflow_with_opa_allow(self, client: TestClient, db_session: Session):
        """Test workflow with OPA returning allow decision."""
        db_session.query(ActionLog).delete()
        db_session.query(WorkflowJob).delete()
        db_session.commit()

        with patch("services.gateway.app.api.v1.routers.workflows.get_settings") as mock_settings:
            with patch("services.gateway.app.api.v1.routers.workflows.httpx.Client") as mock_client_class:
                settings = Mock()
                settings.opa_url = "http://localhost:8181"
                mock_settings.return_value = settings

                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"result": {"action": "allow"}}

                mock_client = Mock()
                mock_client.__enter__ = Mock(return_value=mock_client)
                mock_client.__exit__ = Mock(return_value=None)
                mock_client.post.return_value = mock_response

                mock_client_class.return_value = mock_client

                payload = {"kind": "deploy", "subject": "deploy:test"}

                response = client.post("/v1/workflows/run", json=payload)

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "queued"
                assert data["action"] == "allow"

    def test_run_workflow_with_opa_block(self, client: TestClient, db_session: Session):
        """Test workflow with OPA returning block decision."""
        db_session.query(Approval).delete()
        db_session.query(ActionLog).delete()
        db_session.query(WorkflowJob).delete()
        db_session.commit()

        with patch("services.gateway.app.api.v1.routers.workflows.get_settings") as mock_settings:
            with patch("services.gateway.app.api.v1.routers.workflows.httpx.Client") as mock_client_class:
                settings = Mock()
                settings.opa_url = "http://localhost:8181"
                mock_settings.return_value = settings

                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"result": {"allow": False}}

                mock_client = Mock()
                mock_client.__enter__ = Mock(return_value=mock_client)
                mock_client.__exit__ = Mock(return_value=None)
                mock_client.post.return_value = mock_response

                mock_client_class.return_value = mock_client

                payload = {"kind": "deploy", "subject": "deploy:prod"}

                response = client.post("/v1/workflows/run", json=payload)

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "awaiting_approval"

    def test_run_workflow_opa_http_error_fallback_to_policy(self, client: TestClient, db_session: Session):
        """Test workflow falls back to policy file when OPA returns HTTP error."""
        db_session.query(ActionLog).delete()
        db_session.query(WorkflowJob).delete()
        db_session.commit()

        with patch("services.gateway.app.api.v1.routers.workflows.get_settings") as mock_settings:
            with patch("services.gateway.app.api.v1.routers.workflows.httpx.Client") as mock_client_class:
                with patch("services.gateway.app.api.v1.routers.workflows._load_policy") as mock_policy:
                    settings = Mock()
                    settings.opa_url = "http://localhost:8181"
                    mock_settings.return_value = settings

                    mock_response = Mock()
                    mock_response.status_code = 500
                    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                        "500 error", request=Mock(), response=mock_response
                    )

                    mock_client = Mock()
                    mock_client.__enter__ = Mock(return_value=mock_client)
                    mock_client.__exit__ = Mock(return_value=None)
                    mock_client.post.return_value = mock_response

                    mock_client_class.return_value = mock_client

                    # Policy file returns nudge
                    mock_policy.return_value = {"deploy": {"action": "nudge"}}

                    payload = {"kind": "deploy", "subject": "deploy:test"}

                    response = client.post("/v1/workflows/run", json=payload)

                    assert response.status_code == 200
                    data = response.json()
                    assert data["status"] == "queued"
                    assert data["action"] == "nudge"

    def test_run_workflow_opa_request_error_fallback_to_policy(self, client: TestClient, db_session: Session):
        """Test workflow falls back to policy file when OPA is unreachable."""
        db_session.query(ActionLog).delete()
        db_session.query(WorkflowJob).delete()
        db_session.commit()

        with patch("services.gateway.app.api.v1.routers.workflows.get_settings") as mock_settings:
            with patch("services.gateway.app.api.v1.routers.workflows.httpx.Client") as mock_client_class:
                with patch("services.gateway.app.api.v1.routers.workflows._load_policy") as mock_policy:
                    settings = Mock()
                    settings.opa_url = "http://localhost:8181"
                    mock_settings.return_value = settings

                    mock_client = Mock()
                    mock_client.__enter__ = Mock(return_value=mock_client)
                    mock_client.__exit__ = Mock(return_value=None)
                    mock_client.post.side_effect = httpx.ConnectError("Connection refused")

                    mock_client_class.return_value = mock_client

                    # Policy file returns allow
                    mock_policy.return_value = {"deploy": {"action": "allow"}}

                    payload = {"kind": "deploy", "subject": "deploy:test"}

                    response = client.post("/v1/workflows/run", json=payload)

                    assert response.status_code == 200
                    data = response.json()
                    assert data["status"] == "queued"
                    assert data["action"] == "allow"

    def test_run_workflow_policy_file_default_nudge(self, client: TestClient, db_session: Session):
        """Test workflow defaults to 'nudge' when policy file has no matching rule."""
        db_session.query(ActionLog).delete()
        db_session.query(WorkflowJob).delete()
        db_session.commit()

        with patch("services.gateway.app.api.v1.routers.workflows.get_settings") as mock_settings:
            with patch("services.gateway.app.api.v1.routers.workflows._load_policy") as mock_policy:
                settings = Mock()
                settings.opa_url = None  # No OPA
                mock_settings.return_value = settings

                # Policy file has no matching rule
                mock_policy.return_value = {}

                payload = {"kind": "unknown_kind", "subject": "test"}

                response = client.post("/v1/workflows/run", json=payload)

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "queued"
                assert data["action"] == "nudge"


class TestWorkflowErrorHandling:
    """Test workflow error handling paths."""

    def test_run_workflow_integrity_error(self, client: TestClient, db_session: Session):
        """Test workflow handles database integrity errors."""
        with patch.object(db_session, "commit", side_effect=IntegrityError("", "", "")):
            payload = {"action": "allow", "subject": "test"}

            response = client.post("/v1/workflows/run", json=payload)

            assert response.status_code == 409
            assert "conflict" in response.json()["detail"].lower()

    def test_run_workflow_operational_error(self, client: TestClient, db_session: Session):
        """Test workflow handles database operational errors."""
        with patch.object(db_session, "commit", side_effect=OperationalError("", "", "")):
            payload = {"action": "allow", "subject": "test"}

            response = client.post("/v1/workflows/run", json=payload)

            assert response.status_code == 503
            assert "unavailable" in response.json()["detail"].lower()

    def test_run_workflow_unexpected_error(self, client: TestClient, db_session: Session):
        """Test workflow handles unexpected errors."""
        with patch.object(db_session, "commit", side_effect=RuntimeError("Unexpected")):
            payload = {"action": "allow", "subject": "test"}

            response = client.post("/v1/workflows/run", json=payload)

            assert response.status_code == 500
            assert "internal" in response.json()["detail"].lower()

    def test_list_jobs_operational_error(self, client: TestClient, db_session: Session):
        """Test list jobs handles database errors."""
        with patch.object(db_session, "query", side_effect=OperationalError("", "", "")):
            response = client.get("/v1/workflows/jobs")

            assert response.status_code == 503
            assert "unavailable" in response.json()["detail"].lower()

    def test_list_jobs_unexpected_error(self, client: TestClient, db_session: Session):
        """Test list jobs handles unexpected errors."""
        with patch.object(db_session, "query", side_effect=RuntimeError("Unexpected")):
            response = client.get("/v1/workflows/jobs")

            assert response.status_code == 500
            assert "internal" in response.json()["detail"].lower()

    def test_get_job_operational_error(self, client: TestClient, db_session: Session):
        """Test get job handles database errors."""
        with patch.object(db_session, "get", side_effect=OperationalError("", "", "")):
            response = client.get("/v1/workflows/jobs/1")

            assert response.status_code == 503
            assert "unavailable" in response.json()["detail"].lower()

    def test_get_job_unexpected_error(self, client: TestClient, db_session: Session):
        """Test get job handles unexpected errors."""
        with patch.object(db_session, "get", side_effect=RuntimeError("Unexpected")):
            response = client.get("/v1/workflows/jobs/1")

            assert response.status_code == 500
            assert "internal" in response.json()["detail"].lower()


class TestWorkflowMetrics:
    """Test workflow metrics integration."""

    def test_run_workflow_metrics_auto_path(self, client: TestClient, db_session: Session):
        """Test workflow increments auto metrics counter."""
        db_session.query(ActionLog).delete()
        db_session.query(WorkflowJob).delete()
        db_session.commit()

        with patch("services.gateway.app.api.v1.routers.workflows.global_metrics") as mock_metrics:
            mock_counter = Mock()
            mock_metrics.__getitem__.return_value = mock_counter

            payload = {"action": "allow", "subject": "test"}

            response = client.post("/v1/workflows/run", json=payload)

            assert response.status_code == 200
            mock_counter.labels.assert_called_with(mode="auto")
            mock_counter.labels.return_value.inc.assert_called_once()

    def test_run_workflow_metrics_hitl_path(self, client: TestClient, db_session: Session):
        """Test blocked workflow increments HITL metrics counter."""
        db_session.query(Approval).delete()
        db_session.query(ActionLog).delete()
        db_session.query(WorkflowJob).delete()
        db_session.commit()

        with patch("services.gateway.app.api.v1.routers.workflows.global_metrics") as mock_metrics:
            mock_counter = Mock()
            mock_metrics.__getitem__.return_value = mock_counter

            payload = {"action": "block", "subject": "test"}

            response = client.post("/v1/workflows/run", json=payload)

            assert response.status_code == 200
            mock_counter.labels.assert_called_with(mode="hitl")
            mock_counter.labels.return_value.inc.assert_called_once()

    def test_run_workflow_metrics_key_error_auto_path(self, client: TestClient, db_session: Session):
        """Test workflow handles metrics KeyError gracefully for auto path."""
        db_session.query(ActionLog).delete()
        db_session.query(WorkflowJob).delete()
        db_session.commit()

        with patch("services.gateway.app.api.v1.routers.workflows.global_metrics") as mock_metrics:
            mock_metrics.__getitem__.side_effect = KeyError("missing_metric")

            payload = {"action": "allow", "subject": "test"}

            response = client.post("/v1/workflows/run", json=payload)

            # Should succeed despite metrics error
            assert response.status_code == 200
            assert response.json()["status"] == "queued"

    def test_run_workflow_metrics_key_error_hitl_path(self, client: TestClient, db_session: Session):
        """Test workflow handles metrics KeyError gracefully for HITL path."""
        db_session.query(Approval).delete()
        db_session.query(ActionLog).delete()
        db_session.query(WorkflowJob).delete()
        db_session.commit()

        with patch("services.gateway.app.api.v1.routers.workflows.global_metrics") as mock_metrics:
            mock_metrics.__getitem__.side_effect = KeyError("missing_metric")

            payload = {"action": "block", "subject": "test"}

            response = client.post("/v1/workflows/run", json=payload)

            # Should succeed despite metrics error
            assert response.status_code == 200
            assert response.json()["status"] == "awaiting_approval"
