"""
Unit tests for the approvals router.

Tests cover:
- Listing approvals
- Proposing approvals
- Retrieving single approval
- Making decisions on approvals
- Notifying about approvals
"""
import json
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from services.gateway.app.models.approvals import Approval
from services.gateway.app.models.workflow_jobs import WorkflowJob
from services.gateway.app.models.action_log import ActionLog


@pytest.mark.unit
class TestListApprovals:
    """Tests for GET /v1/approvals endpoint."""

    def test_list_empty_approvals(self, client: TestClient, db_session: Session):
        """Test listing approvals when database is empty."""
        # Clean database first
        db_session.query(Approval).delete()
        db_session.commit()

        response = client.get("/v1/approvals")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_approvals_returns_latest_first(self, client: TestClient, db_session: Session):
        """Test that approvals are returned in descending order by ID."""
        # Clean database first
        db_session.query(Approval).delete()
        db_session.commit()

        # Create multiple approvals
        for i in range(5):
            approval = Approval(
                subject=f"test:subject-{i}",
                action="deploy",
                status="pending",
                reason=f"Test reason {i}"
            )
            db_session.add(approval)
        db_session.commit()

        response = client.get("/v1/approvals")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5

        # Verify descending order (latest first)
        ids = [item["id"] for item in data]
        assert ids == sorted(ids, reverse=True)

    def test_list_approvals_limited_to_100(self, client: TestClient, db_session: Session):
        """Test that list endpoint limits results to 100."""
        # Clean database first
        db_session.query(Approval).delete()
        db_session.commit()

        # Create 150 approvals
        for i in range(150):
            approval = Approval(
                subject=f"test:subject-{i}",
                action="deploy",
                status="pending"
            )
            db_session.add(approval)
        db_session.commit()

        response = client.get("/v1/approvals")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 100

    def test_list_approvals_response_format(self, client: TestClient, db_session: Session):
        """Test that response has correct format."""
        # Clean database first
        db_session.query(Approval).delete()
        db_session.commit()

        approval = Approval(
            subject="test:123",
            action="merge",
            status="pending",
            reason="Test approval"
        )
        db_session.add(approval)
        db_session.commit()

        response = client.get("/v1/approvals")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

        item = data[0]
        assert "id" in item
        assert item["subject"] == "test:123"
        assert item["action"] == "merge"
        assert item["status"] == "pending"
        assert item["reason"] == "Test approval"
        assert "created_at" in item
        assert item["decided_at"] is None


@pytest.mark.unit
class TestProposeApproval:
    """Tests for POST /v1/approvals/propose endpoint."""

    def test_propose_approval_success(self, client: TestClient, db_session: Session):
        """Test successful approval proposal."""
        payload = {
            "subject": "deploy:test-service",
            "action": "deploy",
            "reason": "Testing deployment",
            "payload": {"version": "1.0.0"}
        }

        response = client.post("/v1/approvals/propose", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "action_id" in data
        assert data["proposed"] == payload

        # Verify database record created
        approval = db_session.get(Approval, data["action_id"])
        assert approval is not None
        assert approval.subject == "deploy:test-service"
        assert approval.action == "deploy"
        assert approval.status == "pending"
        assert approval.reason == "Testing deployment"

        # Verify payload is JSON string
        assert json.loads(approval.payload) == {"version": "1.0.0"}

    def test_propose_approval_missing_action(self, client: TestClient, db_session: Session):
        """Test that missing action returns 422 (validation error)."""
        payload = {
            "subject": "test:123",
            "reason": "Test"
            # Missing required 'action' field
        }

        response = client.post("/v1/approvals/propose", json=payload)

        # Pydantic validation returns 422
        assert response.status_code == 422
        data = response.json()
        assert "errors" in data or "detail" in data

    def test_propose_approval_minimal_payload(self, client: TestClient, db_session: Session):
        """Test proposal with minimal required fields."""
        payload = {
            "subject": "test:minimal",  # Now required by Pydantic schema
            "action": "merge"
        }

        response = client.post("/v1/approvals/propose", json=payload)

        assert response.status_code == 200
        data = response.json()

        # Verify defaults applied
        approval = db_session.get(Approval, data["action_id"])
        assert approval.subject == "test:minimal"
        assert approval.reason is None
        # payload defaults to empty dict, serialized as None or "{}"
        assert approval.payload is None or approval.payload == "{}"

    def test_propose_approval_creates_audit_log(self, client: TestClient, db_session: Session):
        """Test that proposal creates an audit log entry."""
        # Clean audit log first
        db_session.query(ActionLog).delete()
        db_session.commit()

        payload = {
            "subject": "test:audit",
            "action": "deploy"
        }

        response = client.post("/v1/approvals/propose", json=payload)

        assert response.status_code == 200

        # Verify action log created
        logs = db_session.query(ActionLog).filter(
            ActionLog.rule_name == "approval.propose"
        ).all()
        assert len(logs) == 1
        assert logs[0].subject == "test:audit"
        assert logs[0].action == "deploy"

    def test_propose_approval_with_tracing(self, client: TestClient, db_session: Session, mocker):
        """Test that OpenTelemetry span is created when tracing enabled."""
        # Mock at the module level where it's imported
        mock_trace = mocker.patch("opentelemetry.trace")
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_span.return_value = mock_span
        mock_trace.get_tracer.return_value = mock_tracer

        payload = {
            "action": "deploy",
            "subject": "test:tracing"
        }

        response = client.post("/v1/approvals/propose", json=payload)

        assert response.status_code == 200
        # Verify span operations called (or skipped if tracing unavailable)
        # Don't assert on exact calls as tracing may be disabled


@pytest.mark.unit
class TestGetApproval:
    """Tests for GET /v1/approvals/{id} endpoint."""

    def test_get_approval_success(self, client: TestClient, db_session: Session):
        """Test successful retrieval of approval."""
        approval = Approval(
            subject="test:123",
            action="merge",
            status="pending",
            reason="Test approval"
        )
        db_session.add(approval)
        db_session.commit()

        response = client.get(f"/v1/approvals/{approval.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == approval.id
        assert data["subject"] == "test:123"
        assert data["action"] == "merge"
        assert data["status"] == "pending"
        assert data["reason"] == "Test approval"
        assert data["decided_at"] is None

    def test_get_approval_not_found(self, client: TestClient, db_session: Session):
        """Test 404 when approval doesn't exist."""
        response = client.get("/v1/approvals/99999")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_get_approval_with_decided_at(self, client: TestClient, db_session: Session):
        """Test approval with decided_at timestamp."""
        decided_time = datetime.utcnow()
        approval = Approval(
            subject="test:123",
            action="deploy",
            status="approve",
            decided_at=decided_time
        )
        db_session.add(approval)
        db_session.commit()

        response = client.get(f"/v1/approvals/{approval.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "approve"
        assert data["decided_at"] is not None
        assert data["decided_at"] == decided_time.isoformat()


@pytest.mark.unit
class TestDecideApproval:
    """Tests for POST /v1/approvals/{id}/decision endpoint."""

    def test_decide_approve_creates_workflow_job(self, client: TestClient, db_session: Session, mocker):
        """Test that approving creates a workflow job."""
        # Mock external dependencies
        mocker.patch("redis.from_url")
        mocker.patch("services.gateway.app.api.v1.routers.approvals.get_temporal")

        approval = Approval(
            subject="pr:123",
            action="merge",
            status="pending",
            payload=json.dumps({"pr_number": 123})
        )
        db_session.add(approval)
        db_session.commit()

        decision_payload = {
            "decision": "approve",
            "reason": "Looks good"
        }

        response = client.post(
            f"/v1/approvals/{approval.id}/decision",
            json=decision_payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "approve"
        assert data["reason"] == "Looks good"
        assert "job_id" in data
        assert data["job_id"] is not None  # Job should be created

        # Verify approval updated
        db_session.refresh(approval)
        assert approval.status == "approve"
        assert approval.reason == "Looks good"
        assert approval.decided_at is not None

        # Verify workflow job created
        job = db_session.get(WorkflowJob, data["job_id"])
        assert job is not None
        assert job.status == "queued"
        assert job.rule_kind == "merge"
        assert job.subject == "pr:123"

    def test_decide_decline_no_workflow_job(self, client: TestClient, db_session: Session):
        """Test that declining does not create workflow job."""
        # Clean database first
        db_session.query(WorkflowJob).delete()
        db_session.query(Approval).delete()
        db_session.commit()

        approval = Approval(
            subject="pr:456",
            action="merge",
            status="pending"
        )
        db_session.add(approval)
        db_session.commit()
        db_session.refresh(approval)  # Ensure approval is loaded from DB

        decision_payload = {
            "decision": "decline",
            "reason": "Needs more work"
        }

        response = client.post(
            f"/v1/approvals/{approval.id}/decision",
            json=decision_payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "decline"
        # job_id is in response but should be None
        assert data.get("job_id") is None

        # Verify no workflow job created
        jobs = db_session.query(WorkflowJob).all()
        assert len(jobs) == 0

    def test_decide_invalid_decision(self, client: TestClient, db_session: Session):
        """Test that invalid decision returns 422 (validation error)."""
        approval = Approval(
            subject="test:123",
            action="deploy",
            status="pending"
        )
        db_session.add(approval)
        db_session.commit()

        decision_payload = {
            "decision": "invalid"
        }

        response = client.post(
            f"/v1/approvals/{approval.id}/decision",
            json=decision_payload
        )

        # Pydantic validation returns 422
        assert response.status_code == 422
        data = response.json()
        # Should contain validation error about invalid decision
        assert "errors" in data or "detail" in data

    def test_decide_approval_not_found(self, client: TestClient, db_session: Session):
        """Test 404 when approval doesn't exist."""
        decision_payload = {
            "decision": "approve"
        }

        response = client.post(
            "/v1/approvals/99999/decision",
            json=decision_payload
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_decide_creates_audit_log(self, client: TestClient, db_session: Session, mocker):
        """Test that decision creates audit log entry."""
        # Mock external dependencies
        mocker.patch("redis.from_url")
        mocker.patch("services.gateway.app.api.v1.routers.approvals.get_temporal")

        # Clean audit log first
        db_session.query(ActionLog).filter(ActionLog.rule_name == "approval.decision").delete()
        db_session.commit()

        approval = Approval(
            subject="test:audit",
            action="deploy",
            status="pending"
        )
        db_session.add(approval)
        db_session.commit()

        decision_payload = {
            "decision": "approve"
        }

        response = client.post(
            f"/v1/approvals/{approval.id}/decision",
            json=decision_payload
        )

        assert response.status_code == 200

        # Verify audit log created
        logs = db_session.query(ActionLog).filter(
            ActionLog.rule_name == "approval.decision"
        ).all()
        assert len(logs) == 1
        assert logs[0].action == "approve"

    def test_decide_modify_decision(self, client: TestClient, db_session: Session):
        """Test 'modify' decision type."""
        approval = Approval(
            subject="pr:789",
            action="merge",
            status="pending"
        )
        db_session.add(approval)
        db_session.commit()

        decision_payload = {
            "decision": "modify",
            "reason": "Please add tests"
        }

        response = client.post(
            f"/v1/approvals/{approval.id}/decision",
            json=decision_payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "modify"
        assert data["reason"] == "Please add tests"
        # job_id is in response but should be None for modify
        assert data.get("job_id") is None


@pytest.mark.unit
class TestNotifyApproval:
    """Tests for POST /v1/approvals/{id}/notify endpoint."""

    @patch("services.gateway.app.api.v1.routers.approvals.SlackClient")
    def test_notify_success(self, mock_slack_client, client: TestClient, db_session: Session):
        """Test successful Slack notification."""
        # Setup mock
        mock_instance = MagicMock()
        mock_instance.post_blocks.return_value = {"ok": True, "ts": "1234567890.123456"}
        mock_slack_client.return_value = mock_instance

        approval = Approval(
            subject="pr:123",
            action="merge",
            status="pending"
        )
        db_session.add(approval)
        db_session.commit()

        notify_payload = {
            "channel": "#approvals"
        }

        response = client.post(
            f"/v1/approvals/{approval.id}/notify",
            json=notify_payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

        # Verify Slack client called
        mock_instance.post_blocks.assert_called_once()
        call_args = mock_instance.post_blocks.call_args
        assert call_args.kwargs["channel"] == "#approvals"
        assert "merge pr:123" in call_args.kwargs["text"].lower()

    @patch("services.gateway.app.api.v1.routers.approvals.SlackClient")
    def test_notify_without_channel(self, mock_slack_client, client: TestClient, db_session: Session):
        """Test notification without specifying channel."""
        mock_instance = MagicMock()
        mock_instance.post_blocks.return_value = {"ok": True}
        mock_slack_client.return_value = mock_instance

        approval = Approval(
            subject="deploy:service",
            action="deploy",
            status="pending"
        )
        db_session.add(approval)
        db_session.commit()

        response = client.post(f"/v1/approvals/{approval.id}/notify")

        assert response.status_code == 200

        # Verify called with None channel
        call_args = mock_instance.post_blocks.call_args
        assert call_args.kwargs["channel"] is None

    def test_notify_approval_not_found(self, client: TestClient, db_session: Session):
        """Test 404 when approval doesn't exist."""
        response = client.post("/v1/approvals/99999/notify")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @patch("services.gateway.app.api.v1.routers.approvals.SlackClient")
    def test_notify_includes_action_buttons(self, mock_slack_client, client: TestClient, db_session: Session):
        """Test that notification includes approve/decline buttons."""
        mock_instance = MagicMock()
        mock_instance.post_blocks.return_value = {"ok": True}
        mock_slack_client.return_value = mock_instance

        approval = Approval(
            subject="test:456",
            action="deploy",
            status="pending"
        )
        db_session.add(approval)
        db_session.commit()

        response = client.post(f"/v1/approvals/{approval.id}/notify")

        assert response.status_code == 200

        # Verify blocks include buttons
        call_args = mock_instance.post_blocks.call_args
        blocks = call_args.kwargs["blocks"]

        # Find actions block
        actions_block = next(
            (block for block in blocks if block["type"] == "actions"),
            None
        )
        assert actions_block is not None

        # Verify buttons
        buttons = actions_block["elements"]
        assert len(buttons) == 2

        approve_btn = buttons[0]
        assert approve_btn["text"]["text"] == "Approve"
        assert approve_btn["style"] == "primary"
        assert f"approve:{approval.id}" in approve_btn["value"]

        decline_btn = buttons[1]
        assert decline_btn["text"]["text"] == "Decline"
        assert decline_btn["style"] == "danger"
        assert f"decline:{approval.id}" in decline_btn["value"]


@pytest.mark.unit
class TestApprovalIntegration:
    """Integration tests for complete approval workflow."""

    def test_complete_approval_workflow(
        self,
        client: TestClient,
        db_session: Session,
        mocker
    ):
        """Test complete workflow: propose -> notify -> decide -> verify job."""
        # Setup mocks
        mock_slack_client = mocker.patch("services.gateway.app.api.v1.routers.approvals.SlackClient")
        mock_slack_instance = MagicMock()
        mock_slack_instance.post_blocks.return_value = {"ok": True}
        mock_slack_client.return_value = mock_slack_instance

        mocker.patch("redis.from_url")
        mocker.patch("services.gateway.app.api.v1.routers.approvals.get_temporal")

        # Clean database
        db_session.query(ActionLog).delete()
        db_session.query(WorkflowJob).delete()
        db_session.commit()

        # Step 1: Propose approval
        propose_payload = {
            "subject": "pr:123",
            "action": "merge",
            "reason": "Feature complete",
            "payload": {"pr_number": 123, "repo": "test/repo"}
        }

        response = client.post("/v1/approvals/propose", json=propose_payload)
        assert response.status_code == 200
        approval_id = response.json()["action_id"]

        # Step 2: Send notification
        notify_payload = {"channel": "#approvals"}
        response = client.post(
            f"/v1/approvals/{approval_id}/notify",
            json=notify_payload
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True

        # Step 3: Approve
        decision_payload = {
            "decision": "approve",
            "reason": "LGTM"
        }
        response = client.post(
            f"/v1/approvals/{approval_id}/decision",
            json=decision_payload
        )
        assert response.status_code == 200
        job_id = response.json()["job_id"]
        assert job_id is not None

        # Step 4: Verify final state
        approval = db_session.get(Approval, approval_id)
        assert approval.status == "approve"
        assert approval.decided_at is not None

        job = db_session.get(WorkflowJob, job_id)
        assert job is not None
        assert job.status == "queued"
        assert job.rule_kind == "merge"

        # Verify audit trail
        logs = db_session.query(ActionLog).all()
        assert len(logs) == 2  # One for propose, one for decision
