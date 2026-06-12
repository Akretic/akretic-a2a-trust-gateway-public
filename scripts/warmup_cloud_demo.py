from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from common.a2a_client import cloud_run_auth_headers


def _base(url: str | None) -> str | None:
    return url.rstrip("/") if url else None


def _service_urls(args: argparse.Namespace, readyz: dict[str, Any] | None = None) -> dict[str, str | None]:
    service_urls = readyz.get("service_urls", {}) if isinstance(readyz, dict) else {}
    return {
        "demo_ui": _base(args.base_url),
        "root": _base(args.root_url or os.getenv("ROOT_ORCHESTRATOR_URL") or service_urls.get("root")),
        "policy": _base(args.policy_url or os.getenv("POLICY_AGENT_URL") or service_urls.get("policy")),
        "knowledge": _base(args.knowledge_url or os.getenv("KNOWLEDGE_AGENT_URL") or service_urls.get("knowledge")),
        "research": _base(args.research_url or os.getenv("RESEARCH_AGENT_URL") or service_urls.get("research")),
        "approval": _base(args.approval_url or os.getenv("APPROVAL_EVIDENCE_URL") or service_urls.get("approval")),
    }


def _measure(summary: dict[str, Any], name: str, fn) -> Any:
    started = time.perf_counter()
    try:
        value = fn()
    except Exception as exc:
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        summary["dependencies"][name] = {
            "ok": False,
            "latency_ms": latency_ms,
            "error_class": type(exc).__name__,
            "error": str(exc),
        }
        summary["failures"].append({"dependency": name, "error_class": type(exc).__name__, "error": str(exc)})
        return None
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    status_code = getattr(value, "status_code", None)
    ok = bool(status_code is None or status_code < 500)
    summary["dependencies"][name] = {
        "ok": ok,
        "latency_ms": latency_ms,
        "status_code": status_code,
    }
    if not ok:
        summary["failures"].append({"dependency": name, "status_code": status_code})
    return value


def _json_response(response: httpx.Response | None) -> dict[str, Any]:
    if response is None:
        return {}
    try:
        return response.json()
    except ValueError:
        return {}


def run_warmup(args: argparse.Namespace) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "base_url": _base(args.base_url),
        "runtime_mode": None,
        "model_mode": None,
        "corpus_backend": None,
        "revision_map": {},
        "dependencies": {},
        "failures": [],
    }
    timeout = httpx.Timeout(connect=args.timeout, read=args.timeout, write=args.timeout, pool=args.timeout)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        home = _measure(summary, "public_demo_ui", lambda: client.get(f"{_base(args.base_url)}/"))
        readyz_response = _measure(summary, "public_readyz", lambda: client.get(f"{_base(args.base_url)}/readyz"))
        readyz = _json_response(readyz_response)
        urls = _service_urls(args, readyz)
        summary["runtime_mode"] = readyz.get("runtime_mode")
        summary["model_mode"] = readyz.get("model_mode")
        summary["corpus_backend"] = readyz.get("corpus_backend")
        summary["revision_map"] = readyz.get("revision_map", {})
        if readyz_response is not None and readyz_response.status_code != 200:
            summary["failures"].append({"dependency": "public_readyz", "status_code": readyz_response.status_code})

        if urls["root"]:
            _measure(
                summary,
                "root_readyz_authenticated",
                lambda: client.get(f"{urls['root']}/readyz", headers=cloud_run_auth_headers(str(urls["root"]))),
            )
        for name in ("policy", "knowledge", "research", "approval"):
            base_url = urls.get(name)
            if not base_url:
                summary["failures"].append({"dependency": f"{name}_agent_card", "error": "missing service URL"})
                continue
            headers = cloud_run_auth_headers(str(base_url))
            _measure(
                summary,
                f"{name}_agent_card_well_known_authenticated",
                lambda base_url=base_url, headers=headers: client.get(
                    f"{base_url}/.well-known/agent-card.json",
                    headers=headers,
                ),
            )
            _measure(
                summary,
                f"{name}_agent_card_legacy_authenticated",
                lambda base_url=base_url, headers=headers: client.get(f"{base_url}/agent.json", headers=headers),
            )

        _measure(summary, "corpus_status", lambda: client.get(f"{_base(args.base_url)}/corpus/status"))
        _measure(
            summary,
            "model_context_envelope_route_probe",
            lambda: client.get(
                f"{_base(args.base_url)}/runs/run_missing_for_warmup/model-context-envelope",
                params={"viewer_persona": "security_reviewer"},
            ),
        )
        vertex_response = _measure(summary, "vertex_gemini_lightweight", lambda: client.get(f"{_base(args.base_url)}/readyz/vertex"))
        if vertex_response is not None and vertex_response.status_code != 200:
            summary["failures"].append({"dependency": "vertex_gemini_lightweight", "status_code": vertex_response.status_code})

        approval_url = urls.get("approval")
        if approval_url:
            run_id = f"warmup_{uuid4().hex}"
            headers = cloud_run_auth_headers(str(approval_url), {"x-akretic-persona": "security_reviewer"})
            record = _measure(
                summary,
                "synthetic_evidence_write",
                lambda: client.post(
                    f"{approval_url}/record_event",
                    json={
                        "run_id": run_id,
                        "persona": "security_reviewer",
                        "agent_id": "warmup",
                        "action": "warmup_evidence_check",
                        "resource_id": "cloud_demo_warmup",
                        "outcome": "result",
                        "reason": "lightweight warmup evidence write",
                    },
                    headers=headers,
                ),
            )
            verify = _measure(
                summary,
                "synthetic_evidence_verify",
                lambda: client.get(f"{approval_url}/verify/{run_id}", headers=headers),
            )
            verify_json = _json_response(verify)
            if verify_json.get("valid") is not True:
                summary["failures"].append({"dependency": "synthetic_evidence_verify", "error": "valid was not true"})

    summary["ok"] = not summary["failures"]
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Warm Cloud Run judging demo dependencies.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--root-url")
    parser.add_argument("--policy-url")
    parser.add_argument("--knowledge-url")
    parser.add_argument("--research-url")
    parser.add_argument("--approval-url")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--output", default="warmup-output.json")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    summary = run_warmup(args)
    Path(args.output).write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
