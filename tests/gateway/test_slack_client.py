"""
Tests for SlackClient service.

Tests the Slack integration service with mocked HTTP calls.
Current coverage: 7% → Target: 70%+
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import httpx

from services.gateway.app.services.slack_client import SlackClient


class TestSlackClientInit:
    """Test SlackClient initialization."""

    def test_init_loads_settings(self):
        """Test that SlackClient loads settings correctly."""
        with patch("services.gateway.app.services.slack_client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                slack_webhook_url="https://hooks.slack.com/test",
                slack_bot_token="xoxb-test-token",
                slack_default_channel="#general",
                max_daily_slack_posts=1000
            )

            client = SlackClient()

            assert client._webhook_url == "https://hooks.slack.com/test"
            assert client._bot_token == "xoxb-test-token"
            assert client._default_channel == "#general"
            assert client._max_daily == 1000

    def test_init_with_no_config(self):
        """Test initialization when Slack is not configured."""
        with patch("services.gateway.app.services.slack_client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                slack_webhook_url=None,
                slack_bot_token=None,
                slack_default_channel=None,
                max_daily_slack_posts=1000
            )

            client = SlackClient()

            assert client._webhook_url is None
            assert client._bot_token is None
            assert client._default_channel is None


class TestPostTextDryRun:
    """Test post_text in dry-run mode (no webhook/token configured)."""

    def test_post_text_dry_run_no_config(self):
        """Test posting text when neither webhook nor token is configured."""
        with patch("services.gateway.app.services.slack_client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                slack_webhook_url=None,
                slack_bot_token=None,
                slack_default_channel=None,
                max_daily_slack_posts=1000
            )

            client = SlackClient()
            result = client.post_text("Test message")

            assert result["ok"] is False
            assert result["dry_run"] is True
            assert result["text"] == "Test message"

    def test_post_text_dry_run_logs_message(self):
        """Test that dry-run mode logs the message."""
        with patch("services.gateway.app.services.slack_client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                slack_webhook_url=None,
                slack_bot_token=None,
                slack_default_channel=None,
                max_daily_slack_posts=1000
            )

            client = SlackClient()
            with patch.object(client._logger, "info") as mock_log:
                client.post_text("Test message")
                mock_log.assert_called_once()


class TestPostTextWebhook:
    """Test post_text using webhook URL."""

    def test_post_text_webhook_success(self):
        """Test successful post via webhook."""
        with patch("services.gateway.app.services.slack_client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                slack_webhook_url="https://hooks.slack.com/test",
                slack_bot_token=None,
                slack_default_channel="#general",
                max_daily_slack_posts=1000
            )

            client = SlackClient()

            # Mock the HTTP client
            with patch("services.gateway.app.services.slack_client.httpx.Client") as mock_client_class:
                mock_client = MagicMock()
                mock_response = Mock()
                mock_response.status_code = 200
                mock_client.post.return_value = mock_response
                mock_client_class.return_value.__enter__.return_value = mock_client

                result = client.post_text("Test message")

                assert result["ok"] is True
                mock_client.post.assert_called_once_with(
                    "https://hooks.slack.com/test",
                    json={"text": "Test message"}
                )

    def test_post_text_webhook_failure(self):
        """Test failed post via webhook (non-200 status)."""
        with patch("services.gateway.app.services.slack_client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                slack_webhook_url="https://hooks.slack.com/test",
                slack_bot_token=None,
                slack_default_channel=None,
                max_daily_slack_posts=1000
            )

            client = SlackClient()

            with patch("services.gateway.app.services.slack_client.httpx.Client") as mock_client_class:
                mock_client = MagicMock()
                mock_response = Mock()
                mock_response.status_code = 500
                mock_client.post.return_value = mock_response
                mock_client_class.return_value.__enter__.return_value = mock_client

                result = client.post_text("Test message")

                assert result["ok"] is False


class TestPostTextBotToken:
    """Test post_text using bot token."""

    def test_post_text_bot_token_success(self):
        """Test successful post via bot token."""
        with patch("services.gateway.app.services.slack_client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                slack_webhook_url=None,
                slack_bot_token="xoxb-test-token",
                slack_default_channel="#general",
                max_daily_slack_posts=1000
            )

            client = SlackClient()

            with patch("services.gateway.app.services.slack_client.httpx.Client") as mock_client_class:
                mock_client = MagicMock()
                mock_response = Mock()
                mock_response.json.return_value = {"ok": True, "ts": "1234567890.123456"}
                mock_client.post.return_value = mock_response
                mock_client_class.return_value.__enter__.return_value = mock_client

                result = client.post_text("Test message", channel="#test")

                assert result["ok"] is True
                assert "response" in result
                mock_client.post.assert_called_once()
                call_args = mock_client.post.call_args
                assert call_args[0][0] == "https://slack.com/api/chat.postMessage"
                assert call_args[1]["headers"]["Authorization"] == "Bearer xoxb-test-token"
                assert call_args[1]["json"]["text"] == "Test message"
                assert call_args[1]["json"]["channel"] == "#test"

    def test_post_text_bot_token_uses_default_channel(self):
        """Test that bot token mode uses default channel when not specified."""
        with patch("services.gateway.app.services.slack_client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                slack_webhook_url=None,
                slack_bot_token="xoxb-test-token",
                slack_default_channel="#general",
                max_daily_slack_posts=1000
            )

            client = SlackClient()

            with patch("services.gateway.app.services.slack_client.httpx.Client") as mock_client_class:
                mock_client = MagicMock()
                mock_response = Mock()
                mock_response.json.return_value = {"ok": True}
                mock_client.post.return_value = mock_response
                mock_client_class.return_value.__enter__.return_value = mock_client

                client.post_text("Test message")

                call_args = mock_client.post.call_args
                assert call_args[1]["json"]["channel"] == "#general"

    def test_post_text_bot_token_failure(self):
        """Test failed post via bot token."""
        with patch("services.gateway.app.services.slack_client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                slack_webhook_url=None,
                slack_bot_token="xoxb-test-token",
                slack_default_channel="#general",
                max_daily_slack_posts=1000
            )

            client = SlackClient()

            with patch("services.gateway.app.services.slack_client.httpx.Client") as mock_client_class:
                mock_client = MagicMock()
                mock_response = Mock()
                mock_response.json.return_value = {"ok": False, "error": "channel_not_found"}
                mock_client.post.return_value = mock_response
                mock_client_class.return_value.__enter__.return_value = mock_client

                result = client.post_text("Test message")

                assert result["ok"] is False


class TestRetryLogic:
    """Test retry logic for HTTP failures."""

    def test_with_retry_succeeds_first_attempt(self):
        """Test that retry logic succeeds on first attempt."""
        with patch("services.gateway.app.services.slack_client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                slack_webhook_url="https://hooks.slack.com/test",
                slack_bot_token=None,
                slack_default_channel=None,
                max_daily_slack_posts=1000
            )

            client = SlackClient()

            with patch("services.gateway.app.services.slack_client.httpx.Client") as mock_client_class:
                mock_client = MagicMock()
                mock_response = Mock()
                mock_response.status_code = 200
                mock_client.post.return_value = mock_response
                mock_client_class.return_value.__enter__.return_value = mock_client

                result = client.post_text("Test")

                assert result["ok"] is True
                assert mock_client.post.call_count == 1

    def test_with_retry_succeeds_second_attempt(self):
        """Test that retry logic retries on HTTP error."""
        with patch("services.gateway.app.services.slack_client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                slack_webhook_url="https://hooks.slack.com/test",
                slack_bot_token=None,
                slack_default_channel=None,
                max_daily_slack_posts=1000
            )

            client = SlackClient()

            with patch("services.gateway.app.services.slack_client.httpx.Client") as mock_client_class:
                mock_client = MagicMock()

                # First attempt: raise HTTPError, second attempt: succeed
                mock_response_fail = Mock()
                mock_response_fail.status_code = 200
                mock_response_success = Mock()
                mock_response_success.status_code = 200

                call_count = [0]
                def side_effect(*args, **kwargs):
                    call_count[0] += 1
                    if call_count[0] == 1:
                        raise httpx.HTTPError("Connection error")
                    return mock_response_success

                mock_client.post.side_effect = side_effect
                mock_client_class.return_value.__enter__.return_value = mock_client

                result = client.post_text("Test")

                assert result["ok"] is True
                assert mock_client.post.call_count == 2  # Retry happened

    def test_with_retry_fails_all_attempts(self):
        """Test that retry logic fails after all attempts."""
        with patch("services.gateway.app.services.slack_client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                slack_webhook_url="https://hooks.slack.com/test",
                slack_bot_token=None,
                slack_default_channel=None,
                max_daily_slack_posts=1000
            )

            client = SlackClient()

            with patch("services.gateway.app.services.slack_client.httpx.Client") as mock_client_class:
                mock_client = MagicMock()
                mock_client.post.side_effect = httpx.HTTPError("Connection error")
                mock_client_class.return_value.__enter__.return_value = mock_client

                # Should raise after 3 attempts
                with pytest.raises(httpx.HTTPError):
                    client.post_text("Test")

                assert mock_client.post.call_count == 3  # 3 retry attempts


class TestQuotaEnforcement:
    """Test daily quota enforcement."""

    def test_post_text_within_quota(self):
        """Test posting when under quota limit."""
        with patch("services.gateway.app.services.slack_client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                slack_webhook_url=None,
                slack_bot_token="xoxb-test-token",
                slack_default_channel="#general",
                max_daily_slack_posts=1000
            )

            client = SlackClient()

            # Mock metrics to show we're under quota
            with patch("services.gateway.app.services.slack_client.global_metrics") as mock_metrics:
                mock_counter = Mock()
                mock_counter._value.get.return_value = 500  # Under limit of 1000
                mock_metrics.get.return_value = mock_counter
                mock_metrics.__getitem__.return_value = mock_counter

                with patch("services.gateway.app.services.slack_client.httpx.Client") as mock_client_class:
                    mock_client = MagicMock()
                    mock_response = Mock()
                    mock_response.json.return_value = {"ok": True}
                    mock_client.post.return_value = mock_response
                    mock_client_class.return_value.__enter__.return_value = mock_client

                    result = client.post_text("Test")

                    assert result["ok"] is True
                    assert "quota_exceeded" not in result

    def test_post_text_quota_exceeded(self):
        """Test posting when quota is exceeded."""
        with patch("services.gateway.app.services.slack_client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                slack_webhook_url=None,
                slack_bot_token="xoxb-test-token",
                slack_default_channel="#general",
                max_daily_slack_posts=1000
            )

            client = SlackClient()

            # Mock metrics to show we're over quota
            with patch("services.gateway.app.services.slack_client.global_metrics") as mock_metrics:
                mock_counter = Mock()
                mock_counter._value.get.return_value = 1001  # Over limit of 1000
                mock_metrics.get.return_value = mock_counter
                mock_metrics.__getitem__.return_value = mock_counter

                result = client.post_text("Test")

                assert result["ok"] is False
                assert result["error"] == "quota_exceeded"


class TestPostBlocks:
    """Test post_blocks method."""

    def test_post_blocks_dry_run(self):
        """Test posting blocks in dry-run mode."""
        with patch("services.gateway.app.services.slack_client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                slack_webhook_url=None,
                slack_bot_token=None,
                slack_default_channel=None,
                max_daily_slack_posts=1000
            )

            client = SlackClient()
            blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "*Bold text*"}}]
            result = client.post_blocks(text="Fallback text", blocks=blocks)

            assert result["ok"] is False
            assert result["dry_run"] is True
            assert result["blocks"] == blocks

    def test_post_blocks_webhook_success(self):
        """Test successful post_blocks via webhook."""
        with patch("services.gateway.app.services.slack_client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                slack_webhook_url="https://hooks.slack.com/test",
                slack_bot_token=None,
                slack_default_channel=None,
                max_daily_slack_posts=1000
            )

            client = SlackClient()
            blocks = [{"type": "section", "text": {"type": "plain_text", "text": "Hello"}}]

            with patch("services.gateway.app.services.slack_client.httpx.Client") as mock_client_class:
                mock_client = MagicMock()
                mock_response = Mock()
                mock_response.status_code = 200
                mock_client.post.return_value = mock_response
                mock_client_class.return_value.__enter__.return_value = mock_client

                result = client.post_blocks(text="Fallback", blocks=blocks)

                assert result["ok"] is True
                call_args = mock_client.post.call_args
                assert call_args[1]["json"]["text"] == "Fallback"
                assert call_args[1]["json"]["blocks"] == blocks

    def test_post_blocks_bot_token_with_channel(self):
        """Test post_blocks via bot token with custom channel."""
        with patch("services.gateway.app.services.slack_client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                slack_webhook_url=None,
                slack_bot_token="xoxb-test-token",
                slack_default_channel="#general",
                max_daily_slack_posts=1000
            )

            client = SlackClient()
            blocks = [{"type": "divider"}]

            with patch("services.gateway.app.services.slack_client.httpx.Client") as mock_client_class:
                mock_client = MagicMock()
                mock_response = Mock()
                mock_response.json.return_value = {"ok": True, "ts": "1234.5678"}
                mock_client.post.return_value = mock_response
                mock_client_class.return_value.__enter__.return_value = mock_client

                result = client.post_blocks(text="Fallback", blocks=blocks, channel="#announcements")

                assert result["ok"] is True
                call_args = mock_client.post.call_args
                assert call_args[1]["json"]["channel"] == "#announcements"
                assert call_args[1]["json"]["blocks"] == blocks

    def test_post_blocks_quota_exceeded(self):
        """Test post_blocks respects quota limits."""
        with patch("services.gateway.app.services.slack_client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                slack_webhook_url=None,
                slack_bot_token="xoxb-test-token",
                slack_default_channel="#general",
                max_daily_slack_posts=100
            )

            client = SlackClient()
            blocks = [{"type": "section"}]

            with patch("services.gateway.app.services.slack_client.global_metrics") as mock_metrics:
                mock_counter = Mock()
                mock_counter._value.get.return_value = 101  # Over limit
                mock_metrics.get.return_value = mock_counter
                mock_metrics.__getitem__.return_value = mock_counter

                result = client.post_blocks(text="Test", blocks=blocks)

                assert result["ok"] is False
                assert result["error"] == "quota_exceeded"


class TestMetricsIncrement:
    """Test metric incrementing."""

    def test_inc_metric_increments_counters(self):
        """Test that _inc_metric increments the right counters."""
        with patch("services.gateway.app.services.slack_client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                slack_webhook_url="https://hooks.slack.com/test",
                slack_bot_token=None,
                slack_default_channel=None,
                max_daily_slack_posts=1000
            )

            client = SlackClient()

            # Mock the global metrics
            with patch("services.gateway.app.services.slack_client.global_metrics") as mock_metrics:
                mock_total_labels = Mock()
                mock_total = Mock()
                mock_total.labels.return_value = mock_total_labels
                mock_quota = Mock()

                def metrics_get(key):
                    if key == "quota_slack_posts_total":
                        return mock_quota
                    return None

                mock_metrics.get.side_effect = metrics_get
                mock_metrics.__getitem__.side_effect = lambda key: mock_total if key == "slack_posts_total" else None

                # Test successful post (ok=True)
                client._inc_metric("text", True)

                # Should increment total and quota
                assert mock_total.labels.called
                assert mock_total_labels.inc.called

    def test_inc_metric_handles_missing_metrics(self):
        """Test that _inc_metric handles missing metrics gracefully."""
        with patch("services.gateway.app.services.slack_client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                slack_webhook_url="https://hooks.slack.com/test",
                slack_bot_token=None,
                slack_default_channel=None,
                max_daily_slack_posts=1000
            )

            client = SlackClient()

            # Mock metrics as None
            with patch("services.gateway.app.services.slack_client.global_metrics", None):
                # Should not raise an exception
                client._inc_metric("text", True)
