"""Tests for policy endpoints."""

import pytest
from fastapi.testclient import TestClient


class TestEvaluatePolicy:
    """Tests for POST /v1/policy/evaluate endpoint."""

    def test_evaluate_policy_missing_kind(self, client: TestClient):
        """Test that missing kind returns 400."""
        payload = {}  # No kind

        response = client.post("/v1/policy/evaluate", json=payload)
        assert response.status_code == 400
        assert "missing kind" in response.json()["detail"]

    def test_evaluate_policy_none_kind(self, client: TestClient):
        """Test that None kind returns 400."""
        payload = {"kind": None}

        response = client.post("/v1/policy/evaluate", json=payload)
        assert response.status_code == 400

    def test_evaluate_policy_empty_kind(self, client: TestClient):
        """Test that empty kind returns 400."""
        payload = {"kind": ""}

        response = client.post("/v1/policy/evaluate", json=payload)
        assert response.status_code == 400

    def test_evaluate_policy_unknown_rule_kind(self, client: TestClient):
        """Test that unknown rule kind allows by default."""
        payload = {"kind": "unknown_rule_type"}

        response = client.post("/v1/policy/evaluate", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["allow"] is True
        assert "no policy" in data["reason"]

    def test_evaluate_policy_stale_pr_default(self, client: TestClient):
        """Test stale_pr rule with default policy."""
        payload = {"kind": "stale_pr"}

        response = client.post("/v1/policy/evaluate", json=payload)
        assert response.status_code == 200
        data = response.json()

        # Default policy: stale_pr has action "nudge" (not "block")
        assert "allow" in data
        assert data["allow"] is True  # nudge != block
        assert data["action"] == "nudge"
        assert "policy" in data
        assert data["policy"]["threshold_hours"] == 48

    def test_evaluate_policy_wip_limit_exceeded_default(self, client: TestClient):
        """Test wip_limit_exceeded rule with default policy."""
        payload = {"kind": "wip_limit_exceeded"}

        response = client.post("/v1/policy/evaluate", json=payload)
        assert response.status_code == 200
        data = response.json()

        # Default policy: wip_limit_exceeded has action "escalate"
        assert data["allow"] is True  # escalate != block
        assert data["action"] == "escalate"
        assert "policy" in data
        assert data["policy"]["limit"] == 5

    def test_evaluate_policy_no_ticket_link_default(self, client: TestClient):
        """Test no_ticket_link rule with default policy."""
        payload = {"kind": "no_ticket_link"}

        response = client.post("/v1/policy/evaluate", json=payload)
        assert response.status_code == 200
        data = response.json()

        # Default policy: no_ticket_link has action "nudge"
        assert data["allow"] is True  # nudge != block
        assert data["action"] == "nudge"

    def test_evaluate_policy_with_additional_fields(self, client: TestClient):
        """Test that additional fields in payload are accepted."""
        payload = {
            "kind": "stale_pr",
            "pr_id": 123,
            "hours_open": 72,
            "author": "john@example.com"
        }

        response = client.post("/v1/policy/evaluate", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["allow"] is True

    def test_evaluate_policy_response_structure(self, client: TestClient):
        """Test that response has expected structure."""
        payload = {"kind": "stale_pr"}

        response = client.post("/v1/policy/evaluate", json=payload)
        assert response.status_code == 200
        data = response.json()

        # Check required fields
        assert "allow" in data
        assert "action" in data
        assert isinstance(data["allow"], bool)
        assert isinstance(data["action"], str)

    @pytest.mark.skip(
        reason="Requires OPA server configuration via settings.opa_url"
    )
    def test_evaluate_policy_with_opa(self, client: TestClient):
        """Test policy evaluation using OPA server.

        TODO: Requires OPA server running and settings.opa_url configured.
        Would test:
        - OPA decision endpoint integration
        - Fallback to YAML if OPA fails
        - OPA response parsing
        """
        payload = {"kind": "stale_pr"}

        response = client.post("/v1/policy/evaluate", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "opa" in data
        assert data["opa"] is True

    @pytest.mark.skip(
        reason="Requires policy.yml file at POLICY_PATH"
    )
    def test_evaluate_policy_custom_yaml(self, client: TestClient):
        """Test policy evaluation using custom YAML file.

        TODO: Requires POLICY_PATH environment variable and policy.yml file.
        Would test:
        - YAML policy loading
        - Custom rule configurations
        - File not found fallback to defaults
        """
        payload = {"kind": "custom_rule"}

        response = client.post("/v1/policy/evaluate", json=payload)
        assert response.status_code == 200

    @pytest.mark.skip(
        reason="Requires custom policy with block action"
    )
    def test_evaluate_policy_block_action(self, client: TestClient):
        """Test that action=block results in allow=false.

        TODO: Would require custom policy with action: "block".
        Default policies use "nudge" or "escalate", never "block".
        """
        # Would need custom policy like:
        # dangerous_operation: {"action": "block"}
        payload = {"kind": "dangerous_operation"}

        response = client.post("/v1/policy/evaluate", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["allow"] is False
        assert data["action"] == "block"
