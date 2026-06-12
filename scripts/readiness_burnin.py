from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]


def _token(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN = (
    "localhost",
    "127.0.0.1",
    "LOCAL_DETERMINISTIC",
    "local deterministic",
    "local-deterministic-test-summary",
    "sample evidence",
    "local://",
    "http://akretic",
    _token("<OPTIONAL_", "SERVICE_ACCOUNT_EMAIL>"),
    _token("<REPOSITORY", "_URL>"),
    _token("TO", "DO"),
    _token("FIX", "ME"),
    _token("PLACE", "HOLDER"),
    "Error 404",
    "That’s an error",
    "That's an error",
)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return round(ordered[index], 2)


def _run_command(command: list[str], timeout: int) -> dict[str, Any]:
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=os.environ.copy(),
        )
        return {
            "command": command,
            "timestamp": started_at,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "timeout": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "timestamp": started_at,
            "returncode": None,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "timeout": True,
        }


def _readyz(base_url: str, timeout: float) -> dict[str, Any]:
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.get(f"{base_url.rstrip('/')}/readyz")
        response.raise_for_status()
        return response.json()


def _urls(args: argparse.Namespace, readyz: dict[str, Any]) -> dict[str, str]:
    service_urls = readyz.get("service_urls", {}) if isinstance(readyz, dict) else {}
    urls = {
        "demo_ui": args.base_url.rstrip("/"),
        "root": args.root_url or os.getenv("ROOT_ORCHESTRATOR_URL") or service_urls.get("root"),
        "policy": args.policy_url or os.getenv("POLICY_AGENT_URL") or service_urls.get("policy"),
        "knowledge": args.knowledge_url or os.getenv("KNOWLEDGE_AGENT_URL") or service_urls.get("knowledge"),
        "research": args.research_url or os.getenv("RESEARCH_AGENT_URL") or service_urls.get("research"),
        "approval": args.approval_url or os.getenv("APPROVAL_EVIDENCE_URL") or service_urls.get("approval"),
    }
    missing = [name for name, value in urls.items() if not value]
    if missing:
        raise RuntimeError(f"missing service URLs: {', '.join(missing)}")
    return {name: str(value).rstrip("/") for name, value in urls.items()}


def _forbidden_findings(text: str) -> list[str]:
    return [token for token in FORBIDDEN if token in text]


def run_burnin(args: argparse.Namespace) -> dict[str, Any]:
    output: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url.rstrip("/"),
        "runs_requested": args.runs,
        "ok": False,
        "failures": [],
        "runs": [],
    }
    readyz = _readyz(args.base_url, args.timeout)
    output["readyz"] = readyz
    urls = _urls(args, readyz)
    output["service_urls"] = urls

    if readyz.get("runtime_mode") != "cloud":
        output["failures"].append({"gate": "runtime_mode", "value": readyz.get("runtime_mode")})
    if args.expect_vertex and readyz.get("model_mode") != "vertex":
        output["failures"].append({"gate": "model_mode", "value": readyz.get("model_mode")})

    warmup_command = [
        sys.executable,
        "scripts/warmup_cloud_demo.py",
        "--base-url",
        urls["demo_ui"],
        "--root-url",
        urls["root"],
        "--policy-url",
        urls["policy"],
        "--knowledge-url",
        urls["knowledge"],
        "--research-url",
        urls["research"],
        "--approval-url",
        urls["approval"],
        "--output",
        args.warmup_output,
    ]
    warmup = _run_command(warmup_command, args.command_timeout)
    output["warmup"] = warmup
    if warmup["returncode"] != 0 or warmup.get("timeout"):
        output["failures"].append({"gate": "warmup", "returncode": warmup["returncode"], "timeout": warmup.get("timeout")})

    verifier_command_base = [
        sys.executable,
        "scripts/p0_verify.py",
        "--base-url",
        urls["demo_ui"],
        "--mode",
        "cloud",
        "--root-url",
        urls["root"],
        "--policy-url",
        urls["policy"],
        "--knowledge-url",
        urls["knowledge"],
        "--research-url",
        urls["research"],
        "--approval-url",
        urls["approval"],
        "--expect-corpus-backend",
        "gcs",
        "--expect-freeform-playground",
        "--expect-corpus-explorer",
        "--expect-corpus-live-retrieval",
        "--expect-decision-receipts",
        "--expect-trust-receipt",
        "--expect-model-context-envelope",
        "--expect-red-team-cards",
    ]
    if args.expect_vertex:
        verifier_command_base.append("--expect-vertex")
    if args.fail_on_local:
        verifier_command_base.append("--fail-on-local")

    latencies: list[float] = []
    for index in range(1, args.runs + 1):
        run = _run_command(verifier_command_base, args.command_timeout)
        text = f"{run.get('stdout', '')}\n{run.get('stderr', '')}"
        run["index"] = index
        run["forbidden_findings"] = _forbidden_findings(text)
        run["http_5xx_seen"] = bool(re.search(r"\b5\d\d\b", text))
        match = re.search(r"FINAL_REVIEW:\s+P0 VERIFY PASSED run_id=([^\s]+)", text)
        run["run_id"] = match.group(1) if match else None
        output["runs"].append(run)
        latencies.append(float(run["latency_ms"]))
        if run["returncode"] != 0:
            output["failures"].append({"gate": "p0_verify", "index": index, "returncode": run["returncode"]})
        if run.get("timeout"):
            output["failures"].append({"gate": "timeout", "index": index})
        if args.expect_zero_5xx and run["http_5xx_seen"]:
            output["failures"].append({"gate": "5xx", "index": index})
        if run["forbidden_findings"]:
            output["failures"].append({"gate": "forbidden_strings", "index": index, "tokens": run["forbidden_findings"]})

    output["latency"] = {
        "p50_ms": round(statistics.median(latencies), 2) if latencies else 0,
        "p95_ms": _percentile(latencies, 0.95),
        "runs_ms": latencies,
    }
    output["ok"] = not output["failures"]
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run five-run Cloud Run judging readiness burn-in.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--expect-zero-5xx", action="store_true")
    parser.add_argument("--expect-vertex", action="store_true")
    parser.add_argument("--fail-on-local", action="store_true")
    parser.add_argument("--root-url")
    parser.add_argument("--policy-url")
    parser.add_argument("--knowledge-url")
    parser.add_argument("--research-url")
    parser.add_argument("--approval-url")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--command-timeout", type=int, default=600)
    parser.add_argument("--output", default="readiness-burnin-output.json")
    parser.add_argument("--warmup-output", default="warmup-output.json")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = run_burnin(args)
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
