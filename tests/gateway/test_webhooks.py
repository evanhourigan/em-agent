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
