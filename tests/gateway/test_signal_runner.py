"""
Tests for signal_runner service.

Tests the signal evaluation and background evaluation service.
Current coverage: 31% → Target: 70%+
"""
import os
import pytest
from unittest.mock import Mock, patch, mock_open, MagicMock
import threading

from services.gateway.app.services.signal_runner import (
    _load_rules,
    evaluate_and_log,
    EvaluatorThread,
    maybe_start_evaluator,
    DEFAULT_RULES,
)


class TestLoadRules:
    """Test _load_rules function."""

    def test_load_rules_file_not_exists_returns_defaults(self):
        """Test that _load_rules returns default rules when file doesn't exist."""
        with patch("os.path.exists", return_value=False):
            rules = _load_rules()

            assert rules == DEFAULT_RULES
            assert len(rules) == 3
            assert rules[0]["kind"] == "stale_pr"
            assert rules[1]["kind"] == "wip_limit_exceeded"
            assert rules[2]["kind"] == "pr_without_review"

    def test_load_rules_from_file(self):
        """Test loading rules from YAML file."""
        yaml_content = """
- name: custom_rule
  kind: stale_pr
  older_than_hours: 72
- name: another_rule
  kind: wip_limit_exceeded
  limit: 10
"""
        with patch("os.path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=yaml_content)):
                rules = _load_rules()

                assert len(rules) == 2
                assert rules[0]["name"] == "custom_rule"
                assert rules[0]["older_than_hours"] == 72
                assert rules[1]["limit"] == 10

    def test_load_rules_empty_file_returns_empty_list(self):
        """Test that empty YAML file returns empty list."""
        with patch("os.path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data="")):
                rules = _load_rules()

                # Empty YAML returns empty list, not defaults
                assert rules == []

    def test_load_rules_invalid_yaml_returns_defaults(self):
        """Test that invalid YAML returns default rules."""
        invalid_yaml = "{ this is not: valid yaml ]["
        with patch("os.path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=invalid_yaml)):
                rules = _load_rules()

                assert rules == DEFAULT_RULES

    def test_load_rules_non_list_yaml_returns_defaults(self):
        """Test that non-list YAML structure returns defaults."""
        yaml_content = """
not_a_list: true
some_key: some_value
"""
        with patch("os.path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=yaml_content)):
                rules = _load_rules()

                assert rules == DEFAULT_RULES

    def test_load_rules_respects_environment_variable(self):
        """Test that RULES_PATH environment variable is respected."""
        custom_path = "/custom/path/rules.yml"
        yaml_content = "- name: test\n  kind: stale_pr"

        with patch.dict(os.environ, {"RULES_PATH": custom_path}):
            with patch("os.path.exists", return_value=True):
                with patch("builtins.open", mock_open(read_data=yaml_content)) as mock_file:
                    rules = _load_rules()

                    # Verify it tried to open the custom path
                    mock_file.assert_called_once()
                    assert len(rules) == 1

    def test_load_rules_exception_during_read_returns_defaults(self):
        """Test that exceptions during file read return defaults."""
        with patch("os.path.exists", return_value=True):
            with patch("builtins.open", side_effect=IOError("Permission denied")):
                rules = _load_rules()

                assert rules == DEFAULT_RULES


class TestEvaluateAndLog:
    """Test evaluate_and_log function."""

    def test_evaluate_and_log_with_no_results(self):
        """Test evaluate_and_log when rules return no results."""
        mock_session = Mock()

        with patch("services.gateway.app.services.signal_runner._evaluate_rule") as mock_eval:
            with patch("services.gateway.app.services.signal_runner._load_policy") as mock_policy:
                mock_eval.return_value = []  # No results
                mock_policy.return_value = {}

                rules = [{"name": "test_rule", "kind": "stale_pr"}]
                count = evaluate_and_log(mock_session, rules)

                assert count == 0
                mock_session.add.assert_not_called()
                mock_session.commit.assert_called_once()

    def test_evaluate_and_log_with_results(self):
        """Test evaluate_and_log creates ActionLog and WorkflowJob entries."""
        mock_session = Mock()

        with patch("services.gateway.app.services.signal_runner._evaluate_rule") as mock_eval:
            with patch("services.gateway.app.services.signal_runner._load_policy") as mock_policy:
                # Mock rule results
                mock_eval.return_value = [
                    {"delivery_id": "org/repo#123", "title": "Test PR"},
                    {"delivery_id": "org/repo#124", "title": "Another PR"},
                ]
                mock_policy.return_value = {"stale_pr": {"action": "nudge"}}

                rules = [{"name": "stale48h", "kind": "stale_pr", "older_than_hours": 48}]
                count = evaluate_and_log(mock_session, rules)

                assert count == 2
                # Should add 2 ActionLog + 2 WorkflowJob = 4 entries
                assert mock_session.add.call_count == 4
                mock_session.commit.assert_called_once()

    def test_evaluate_and_log_uses_default_rules_when_none_provided(self):
        """Test that evaluate_and_log uses default rules when none provided."""
        mock_session = Mock()

        with patch("services.gateway.app.services.signal_runner._evaluate_rule") as mock_eval:
            with patch("services.gateway.app.services.signal_runner._load_policy") as mock_policy:
                with patch("services.gateway.app.services.signal_runner._load_rules") as mock_load:
                    mock_eval.return_value = []
                    mock_policy.return_value = {}
                    mock_load.return_value = DEFAULT_RULES

                    evaluate_and_log(mock_session, rules=None)

                    mock_load.assert_called_once()

    def test_evaluate_and_log_handles_missing_delivery_id(self):
        """Test that evaluate_and_log handles results without delivery_id."""
        mock_session = Mock()

        with patch("services.gateway.app.services.signal_runner._evaluate_rule") as mock_eval:
            with patch("services.gateway.app.services.signal_runner._load_policy") as mock_policy:
                # Result without delivery_id
                mock_eval.return_value = [{"pr_id": "12345", "no_delivery_id": True}]
                mock_policy.return_value = {"test": {"action": "block"}}

                rules = [{"name": "test", "kind": "test"}]
                count = evaluate_and_log(mock_session, rules)

                assert count == 1
                # Should still create entries with stringified result as subject
                assert mock_session.add.call_count == 2

    def test_evaluate_and_log_uses_rule_kind_as_default_name(self):
        """Test that rule kind is used as name when name is missing."""
        mock_session = Mock()

        with patch("services.gateway.app.services.signal_runner._evaluate_rule") as mock_eval:
            with patch("services.gateway.app.services.signal_runner._load_policy") as mock_policy:
                mock_eval.return_value = [{"delivery_id": "test#1"}]
                mock_policy.return_value = {"stale_pr": {"action": "nudge"}}

                # Rule without name, only kind
                rules = [{"kind": "stale_pr", "older_than_hours": 24}]
                count = evaluate_and_log(mock_session, rules)

                assert count == 1

    def test_evaluate_and_log_uses_default_action_when_policy_missing(self):
        """Test that default 'nudge' action is used when policy doesn't specify action."""
        mock_session = Mock()

        with patch("services.gateway.app.services.signal_runner._evaluate_rule") as mock_eval:
            with patch("services.gateway.app.services.signal_runner._load_policy") as mock_policy:
                mock_eval.return_value = [{"delivery_id": "test#1"}]
                # Policy doesn't have an action defined
                mock_policy.return_value = {"unknown_kind": {}}

                rules = [{"name": "test", "kind": "unknown_kind"}]
                count = evaluate_and_log(mock_session, rules)

                assert count == 1
                # Check that ActionLog was created (can't easily inspect its action field)
                assert mock_session.add.call_count == 2

    def test_evaluate_and_log_handles_event_bus_publish_failure(self):
        """Test that event bus publish failure doesn't crash evaluate_and_log."""
        mock_session = Mock()

        with patch("services.gateway.app.services.signal_runner._evaluate_rule") as mock_eval:
            with patch("services.gateway.app.services.signal_runner._load_policy") as mock_policy:
                with patch("services.gateway.app.services.signal_runner.get_event_bus") as mock_bus:
                    mock_eval.return_value = []
                    mock_policy.return_value = {}
                    # Simulate asyncio.create_task failing
                    mock_bus.return_value.publish_json.side_effect = Exception("No event loop")

                    rules = [{"kind": "test"}]
                    # Should not raise
                    count = evaluate_and_log(mock_session, rules)

                    assert count == 0


class TestEvaluatorThread:
    """Test EvaluatorThread class."""

    def test_evaluator_thread_initialization(self):
        """Test EvaluatorThread initializes correctly."""
        mock_factory = Mock()

        thread = EvaluatorThread(mock_factory, interval_sec=300)

        assert thread._session_factory == mock_factory
        assert thread._interval == 300
        assert thread.daemon is True
        assert isinstance(thread._stop, threading.Event)

    def test_evaluator_thread_stop(self):
        """Test that stop() sets the stop event."""
        mock_factory = Mock()

        thread = EvaluatorThread(mock_factory, interval_sec=60)
        thread.stop()

        assert thread._stop.is_set()

    def test_evaluator_thread_is_daemon(self):
        """Test that EvaluatorThread is created as daemon thread."""
        mock_factory = Mock()

        thread = EvaluatorThread(mock_factory, interval_sec=60)

        assert thread.daemon is True

    # Note: run() method is marked pragma: no cover, so we don't test the actual loop


class TestMaybeStartEvaluator:
    """Test maybe_start_evaluator function."""

    def test_maybe_start_evaluator_disabled_returns_none(self):
        """Test that evaluator is not started when disabled."""
        mock_app = Mock()
        mock_factory = Mock()

        with patch.dict(os.environ, {"EVALUATOR_ENABLED": "false"}):
            result = maybe_start_evaluator(mock_app, mock_factory)

            assert result is None

    def test_maybe_start_evaluator_enabled_starts_thread(self):
        """Test that evaluator starts when enabled."""
        mock_app = Mock()
        mock_factory = Mock()

        with patch.dict(os.environ, {"EVALUATOR_ENABLED": "true", "EVALUATOR_INTERVAL_SEC": "120"}):
            with patch("services.gateway.app.services.signal_runner.EvaluatorThread.start") as mock_start:
                result = maybe_start_evaluator(mock_app, mock_factory)

                assert result is not None
                assert isinstance(result, EvaluatorThread)
                assert result._interval == 120
                mock_start.assert_called_once()
                assert hasattr(mock_app.state, "evaluator_thread")

    def test_maybe_start_evaluator_respects_yes_value(self):
        """Test that 'yes' is recognized as enabled."""
        mock_app = Mock()
        mock_factory = Mock()

        with patch.dict(os.environ, {"EVALUATOR_ENABLED": "yes"}):
            with patch("services.gateway.app.services.signal_runner.EvaluatorThread.start"):
                result = maybe_start_evaluator(mock_app, mock_factory)

                assert result is not None

    def test_maybe_start_evaluator_respects_1_value(self):
        """Test that '1' is recognized as enabled."""
        mock_app = Mock()
        mock_factory = Mock()

        with patch.dict(os.environ, {"EVALUATOR_ENABLED": "1"}):
            with patch("services.gateway.app.services.signal_runner.EvaluatorThread.start"):
                result = maybe_start_evaluator(mock_app, mock_factory)

                assert result is not None

    def test_maybe_start_evaluator_case_insensitive(self):
        """Test that enable check is case-insensitive."""
        mock_app = Mock()
        mock_factory = Mock()

        with patch.dict(os.environ, {"EVALUATOR_ENABLED": "TRUE"}):
            with patch("services.gateway.app.services.signal_runner.EvaluatorThread.start"):
                result = maybe_start_evaluator(mock_app, mock_factory)

                assert result is not None

    def test_maybe_start_evaluator_uses_default_interval(self):
        """Test that default interval is 600 seconds."""
        mock_app = Mock()
        mock_factory = Mock()

        with patch.dict(os.environ, {"EVALUATOR_ENABLED": "true"}, clear=True):
            # Don't set EVALUATOR_INTERVAL_SEC, should use default
            with patch("services.gateway.app.services.signal_runner.EvaluatorThread.start"):
                result = maybe_start_evaluator(mock_app, mock_factory)

                assert result._interval == 600

    def test_maybe_start_evaluator_custom_interval(self):
        """Test custom interval from environment variable."""
        mock_app = Mock()
        mock_factory = Mock()

        with patch.dict(os.environ, {"EVALUATOR_ENABLED": "true", "EVALUATOR_INTERVAL_SEC": "1800"}):
            with patch("services.gateway.app.services.signal_runner.EvaluatorThread.start"):
                result = maybe_start_evaluator(mock_app, mock_factory)

                assert result._interval == 1800

    def test_maybe_start_evaluator_logs_startup(self):
        """Test that evaluator logs when started."""
        mock_app = Mock()
        mock_factory = Mock()

        with patch.dict(os.environ, {"EVALUATOR_ENABLED": "true"}):
            with patch("services.gateway.app.services.signal_runner.EvaluatorThread.start"):
                with patch("services.gateway.app.services.signal_runner.get_logger") as mock_logger:
                    mock_log_instance = Mock()
                    mock_logger.return_value = mock_log_instance

                    maybe_start_evaluator(mock_app, mock_factory)

                    # Should have logged the startup
                    mock_log_instance.info.assert_called()


class TestDefaultRules:
    """Test default rules constant."""

    def test_default_rules_structure(self):
        """Test that DEFAULT_RULES has expected structure."""
        assert len(DEFAULT_RULES) == 3

        # First rule: stale PRs
        assert DEFAULT_RULES[0]["name"] == "stale48h"
        assert DEFAULT_RULES[0]["kind"] == "stale_pr"
        assert DEFAULT_RULES[0]["older_than_hours"] == 48

        # Second rule: WIP limit
        assert DEFAULT_RULES[1]["name"] == "wip_limit"
        assert DEFAULT_RULES[1]["kind"] == "wip_limit_exceeded"
        assert DEFAULT_RULES[1]["limit"] == 5

        # Third rule: PR without review
        assert DEFAULT_RULES[2]["name"] == "pr_no_review"
        assert DEFAULT_RULES[2]["kind"] == "pr_without_review"
        assert DEFAULT_RULES[2]["older_than_hours"] == 12
