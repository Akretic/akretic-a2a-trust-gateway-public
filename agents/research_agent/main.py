from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request

from common.agent_cards import agent_card_public_url
from common.corpus import load_metadata, read_document_text

app = FastAPI(title="Akretic Seeded Research Agent")
CARD_PATH = Path(__file__).resolve().parent / "agent-card.json"


def _citation_from_text(text: str) -> str:
    for line in text.splitlines():
        if line.lower().startswith("citation:"):
            return line.split(":", 1)[1].strip()
    return "seeded://vendornova/unknown"


def _seeded_snippets() -> list[dict[str, Any]]:
    snippets: list[dict[str, Any]] = []
    for doc in load_metadata():
        if doc.get("source_type") != "synthetic_public":
            continue
        text = read_document_text(doc)
        snippets.append(
            {
                "source_id": doc["source_id"],
                "source_type": doc["source_type"],
                "classification": doc["classification"],
                "title": doc["title"],
                "text": text,
                "citation": _citation_from_text(text),
                "content_sha256": doc.get("content_sha256"),
            }
        )
    return sorted(snippets, key=lambda snippet: snippet["source_id"])


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "research-agent"}


@app.get("/readyz")
def readyz() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "research-agent",
        "runtime_mode": os.getenv("AKRETIC_RUNTIME_MODE", "local"),
        "revision": os.getenv("K_REVISION", "local"),
        "seeded_public_snippet_count": len(_seeded_snippets()),
    }


@app.get("/agent.json")
@app.get("/agent-card.json")
@app.get("/.well-known/agent-card.json")
def agent_card(request: Request) -> dict[str, Any]:
    card = json.loads(CARD_PATH.read_text(encoding="utf-8"))
    card["url"] = agent_card_public_url("RESEARCH_AGENT_PUBLIC_URL", str(request.base_url).rstrip("/"))
    return card


@app.post("/research_vendor_profile")
def research_vendor_profile(payload: dict[str, Any]) -> dict[str, Any]:
    snippets = _seeded_snippets()[:1]
    return {
        "run_id": payload.get("run_id", "local-run"),
        "vendor": payload.get("vendor", "VendorNova"),
        "source_scope": "seeded_allowlisted_public",
        "snippets": snippets,
        "source_ids": [snippet["source_id"] for snippet in snippets],
        "citations": [snippet["citation"] for snippet in snippets],
    }


@app.post("/check_public_risk_signals")
def check_public_risk_signals(payload: dict[str, Any]) -> dict[str, Any]:
    snippets = _seeded_snippets()
    return {
        "run_id": payload.get("run_id", "local-run"),
        "vendor": payload.get("vendor", "VendorNova"),
        "source_scope": "seeded_allowlisted_public",
        "snippets": snippets,
        "source_ids": [snippet["source_id"] for snippet in snippets],
        "citations": [snippet["citation"] for snippet in snippets],
    }
