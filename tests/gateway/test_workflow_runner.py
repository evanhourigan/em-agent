"""
Tests for workflow_runner service.

Tests the workflow job processing and retention background services.
Current coverage: 34% → Target: 70%+
"""
import os
import pytest
from unittest.mock import Mock, patch, MagicMock
import threading

from services.gateway.app.services.workflow_runner import (
    WorkflowRunner,
    RetentionRunner,
    maybe_start_workflow_runner,
    maybe_stop_workflow_runner,
    maybe_start_retention,
    maybe_stop_retention,
)


class TestWorkflowRunner:
    """Test WorkflowRunner class."""

    def test_workflow_runner_initialization(self):
        """Test WorkflowRunner initializes correctly."""
        mock_factory = Mock()

        runner = WorkflowRunner(mock_factory, interval_sec=30)

        assert runner._session_factory == mock_factory
        assert runner._interval == 30
        assert runner.daemon is True
        assert isinstance(runner._stop, threading.Event)

    def test_workflow_runner_default_interval(self):
        """Test WorkflowRunner uses default interval."""
        mock_factory = Mock()

        runner = WorkflowRunner(mock_factory)

        assert runner._interval == 10

    def test_workflow_runner_stop(self):
        """Test that stop() sets the stop event."""
        mock_factory = Mock()

        runner = WorkflowRunner(mock_factory, interval_sec=60)
        runner.stop()

        assert runner._stop.is_set()

    def test_workflow_runner_is_daemon(self):
        """Test that WorkflowRunner is created as daemon thread."""
        mock_factory = Mock()

        runner = WorkflowRunner(mock_factory)

        assert runner.daemon is True


class TestWorkflowRunnerProcessBatch:
    """Test WorkflowRunner._process_batch method."""

    def test_process_batch_no_jobs(self):
        """Test _process_batch when no jobs are queued."""
        mock_factory = Mock()
        mock_session = Mock()

        # Mock query to return empty list
        mock_query = Mock()
        mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        mock_session.query.return_value = mock_query

        runner = WorkflowRunner(mock_factory)
        runner._process_batch(mock_session)

        # Should not commit when no jobs processed
        mock_session.commit.assert_not_called()

    def test_process_batch_processes_queued_jobs(self):
        """Test _process_batch processes queued jobs."""
        mock_factory = Mock()
        mock_session = Mock()

        # Create mock jobs
        job1 = Mock(id=1, rule_kind="stale_pr", status="queued")
        job2 = Mock(id=2, rule_kind="wip_limit", status="queued")

        # Mock query to return jobs
        mock_query = Mock()
        mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [job1, job2]
        mock_session.query.return_value = mock_query

        runner = WorkflowRunner(mock_factory)

        with patch("services.gateway.app.services.workflow_runner.get_logger") as mock_logger:
            mock_log_instance = Mock()
            mock_logger.return_value = mock_log_instance

            runner = WorkflowRunner(mock_factory)
            runner._process_batch(mock_session)

        # Jobs should be marked as done
        assert job1.status == "done"
        assert job2.status == "done"

        # Should commit after processing
        mock_session.commit.assert_called_once()

        # Should log the count
        mock_log_instance.info.assert_called_once_with("workflow_runner.processed", count=2)

    def test_process_batch_limits_to_25_jobs(self):
        """Test _process_batch respects 25 job limit."""
        mock_factory = Mock()
        mock_session = Mock()

        # Mock query chain
        mock_query = Mock()
        mock_filter = Mock()
        mock_order = Mock()
        mock_limit = Mock()

        mock_query.filter.return_value = mock_filter
        mock_filter.order_by.return_value = mock_order
        mock_order.limit.return_value = mock_limit
        mock_limit.all.return_value = []

        mock_session.query.return_value = mock_query

        runner = WorkflowRunner(mock_factory)
        runner._process_batch(mock_session)

        # Verify limit was called with 25
        mock_order.limit.assert_called_once_with(25)

    def test_process_batch_with_opentelemetry_span(self):
        """Test _process_batch creates OpenTelemetry spans when available."""
        mock_factory = Mock()
        mock_session = Mock()

        job = Mock(id=1, rule_kind="test_rule", status="queued")

        mock_query = Mock()
        mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [job]
        mock_session.query.return_value = mock_query

        runner = WorkflowRunner(mock_factory)

        # Mock OpenTelemetry - patch the import
        mock_span = Mock()
        mock_tracer = Mock()
        mock_tracer.start_span.return_value = mock_span

        mock_trace_module = Mock()
        mock_trace_module.get_tracer.return_value = mock_tracer

        import sys
        # Create parent module that has trace attribute
        mock_otel_module = Mock()
        mock_otel_module.trace = mock_trace_module

        sys.modules['opentelemetry'] = mock_otel_module
        sys.modules['opentelemetry.trace'] = mock_trace_module

        try:
            runner._process_batch(mock_session)

            # Span should be created and ended
            mock_tracer.start_span.assert_called_once_with("workflow.process")
            mock_span.set_attribute.assert_any_call("workflow.job_id", 1)
            mock_span.set_attribute.assert_any_call("workflow.rule_kind", "test_rule")
            mock_span.end.assert_called_once()
        finally:
            # Clean up sys.modules
            if 'opentelemetry' in sys.modules:
                del sys.modules['opentelemetry']
            if 'opentelemetry.trace' in sys.modules:
                del sys.modules['opentelemetry.trace']

    def test_process_batch_handles_opentelemetry_import_error(self):
        """Test _process_batch handles OpenTelemetry not being available."""
        mock_factory = Mock()
        mock_session = Mock()

        job = Mock(id=1, rule_kind="test_rule", status="queued")

        mock_query = Mock()
        mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [job]
        mock_session.query.return_value = mock_query

        runner = WorkflowRunner(mock_factory)

        # OpenTelemetry should not be in sys.modules by default in tests
        # Just run the batch - it will handle missing OpenTelemetry gracefully
        runner._process_batch(mock_session)

        # Should still process job without span
        assert job.status == "done"
        mock_session.commit.assert_called_once()

    def test_process_batch_handles_span_end_exception(self):
        """Test _process_batch handles exceptions when ending span."""
        mock_factory = Mock()
        mock_session = Mock()

        job = Mock(id=1, rule_kind="test_rule", status="queued")

        mock_query = Mock()
        mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [job]
        mock_session.query.return_value = mock_query

        runner = WorkflowRunner(mock_factory)

        # Mock span that throws on end()
        mock_span = Mock()
        mock_span.end.side_effect = Exception("Span end error")
        mock_tracer = Mock()
        mock_tracer.start_span.return_value = mock_span

        mock_trace_module = Mock()
        mock_trace_module.get_tracer.return_value = mock_tracer

        import sys
        # Create parent module that has trace attribute
        mock_otel_module = Mock()
        mock_otel_module.trace = mock_trace_module

        sys.modules['opentelemetry'] = mock_otel_module
        sys.modules['opentelemetry.trace'] = mock_trace_module

        try:
            # Should not raise
            runner._process_batch(mock_session)

            # Should still process job
            assert job.status == "done"
            mock_session.commit.assert_called_once()
        finally:
            # Clean up sys.modules
            if 'opentelemetry' in sys.modules:
                del sys.modules['opentelemetry']
            if 'opentelemetry.trace' in sys.modules:
                del sys.modules['opentelemetry.trace']


class TestMaybeStartWorkflowRunner:
    """Test maybe_start_workflow_runner function."""

    def test_maybe_start_workflow_runner_disabled_returns_none(self):
        """Test that runner is not started when disabled."""
        mock_app = Mock()
        mock_factory = Mock()

        with patch.dict(os.environ, {"WORKFLOW_RUNNER_ENABLED": "false"}):
            result = maybe_start_workflow_runner(mock_app, mock_factory)

            assert result is None

    def test_maybe_start_workflow_runner_enabled_starts_thread(self):
        """Test that runner starts when enabled."""
        mock_app = Mock()
        mock_factory = Mock()

        with patch.dict(os.environ, {"WORKFLOW_RUNNER_ENABLED": "true", "WORKFLOW_RUNNER_INTERVAL_SEC": "15"}):
            with patch("services.gateway.app.services.workflow_runner.WorkflowRunner.start") as mock_start:
                result = maybe_start_workflow_runner(mock_app, mock_factory)

                assert result is not None
                assert isinstance(result, WorkflowRunner)
                assert result._interval == 15
                mock_start.assert_called_once()
                assert hasattr(mock_app.state, "workflow_runner_thread")

    def test_maybe_start_workflow_runner_respects_yes_value(self):
        """Test that 'yes' is recognized as enabled."""
        mock_app = Mock()
        mock_factory = Mock()

        with patch.dict(os.environ, {"WORKFLOW_RUNNER_ENABLED": "yes"}):
            with patch("services.gateway.app.services.workflow_runner.WorkflowRunner.start"):
                result = maybe_start_workflow_runner(mock_app, mock_factory)

                assert result is not None

    def test_maybe_start_workflow_runner_respects_1_value(self):
        """Test that '1' is recognized as enabled."""
        mock_app = Mock()
        mock_factory = Mock()

        with patch.dict(os.environ, {"WORKFLOW_RUNNER_ENABLED": "1"}):
            with patch("services.gateway.app.services.workflow_runner.WorkflowRunner.start"):
                result = maybe_start_workflow_runner(mock_app, mock_factory)

                assert result is not None

    def test_maybe_start_workflow_runner_case_insensitive(self):
        """Test that enable check is case-insensitive."""
        mock_app = Mock()
        mock_factory = Mock()

        with patch.dict(os.environ, {"WORKFLOW_RUNNER_ENABLED": "TRUE"}):
            with patch("services.gateway.app.services.workflow_runner.WorkflowRunner.start"):
                result = maybe_start_workflow_runner(mock_app, mock_factory)

                assert result is not None

    def test_maybe_start_workflow_runner_uses_default_interval(self):
        """Test that default interval is 10 seconds."""
        mock_app = Mock()
        mock_factory = Mock()

        with patch.dict(os.environ, {"WORKFLOW_RUNNER_ENABLED": "true"}, clear=True):
            # Don't set WORKFLOW_RUNNER_INTERVAL_SEC, should use default
            with patch("services.gateway.app.services.workflow_runner.WorkflowRunner.start"):
                result = maybe_start_workflow_runner(mock_app, mock_factory)

                assert result._interval == 10

    def test_maybe_start_workflow_runner_custom_interval(self):
        """Test custom interval from environment variable."""
        mock_app = Mock()
        mock_factory = Mock()

        with patch.dict(os.environ, {"WORKFLOW_RUNNER_ENABLED": "true", "WORKFLOW_RUNNER_INTERVAL_SEC": "120"}):
            with patch("services.gateway.app.services.workflow_runner.WorkflowRunner.start"):
                result = maybe_start_workflow_runner(mock_app, mock_factory)

                assert result._interval == 120

    def test_maybe_start_workflow_runner_logs_startup(self):
        """Test that runner logs when started."""
        mock_app = Mock()
        mock_factory = Mock()

        with patch.dict(os.environ, {"WORKFLOW_RUNNER_ENABLED": "true"}):
            with patch("services.gateway.app.services.workflow_runner.WorkflowRunner.start"):
                with patch("services.gateway.app.services.workflow_runner.get_logger") as mock_logger:
                    mock_log_instance = Mock()
                    mock_logger.return_value = mock_log_instance

                    maybe_start_workflow_runner(mock_app, mock_factory)

                    # Should have logged the startup
                    mock_log_instance.info.assert_called()


class TestMaybeStopWorkflowRunner:
    """Test maybe_stop_workflow_runner function."""

    def test_maybe_stop_workflow_runner_stops_thread(self):
        """Test that maybe_stop_workflow_runner calls stop() on thread."""
        mock_app = Mock()
        mock_thread = Mock()
        mock_app.state.workflow_runner_thread = mock_thread

        maybe_stop_workflow_runner(mock_app)

        mock_thread.stop.assert_called_once()

    def test_maybe_stop_workflow_runner_no_thread(self):
        """Test that maybe_stop_workflow_runner handles missing thread."""
        mock_app = Mock()
        mock_app.state = Mock(spec=[])  # No workflow_runner_thread attribute

        # Should not raise
        maybe_stop_workflow_runner(mock_app)

    def test_maybe_stop_workflow_runner_handles_exception(self):
        """Test that maybe_stop_workflow_runner handles exceptions."""
        mock_app = Mock()
        mock_thread = Mock()
        mock_thread.stop.side_effect = Exception("Stop failed")
        mock_app.state.workflow_runner_thread = mock_thread

        # Should not raise
        maybe_stop_workflow_runner(mock_app)


class TestRetentionRunner:
    """Test RetentionRunner class."""

    def test_retention_runner_initialization(self):
        """Test RetentionRunner initializes correctly."""
        mock_factory = Mock()

        runner = RetentionRunner(mock_factory, days=30, interval_sec=3600)

        assert runner._session_factory == mock_factory
        assert runner._days == 30
        assert runner._interval == 3600
        assert runner.daemon is True
        assert isinstance(runner._stop, threading.Event)

    def test_retention_runner_default_interval(self):
        """Test RetentionRunner uses default interval."""
        mock_factory = Mock()

        runner = RetentionRunner(mock_factory, days=7)

        assert runner._interval == 86400

    def test_retention_runner_stop(self):
        """Test that stop() sets the stop event."""
        mock_factory = Mock()

        runner = RetentionRunner(mock_factory, days=7, interval_sec=60)
        runner.stop()

        assert runner._stop.is_set()

    def test_retention_runner_is_daemon(self):
        """Test that RetentionRunner is created as daemon thread."""
        mock_factory = Mock()

        runner = RetentionRunner(mock_factory, days=7)

        assert runner.daemon is True


class TestMaybeStartRetention:
    """Test maybe_start_retention function."""

    def test_maybe_start_retention_disabled_returns_none(self):
        """Test that retention is not started when days <= 0."""
        mock_app = Mock()
        mock_factory = Mock()

        with patch.dict(os.environ, {"RETENTION_DAYS": "0"}):
            result = maybe_start_retention(mock_app, mock_factory)

            assert result is None

    def test_maybe_start_retention_negative_days_returns_none(self):
        """Test that retention is not started when days is negative."""
        mock_app = Mock()
        mock_factory = Mock()

        with patch.dict(os.environ, {"RETENTION_DAYS": "-5"}):
            result = maybe_start_retention(mock_app, mock_factory)

            assert result is None

    def test_maybe_start_retention_empty_string_returns_none(self):
        """Test that retention is not started when days is empty string."""
        mock_app = Mock()
        mock_factory = Mock()

        with patch.dict(os.environ, {"RETENTION_DAYS": ""}):
            result = maybe_start_retention(mock_app, mock_factory)

            assert result is None

    def test_maybe_start_retention_enabled_starts_thread(self):
        """Test that retention starts when days > 0."""
        mock_app = Mock()
        mock_factory = Mock()

        with patch.dict(os.environ, {"RETENTION_DAYS": "30", "RETENTION_INTERVAL_SEC": "7200"}):
            with patch("services.gateway.app.services.workflow_runner.RetentionRunner.start") as mock_start:
                result = maybe_start_retention(mock_app, mock_factory)

                assert result is not None
                assert isinstance(result, RetentionRunner)
                assert result._days == 30
                assert result._interval == 7200
                mock_start.assert_called_once()
                assert hasattr(mock_app.state, "retention_runner_thread")

    def test_maybe_start_retention_uses_default_interval(self):
        """Test that default interval is 86400 seconds (1 day)."""
        mock_app = Mock()
        mock_factory = Mock()

        with patch.dict(os.environ, {"RETENTION_DAYS": "7"}, clear=True):
            # Don't set RETENTION_INTERVAL_SEC, should use default
            with patch("services.gateway.app.services.workflow_runner.RetentionRunner.start"):
                result = maybe_start_retention(mock_app, mock_factory)

                assert result._interval == 86400

    def test_maybe_start_retention_custom_interval(self):
        """Test custom interval from environment variable."""
        mock_app = Mock()
        mock_factory = Mock()

        with patch.dict(os.environ, {"RETENTION_DAYS": "14", "RETENTION_INTERVAL_SEC": "43200"}):
            with patch("services.gateway.app.services.workflow_runner.RetentionRunner.start"):
                result = maybe_start_retention(mock_app, mock_factory)

                assert result._interval == 43200

    def test_maybe_start_retention_logs_startup(self):
        """Test that retention logs when started."""
        mock_app = Mock()
        mock_factory = Mock()

        with patch.dict(os.environ, {"RETENTION_DAYS": "30"}):
            with patch("services.gateway.app.services.workflow_runner.RetentionRunner.start"):
                with patch("services.gateway.app.services.workflow_runner.get_logger") as mock_logger:
                    mock_log_instance = Mock()
                    mock_logger.return_value = mock_log_instance

                    maybe_start_retention(mock_app, mock_factory)

                    # Should have logged the startup
                    mock_log_instance.info.assert_called()


class TestMaybeStopRetention:
    """Test maybe_stop_retention function."""

    def test_maybe_stop_retention_stops_thread(self):
        """Test that maybe_stop_retention calls stop() on thread."""
        mock_app = Mock()
        mock_thread = Mock()
        mock_app.state.retention_runner_thread = mock_thread

        maybe_stop_retention(mock_app)

        mock_thread.stop.assert_called_once()

    def test_maybe_stop_retention_no_thread(self):
        """Test that maybe_stop_retention handles missing thread."""
        mock_app = Mock()
        mock_app.state = Mock(spec=[])  # No retention_runner_thread attribute

        # Should not raise
        maybe_stop_retention(mock_app)

    def test_maybe_stop_retention_handles_exception(self):
        """Test that maybe_stop_retention handles exceptions."""
        mock_app = Mock()
        mock_thread = Mock()
        mock_thread.stop.side_effect = Exception("Stop failed")
        mock_app.state.retention_runner_thread = mock_thread

        # Should not raise
        maybe_stop_retention(mock_app)
