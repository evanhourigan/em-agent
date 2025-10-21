"""
Tests for workflows router.

Basic validation tests to ensure refactored endpoints work correctly.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

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
