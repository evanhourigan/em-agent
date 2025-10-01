from __future__ import annotations

from typing import Any, Dict

# Global metrics registry populated during app startup in observability.add_prometheus
metrics: Dict[str, Any] = {}


