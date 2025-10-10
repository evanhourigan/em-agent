import logging
from typing import Any, Dict

import structlog
import re


def _configure_stdlib_logging() -> None:
    logging.basicConfig(
        format="%(message)s",
        level=logging.INFO,
    )


def configure_structlog() -> None:
    _configure_stdlib_logging()

    # Redaction processor for secrets and tokens
    secret_keys = {"authorization", "x-slack-signature", "slack_signing_secret", "slack_bot_token", "openai_api_key"}

    def _redact_event_logger(_logger, _name, event_dict: Dict[str, Any]):  # type: ignore[override]
        # redact obvious keys
        for k in list(event_dict.keys()):
            lk = str(k).lower()
            if lk in secret_keys:
                event_dict[k] = "[REDACTED]"
        # redact bearer tokens in strings
        for k, v in list(event_dict.items()):
            if isinstance(v, str):
                if "Bearer " in v:
                    event_dict[k] = re.sub(r"Bearer\s+[A-Za-z0-9\-_.=:+/]+", "Bearer [REDACTED]", v)
                if "xoxb-" in v or "xapp-" in v:
                    event_dict[k] = "[REDACTED]"
        return event_dict

    structlog.configure(
        processors=[
            _redact_event_logger,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str):
    return structlog.get_logger(name)
