from __future__ import annotations

import os

from ..core.logging import get_logger

try:
    from temporalio.client import Client  # type: ignore

    _HAS_TEMPORAL = True
except Exception:  # pragma: no cover
    _HAS_TEMPORAL = False


class TemporalGateway:
    def __init__(self) -> None:
        self._logger = get_logger(__name__)
        self._client: Client | None = None
        self._addr = os.getenv("TEMPORAL_ADDRESS", "temporal:7233")
        self._namespace = os.getenv("TEMPORAL_NAMESPACE", "default")

    async def ensure(self) -> Client | None:
        if not _HAS_TEMPORAL:
            return None
        if self._client is None:
            self._client = await Client.connect(self._addr, namespace=self._namespace)
            self._logger.info(
                "temporal.connected", address=self._addr, namespace=self._namespace
            )
        return self._client


_gw: TemporalGateway | None = None


def get_temporal() -> TemporalGateway:
    global _gw
    if _gw is None:
        _gw = TemporalGateway()
    return _gw
