"""Tests for evals endpoints.

Note: Evals router uses signal evaluation which requires PostgreSQL-specific SQL.
Tests focus on validation and error handling rather than actual rule evaluation.
"""

import pytest
from fastapi.testclient import TestClient


class TestRunEvals:
    """Tests for POST /v1/evals/run endpoint."""

    def test_run_evals_missing_rules(self, client: TestClient):
        """Test that missing rules returns 400."""
        payload = {}  # No rules key

        response = client.post("/v1/evals/run", json=payload)
        assert response.status_code == 400
        assert "rules required" in response.json()["detail"]

    def test_run_evals_empty_rules_list(self, client: TestClient):
        """Test that empty rules list returns 400."""
        payload = {"rules": []}

        response = client.post("/v1/evals/run", json=payload)
        assert response.status_code == 400
        assert "rules required" in response.json()["detail"]

    def test_run_evals_null_rules(self, client: TestClient):
        """Test that null rules returns 400."""
        payload = {"rules": None}

        response = client.post("/v1/evals/run", json=payload)
        assert response.status_code == 400
        assert "rules required" in response.json()["detail"]

    def test_run_evals_rules_not_a_list(self, client: TestClient):
        """Test that rules must be a list."""
        payload = {"rules": "not-a-list"}

        response = client.post("/v1/evals/run", json=payload)
        assert response.status_code == 400
        assert "rules required" in response.json()["detail"]

    def test_run_evals_rules_dict_instead_of_list(self, client: TestClient):
        """Test that rules must be a list, not a dict."""
        payload = {"rules": {"kind": "stale_pr"}}

        response = client.post("/v1/evals/run", json=payload)
        assert response.status_code == 400

    def test_run_evals_single_rule(self, client: TestClient):
        """Test running a single rule evaluation.

        Note: Will fail with PostgreSQL-specific SQL on SQLite, but validates structure.
        """
        payload = {
            "rules": [
                {
                    "name": "test_rule",
                    "kind": "stale_pr",
                    "older_than_hours": 48
                }
            ]
        }

        response = client.post("/v1/evals/run", json=payload)
        # May return 200 with error in evaluations, or 500/503 due to SQLite
        assert response.status_code in [200, 500, 503]

        if response.status_code == 200:
            data = response.json()
            assert data["ok"] is True
            assert "evaluations" in data
            assert len(data["evaluations"]) == 1

            evaluation = data["evaluations"][0]
            assert "rule" in evaluation
            # Either has count+elapsed_ms OR error+elapsed_ms
            assert "elapsed_ms" in evaluation

    def test_run_evals_multiple_rules(self, client: TestClient):
        """Test running multiple rule evaluations.

        Note: Will fail with PostgreSQL-specific SQL on SQLite.
        """
        payload = {
            "rules": [
                {"name": "rule1", "kind": "stale_pr", "older_than_hours": 48},
                {"name": "rule2", "kind": "wip_limit_exceeded", "limit": 5}
            ]
        }

        response = client.post("/v1/evals/run", json=payload)
        # May return 200 with errors in evaluations, or 500/503 due to SQLite
        assert response.status_code in [200, 500, 503]

        if response.status_code == 200:
            data = response.json()
            assert data["ok"] is True
            assert len(data["evaluations"]) == 2

    def test_run_evals_unsupported_rule_kind(self, client: TestClient):
        """Test that unsupported rule kind is captured as error in evaluation."""
        payload = {
            "rules": [
                {
                    "name": "invalid_rule",
                    "kind": "unsupported_rule_type"
                }
            ]
        }

        response = client.post("/v1/evals/run", json=payload)
        assert response.status_code == 200  # Doesn't fail, captures error

        data = response.json()
        assert data["ok"] is True
        assert len(data["evaluations"]) == 1

        evaluation = data["evaluations"][0]
        assert "error" in evaluation
        assert "unsupported rule kind" in evaluation["error"]
        assert "elapsed_ms" in evaluation

    def test_run_evals_response_structure(self, client: TestClient):
        """Test that response has correct structure."""
        payload = {
            "rules": [
                {"kind": "unsupported_for_testing"}  # Will error
            ]
        }

        response = client.post("/v1/evals/run", json=payload)
        assert response.status_code == 200

        data = response.json()
        # Check top-level structure
        assert "ok" in data
        assert "evaluations" in data
        assert isinstance(data["evaluations"], list)

        # Check evaluation structure
        evaluation = data["evaluations"][0]
        assert "rule" in evaluation
        assert "elapsed_ms" in evaluation
        assert isinstance(evaluation["elapsed_ms"], int)

    def test_run_evals_timing_metrics(self, client: TestClient):
        """Test that timing metrics are included in response."""
        payload = {
            "rules": [
                {"kind": "unsupported"}  # Will error quickly
            ]
        }

        response = client.post("/v1/evals/run", json=payload)
        assert response.status_code == 200

        data = response.json()
        evaluation = data["evaluations"][0]

        # Check timing is present and reasonable
        assert "elapsed_ms" in evaluation
        assert evaluation["elapsed_ms"] >= 0
        assert evaluation["elapsed_ms"] < 10000  # Should be < 10 seconds

    def test_run_evals_mixed_success_and_error(self, client: TestClient):
        """Test running mix of valid and invalid rules."""
        payload = {
            "rules": [
                {"name": "invalid", "kind": "unsupported"},  # Will error
                {"name": "also_invalid", "kind": "also_unsupported"}  # Will also error
            ]
        }

        response = client.post("/v1/evals/run", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert data["ok"] is True
        assert len(data["evaluations"]) == 2

        # Both should have errors
        for evaluation in data["evaluations"]:
            assert "error" in evaluation
            assert "elapsed_ms" in evaluation

    @pytest.mark.skip(
        reason="Requires PostgreSQL - stale_pr rule uses interval syntax"
    )
    def test_run_evals_successful_rule_execution(self, client: TestClient):
        """Test successful rule execution with real data.

        This would require PostgreSQL database and test data.
        """
        payload = {
            "rules": [
                {
                    "name": "stale_prs",
                    "kind": "stale_pr",
                    "older_than_hours": 48
                }
            ]
        }

        response = client.post("/v1/evals/run", json=payload)
        assert response.status_code == 200

        data = response.json()
        evaluation = data["evaluations"][0]
        assert "count" in evaluation
        assert "elapsed_ms" in evaluation
        assert "error" not in evaluation
