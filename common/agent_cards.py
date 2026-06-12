from __future__ import annotations

import os
from pathlib import Path
from typing import Any

REQUIRED_CARD_FIELDS = {"name", "description", "version", "url", "skills"}


def validate_agent_card(card: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_CARD_FIELDS:
        if not card.get(field):
            errors.append(f"missing {field}")
    if not isinstance(card.get("skills", []), list) or not card.get("skills"):
        errors.append("skills must be a non-empty list")
    return errors


def load_card(path: str | Path) -> dict[str, Any]:
    import json

    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_cloud_url(url: str) -> str:
    value = str(url or "").strip().rstrip("/")
    if os.getenv("AKRETIC_RUNTIME_MODE", "local").strip().lower() == "cloud":
        if value.lower().startswith("http://"):
            return "https://" + value[7:]
    return value


def agent_card_public_url(env_name: str, request_base_url: str) -> str:
    configured = os.getenv(env_name)
    return normalize_cloud_url(configured or request_base_url)
