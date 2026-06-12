from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

LOGGER = logging.getLogger("akretic")

RESTRICTED_LOG_MARKERS = (
    "AKRETIC_EXEC_ONLY_CANARY_DO_NOT_SUMMARIZE",
    "Project Helios",
    "confidential acquisition timing",
)


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        cleaned = value
        for marker in RESTRICTED_LOG_MARKERS:
            cleaned = cleaned.replace(marker, "[restricted marker omitted]")
        return cleaned
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, tuple):
        return [_clean(item) for item in value]
    return value


def log_event(event_type: str, **fields: Any) -> None:
    """Emit one structured JSON log line without document text."""
    record = {
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": fields.pop("service", None) or os.getenv("K_SERVICE") or os.getenv("AKRETIC_SERVICE_NAME"),
        "revision": fields.pop("revision", None) or os.getenv("K_REVISION"),
        **fields,
    }
    LOGGER.info(json.dumps(_clean(record), sort_keys=True, default=str))
