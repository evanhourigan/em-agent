from __future__ import annotations

import json
import os
from typing import Any

from ..core.logging import get_logger

try:
    from nats.aio.client import Client as NATS  # type: ignore

    _HAS_NATS = True
except Exception:  # pragma: no cover
    _HAS_NATS = False


class EventBus:
    def __init__(self) -> None:
        self._logger = get_logger(__name__)
        self._nats: NATS | None = None
        self._url = os.getenv("NATS_URL", "nats://nats:4222")

    async def connect(self) -> None:
        if not _HAS_NATS:
            self._logger.info("eventbus.disabled", reason="nats-py not installed")
            return
        if self._nats is not None:
            return
        self._nats = NATS()
        await self._nats.connect(servers=[self._url])
        self._logger.info("eventbus.connected", url=self._url)

    async def publish_json(self, subject: str, payload: dict[str, Any]) -> None:
        if not _HAS_NATS or self._nats is None:
            return
        data = json.dumps(payload).encode("utf-8")
        await self._nats.publish(subject, data)


_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus
