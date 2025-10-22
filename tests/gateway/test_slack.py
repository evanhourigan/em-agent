"""
Tests for Slack commands router.

Tests Slack command parsing, signature verification, and command handlers.
Current coverage: 3% → Target: 30%+ (150+ lines)
"""
import os
import hashlib
import hmac
import json
import time
import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi import HTTPException
from fastapi.testclient import TestClient

from services.gateway.app.api.v1.routers.slack import _verify_slack


class TestVerifySlack:
    """Test _verify_slack signature verification."""

    def test_verify_slack_signing_not_required(self):
        """Test that verification is skipped when signing not required."""
        with patch("services.gateway.app.api.v1.routers.slack.get_settings") as mock_settings:
            settings = Mock()
            settings.slack_signing_required = False
            mock_settings.return_value = settings

            mock_request = Mock()
            # Should not raise
            _verify_slack(mock_request, b"body", "123456789", "v0=abc123")

    def test_verify_slack_missing_secret_raises_401(self):
        """Test that missing signing secret raises 401."""
        with patch("services.gateway.app.api.v1.routers.slack.get_settings") as mock_settings:
            settings = Mock()
            settings.slack_signing_required = True
            settings.slack_signing_secret = None
            mock_settings.return_value = settings

            mock_request = Mock()

            with pytest.raises(HTTPException) as exc_info:
                _verify_slack(mock_request, b"body", "123456789", "v0=abc123")

            assert exc_info.value.status_code == 401
            assert "slack signing secret not set" in exc_info.value.detail

    def test_verify_slack_missing_headers_raises_401(self):
        """Test that missing timestamp or signature raises 401."""
        with patch("services.gateway.app.api.v1.routers.slack.get_settings") as mock_settings:
            settings = Mock()
            settings.slack_signing_required = True
            settings.slack_signing_secret = "test-secret"
            mock_settings.return_value = settings

            mock_request = Mock()

            # Missing timestamp
            with pytest.raises(HTTPException) as exc_info:
                _verify_slack(mock_request, b"body", None, "v0=abc123")
            assert exc_info.value.status_code == 401
            assert "missing slack headers" in exc_info.value.detail

            # Missing signature
            with pytest.raises(HTTPException) as exc_info:
                _verify_slack(mock_request, b"body", "123456789", None)
            assert exc_info.value.status_code == 401

    def test_verify_slack_bad_timestamp_raises_401(self):
        """Test that non-numeric timestamp raises 401."""
        with patch("services.gateway.app.api.v1.routers.slack.get_settings") as mock_settings:
            settings = Mock()
            settings.slack_signing_required = True
            settings.slack_signing_secret = "test-secret"
            mock_settings.return_value = settings

            mock_request = Mock()

            with pytest.raises(HTTPException) as exc_info:
                _verify_slack(mock_request, b"body", "not-a-number", "v0=abc123")

            assert exc_info.value.status_code == 401
            assert "bad timestamp" in exc_info.value.detail

    def test_verify_slack_old_timestamp_raises_401(self):
        """Test that old timestamp (>5 min) raises 401."""
        with patch("services.gateway.app.api.v1.routers.slack.get_settings") as mock_settings:
            settings = Mock()
            settings.slack_signing_required = True
            settings.slack_signing_secret = "test-secret"
            mock_settings.return_value = settings

            mock_request = Mock()

            # Timestamp from 10 minutes ago
            old_ts = str(int(time.time()) - 600)

            with pytest.raises(HTTPException) as exc_info:
                _verify_slack(mock_request, b"body", old_ts, "v0=abc123")

            assert exc_info.value.status_code == 401
            assert "timestamp too old" in exc_info.value.detail

    def test_verify_slack_invalid_signature_raises_401(self):
        """Test that invalid signature raises 401."""
        with patch("services.gateway.app.api.v1.routers.slack.get_settings") as mock_settings:
            settings = Mock()
            settings.slack_signing_required = True
            settings.slack_signing_secret = "test-secret"
            mock_settings.return_value = settings

            mock_request = Mock()
            ts = str(int(time.time()))
            body = b"test body"

            # Invalid signature
            with pytest.raises(HTTPException) as exc_info:
                _verify_slack(mock_request, body, ts, "v0=invalid_signature")

            assert exc_info.value.status_code == 401
            assert "invalid signature" in exc_info.value.detail

    def test_verify_slack_valid_signature_passes(self):
        """Test that valid signature passes verification."""
        with patch("services.gateway.app.api.v1.routers.slack.get_settings") as mock_settings:
            settings = Mock()
            settings.slack_signing_required = True
            settings.slack_signing_secret = "test-secret"
            mock_settings.return_value = settings

            mock_request = Mock()
            ts = str(int(time.time()))
            body = b"test body"

            # Compute valid signature
            basestring = f"v0:{ts}:{body.decode()}".encode()
            mac = hmac.new(settings.slack_signing_secret.encode(), basestring, hashlib.sha256)
            valid_sig = f"v0={mac.hexdigest()}"

            # Should not raise
            _verify_slack(mock_request, body, ts, valid_sig)


class TestSlackCommands:
    """Test /v1/slack/commands endpoint."""

    def test_commands_empty_text_returns_usage(self, client):
        """Test that empty command text returns usage message."""
        with patch("services.gateway.app.api.v1.routers.slack.get_settings") as mock_settings:
            settings = Mock()
            settings.slack_signing_required = False
            mock_settings.return_value = settings

            # Empty payload
            response = client.post(
                "/v1/slack/commands",
                content=b"text=",
                headers={"content-type": "application/x-www-form-urlencoded"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert "Usage" in data["message"]

    def test_commands_no_text_returns_usage(self, client):
        """Test that missing text field returns usage message."""
        with patch("services.gateway.app.api.v1.routers.slack.get_settings") as mock_settings:
            settings = Mock()
            settings.slack_signing_required = False
            mock_settings.return_value = settings

            response = client.post(
                "/v1/slack/commands",
                content=b"user_id=U123",
                headers={"content-type": "application/x-www-form-urlencoded"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert "Usage" in data["message"]

    def test_commands_parses_form_encoded_payload(self, client):
        """Test that commands endpoint parses form-encoded payload."""
        with patch("services.gateway.app.api.v1.routers.slack.get_settings") as mock_settings:
            with patch("services.gateway.app.api.v1.routers.slack.get_sessionmaker") as mock_sessionmaker:
                with patch("services.gateway.app.api.v1.routers.slack._evaluate_rule") as mock_eval:
                    settings = Mock()
                    settings.slack_signing_required = False
                    mock_settings.return_value = settings

                    mock_session = Mock()
                    mock_sessionmaker.return_value.return_value.__enter__.return_value = mock_session
                    mock_sessionmaker.return_value.return_value.__exit__.return_value = None

                    mock_eval.return_value = []

                    response = client.post(
                        "/v1/slack/commands",
                        content=b"text=signals+stale_pr",
                        headers={"content-type": "application/x-www-form-urlencoded"}
                    )

                    assert response.status_code == 200

    def test_commands_parses_json_payload(self, client):
        """Test that commands endpoint parses JSON payload."""
        with patch("services.gateway.app.api.v1.routers.slack.get_settings") as mock_settings:
            with patch("services.gateway.app.api.v1.routers.slack.get_sessionmaker") as mock_sessionmaker:
                with patch("services.gateway.app.api.v1.routers.slack._evaluate_rule") as mock_eval:
                    settings = Mock()
                    settings.slack_signing_required = False
                    mock_settings.return_value = settings

                    mock_session = Mock()
                    mock_sessionmaker.return_value.return_value.__enter__.return_value = mock_session
                    mock_sessionmaker.return_value.return_value.__exit__.return_value = None

                    mock_eval.return_value = []

                    response = client.post(
                        "/v1/slack/commands",
                        json={"text": "signals stale_pr"},
                        headers={"content-type": "application/json"}
                    )

                    assert response.status_code == 200


class TestSlackSignalsCommand:
    """Test 'signals' command."""

    def test_signals_command_default_kinds(self, client):
        """Test signals command with default kinds."""
        with patch("services.gateway.app.api.v1.routers.slack.get_settings") as mock_settings:
            with patch("services.gateway.app.api.v1.routers.slack.get_sessionmaker") as mock_sessionmaker:
                with patch("services.gateway.app.api.v1.routers.slack._evaluate_rule") as mock_eval:
                    settings = Mock()
                    settings.slack_signing_required = False
                    mock_settings.return_value = settings

                    mock_session = Mock()
                    mock_sessionmaker.return_value.return_value.__enter__.return_value = mock_session
                    mock_sessionmaker.return_value.return_value.__exit__.return_value = None

                    # Mock results for different kinds
                    def eval_side_effect(session, rule):
                        kind = rule["kind"]
                        if kind == "stale_pr":
                            return [{"delivery_id": "org/repo#123"}]
                        elif kind == "wip_limit_exceeded":
                            return []
                        else:
                            return [{"subject": "test"}]

                    mock_eval.side_effect = eval_side_effect

                    response = client.post(
                        "/v1/slack/commands",
                        content=b"text=signals",
                        headers={"content-type": "application/x-www-form-urlencoded"}
                    )

                    assert response.status_code == 200
                    data = response.json()
                    assert data["ok"] is True
                    # Should evaluate all 3 default kinds
                    assert "stale_pr" in data["message"]
                    assert "wip_limit_exceeded" in data["message"]
                    assert "pr_without_review" in data["message"]

    def test_signals_command_specific_kind(self, client):
        """Test signals command with specific kind."""
        with patch("services.gateway.app.api.v1.routers.slack.get_settings") as mock_settings:
            with patch("services.gateway.app.api.v1.routers.slack.get_sessionmaker") as mock_sessionmaker:
                with patch("services.gateway.app.api.v1.routers.slack._evaluate_rule") as mock_eval:
                    settings = Mock()
                    settings.slack_signing_required = False
                    mock_settings.return_value = settings

                    mock_session = Mock()
                    mock_sessionmaker.return_value.return_value.__enter__.return_value = mock_session
                    mock_sessionmaker.return_value.return_value.__exit__.return_value = None

                    mock_eval.return_value = [
                        {"delivery_id": "org/repo#123"},
                        {"delivery_id": "org/repo#124"}
                    ]

                    response = client.post(
                        "/v1/slack/commands",
                        content=b"text=signals+stale_pr",
                        headers={"content-type": "application/x-www-form-urlencoded"}
                    )

                    assert response.status_code == 200
                    data = response.json()
                    assert data["ok"] is True
                    assert "stale_pr: 2 found" in data["message"]

    def test_signals_command_handles_eval_error(self, client):
        """Test signals command handles evaluation error."""
        with patch("services.gateway.app.api.v1.routers.slack.get_settings") as mock_settings:
            with patch("services.gateway.app.api.v1.routers.slack.get_sessionmaker") as mock_sessionmaker:
                with patch("services.gateway.app.api.v1.routers.slack._evaluate_rule") as mock_eval:
                    settings = Mock()
                    settings.slack_signing_required = False
                    mock_settings.return_value = settings

                    mock_session = Mock()
                    mock_sessionmaker.return_value.return_value.__enter__.return_value = mock_session
                    mock_sessionmaker.return_value.return_value.__exit__.return_value = None

                    # Simulate error
                    mock_eval.side_effect = HTTPException(status_code=400, detail="Invalid rule")

                    response = client.post(
                        "/v1/slack/commands",
                        content=b"text=signals+bad_kind",
                        headers={"content-type": "application/x-www-form-urlencoded"}
                    )

                    assert response.status_code == 200
                    data = response.json()
                    assert data["ok"] is True
                    assert "error" in data["message"]


class TestSlackApprovalsCommand:
    """Test 'approvals' command."""

    def test_approvals_command_no_pending(self, client, db_session):
        """Test approvals command with no pending approvals."""
        with patch("services.gateway.app.api.v1.routers.slack.get_settings") as mock_settings:
            with patch("services.gateway.app.api.v1.routers.slack.get_sessionmaker") as mock_sessionmaker:
                settings = Mock()
                settings.slack_signing_required = False
                mock_settings.return_value = settings

                mock_sessionmaker.return_value.return_value.__enter__.return_value = db_session
                mock_sessionmaker.return_value.return_value.__exit__.return_value = None

                response = client.post(
                    "/v1/slack/commands",
                    content=b"text=approvals",
                    headers={"content-type": "application/x-www-form-urlencoded"}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["ok"] is True
                assert "No pending approvals" in data["message"]


class TestSlackApproveDeclineCommand:
    """Test 'approve' and 'decline' commands."""

    def test_approve_command_success(self, client):
        """Test approve command with valid approval ID."""
        with patch("services.gateway.app.api.v1.routers.slack.get_settings") as mock_settings:
            with patch("services.gateway.app.api.v1.routers.slack.approvals_decide") as mock_decide:
                settings = Mock()
                settings.slack_signing_required = False
                mock_settings.return_value = settings

                mock_decide.return_value = {"status": "approved", "job_id": "workflow-123"}

                response = client.post(
                    "/v1/slack/commands",
                    content=b"text=approve+42",
                    headers={"content-type": "application/x-www-form-urlencoded"}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["ok"] is True
                assert "approval #42 approved" in data["message"]
                assert "job_id=workflow-123" in data["message"]
                mock_decide.assert_called_once_with(42, {"decision": "approve", "reason": "slack"})

    def test_decline_command_success(self, client):
        """Test decline command with valid approval ID."""
        with patch("services.gateway.app.api.v1.routers.slack.get_settings") as mock_settings:
            with patch("services.gateway.app.api.v1.routers.slack.approvals_decide") as mock_decide:
                settings = Mock()
                settings.slack_signing_required = False
                mock_settings.return_value = settings

                mock_decide.return_value = {"status": "declined"}

                response = client.post(
                    "/v1/slack/commands",
                    content=b"text=decline+99",
                    headers={"content-type": "application/x-www-form-urlencoded"}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["ok"] is True
                assert "approval #99 declined" in data["message"]
                mock_decide.assert_called_once_with(99, {"decision": "decline", "reason": "slack"})

    def test_approve_command_invalid_format_returns_usage(self, client):
        """Test approve command with invalid format returns usage."""
        with patch("services.gateway.app.api.v1.routers.slack.get_settings") as mock_settings:
            settings = Mock()
            settings.slack_signing_required = False
            mock_settings.return_value = settings

            # Missing approval ID - falls through to usage message
            response = client.post(
                "/v1/slack/commands",
                content=b"text=approve",
                headers={"content-type": "application/x-www-form-urlencoded"}
            )

            assert response.status_code == 200
            assert "Usage" in response.json()["message"]

    def test_approve_command_non_numeric_id_raises_400(self, client):
        """Test approve command with non-numeric ID raises 400."""
        with patch("services.gateway.app.api.v1.routers.slack.get_settings") as mock_settings:
            settings = Mock()
            settings.slack_signing_required = False
            mock_settings.return_value = settings

            response = client.post(
                "/v1/slack/commands",
                content=b"text=approve+abc",
                headers={"content-type": "application/x-www-form-urlencoded"}
            )

            assert response.status_code == 400


class TestSlackApprovalsPostCommand:
    """Test 'approvals post' command."""

    def test_approvals_post_with_pending(self, client, db_session):
        """Test approvals post command with pending approvals."""
        from services.gateway.app.models.approvals import Approval

        with patch("services.gateway.app.api.v1.routers.slack.get_settings") as mock_settings:
            with patch("services.gateway.app.api.v1.routers.slack.get_sessionmaker") as mock_sessionmaker:
                with patch("services.gateway.app.services.slack_client.SlackClient") as mock_slack:
                    settings = Mock()
                    settings.slack_signing_required = False
                    mock_settings.return_value = settings

                    # Create mock approvals
                    approval1 = Approval(id=1, action="deploy", subject="v1.0.0", status="pending")
                    approval2 = Approval(id=2, action="merge", subject="PR#123", status="pending")

                    mock_query = Mock()
                    mock_filter = Mock()
                    mock_order = Mock()
                    mock_limit = Mock()

                    mock_query.filter.return_value = mock_filter
                    mock_filter.order_by.return_value = mock_order
                    mock_order.limit.return_value = mock_limit
                    mock_limit.all.return_value = [approval1, approval2]

                    mock_session = Mock()
                    mock_session.query.return_value = mock_query

                    mock_sessionmaker.return_value.return_value.__enter__.return_value = mock_session
                    mock_sessionmaker.return_value.return_value.__exit__.return_value = None

                    mock_slack_instance = Mock()
                    mock_slack_instance.post_blocks.return_value = {"ok": True, "ts": "123.456"}
                    mock_slack.return_value = mock_slack_instance

                    response = client.post(
                        "/v1/slack/commands",
                        content=b"text=approvals+post+%23channel",
                        headers={"content-type": "application/x-www-form-urlencoded"}
                    )

                    assert response.status_code == 200
                    data = response.json()
                    assert data["ok"] is True
                    assert "posted" in data
                    mock_slack_instance.post_blocks.assert_called_once()

    def test_approvals_post_no_pending(self, client, db_session):
        """Test approvals post command with no pending approvals."""
        with patch("services.gateway.app.api.v1.routers.slack.get_settings") as mock_settings:
            with patch("services.gateway.app.api.v1.routers.slack.get_sessionmaker") as mock_sessionmaker:
                settings = Mock()
                settings.slack_signing_required = False
                mock_settings.return_value = settings

                mock_query = Mock()
                mock_filter = Mock()
                mock_order = Mock()
                mock_limit = Mock()

                mock_query.filter.return_value = mock_filter
                mock_filter.order_by.return_value = mock_order
                mock_order.limit.return_value = mock_limit
                mock_limit.all.return_value = []

                mock_session = Mock()
                mock_session.query.return_value = mock_query

                mock_sessionmaker.return_value.return_value.__enter__.return_value = mock_session
                mock_sessionmaker.return_value.return_value.__exit__.return_value = None

                response = client.post(
                    "/v1/slack/commands",
                    content=b"text=approvals+post",
                    headers={"content-type": "application/x-www-form-urlencoded"}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["ok"] is True
                assert "No pending approvals" in data["message"]


class TestSlackStandupCommand:
    """Test 'standup' command."""

    def test_standup_command_default_hours(self, client):
        """Test standup command with default 48 hours."""
        with patch("services.gateway.app.api.v1.routers.slack.get_settings") as mock_settings:
            with patch("services.gateway.app.api.v1.routers.slack.get_sessionmaker") as mock_sessionmaker:
                with patch("services.gateway.app.api.v1.routers.slack.build_standup") as mock_build:
                    settings = Mock()
                    settings.slack_signing_required = False
                    mock_settings.return_value = settings

                    mock_session = Mock()
                    mock_sessionmaker.return_value.return_value.__enter__.return_value = mock_session
                    mock_sessionmaker.return_value.return_value.__exit__.return_value = None

                    mock_build.return_value = {
                        "stale_pr_count": 5,
                        "stale_pr_top": ["PR#123", "PR#124"],
                        "wip_open_prs": 10,
                        "pr_without_review_count": 3,
                        "deployments_last_24h": 2
                    }

                    response = client.post(
                        "/v1/slack/commands",
                        content=b"text=standup",
                        headers={"content-type": "application/x-www-form-urlencoded"}
                    )

                    assert response.status_code == 200
                    data = response.json()
                    assert data["ok"] is True
                    assert "stale_prs:5" in data["message"]
                    assert "wip:10" in data["message"]

    def test_standup_command_custom_hours(self, client):
        """Test standup command with custom hours."""
        with patch("services.gateway.app.api.v1.routers.slack.get_settings") as mock_settings:
            with patch("services.gateway.app.api.v1.routers.slack.get_sessionmaker") as mock_sessionmaker:
                with patch("services.gateway.app.api.v1.routers.slack.build_standup") as mock_build:
                    settings = Mock()
                    settings.slack_signing_required = False
                    mock_settings.return_value = settings

                    mock_session = Mock()
                    mock_sessionmaker.return_value.return_value.__enter__.return_value = mock_session
                    mock_sessionmaker.return_value.return_value.__exit__.return_value = None

                    mock_build.return_value = {
                        "stale_pr_count": 0,
                        "stale_pr_top": [],
                        "wip_open_prs": 0,
                        "pr_without_review_count": 0,
                        "deployments_last_24h": 0
                    }

                    response = client.post(
                        "/v1/slack/commands",
                        content=b"text=standup+24",
                        headers={"content-type": "application/x-www-form-urlencoded"}
                    )

                    assert response.status_code == 200
                    # Should call build_standup with 24
                    mock_build.assert_called_once_with(mock_session, 24)
