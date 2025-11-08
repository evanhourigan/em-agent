from __future__ import annotations

from typing import Any

# Global metrics registry populated during app startup in observability.add_prometheus
metrics: dict[str, Any] = {}
