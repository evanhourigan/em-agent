"""
Tests for agent router.

Tests agent query routing, tool orchestration, and approval proposals.
Current coverage: 4% → Target: 30%+ (45+ lines)
"""
import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi import HTTPException
from fastapi.testclient import TestClient
import httpx


class TestRunAgentBasic:
    """Test /v1/agent/run basic functionality."""

    def test_run_agent_missing_query_raises_400(self, client):
        """Test that missing query raises 400."""
        response = client.post("/v1/agent/run", json={})

        assert response.status_code == 400
        assert "query required" in response.json()["detail"]

    def test_run_agent_empty_query_raises_400(self, client):
        """Test that empty query raises 400."""
        response = client.post("/v1/agent/run", json={"query": ""})

        assert response.status_code == 400
        assert "query required" in response.json()["detail"]

    def test_run_agent_whitespace_query_raises_400(self, client):
        """Test that whitespace-only query raises 400."""
        response = client.post("/v1/agent/run", json={"query": "   "})

        assert response.status_code == 400


class TestRunAgentSprintHealth:
    """Test agent routing for 'sprint health' queries."""

    def test_sprint_health_query_without_nudge(self, client):
        """Test sprint health query without nudge keyword."""
        with patch("services.gateway.app.api.v1.routers.agent.get_settings") as mock_settings:
            with patch("services.gateway.app.api.v1.routers.agent.httpx.Client") as mock_client_class:
                settings = Mock()
                settings.rag_url = "http://localhost:8001/rag"
                mock_settings.return_value = settings

                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"sprint_health": "good"}

                mock_client = MagicMock()
                mock_client.__enter__ = Mock(return_value=mock_client)
                mock_client.__exit__ = Mock(return_value=None)
                mock_client.post.return_value = mock_response

                mock_client_class.return_value = mock_client

                response = client.post("/v1/agent/run", json={"query": "sprint health"})

                assert response.status_code == 200
                data = response.json()
                assert "plan" in data
                assert "report" in data
                assert data["plan"][0]["tool"] == "reports.sprint_health"

    def test_sprint_health_with_nudge(self, client):
        """Test sprint health query with nudge keyword."""
        with patch("services.gateway.app.api.v1.routers.agent.get_settings") as mock_settings:
            with patch("services.gateway.app.api.v1.routers.agent.httpx.Client") as mock_client_class:
                settings = Mock()
                settings.rag_url = "http://localhost:8001/rag"
                mock_settings.return_value = settings

                mock_sprint_response = Mock()
                mock_sprint_response.status_code = 200
                mock_sprint_response.json.return_value = {"sprint_health": "good"}

                mock_signals_response = Mock()
                mock_signals_response.status_code = 200
                mock_signals_response.json.return_value = {
                    "results": {"pr_without_review": [{"delivery_id": "org/repo#123"}]}
                }

                mock_proposal_response = Mock()
                mock_proposal_response.status_code = 200
                mock_proposal_response.json.return_value = {"approval_id": 42, "status": "pending"}

                mock_client = MagicMock()
                mock_client.__enter__ = Mock(return_value=mock_client)
                mock_client.__exit__ = Mock(return_value=None)

                # Mock multiple POST calls
                mock_client.post.side_effect = [
                    mock_sprint_response,
                    mock_signals_response,
                    mock_proposal_response
                ]

                mock_client_class.return_value = mock_client

                response = client.post("/v1/agent/run", json={"query": "sprint health nudge"})

                assert response.status_code == 200
                data = response.json()
                assert "plan" in data
                assert "proposed" in data
                assert "candidates" in data
                assert len(data["plan"]) == 3  # sprint_health, signals, approvals


class TestRunAgentStaleQuery:
    """Test agent routing for 'stale' and 'triage' queries."""

    def test_stale_query(self, client):
        """Test stale PR query."""
        with patch("services.gateway.app.api.v1.routers.agent.get_settings") as mock_settings:
            with patch("services.gateway.app.api.v1.routers.agent.httpx.Client") as mock_client_class:
                settings = Mock()
                settings.rag_url = "http://localhost:8001/rag"
                mock_settings.return_value = settings

                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"stale_prs": [{"id": "PR#123"}]}

                mock_client = MagicMock()
                mock_client.__enter__ = Mock(return_value=mock_client)
                mock_client.__exit__ = Mock(return_value=None)
                mock_client.post.return_value = mock_response

                mock_client_class.return_value = mock_client

                response = client.post("/v1/agent/run", json={"query": "stale prs"})

                assert response.status_code == 200
                data = response.json()
                assert "plan" in data
                assert "result" in data
                assert data["plan"][0]["tool"] == "signals.evaluate"

    def test_triage_query(self, client):
        """Test triage query."""
        with patch("services.gateway.app.api.v1.routers.agent.get_settings") as mock_settings:
            with patch("services.gateway.app.api.v1.routers.agent.httpx.Client") as mock_client_class:
                settings = Mock()
                settings.rag_url = "http://localhost:8001/rag"
                mock_settings.return_value = settings

                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"stale_prs": []}

                mock_client = MagicMock()
                mock_client.__enter__ = Mock(return_value=mock_client)
                mock_client.__exit__ = Mock(return_value=None)
                mock_client.post.return_value = mock_response

                mock_client_class.return_value = mock_client

                response = client.post("/v1/agent/run", json={"query": "triage"})

                assert response.status_code == 200
                data = response.json()
                assert "plan" in data


class TestRunAgentLabelNoTicket:
    """Test agent routing for 'label no ticket' queries."""

    def test_label_no_ticket_query(self, client):
        """Test label PRs with no ticket link."""
        with patch("services.gateway.app.api.v1.routers.agent.get_settings") as mock_settings:
            with patch("services.gateway.app.api.v1.routers.agent.httpx.Client") as mock_client_class:
                settings = Mock()
                settings.rag_url = "http://localhost:8001/rag"
                mock_settings.return_value = settings

                mock_signals_response = Mock()
                mock_signals_response.status_code = 200
                mock_signals_response.json.return_value = {
                    "results": {"no_ticket_link": [{"delivery_id": "org/repo#123"}]}
                }

                mock_proposal_response = Mock()
                mock_proposal_response.status_code = 200
                mock_proposal_response.json.return_value = {"approval_id": 99, "status": "pending"}

                mock_client = MagicMock()
                mock_client.__enter__ = Mock(return_value=mock_client)
                mock_client.__exit__ = Mock(return_value=None)
                mock_client.post.side_effect = [mock_signals_response, mock_proposal_response]

                mock_client_class.return_value = mock_client

                response = client.post("/v1/agent/run", json={"query": "label no ticket"})

                assert response.status_code == 200
                data = response.json()
                assert "plan" in data
                assert "proposed" in data
                assert "candidates" in data
                assert len(data["plan"]) == 2  # signals, approvals


class TestRunAgentDefaultRAG:
    """Test agent default routing to RAG."""

    def test_default_rag_query(self, client):
        """Test that unrecognized queries default to RAG search."""
        with patch("services.gateway.app.api.v1.routers.agent.get_settings") as mock_settings:
            with patch("services.gateway.app.api.v1.routers.agent.httpx.Client") as mock_client_class:
                settings = Mock()
                settings.rag_url = "http://localhost:8001/rag"
                mock_settings.return_value = settings

                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"results": [{"doc": "answer"}]}

                mock_client = MagicMock()
                mock_client.__enter__ = Mock(return_value=mock_client)
                mock_client.__exit__ = Mock(return_value=None)
                mock_client.post.return_value = mock_response

                mock_client_class.return_value = mock_client

                response = client.post("/v1/agent/run", json={"query": "random question"})

                assert response.status_code == 200
                data = response.json()
                assert "plan" in data
                assert "result" in data
                assert data["plan"][0]["tool"] == "rag.search"


class TestRunAgentErrorHandling:
    """Test agent error handling."""

    def test_httpx_error_raises_502(self, client):
        """Test that httpx errors raise 502."""
        with patch("services.gateway.app.api.v1.routers.agent.get_settings") as mock_settings:
            with patch("services.gateway.app.api.v1.routers.agent.httpx.Client") as mock_client_class:
                settings = Mock()
                settings.rag_url = "http://localhost:8001/rag"
                mock_settings.return_value = settings

                mock_client = MagicMock()
                mock_client.__enter__ = Mock(return_value=mock_client)
                mock_client.__exit__ = Mock(return_value=None)
                mock_client.post.side_effect = httpx.ConnectError("Connection failed")

                mock_client_class.return_value = mock_client

                response = client.post("/v1/agent/run", json={"query": "sprint health"})

                assert response.status_code == 502
                assert "Connection failed" in response.json()["detail"]


class TestRunAgentSummarizePR:
    """Test agent PR summarization."""

    def test_summarize_pr_with_target(self, client):
        """Test PR summarization with target in query."""
        with patch("services.gateway.app.api.v1.routers.agent.get_settings") as mock_settings:
            with patch("services.gateway.app.api.v1.routers.agent.httpx.Client") as mock_client_class:
                settings = Mock()
                settings.rag_url = "http://localhost:8001/rag"
                mock_settings.return_value = settings

                mock_proposal_response = Mock()
                mock_proposal_response.status_code = 200
                mock_proposal_response.json.return_value = {"approval_id": 50, "status": "pending"}

                mock_client = MagicMock()
                mock_client.__enter__ = Mock(return_value=mock_client)
                mock_client.__exit__ = Mock(return_value=None)
                mock_client.post.return_value = mock_proposal_response

                mock_client_class.return_value = mock_client

                response = client.post("/v1/agent/run", json={"query": "summarize pr org/repo#456"})

                assert response.status_code == 200
                data = response.json()
                assert "plan" in data
                assert "proposed" in data
                assert data["target"] == "org/repo#456"

    def test_summarize_pr_without_target_raises_400(self, client):
        """Test PR summarization without target raises 400."""
        with patch("services.gateway.app.api.v1.routers.agent.get_settings") as mock_settings:
            with patch("services.gateway.app.api.v1.routers.agent.httpx.Client") as mock_client_class:
                settings = Mock()
                settings.rag_url = "http://localhost:8001/rag"
                mock_settings.return_value = settings

                mock_client = MagicMock()
                mock_client.__enter__ = Mock(return_value=mock_client)
                mock_client.__exit__ = Mock(return_value=None)

                mock_client_class.return_value = mock_client

                response = client.post("/v1/agent/run", json={"query": "summarize pr"})

                assert response.status_code == 400
                assert "target" in response.json()["detail"]
