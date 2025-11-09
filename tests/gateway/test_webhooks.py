"""Tests for webhooks endpoints."""

import hashlib
import hmac
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _compute_github_signature(secret: str, body: bytes) -> str:
    """Compute GitHub webhook signature."""
    mac = hmac.new(secret.encode("utf-8"), msg=body, digestmod=hashlib.sha256)
    return "sha256=" + mac.hexdigest()


class TestGitHubWebhook:
    """Tests for POST /webhooks/github endpoint."""

    def test_github_webhook_basic_success(self, client: TestClient, db_session: Session):
        """Test basic GitHub webhook reception."""
        from services.gateway.app.models.events import EventRaw

        # Clean events
        db_session.query(EventRaw).delete()
        db_session.commit()

        payload = {"action": "opened", "pull_request": {"id": 123}}
        headers = {
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "12345-67890-abcdef"
        }

        response = client.post(
            "/webhooks/github",
            json=payload,
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "id" in data

        # Verify event was stored
        event = db_session.query(EventRaw).filter_by(delivery_id="12345-67890-abcdef").first()
        assert event is not None
        assert event.source == "github"
        assert event.event_type == "pull_request"
        assert event.delivery_id == "12345-67890-abcdef"

    def test_github_webhook_duplicate_delivery(self, client: TestClient, db_session: Session):
        """Test that duplicate delivery IDs are rejected."""
        from services.gateway.app.models.events import EventRaw

        # Clean and create existing event
        db_session.query(EventRaw).delete()
        existing = EventRaw(
            source="github",
            event_type="pull_request",
            delivery_id="duplicate-123",
            payload=json.dumps({"test": "data"})
        )
        db_session.add(existing)
        db_session.commit()
        existing_id = existing.id

        # Try to send duplicate
        payload = {"action": "opened"}
        headers = {
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "duplicate-123"  # Duplicate
        }

        response = client.post(
            "/webhooks/github",
            json=payload,
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "duplicate"
        assert data["id"] == existing_id

        # Verify no new event was created
        count = db_session.query(EventRaw).filter_by(delivery_id="duplicate-123").count()
        assert count == 1

    def test_github_webhook_without_delivery_id(self, client: TestClient, db_session: Session):
        """Test webhook without X-GitHub-Delivery header."""
        from services.gateway.app.models.events import EventRaw

        # Clean events
        db_session.query(EventRaw).delete()
        db_session.commit()

        payload = {"action": "opened"}
        headers = {"X-GitHub-Event": "pull_request"}

        response = client.post(
            "/webhooks/github",
            json=payload,
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

        # Event stored with empty delivery_id
        event = db_session.query(EventRaw).filter_by(source="github").first()
        assert event is not None
        assert event.delivery_id == ""

    def test_github_webhook_without_event_type(self, client: TestClient, db_session: Session):
        """Test webhook without X-GitHub-Event header."""
        from services.gateway.app.models.events import EventRaw

        # Clean events
        db_session.query(EventRaw).delete()
        db_session.commit()

        payload = {"action": "test"}
        headers = {"X-GitHub-Delivery": "test-123"}

        response = client.post(
            "/webhooks/github",
            json=payload,
            headers=headers
        )
        assert response.status_code == 200

        # Event stored with "unknown" event_type
        event = db_session.query(EventRaw).filter_by(delivery_id="test-123").first()
        assert event is not None
        assert event.event_type == "unknown"

    @pytest.mark.skip(
        reason="Signature verification requires app.state.github_webhook_secret configuration"
    )
    def test_github_webhook_valid_signature(self, client: TestClient, db_session: Session):
        """Test webhook with valid HMAC signature.

        TODO: Requires setting app.state.github_webhook_secret in test setup.
        """
        from services.gateway.app.models.events import EventRaw

        db_session.query(EventRaw).delete()
        db_session.commit()

        secret = "test-secret"
        payload = {"action": "opened"}
        body = json.dumps(payload).encode("utf-8")
        signature = _compute_github_signature(secret, body)

        headers = {
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "signed-123",
            "X-Hub-Signature-256": signature
        }

        # Would need to configure client app state with github_webhook_secret
        response = client.post(
            "/webhooks/github",
            json=payload,
            headers=headers
        )
        assert response.status_code == 200

    @pytest.mark.skip(
        reason="Signature verification requires app.state.github_webhook_secret configuration"
    )
    def test_github_webhook_invalid_signature(self, client: TestClient):
        """Test webhook with invalid HMAC signature returns 401.

        TODO: Requires setting app.state.github_webhook_secret in test setup.
        """
        payload = {"action": "opened"}
        headers = {
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "invalid-sig-123",
            "X-Hub-Signature-256": "sha256=invalid_signature_here"
        }

        response = client.post(
            "/webhooks/github",
            json=payload,
            headers=headers
        )
        assert response.status_code == 401
        assert "invalid signature" in response.json()["detail"]

    def test_github_webhook_stores_headers(self, client: TestClient, db_session: Session):
        """Test that webhook stores request headers."""
        from services.gateway.app.models.events import EventRaw

        db_session.query(EventRaw).delete()
        db_session.commit()

        payload = {"test": "data"}
        headers = {
            "X-GitHub-Event": "push",
            "X-GitHub-Delivery": "headers-test-123",
            "Custom-Header": "custom-value"
        }

        response = client.post(
            "/webhooks/github",
            json=payload,
            headers=headers
        )
        assert response.status_code == 200

        event = db_session.query(EventRaw).filter_by(delivery_id="headers-test-123").first()
        assert event is not None
        assert event.headers is not None
        assert isinstance(event.headers, dict)
        # Check that our custom header was stored
        assert "custom-header" in str(event.headers).lower()

    def test_github_webhook_stores_payload(self, client: TestClient, db_session: Session):
        """Test that webhook stores the full payload."""
        from services.gateway.app.models.events import EventRaw

        db_session.query(EventRaw).delete()
        db_session.commit()

        payload = {"action": "opened", "number": 42, "title": "Test PR"}
        headers = {
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "payload-test-123"
        }

        response = client.post(
            "/webhooks/github",
            json=payload,
            headers=headers
        )
        assert response.status_code == 200

        event = db_session.query(EventRaw).filter_by(delivery_id="payload-test-123").first()
        assert event is not None
        assert event.payload is not None
        # Payload should contain our test data
        assert "opened" in event.payload
        assert "42" in event.payload or 42 in json.loads(event.payload)


class TestGitHubIssuesWebhook:
    """Tests for GitHub Issues events via POST /webhooks/github endpoint."""

    def test_github_issues_opened_event(self, client: TestClient, db_session: Session):
        """Test GitHub issues 'opened' event."""
        from services.gateway.app.models.events import EventRaw

        # Clean events
        db_session.query(EventRaw).delete()
        db_session.commit()

        payload = {
            "action": "opened",
            "issue": {
                "number": 42,
                "title": "Add authentication feature",
                "state": "open",
                "labels": [{"name": "feature"}],
                "assignee": {"login": "alice"}
            },
            "repository": {
                "name": "em-agent",
                "owner": {"login": "evanhourigan"}
            }
        }
        headers = {
            "X-GitHub-Event": "issues",
            "X-GitHub-Delivery": "issues-opened-123"
        }

        response = client.post(
            "/webhooks/github",
            json=payload,
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "id" in data

        # Verify event was stored
        event = db_session.query(EventRaw).filter_by(delivery_id="issues-opened-123").first()
        assert event is not None
        assert event.source == "github"
        assert event.event_type == "issues"
        assert event.delivery_id == "issues-opened-123"

        # Verify payload contains issue data
        assert "42" in event.payload or 42 in json.loads(event.payload).get("issue", {}).get("number", 0)
        assert "authentication" in event.payload.lower()

    def test_github_issues_closed_event(self, client: TestClient, db_session: Session):
        """Test GitHub issues 'closed' event."""
        from services.gateway.app.models.events import EventRaw

        db_session.query(EventRaw).delete()
        db_session.commit()

        payload = {
            "action": "closed",
            "issue": {
                "number": 42,
                "title": "Add authentication feature",
                "state": "closed"
            },
            "repository": {
                "name": "em-agent",
                "owner": {"login": "evanhourigan"}
            }
        }
        headers = {
            "X-GitHub-Event": "issues",
            "X-GitHub-Delivery": "issues-closed-123"
        }

        response = client.post(
            "/webhooks/github",
            json=payload,
            headers=headers
        )
        assert response.status_code == 200

        event = db_session.query(EventRaw).filter_by(delivery_id="issues-closed-123").first()
        assert event is not None
        assert event.event_type == "issues"

        # Verify action is in payload
        payload_data = json.loads(event.payload)
        assert payload_data["action"] == "closed"
        assert payload_data["issue"]["state"] == "closed"

    def test_github_issues_labeled_event(self, client: TestClient, db_session: Session):
        """Test GitHub issues 'labeled' event."""
        from services.gateway.app.models.events import EventRaw

        db_session.query(EventRaw).delete()
        db_session.commit()

        payload = {
            "action": "labeled",
            "issue": {
                "number": 42,
                "title": "Fix login bug",
                "labels": [{"name": "bug"}, {"name": "priority-high"}]
            },
            "label": {"name": "bug"}
        }
        headers = {
            "X-GitHub-Event": "issues",
            "X-GitHub-Delivery": "issues-labeled-123"
        }

        response = client.post(
            "/webhooks/github",
            json=payload,
            headers=headers
        )
        assert response.status_code == 200

        event = db_session.query(EventRaw).filter_by(delivery_id="issues-labeled-123").first()
        assert event is not None
        assert event.event_type == "issues"
        assert "bug" in event.payload

    def test_github_issues_assigned_event(self, client: TestClient, db_session: Session):
        """Test GitHub issues 'assigned' event."""
        from services.gateway.app.models.events import EventRaw

        db_session.query(EventRaw).delete()
        db_session.commit()

        payload = {
            "action": "assigned",
            "issue": {
                "number": 42,
                "assignee": {"login": "alice"}
            },
            "assignee": {"login": "alice"}
        }
        headers = {
            "X-GitHub-Event": "issues",
            "X-GitHub-Delivery": "issues-assigned-123"
        }

        response = client.post(
            "/webhooks/github",
            json=payload,
            headers=headers
        )
        assert response.status_code == 200

        event = db_session.query(EventRaw).filter_by(delivery_id="issues-assigned-123").first()
        assert event is not None
        assert "alice" in event.payload


class TestJiraWebhook:
    """Tests for POST /webhooks/jira endpoint."""

    def test_jira_webhook_basic_success(self, client: TestClient, db_session: Session):
        """Test basic Jira webhook reception."""
        from services.gateway.app.models.events import EventRaw

        # Clean events
        db_session.query(EventRaw).delete()
        db_session.commit()

        payload = {"webhookEvent": "jira:issue_created", "issue": {"id": "10000"}}
        headers = {"X-Atlassian-Webhook-Identifier": "jira-webhook-123"}

        response = client.post(
            "/webhooks/jira",
            json=payload,
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "id" in data

        # Verify event was stored
        event = db_session.query(EventRaw).filter_by(delivery_id="jira-webhook-123").first()
        assert event is not None
        assert event.source == "jira"
        assert event.event_type == "unknown"  # Jira doesn't extract event_type
        assert event.delivery_id == "jira-webhook-123"

    def test_jira_webhook_duplicate_delivery(self, client: TestClient, db_session: Session):
        """Test that duplicate Jira webhook identifiers are rejected."""
        from services.gateway.app.models.events import EventRaw

        # Clean and create existing event
        db_session.query(EventRaw).delete()
        existing = EventRaw(
            source="jira",
            event_type="unknown",
            delivery_id="jira-duplicate-456",
            payload=json.dumps({"test": "data"})
        )
        db_session.add(existing)
        db_session.commit()
        existing_id = existing.id

        # Try to send duplicate
        payload = {"webhookEvent": "jira:issue_updated"}
        headers = {"X-Atlassian-Webhook-Identifier": "jira-duplicate-456"}

        response = client.post(
            "/webhooks/jira",
            json=payload,
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "duplicate"
        assert data["id"] == existing_id

        # Verify no new event was created
        count = db_session.query(EventRaw).filter_by(delivery_id="jira-duplicate-456").count()
        assert count == 1

    def test_jira_webhook_without_identifier(self, client: TestClient, db_session: Session):
        """Test Jira webhook without X-Atlassian-Webhook-Identifier header."""
        from services.gateway.app.models.events import EventRaw

        # Clean events
        db_session.query(EventRaw).delete()
        db_session.commit()

        payload = {"webhookEvent": "jira:issue_created"}

        response = client.post(
            "/webhooks/jira",
            json=payload
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

        # Event stored with empty delivery_id
        event = db_session.query(EventRaw).filter_by(source="jira").first()
        assert event is not None
        assert event.delivery_id == ""

    def test_jira_webhook_stores_payload(self, client: TestClient, db_session: Session):
        """Test that Jira webhook stores the full payload."""
        from services.gateway.app.models.events import EventRaw

        db_session.query(EventRaw).delete()
        db_session.commit()

        payload = {
            "webhookEvent": "jira:issue_created",
            "issue": {"id": "10001", "key": "PROJ-123"}
        }
        headers = {"X-Atlassian-Webhook-Identifier": "jira-payload-test"}

        response = client.post(
            "/webhooks/jira",
            json=payload,
            headers=headers
        )
        assert response.status_code == 200

        event = db_session.query(EventRaw).filter_by(delivery_id="jira-payload-test").first()
        assert event is not None
        assert event.payload is not None
        # Payload should contain our test data
        assert "PROJ-123" in event.payload

    def test_jira_webhook_no_signature_field(self, client: TestClient, db_session: Session):
        """Test that Jira webhooks have null signature."""
        from services.gateway.app.models.events import EventRaw

        db_session.query(EventRaw).delete()
        db_session.commit()

        payload = {"test": "data"}
        headers = {"X-Atlassian-Webhook-Identifier": "jira-sig-test"}

        response = client.post(
            "/webhooks/jira",
            json=payload,
            headers=headers
        )
        assert response.status_code == 200

        event = db_session.query(EventRaw).filter_by(delivery_id="jira-sig-test").first()
        assert event is not None
        assert event.signature is None  # Jira webhooks don't have signatures


class TestLinearWebhook:
    """Tests for POST /webhooks/linear endpoint."""

    def test_linear_webhook_issue_create(self, client: TestClient, db_session: Session):
        """Test Linear issue create event."""
        from services.gateway.app.models.events import EventRaw

        # Clean events
        db_session.query(EventRaw).delete()
        db_session.commit()

        payload = {
            "action": "create",
            "type": "Issue",
            "data": {
                "id": "abc-123",
                "identifier": "ENG-42",
                "title": "Add authentication",
                "description": "Implement OAuth2 flow",
                "state": {"id": "state-123", "name": "In Progress"},
                "team": {"id": "team-123", "name": "Engineering"},
                "assignee": {"id": "user-123", "name": "Alice"}
            },
            "url": "https://linear.app/issue/ENG-42",
            "createdAt": "2025-11-09T10:00:00.000Z"
        }
        headers = {"Linear-Signature": "sha256=test"}

        response = client.post(
            "/webhooks/linear",
            json=payload,
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "id" in data

        # Verify event was stored
        event = db_session.query(EventRaw).filter_by(source="linear").first()
        assert event is not None
        assert event.source == "linear"
        assert event.event_type == "Issue:create"
        assert "linear-Issue-create-abc-123" in event.delivery_id

        # Verify payload contains issue data
        assert "ENG-42" in event.payload
        assert "authentication" in event.payload.lower()

    def test_linear_webhook_issue_update(self, client: TestClient, db_session: Session):
        """Test Linear issue update event."""
        from services.gateway.app.models.events import EventRaw

        db_session.query(EventRaw).delete()
        db_session.commit()

        payload = {
            "action": "update",
            "type": "Issue",
            "data": {
                "id": "def-456",
                "identifier": "ENG-43",
                "title": "Fix bug in login",
                "state": {"name": "Done"}
            },
            "url": "https://linear.app/issue/ENG-43"
        }

        response = client.post(
            "/webhooks/linear",
            json=payload
        )
        assert response.status_code == 200

        event = db_session.query(EventRaw).filter_by(source="linear").first()
        assert event is not None
        assert event.event_type == "Issue:update"
        assert "Done" in event.payload

    def test_linear_webhook_comment_create(self, client: TestClient, db_session: Session):
        """Test Linear comment create event."""
        from services.gateway.app.models.events import EventRaw

        db_session.query(EventRaw).delete()
        db_session.commit()

        payload = {
            "action": "create",
            "type": "Comment",
            "data": {
                "id": "comment-789",
                "body": "This looks good!",
                "issue": {"id": "issue-123", "identifier": "ENG-42"}
            }
        }

        response = client.post(
            "/webhooks/linear",
            json=payload
        )
        assert response.status_code == 200

        event = db_session.query(EventRaw).filter_by(source="linear").first()
        assert event is not None
        assert event.event_type == "Comment:create"
        assert "looks good" in event.payload.lower()

    def test_linear_webhook_duplicate_delivery(self, client: TestClient, db_session: Session):
        """Test that duplicate Linear webhook deliveries are rejected."""
        from services.gateway.app.models.events import EventRaw

        # Clean and create existing event
        db_session.query(EventRaw).delete()
        payload_data = json.dumps({
            "action": "create",
            "type": "Issue",
            "data": {"id": "duplicate-123"}
        })
        existing = EventRaw(
            source="linear",
            event_type="Issue:create",
            delivery_id="linear-Issue-create-duplicate-123",
            payload=payload_data
        )
        db_session.add(existing)
        db_session.commit()
        existing_id = existing.id

        # Try to send duplicate
        payload = {
            "action": "create",
            "type": "Issue",
            "data": {"id": "duplicate-123"}
        }

        response = client.post(
            "/webhooks/linear",
            json=payload
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "duplicate"
        assert data["id"] == existing_id

        # Verify no new event was created
        count = db_session.query(EventRaw).filter_by(
            delivery_id="linear-Issue-create-duplicate-123"
        ).count()
        assert count == 1

    def test_linear_webhook_without_data(self, client: TestClient, db_session: Session):
        """Test Linear webhook with malformed payload uses fallback delivery_id."""
        from services.gateway.app.models.events import EventRaw

        db_session.query(EventRaw).delete()
        db_session.commit()

        # Malformed payload (no data field)
        payload = {"action": "create"}

        response = client.post(
            "/webhooks/linear",
            json=payload
        )
        assert response.status_code == 200

        # Should create event with timestamp-based delivery_id
        event = db_session.query(EventRaw).filter_by(source="linear").first()
        assert event is not None
        assert event.delivery_id.startswith("linear-")
        assert event.event_type == "unknown:create"  # Type is unknown, but action is parsed

    def test_linear_webhook_stores_payload(self, client: TestClient, db_session: Session):
        """Test that Linear webhook stores the full payload."""
        from services.gateway.app.models.events import EventRaw

        db_session.query(EventRaw).delete()
        db_session.commit()

        payload = {
            "action": "update",
            "type": "Issue",
            "data": {
                "id": "payload-test",
                "identifier": "ENG-99",
                "title": "Test payload storage",
                "priority": 1
            }
        }

        response = client.post(
            "/webhooks/linear",
            json=payload
        )
        assert response.status_code == 200

        event = db_session.query(EventRaw).filter_by(source="linear").first()
        assert event is not None
        assert event.payload is not None
        # Payload should contain our test data
        assert "ENG-99" in event.payload
        assert "payload-test" in event.payload


class TestPagerDutyWebhook:
    """Tests for POST /webhooks/pagerduty endpoint."""

    def test_pagerduty_webhook_incident_triggered(self, client: TestClient, db_session: Session):
        """Test PagerDuty incident.triggered event."""
        from services.gateway.app.models.events import EventRaw

        # Clean events
        db_session.query(EventRaw).delete()
        db_session.commit()

        payload = {
            "event": {
                "id": "event-123",
                "event_type": "incident.triggered",
                "resource_type": "incident",
                "occurred_at": "2025-11-09T10:00:00Z",
                "data": {
                    "id": "P123ABC",
                    "incident_number": 42,
                    "title": "Database high CPU usage",
                    "status": "triggered",
                    "urgency": "high",
                    "service": {
                        "summary": "Production Database"
                    }
                }
            }
        }
        headers = {"X-PagerDuty-Signature": "sha256=test"}

        response = client.post(
            "/webhooks/pagerduty",
            json=payload,
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "id" in data

        # Verify event was stored
        event = db_session.query(EventRaw).filter_by(source="pagerduty").first()
        assert event is not None
        assert event.source == "pagerduty"
        assert event.event_type == "incident.triggered"
        assert "pagerduty-incident.triggered-P123ABC" in event.delivery_id

        # Verify payload contains incident data
        assert "P123ABC" in event.payload
        assert "Database" in event.payload

    def test_pagerduty_webhook_incident_resolved(self, client: TestClient, db_session: Session):
        """Test PagerDuty incident.resolved event."""
        from services.gateway.app.models.events import EventRaw

        db_session.query(EventRaw).delete()
        db_session.commit()

        payload = {
            "event": {
                "event_type": "incident.resolved",
                "data": {
                    "id": "P456DEF",
                    "incident_number": 43,
                    "title": "API latency resolved",
                    "status": "resolved"
                }
            }
        }

        response = client.post(
            "/webhooks/pagerduty",
            json=payload
        )
        assert response.status_code == 200

        event = db_session.query(EventRaw).filter_by(source="pagerduty").first()
        assert event is not None
        assert event.event_type == "incident.resolved"
        assert "resolved" in event.payload

    def test_pagerduty_webhook_incident_acknowledged(self, client: TestClient, db_session: Session):
        """Test PagerDuty incident.acknowledged event."""
        from services.gateway.app.models.events import EventRaw

        db_session.query(EventRaw).delete()
        db_session.commit()

        payload = {
            "event": {
                "event_type": "incident.acknowledged",
                "data": {
                    "id": "P789GHI",
                    "incident_number": 44,
                    "title": "Memory leak detected",
                    "assignments": [
                        {"assignee": {"summary": "Alice (On-Call)"}}
                    ]
                }
            }
        }

        response = client.post(
            "/webhooks/pagerduty",
            json=payload
        )
        assert response.status_code == 200

        event = db_session.query(EventRaw).filter_by(source="pagerduty").first()
        assert event is not None
        assert event.event_type == "incident.acknowledged"
        assert "Alice" in event.payload

    def test_pagerduty_webhook_duplicate_delivery(self, client: TestClient, db_session: Session):
        """Test that duplicate PagerDuty webhook deliveries are rejected."""
        from services.gateway.app.models.events import EventRaw

        # Clean and create existing event
        db_session.query(EventRaw).delete()
        payload_data = json.dumps({
            "event": {
                "event_type": "incident.triggered",
                "data": {"id": "PDUPLICATE"}
            }
        })
        existing = EventRaw(
            source="pagerduty",
            event_type="incident.triggered",
            delivery_id="pagerduty-incident.triggered-PDUPLICATE",
            payload=payload_data
        )
        db_session.add(existing)
        db_session.commit()
        existing_id = existing.id

        # Try to send duplicate
        payload = {
            "event": {
                "event_type": "incident.triggered",
                "data": {"id": "PDUPLICATE"}
            }
        }

        response = client.post(
            "/webhooks/pagerduty",
            json=payload
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "duplicate"
        assert data["id"] == existing_id

        # Verify no new event was created
        count = db_session.query(EventRaw).filter_by(
            delivery_id="pagerduty-incident.triggered-PDUPLICATE"
        ).count()
        assert count == 1

    def test_pagerduty_webhook_without_event_data(self, client: TestClient, db_session: Session):
        """Test PagerDuty webhook with malformed payload uses fallback delivery_id."""
        from services.gateway.app.models.events import EventRaw

        db_session.query(EventRaw).delete()
        db_session.commit()

        # Malformed payload (no event field)
        payload = {"something": "else"}

        response = client.post(
            "/webhooks/pagerduty",
            json=payload
        )
        assert response.status_code == 200

        # Should create event with timestamp-based delivery_id
        event = db_session.query(EventRaw).filter_by(source="pagerduty").first()
        assert event is not None
        assert event.delivery_id.startswith("pagerduty-")
        assert event.event_type == "unknown"

    def test_pagerduty_webhook_stores_payload(self, client: TestClient, db_session: Session):
        """Test that PagerDuty webhook stores the full payload."""
        from services.gateway.app.models.events import EventRaw

        db_session.query(EventRaw).delete()
        db_session.commit()

        payload = {
            "event": {
                "event_type": "incident.escalated",
                "data": {
                    "id": "PTEST999",
                    "incident_number": 999,
                    "title": "Test payload storage",
                    "urgency": "high",
                    "priority": {"summary": "P1"}
                }
            }
        }

        response = client.post(
            "/webhooks/pagerduty",
            json=payload
        )
        assert response.status_code == 200

        event = db_session.query(EventRaw).filter_by(source="pagerduty").first()
        assert event is not None
        assert event.payload is not None
        # Payload should contain our test data
        assert "PTEST999" in event.payload
        assert "999" in event.payload or 999 in json.loads(event.payload).get("event", {}).get("data", {}).get("incident_number", 0)
