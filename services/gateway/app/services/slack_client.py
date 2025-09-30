from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from ..core.config import get_settings
from ..core.logging import get_logger


class SlackClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._webhook_url: Optional[str] = settings.slack_webhook_url
        self._bot_token: Optional[str] = settings.slack_bot_token
        self._default_channel: Optional[str] = settings.slack_default_channel
        self._logger = get_logger(__name__)

    def post_text(self, text: str, channel: Optional[str] = None) -> Dict[str, Any]:
        if not self._webhook_url and not self._bot_token:
            self._logger.info("slack.post.dry_run", text=text)
            return {"ok": False, "dry_run": True, "text": text}

        if self._webhook_url:
            with httpx.Client(timeout=10) as client:
                resp = client.post(self._webhook_url, json={"text": text})
                return {"ok": resp.status_code < 300}

        # Bot token path (chat.postMessage)
        headers = {"Authorization": f"Bearer {self._bot_token}"}
        payload = {"channel": channel or self._default_channel, "text": text}
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                "https://slack.com/api/chat.postMessage", headers=headers, json=payload
            )
            data = resp.json()
            return {"ok": bool(data.get("ok")), "response": data}

    def post_blocks(
        self, *, text: str, blocks: list[dict[str, Any]], channel: Optional[str] = None
    ) -> Dict[str, Any]:
        if not self._webhook_url and not self._bot_token:
            self._logger.info("slack.post.dry_run", blocks=len(blocks))
            return {"ok": False, "dry_run": True, "blocks": blocks}

        if self._webhook_url:
            with httpx.Client(timeout=10) as client:
                resp = client.post(self._webhook_url, json={"text": text, "blocks": blocks})
                return {"ok": resp.status_code < 300}

        headers = {"Authorization": f"Bearer {self._bot_token}"}
        payload = {"channel": channel or self._default_channel, "text": text, "blocks": blocks}
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                "https://slack.com/api/chat.postMessage", headers=headers, json=payload
            )
            data = resp.json()
            return {"ok": bool(data.get("ok")), "response": data}
