from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from common.a2a_client import cloud_run_auth_headers


def _token(*parts: str) -> str:
    return "".join(parts)


CLOUD_FORBIDDEN_TOKENS = (
    "127.0.0.1",
    "localhost",
    "LOCAL_DETERMINISTIC",
    "local deterministic",
    "local-deterministic-test-summary",
    "sample evidence",
    _token("<OPTIONAL_", "SERVICE_ACCOUNT_EMAIL>"),
    _token("<REPOSITORY", "_URL>"),
    _token("TO", "DO"),
    _token("FIX", "ME"),
    _token("PLACE", "HOLDER"),
    "Error 404",
    "That’s an error",
    "That's an error",
    "local://",
    "http://akretic",
)
LOCAL_TOKENS = ("127.0.0.1", "localhost", "LOCAL_DETERMINISTIC", "local deterministic")
DENIED_CANARIES = (
    "Project Helios",
    "confidential acquisition timing",
    "AKRETIC_EXEC_ONLY_CANARY_DO_NOT_SUMMARIZE",
)
PRIMARY_ARTIFACTS = (
    "raw/run.html",
    "raw/evidence-unauthorized.json",
    "raw/evidence-before-decision.json",
    "raw/evidence-before-decision.html",
    "raw/approval-unauthorized.html",
    "raw/approval-authorized.html",
    "raw/model-context-envelope.json",
    "raw/model-context-envelope.html",
    "raw/a2a-trust-receipt.json",
    "raw/a2a-trust-receipt.html",
    "raw/evidence-final.json",
    "raw/evidence-final.html",
    "raw/verify-final.json",
)
IDENTITY_SOURCE_LABEL = "demo identity adapter"
BROWSER_TRANSPORT_LABEL = "viewer persona selector"
VERIFIER_TRANSPORT_LABEL = "x-akretic-persona header"
CLOUD_UNKNOWN_FIELD_HINTS = (
    "project",
    "location",
    "revision",
    "model",
    "runtime",
    "cloud service",
    "cloud_run_service",
    "cloud run url",
    "service url",
    "corpus backend",
    "corpus",
)
REQUIRED_SERVICE_KEYS = ("demo_ui", "root", "policy", "knowledge", "research", "approval")
REQUIRED_AGENT_CARD_KEYS = ("policy", "knowledge", "research", "approval")
SERVICE_KEY_TO_CLOUD_RUN_SERVICE = {
    "demo_ui": "akretic-demo-ui",
    "root": "akretic-root-orchestrator",
    "policy": "akretic-policy-agent",
    "knowledge": "akretic-knowledge-agent",
    "research": "akretic-research-agent",
    "approval": "akretic-approval-evidence",
}
READYZ_ARTIFACTS = {
    "public": "raw/readyz-public.json",
    "deep": "raw/readyz-deep.json",
    "root": "raw/private-health-authenticated-root.json",
    "policy": "raw/private-health-authenticated-policy.json",
    "knowledge": "raw/private-health-authenticated-knowledge.json",
    "research": "raw/private-health-authenticated-research.json",
    "approval": "raw/private-health-authenticated-approval.json",
}
AGENT_CARD_ARTIFACTS = {
    "policy": "raw/agent-card-policy.json",
    "knowledge": "raw/agent-card-knowledge.json",
    "research": "raw/agent-card-research.json",
    "approval": "raw/agent-card-approval.json",
}
CLOUD_REQUIRED_PACKET_FILES = (
    "README.md",
    "FINAL_REVIEW.md",
    "manifest.json",
    "deploy-manifest.json",
    "forbidden-string-scan.json",
    "PROCESS_FLOW.md",
    "process-flowchart.html",
    "pytest-output.txt",
    "pytest-output.json",
    "p0-verify-output.txt",
    "p0-verify-output.json",
    "warmup-output.json",
    "readiness-burnin-output.json",
    "run-id-integrity.json",
    "deploy-manifest-integrity.json",
    "referenced-artifact-integrity.json",
    "final-review-integrity.json",
    "raw/readyz-public.json",
    "raw/readyz-deep.json",
    "raw/private-health-authenticated-root.json",
    "raw/private-health-authenticated-policy.json",
    "raw/private-health-authenticated-knowledge.json",
    "raw/private-health-authenticated-research.json",
    "raw/private-health-authenticated-approval.json",
    "raw/corpus-status.json",
    "raw/corpus-metadata.json",
    "raw/playground-allowed.json",
    "raw/playground-denied-executive-memo.json",
    "raw/playground-unsupported-intent.json",
    "raw/corpus-retrieval-allowed.json",
    "raw/corpus-retrieval-denied.json",
    "raw/model-context-envelope.json",
    "raw/a2a-trust-receipt.json",
    "raw/red-team-results.json",
    "screenshots/home.png",
    "screenshots/guided-run.png",
    "screenshots/evidence-before-decision.png",
    "screenshots/approval-unauthorized.png",
    "screenshots/approval-authorized.png",
    "screenshots/evidence-final-after-decision.png",
    "screenshots/corpus-explorer.png",
    "screenshots/corpus-retrieval-allowed.png",
    "screenshots/corpus-retrieval-denied.png",
    "screenshots/playground.png",
    "screenshots/playground-result-allowed.png",
    "screenshots/playground-result-denied.png",
    "screenshots/model-context-envelope.png",
    "screenshots/a2a-trust-receipt.png",
    "screenshots/red-team-executive-memo-denied.png",
    "screenshots/red-team-procurement-approval-denied.png",
    "screenshots/red-team-knowledge-no-receipt-403.png",
    "screenshots/red-team-tamper-detected.png",
    "screenshots/07-evidence-unauthorized.png",
    "screenshots/process-flowchart.png",
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _base(url: str) -> str:
    return url.rstrip("/")


def _packet_relative(packet_dir: Path, path: Path) -> str:
    return path.relative_to(packet_dir).as_posix()


def _contains_local(value: str) -> bool:
    lowered = value.lower()
    return any(token.lower() in lowered for token in LOCAL_TOKENS)


def _extract(pattern: str, text: str, label: str) -> str:
    match = re.search(pattern, text)
    if not match or not match.group(1).strip():
        raise RuntimeError(f"unable to extract {label}")
    return match.group(1).strip()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, value: Any) -> None:
    _write_text(path, json.dumps(value, indent=2, sort_keys=True))


def _local_pytest_env() -> dict[str, str]:
    env = os.environ.copy()
    for name in (
        "AKRETIC_CLOUD_RUN_AUTH",
        "AKRETIC_RUNTIME_MODE",
        "AKRETIC_GEMINI_MODE",
        "AKRETIC_CORPUS_BACKEND",
        "ROOT_ORCHESTRATOR_URL",
        "POLICY_AGENT_URL",
        "KNOWLEDGE_AGENT_URL",
        "RESEARCH_AGENT_URL",
        "APPROVAL_EVIDENCE_URL",
        "EVIDENCE_GCS_BUCKET",
        "EVIDENCE_GCS_PREFIX",
        "AKRETIC_EVIDENCE_BUCKET",
        "AKRETIC_EVIDENCE_PREFIX",
        "AKRETIC_CORPUS_BUCKET",
        "AKRETIC_CORPUS_PREFIX",
    ):
        env.pop(name, None)
    return env


def _run_command(command: list[str], *, cwd: Path, timeout: int, env: dict[str, str] | None = None) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat()
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    return {
        "command": command,
        "cwd": str(cwd),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "timestamp": started_at,
    }


def _service_urls(args: argparse.Namespace) -> dict[str, str]:
    return {
        "demo_ui": _base(args.base_url),
        "root": _base(args.root_url or os.getenv("ROOT_ORCHESTRATOR_URL", "http://127.0.0.1:8100")),
        "policy": _base(args.policy_url or os.getenv("POLICY_AGENT_URL", "http://127.0.0.1:8101")),
        "knowledge": _base(args.knowledge_url or os.getenv("KNOWLEDGE_AGENT_URL", "http://127.0.0.1:8102")),
        "research": _base(args.research_url or os.getenv("RESEARCH_AGENT_URL", "http://127.0.0.1:8103")),
        "approval": _base(args.approval_url or os.getenv("APPROVAL_EVIDENCE_URL", "http://127.0.0.1:8104")),
    }


def _assert_cloud_urls(urls: dict[str, str]) -> None:
    for name, url in urls.items():
        if not url:
            raise RuntimeError(f"cloud handoff requires {name} URL")
        if not url.startswith("https://"):
            raise RuntimeError(f"cloud handoff URL for {name} must be https")
        if _contains_local(url):
            raise RuntimeError(f"cloud handoff URL for {name} references a local endpoint")


def scan_forbidden_strings(packet_dir: Path, *, mode: str) -> list[dict[str, str]]:
    if mode != "cloud":
        return []
    findings: list[dict[str, str]] = []
    for path in packet_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() in {".png", ".zip"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in CLOUD_FORBIDDEN_TOKENS:
            if token in text:
                findings.append({"path": str(path), "token": token})
        for line in text.splitlines():
            lowered = line.lower()
            if "unknown" in lowered and any(
                field in lowered for field in CLOUD_UNKNOWN_FIELD_HINTS
            ):
                findings.append({"path": str(path), "token": "UNKNOWN", "line": line[:200]})
    return findings


def validate_required_packet_files(packet_dir: Path, *, mode: str) -> list[str]:
    if mode != "cloud":
        return []
    return [
        relative
        for relative in CLOUD_REQUIRED_PACKET_FILES
        if not (packet_dir / relative).exists()
    ]


def referenced_artifact_paths(packet_dir: Path) -> dict[str, list[str]]:
    references: dict[str, list[str]] = {}
    scanned = ("README.md", "FINAL_REVIEW.md", "PROCESS_FLOW.md", "manifest.json")
    pattern = re.compile(
        r"(?:raw|screenshots)/[A-Za-z0-9_.\\/-]+|"
        r"(?:README|FINAL_REVIEW|PROCESS_FLOW|manifest|deploy-manifest|deploy-manifest-integrity|"
        r"referenced-artifact-integrity|final-review-integrity|forbidden-string-scan|verifier-output|"
        r"run-id-integrity|process-flowchart|pytest-output|p0-verify-output|warmup-output|"
        r"warmup-command-output|readiness-burnin-output|readiness-burnin-command-output)"
        r"\.(?:md|json|txt|html|png)"
    )
    for relative in scanned:
        path = packet_dir / relative
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        refs = sorted(
            {
                match.group(0).replace("\\", "/")
                for match in pattern.finditer(text)
                if not match.group(0).startswith("http")
            }
        )
        references[relative] = refs
    return references


def validate_referenced_artifacts(packet_dir: Path, manifest: dict[str, Any], *, mode: str) -> list[dict[str, str]]:
    if mode != "cloud":
        return []
    failures: list[dict[str, str]] = []
    screenshots = manifest.get("screenshots")
    if not isinstance(screenshots, dict) or not screenshots:
        failures.append({"path": "manifest.json", "reference": "screenshots", "reason": "empty"})
    for source, refs in referenced_artifact_paths(packet_dir).items():
        for ref in refs:
            if not (packet_dir / ref).exists():
                failures.append({"path": source, "reference": ref, "reason": "missing"})
    return failures


def _artifact_body(packet_dir: Path, relative: str) -> Any:
    path = packet_dir / relative
    if not path.exists():
        return None
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if isinstance(artifact, dict) and "body" in artifact:
        return artifact.get("body")
    return artifact


def _record_mismatch(
    failures: list[dict[str, str]],
    *,
    field: str,
    expected: Any,
    actual: Any,
    source: str,
) -> None:
    if expected != actual:
        failures.append(
            {
                "field": field,
                "source": source,
                "expected": str(expected),
                "actual": str(actual),
            }
        )


def validate_deploy_manifest_consistency(
    packet_dir: Path,
    deploy_manifest: dict[str, Any],
    manifest: dict[str, Any],
    *,
    packet_zip_name: str,
    packet_generator_commit_sha: str,
    mode: str,
) -> list[dict[str, str]]:
    if mode != "cloud":
        return []
    failures: list[dict[str, str]] = []
    _record_mismatch(
        failures,
        field="deploy_manifest.commit_sha",
        expected=packet_generator_commit_sha,
        actual=deploy_manifest.get("commit_sha"),
        source="deploy-manifest.json",
    )
    _record_mismatch(
        failures,
        field="manifest.commit_sha",
        expected=packet_generator_commit_sha,
        actual=manifest.get("commit_sha"),
        source="manifest.json",
    )
    _record_mismatch(
        failures,
        field="image_digest",
        expected=deploy_manifest.get("image_digest"),
        actual=manifest.get("image_digest"),
        source="deploy-manifest.json",
    )
    _record_mismatch(
        failures,
        field="packet_filename",
        expected=packet_zip_name,
        actual=deploy_manifest.get("packet_filename"),
        source="deploy-manifest.json",
    )
    _record_mismatch(
        failures,
        field="corpus_backend",
        expected=deploy_manifest.get("corpus_backend"),
        actual=manifest.get("corpus_backend"),
        source="deploy-manifest.json",
    )

    deploy_model = deploy_manifest.get("model_metadata") if isinstance(deploy_manifest.get("model_metadata"), dict) else {}
    for deploy_field, manifest_field in (
        ("runtime_mode", "runtime_mode"),
        ("model_mode", "model_mode"),
        ("model", "model"),
        ("project_id", "project_label"),
        ("location", "location"),
    ):
        _record_mismatch(
            failures,
            field=f"model_metadata.{deploy_field}",
            expected=deploy_model.get(deploy_field),
            actual=manifest.get(manifest_field),
            source="deploy-manifest.json",
        )

    deploy_urls = deploy_manifest.get("service_urls") if isinstance(deploy_manifest.get("service_urls"), dict) else {}
    deploy_revisions = deploy_manifest.get("service_revisions") if isinstance(deploy_manifest.get("service_revisions"), dict) else {}
    for key, service in SERVICE_KEY_TO_CLOUD_RUN_SERVICE.items():
        _record_mismatch(
            failures,
            field=f"cloud_run_service_urls.{key}",
            expected=deploy_urls.get(service),
            actual=manifest.get("cloud_run_service_urls", {}).get(key),
            source="deploy-manifest.json",
        )
        _record_mismatch(
            failures,
            field=f"cloud_run_revisions.{key}",
            expected=deploy_revisions.get(service),
            actual=manifest.get("cloud_run_revisions", {}).get(key),
            source="deploy-manifest.json",
        )

    latest_model = manifest.get("model_metadata") if isinstance(manifest.get("model_metadata"), dict) else {}
    for model_field, manifest_field in (
        ("runtime_mode", "runtime_mode"),
        ("mode", "model_mode"),
        ("model", "model"),
        ("project_id", "project_label"),
        ("location", "location"),
    ):
        _record_mismatch(
            failures,
            field=f"evidence.latest_model.{model_field}",
            expected=manifest.get(manifest_field),
            actual=latest_model.get(model_field),
            source="raw/evidence-final.json",
        )

    readyz = _artifact_body(packet_dir, "raw/readyz-public.json")
    if not isinstance(readyz, dict):
        failures.append({"field": "readyz", "source": "raw/readyz-public.json", "expected": "dict", "actual": type(readyz).__name__})
        return failures
    for field in ("runtime_mode", "model_mode", "model", "corpus_backend"):
        _record_mismatch(
            failures,
            field=f"readyz.{field}",
            expected=manifest.get(field),
            actual=readyz.get(field),
            source="raw/readyz-public.json",
        )
    readyz_service_urls = readyz.get("service_urls") if isinstance(readyz.get("service_urls"), dict) else {}
    readyz_revisions = readyz.get("revision_map") if isinstance(readyz.get("revision_map"), dict) else {}
    for key in ("root", "policy", "knowledge", "research", "approval"):
        _record_mismatch(
            failures,
            field=f"readyz.service_urls.{key}",
            expected=manifest.get("cloud_run_service_urls", {}).get(key),
            actual=readyz_service_urls.get(key),
            source="raw/readyz-public.json",
        )
    for key in REQUIRED_SERVICE_KEYS:
        _record_mismatch(
            failures,
            field=f"readyz.revision_map.{key}",
            expected=manifest.get("cloud_run_revisions", {}).get(key),
            actual=readyz_revisions.get(key),
            source="raw/readyz-public.json",
        )
    readyz_checks = readyz.get("checks") if isinstance(readyz.get("checks"), dict) else {}
    corpus_check = readyz_checks.get("corpus_backend") if isinstance(readyz_checks.get("corpus_backend"), dict) else {}
    vertex_check = readyz_checks.get("vertex_config") if isinstance(readyz_checks.get("vertex_config"), dict) else {}
    _record_mismatch(
        failures,
        field="readyz.checks.corpus_backend.corpus_manifest_hash",
        expected=manifest.get("corpus_manifest_hash"),
        actual=corpus_check.get("corpus_manifest_hash"),
        source="raw/readyz-public.json",
    )
    _record_mismatch(
        failures,
        field="readyz.checks.corpus_backend.document_count",
        expected=manifest.get("corpus_document_count"),
        actual=corpus_check.get("document_count"),
        source="raw/readyz-public.json",
    )
    for readyz_field, manifest_field in (
        ("runtime_mode", "runtime_mode"),
        ("model_mode", "model_mode"),
        ("model", "model"),
        ("project_id", "project_label"),
        ("location", "location"),
    ):
        _record_mismatch(
            failures,
            field=f"readyz.checks.vertex_config.{readyz_field}",
            expected=manifest.get(manifest_field),
            actual=vertex_check.get(readyz_field),
            source="raw/readyz-public.json",
        )
    return failures


def validate_final_review_consistency(packet_dir: Path, manifest: dict[str, Any], *, mode: str) -> list[dict[str, str]]:
    if mode != "cloud":
        return []
    path = packet_dir / "FINAL_REVIEW.md"
    if not path.exists():
        return [{"field": "FINAL_REVIEW.md", "source": "FINAL_REVIEW.md", "expected": "present", "actual": "missing"}]
    text = path.read_text(encoding="utf-8", errors="ignore")
    required_fragments = [
        f"- commit SHA: `{manifest['commit_sha']}`",
        f"- build ID: `{manifest.get('build_id')}`",
        f"- image digest: `{manifest.get('image_digest')}`",
        f"- model mode: `{manifest['model_mode']}`",
        f"- runtime mode: `{manifest['runtime_mode']}`",
        f"- corpus backend: `{manifest.get('corpus_backend')}`",
        f"- corpus manifest hash: `{manifest.get('corpus_manifest_hash')}`",
    ]
    required_fragments.extend(
        f"- `{key}`: {value}" for key, value in manifest.get("cloud_run_service_urls", {}).items()
    )
    required_fragments.extend(
        f"- `{key}`: {value}" for key, value in manifest.get("cloud_run_revisions", {}).items()
    )
    return [
        {
            "field": "FINAL_REVIEW.md",
            "source": "FINAL_REVIEW.md",
            "expected": fragment,
            "actual": "missing",
        }
        for fragment in required_fragments
        if fragment not in text
    ]


def _extract_verifier_run_id(verifier: dict[str, Any]) -> str | None:
    match = re.search(r"FINAL_REVIEW:\s+P0 VERIFY PASSED run_id=([^\s]+)", verifier.get("stdout", ""))
    return match.group(1) if match else None


def _git_commit_sha(repo_root: Path) -> str:
    result = _run_command(["git", "rev-parse", "HEAD"], cwd=repo_root, timeout=30)
    if result["returncode"] != 0:
        return "UNKNOWN"
    return result["stdout"].strip() or "UNKNOWN"


def _cloud_run_revisions(args: argparse.Namespace) -> dict[str, str]:
    return {
        "demo_ui": args.demo_ui_revision or os.getenv("DEMO_UI_REVISION", "UNKNOWN"),
        "root": args.root_revision or os.getenv("ROOT_ORCHESTRATOR_REVISION", "UNKNOWN"),
        "policy": args.policy_revision or os.getenv("POLICY_AGENT_REVISION", "UNKNOWN"),
        "knowledge": args.knowledge_revision or os.getenv("KNOWLEDGE_AGENT_REVISION", "UNKNOWN"),
        "research": args.research_revision or os.getenv("RESEARCH_AGENT_REVISION", "UNKNOWN"),
        "approval": args.approval_revision or os.getenv("APPROVAL_EVIDENCE_REVISION", "UNKNOWN"),
    }


def _agent_card_urls(urls: dict[str, str]) -> dict[str, str]:
    return {
        "policy": f"{urls['policy']}/.well-known/agent-card.json",
        "knowledge": f"{urls['knowledge']}/.well-known/agent-card.json",
        "research": f"{urls['research']}/.well-known/agent-card.json",
        "approval": f"{urls['approval']}/.well-known/agent-card.json",
    }


def _service_headers(name: str, base_url: str, mode: str) -> dict[str, str] | None:
    if mode == "cloud" and name != "demo_ui":
        return cloud_run_auth_headers(base_url)
    return None


def _response_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        text = response.text
        return text if len(text) <= 8000 else text[:8000] + "\n[truncated]"


def _captured_response(
    *,
    service: str,
    route: str,
    response: httpx.Response,
    authenticated: bool,
) -> dict[str, Any]:
    return {
        "service": service,
        "route": route,
        "url": str(response.url),
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type", ""),
        "authenticated": authenticated,
        "auth_mode": "identity_token" if authenticated else "none",
        "body": _response_body(response),
    }


def _omit_cloud_health_body_if_non_success(artifact: dict[str, Any], *, mode: str) -> dict[str, Any]:
    if mode == "cloud" and int(artifact.get("status_code") or 0) != 200:
        artifact["body"] = ""
        artifact["body_omitted"] = "non-200 Cloud Run boundary probe body omitted from handoff packet"
    return artifact


def _capture_cloud_service_artifacts(
    urls: dict[str, str],
    packet_dir: Path,
    *,
    mode: str,
    timeout: float,
) -> dict[str, str]:
    captured: dict[str, str] = {}
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for label, route in (("public", "/readyz"), ("deep", "/readyz")):
            response = client.get(f"{urls['demo_ui']}{route}")
            artifact = _captured_response(
                service="demo_ui",
                route=route,
                response=response,
                authenticated=False,
            )
            if response.status_code != 200:
                raise RuntimeError(f"public {route} readiness check returned HTTP {response.status_code}")
            relative = READYZ_ARTIFACTS[label]
            _write_json(packet_dir / relative, artifact)
            captured[f"readyz_{label}"] = relative

        for name in ("root", "policy", "knowledge", "research", "approval"):
            base_url = urls[name]
            headers = _service_headers(name, base_url, mode)
            authenticated = bool(headers and headers.get("Authorization"))
            route = "/readyz" if mode == "cloud" else "/healthz"
            response = client.get(f"{base_url}{route}", headers=headers)
            artifact = _captured_response(
                service=name,
                route=route,
                response=response,
                authenticated=authenticated,
            )
            if response.status_code != 200:
                raise RuntimeError(f"{name} authenticated readiness check returned HTTP {response.status_code}")
            relative = READYZ_ARTIFACTS[name]
            _write_json(packet_dir / relative, artifact)
            captured[f"readyz_{name}"] = relative

        for name, relative in AGENT_CARD_ARTIFACTS.items():
            base_url = urls[name]
            headers = _service_headers(name, base_url, mode)
            authenticated = bool(headers and headers.get("Authorization"))
            routes: dict[str, Any] = {}
            for route in ("/.well-known/agent-card.json", "/agent.json"):
                response = client.get(f"{base_url}{route}", headers=headers)
                routes[route] = _captured_response(
                    service=name,
                    route=route,
                    response=response,
                    authenticated=authenticated,
                )
                if response.status_code != 200:
                    raise RuntimeError(f"{name} Agent Card route {route} returned HTTP {response.status_code}")
            _write_json(
                packet_dir / relative,
                {
                    "service": name,
                    "base_url": base_url,
                    "authenticated": authenticated,
                    "auth_mode": "identity_token" if authenticated else "none",
                    "routes": routes,
                },
            )
            captured[f"agent_card_{name}"] = relative
    return captured


def _run_ids_in_text(text: str) -> set[str]:
    return set(re.findall(r"run_(?!id\b)[A-Za-z0-9]+", text))


def validate_primary_run_integrity(packet_dir: Path, judge_run_id: str) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for relative in PRIMARY_ARTIFACTS:
        path = packet_dir / relative
        if not path.exists():
            failures.append({"path": relative, "reason": "missing"})
            continue
        run_ids = _run_ids_in_text(path.read_text(encoding="utf-8", errors="ignore"))
        if judge_run_id not in run_ids:
            failures.append({"path": relative, "reason": "judge_run_id missing", "run_ids": sorted(run_ids)})
        extra = sorted(run_ids - {judge_run_id})
        if extra:
            failures.append({"path": relative, "reason": "mixed run IDs", "run_ids": extra})
    return failures


def _capture_judge_flow(
    base_url: str,
    knowledge_url: str,
    packet_dir: Path,
    *,
    mode: str,
    timeout: float,
) -> dict[str, Any]:
    raw_dir = packet_dir / "raw"
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        home = client.get(f"{base_url}/")
        home.raise_for_status()
        _write_text(raw_dir / "home.html", home.text)

        corpus_status = client.get(f"{base_url}/corpus/status")
        corpus_status.raise_for_status()
        _write_text(raw_dir / "corpus-status.json", corpus_status.text)

        corpus_metadata = client.get(f"{base_url}/corpus/metadata.json")
        corpus_metadata.raise_for_status()
        _write_text(raw_dir / "corpus-metadata.json", corpus_metadata.text)

        corpus_explorer = client.get(f"{base_url}/corpus")
        corpus_explorer.raise_for_status()
        _write_text(raw_dir / "corpus-explorer.html", corpus_explorer.text)

        playground_allowed = client.post(
            f"{base_url}/playground/run",
            data={
                "persona": "procurement_user",
                "vendor_id": "vendornova",
                "prompt": "Summarize VendorNova risk for procurement.",
            },
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        playground_allowed.raise_for_status()
        _write_text(raw_dir / "playground-freeform-allowed.html", playground_allowed.text)

        playground_allowed_json = client.post(
            f"{base_url}/playground/run.json",
            json={
                "persona": "procurement_user",
                "vendor_id": "vendornova",
                "prompt": "Summarize VendorNova risk for procurement.",
            },
        )
        playground_allowed_json.raise_for_status()
        _write_text(raw_dir / "playground-allowed.json", playground_allowed_json.text)

        playground_denied = client.post(
            f"{base_url}/playground/run",
            data={
                "persona": "procurement_user",
                "vendor_id": "vendornova",
                "prompt": "Can I see the executive acquisition memo?",
            },
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        playground_denied.raise_for_status()
        _write_text(raw_dir / "playground-freeform-denied.html", playground_denied.text)

        playground_denied_json = client.post(
            f"{base_url}/playground/run.json",
            json={
                "persona": "procurement_user",
                "vendor_id": "vendornova",
                "prompt": "Can I see the executive acquisition memo?",
            },
        )
        playground_denied_json.raise_for_status()
        _write_text(raw_dir / "playground-denied-executive-memo.json", playground_denied_json.text)

        playground_unsupported = client.post(
            f"{base_url}/playground/run.json",
            json={
                "persona": "procurement_user",
                "vendor_id": "vendornova",
                "prompt": "Schedule lunch and order office chairs.",
            },
        )
        playground_unsupported.raise_for_status()
        _write_text(raw_dir / "playground-unsupported-intent.json", playground_unsupported.text)

        corpus_allowed = client.post(
            f"{base_url}/corpus/retrieve-result",
            data={"persona": "security_reviewer", "source_id": "vendornova_profile"},
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        corpus_allowed.raise_for_status()
        _write_text(raw_dir / "corpus-retrieval-allowed.html", corpus_allowed.text)

        corpus_allowed_json = client.post(
            f"{base_url}/corpus/retrieve",
            json={"persona": "security_reviewer", "source_id": "vendornova_profile"},
        )
        corpus_allowed_json.raise_for_status()
        _write_text(raw_dir / "corpus-retrieval-allowed.json", corpus_allowed_json.text)

        corpus_denied = client.post(
            f"{base_url}/corpus/retrieve-result",
            data={"persona": "procurement_user", "source_id": "executive_acquisition_memo"},
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        corpus_denied.raise_for_status()
        _write_text(raw_dir / "corpus-retrieval-denied.html", corpus_denied.text)

        corpus_denied_json = client.post(
            f"{base_url}/corpus/retrieve",
            json={"persona": "procurement_user", "source_id": "executive_acquisition_memo"},
        )
        corpus_denied_json.raise_for_status()
        _write_text(raw_dir / "corpus-retrieval-denied.json", corpus_denied_json.text)

        red_team = client.post(
            f"{base_url}/red-team/run",
            data={"challenge": "prompt_injection_export"},
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        red_team.raise_for_status()
        _write_text(raw_dir / "red-team-challenge.html", red_team.text)

        red_team_json_results = []
        for challenge in (
            "self_assert_admin",
            "executive_memo",
            "retrieve_all",
            "prompt_injection_export",
            "approve_as_procurement",
            "knowledge_without_receipt",
            "unauthorized_evidence",
            "tamper_evidence",
        ):
            response = client.post(
                f"{base_url}/red-team/run",
                data={"challenge": challenge},
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            _write_text(raw_dir / f"red-team-{challenge}.html", response.text)
            json_response = client.post(f"{base_url}/red-team/run.json", json={"challenge": challenge})
            json_response.raise_for_status()
            red_team_json_results.append(json_response.json())

        _write_json(raw_dir / "red-team-results.json", {"results": red_team_json_results})

        knowledge_headers = _service_headers("knowledge", knowledge_url, mode)
        knowledge_no_receipt = client.post(
            f"{knowledge_url}/retrieve_permitted_context",
            json={
                "persona": "procurement_user",
                "query": "VendorNova",
                "write_evidence": False,
                "run_id": "handoff-knowledge-no-receipt",
            },
            headers={**(knowledge_headers or {}), "x-akretic-persona": "procurement_user"},
        )
        _write_json(
            raw_dir / "knowledge-no-receipt-403.json",
            {
                "status_code": knowledge_no_receipt.status_code,
                "body": _response_body(knowledge_no_receipt),
            },
        )
        knowledge_invalid_receipt = client.post(
            f"{knowledge_url}/retrieve_permitted_context",
            json={
                "persona": "procurement_user",
                "query": "VendorNova",
                "write_evidence": False,
                "run_id": "handoff-knowledge-invalid-receipt",
                "policy_decision_receipt": {
                    "payload": {
                        "decision_id": "invalid",
                        "run_id": "handoff-knowledge-invalid-receipt",
                        "actor_id": "procurement_user",
                        "action": "retrieve_internal",
                        "resource_id": "vendornova_review_context",
                        "outcome": "allow",
                        "expires_at": "2999-01-01T00:00:00Z",
                    },
                    "hmac": "invalid",
                },
            },
            headers={**(knowledge_headers or {}), "x-akretic-persona": "procurement_user"},
        )
        _write_json(
            raw_dir / "knowledge-invalid-receipt-403.json",
            {
                "status_code": knowledge_invalid_receipt.status_code,
                "body": _response_body(knowledge_invalid_receipt),
            },
        )

        run_response = client.post(
            f"{base_url}/run",
            data={
                "persona": "procurement_user",
                "query": "VendorNova procurement security policy",
            },
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        run_response.raise_for_status()
        _write_text(raw_dir / "run.html", run_response.text)

        run_id = _extract(r"<span>Run ID</span><strong>([^<]+)</strong>", run_response.text, "run_id")
        approval_id = _extract(r'name="approval_id" value="([^"]+)"', run_response.text, "approval_id")

        evidence_unauthorized = client.get(
            f"{base_url}/evidence/{run_id}.json",
            params={"viewer_persona": "procurement_user"},
        )
        if evidence_unauthorized.status_code != 403:
            raise RuntimeError(
                f"unauthorized evidence proof returned HTTP {evidence_unauthorized.status_code}, expected 403"
            )
        try:
            unauthorized_body: Any = evidence_unauthorized.json()
        except ValueError:
            unauthorized_body = evidence_unauthorized.text
        _write_json(
            raw_dir / "evidence-unauthorized.json",
            {
                "run_id": run_id,
                "status_code": evidence_unauthorized.status_code,
                "url": str(evidence_unauthorized.url),
                "body": unauthorized_body,
            },
        )

        evidence = client.get(
            f"{base_url}/evidence/{run_id}.json",
            headers={"x-akretic-persona": "security_reviewer"},
        )
        evidence.raise_for_status()
        _write_text(raw_dir / "evidence-before-decision.json", evidence.text)

        evidence_html = client.get(
            f"{base_url}/evidence/{run_id}",
            headers={"x-akretic-persona": "security_reviewer"},
        )
        evidence_html.raise_for_status()
        _write_text(raw_dir / "evidence-before-decision.html", evidence_html.text)

        unauthorized = client.post(
            f"{base_url}/approval/decide",
            data={
                "run_id": run_id,
                "approval_id": approval_id,
                "reviewer_persona": "procurement_user",
                "status": "approved",
                "reason": "final handoff unauthorized reviewer proof",
            },
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        unauthorized.raise_for_status()
        _write_text(raw_dir / "approval-unauthorized.html", unauthorized.text)

        authorized = client.post(
            f"{base_url}/approval/decide",
            data={
                "run_id": run_id,
                "approval_id": approval_id,
                "reviewer_persona": "security_reviewer",
                "status": "approved",
                "reason": "final handoff reviewer proof",
            },
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        authorized.raise_for_status()
        _write_text(raw_dir / "approval-authorized.html", authorized.text)

        verify = client.get(
            f"{base_url}/verify/{run_id}",
            headers={"x-akretic-persona": "security_reviewer"},
        )
        verify.raise_for_status()
        _write_text(raw_dir / "verify-final.json", verify.text)

        envelope = client.get(
            f"{base_url}/runs/{run_id}/model-context-envelope",
            headers={"x-akretic-persona": "security_reviewer"},
        )
        envelope.raise_for_status()
        _write_text(raw_dir / "model-context-envelope.json", envelope.text)
        envelope_html = client.get(
            f"{base_url}/runs/{run_id}/model-context-envelope.html",
            headers={"x-akretic-persona": "security_reviewer"},
        )
        envelope_html.raise_for_status()
        _write_text(raw_dir / "model-context-envelope.html", envelope_html.text)

        trust_receipt = client.get(
            f"{base_url}/runs/{run_id}/a2a-trust-receipt.json",
            headers={"x-akretic-persona": "security_reviewer"},
        )
        trust_receipt.raise_for_status()
        _write_text(raw_dir / "a2a-trust-receipt.json", trust_receipt.text)

        trust_receipt_html = client.get(
            f"{base_url}/runs/{run_id}/a2a-trust-receipt.html",
            headers={"x-akretic-persona": "security_reviewer"},
        )
        trust_receipt_html.raise_for_status()
        _write_text(raw_dir / "a2a-trust-receipt.html", trust_receipt_html.text)

        final_evidence = client.get(
            f"{base_url}/evidence/{run_id}.json",
            headers={"x-akretic-persona": "security_reviewer"},
        )
        final_evidence.raise_for_status()
        _write_text(raw_dir / "evidence-final.json", final_evidence.text)

        final_evidence_html = client.get(
            f"{base_url}/evidence/{run_id}",
            headers={"x-akretic-persona": "security_reviewer"},
        )
        final_evidence_html.raise_for_status()
        _write_text(raw_dir / "evidence-final.html", final_evidence_html.text)

    final_report = final_evidence.json()
    final_events = final_report.get("events", [])
    final_head_hash = final_report.get("verification", {}).get("head_hash")
    if final_events and final_head_hash != final_events[-1].get("event_hash"):
        raise RuntimeError("final evidence head_hash does not match final event hash")
    if final_report.get("verification", {}).get("valid") is not True:
        raise RuntimeError("final evidence verification is not valid")
    if not final_report.get("summary", {}).get("reviewer_decisions"):
        raise RuntimeError("final evidence reviewer_decisions is empty")
    if not any(event.get("outcome") == "not_recorded" for event in final_events):
        raise RuntimeError("final evidence missing unauthorized approval attempt")
    if not any(event.get("outcome") in {"approved", "rejected"} for event in final_events):
        raise RuntimeError("final evidence missing authorized approval decision")
    if not any(
        isinstance(event.get("metadata"), dict)
        and event.get("metadata", {}).get("external_egress_performed") is False
        for event in final_events
    ):
        raise RuntimeError("final evidence missing external_egress_performed=false")
    if knowledge_no_receipt.status_code != 403:
        raise RuntimeError("knowledge agent accepted retrieval without a policy receipt")
    if knowledge_invalid_receipt.status_code != 403:
        raise RuntimeError("knowledge agent accepted an invalid policy receipt")

    return {
        "judge_run_id": run_id,
        "approval_id": approval_id,
        "latest_model": final_report.get("summary", {}).get("latest_model", {}),
        "verification": verify.json(),
        "final_report": final_report,
    }


def _capture_screenshots_from_artifacts(packet_dir: Path, timeout_ms: int) -> dict[str, str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required for final handoff screenshots") from exc

    screenshot_dir = packet_dir / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = packet_dir / "raw"
    pages = [
        ("home", "home.png", raw_dir / "home.html", False),
        ("guided_run", "guided-run.png", raw_dir / "run.html", False),
        ("evidence_before_decision", "evidence-before-decision.png", raw_dir / "evidence-before-decision.html", False),
        ("approval_unauthorized", "approval-unauthorized.png", raw_dir / "approval-unauthorized.html", False),
        ("approval_authorized", "approval-authorized.png", raw_dir / "approval-authorized.html", False),
        ("evidence_final_after_decision", "evidence-final-after-decision.png", raw_dir / "evidence-final.html", False),
        ("evidence_unauthorized", "07-evidence-unauthorized.png", raw_dir / "evidence-unauthorized.json", False),
        ("corpus_explorer", "corpus-explorer.png", raw_dir / "corpus-explorer.html", False),
        ("corpus_retrieval_allowed", "corpus-retrieval-allowed.png", raw_dir / "corpus-retrieval-allowed.html", False),
        ("corpus_retrieval_denied", "corpus-retrieval-denied.png", raw_dir / "corpus-retrieval-denied.html", False),
        ("playground", "playground.png", raw_dir / "playground-freeform-allowed.html", False),
        ("playground_result_allowed", "playground-result-allowed.png", raw_dir / "playground-freeform-allowed.html", False),
        ("playground_result_denied", "playground-result-denied.png", raw_dir / "playground-freeform-denied.html", False),
        ("model_context_envelope", "model-context-envelope.png", raw_dir / "model-context-envelope.html", False),
        ("a2a_trust_receipt", "a2a-trust-receipt.png", raw_dir / "a2a-trust-receipt.html", True),
        ("red_team_self_assert_admin", "red-team-self-assert-admin.png", raw_dir / "red-team-self_assert_admin.html", False),
        ("red_team_executive_memo_denied", "red-team-executive-memo-denied.png", raw_dir / "red-team-executive_memo.html", False),
        ("red_team_retrieve_all_filtered", "red-team-retrieve-all-filtered.png", raw_dir / "red-team-retrieve_all.html", False),
        ("red_team_prompt_injection_approval_required", "red-team-prompt-injection-approval-required.png", raw_dir / "red-team-prompt_injection_export.html", False),
        ("red_team_procurement_approval_denied", "red-team-procurement-approval-denied.png", raw_dir / "red-team-approve_as_procurement.html", False),
        ("red_team_knowledge_no_receipt_403", "red-team-knowledge-no-receipt-403.png", raw_dir / "red-team-knowledge_without_receipt.html", False),
        ("red_team_unauthorized_evidence_403", "red-team-unauthorized-evidence-403.png", raw_dir / "red-team-unauthorized_evidence.html", False),
        ("red_team_tamper_detected", "red-team-tamper-detected.png", raw_dir / "red-team-tamper_evidence.html", False),
        ("process_flowchart", "process-flowchart.png", packet_dir / "process-flowchart.html", False),
    ]
    captured: dict[str, str] = {"source": "primary raw artifacts"}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1024})
        page.set_default_timeout(timeout_ms)
        for key, filename, html_path, full_page in pages:
            if not html_path.exists():
                continue
            source = html_path.read_text(encoding="utf-8")
            if html_path.suffix.lower() == ".json":
                source = html.escape(source)
                source = (
                    "<!doctype html><html><head><meta charset=\"utf-8\">"
                    "<style>body{font-family:Inter,ui-sans-serif,system-ui;margin:32px;"
                    "background:#f6f7f9;color:#111827}pre{white-space:pre-wrap;"
                    "overflow-wrap:anywhere;background:#fff;border:1px solid #d9dee7;"
                    "border-radius:8px;padding:18px;line-height:1.45}</style></head>"
                    f"<body><h1>{filename}</h1><pre>{source}</pre></body></html>"
                )
            page.set_content(source, wait_until="load")
            target = screenshot_dir / filename
            page.screenshot(path=str(target), full_page=full_page)
            captured[key] = _packet_relative(packet_dir, target)
        browser.close()
    return captured


def _process_flowchart_html(mode: str, urls: dict[str, str]) -> str:
    service_rows = "".join(
        f"<tr><td>{html.escape(name)}</td><td>{html.escape(url)}</td></tr>"
        for name, url in urls.items()
    )
    return f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Akretic A2A Trust Gateway Process Flowchart</title>
  <style>
    body {{
      margin: 0;
      background: #f6f7f9;
      color: #111827;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 30px 24px 44px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; }}
    p {{ color: #4b5563; line-height: 1.5; }}
    .flow {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin: 24px 0;
    }}
    .node {{
      background: #fff;
      border: 1px solid #d9dee7;
      border-radius: 8px;
      padding: 14px;
      min-height: 122px;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
      position: relative;
    }}
    .node strong {{ display: block; margin-bottom: 8px; font-size: 15px; }}
    .node span {{ display: block; color: #4b5563; font-size: 13px; line-height: 1.4; }}
    .node.ok {{ border-left: 5px solid #166534; }}
    .node.warn {{ border-left: 5px solid #b45309; }}
    .node.deny {{ border-left: 5px solid #b91c1c; }}
    .node.info {{ border-left: 5px solid #1d4ed8; }}
    .arrow {{
      display: flex;
      align-items: center;
      justify-content: center;
      color: #64748b;
      font-weight: 800;
      font-size: 18px;
    }}
    .table-wrap {{ overflow-x: auto; background: #fff; border: 1px solid #d9dee7; border-radius: 8px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 9px 12px; border-bottom: 1px solid #e5e7eb; text-align: left; font-size: 13px; }}
    th {{ color: #374151; background: #f9fafb; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
  </style>
</head>
<body>
<main>
  <h1>Akretic A2A Trust Gateway Process Flowchart</h1>
  <p>
    Runtime mode: <code>{html.escape(mode)}</code>. This challenge prototype shows
    policy-mediated A2A collaboration, permission-preserving retrieval,
    approval-gated side effects, and tamper-evident evidence over a synthetic corpus.
  </p>
  <section class="flow" aria-label="Akretic proof process flow">
    <div class="node info"><strong>1. Demo Identity</strong><span>Browser persona selector or verifier header derives the actor. Request-body claims do not upgrade access.</span></div>
    <div class="node warn"><strong>2. Policy Agent</strong><span>Gate0-lite returns allow, deny, or approval_required and issues decision receipts.</span></div>
    <div class="node deny"><strong>3. Knowledge Agent</strong><span>Restricted chunks are filtered before model context; denied source IDs remain visible as proof.</span></div>
    <div class="node info"><strong>4. Research Agent</strong><span>Seeded allowlisted public snippets are returned through the same A2A evidence path.</span></div>
    <div class="node ok"><strong>5. Root Orchestrator</strong><span>Gemini summarizes only permitted model context after policy, retrieval, and research controls.</span></div>
    <div class="node warn"><strong>6. Approval/Evidence</strong><span>External action pauses at approval_required; unauthorized reviewer attempts are not_recorded.</span></div>
    <div class="node ok"><strong>7. Authorized Decision</strong><span>security_reviewer records the decision; no external egress is performed in this prototype.</span></div>
    <div class="node ok"><strong>8. Verify And Packet</strong><span>Hash chain, head hash, A2A Trust Receipt, screenshots, pytest, burn-in, and forbidden scans are packaged.</span></div>
  </section>
  <h2>Service Map</h2>
  <div class="table-wrap">
    <table>
      <thead><tr><th>Service</th><th>URL</th></tr></thead>
      <tbody>{service_rows}</tbody>
    </table>
  </div>
</main>
</body>
</html>
""".strip() + "\n"


def _process_notes(mode: str) -> str:
    return f"""
# Akretic A2A Trust Gateway Review Process

Runtime mode: `{mode}`

## Process Summary

1. Browser persona or verifier header is translated by the demo identity adapter.
2. Policy Agent evaluates governed actions before retrieval, research, approval, or evidence access.
3. Knowledge Agent filters the synthetic corpus before any model context is assembled.
4. Research Agent returns seeded allowlisted public snippets for the VendorNova proof path.
5. Root Orchestrator calls Vertex Gemini only after permitted context is assembled.
6. Approval/Evidence Agent records approval_required, unauthorized not_recorded attempts, authorized reviewer decisions, and verify/report actions.
7. The final packet includes raw responses, screenshots, pytest output, P0 verifier output, warmup, burn-in, deploy manifest, forbidden-string scan, and run-ID integrity evidence.

## Review Surfaces

- `process-flowchart.html`
- `screenshots/process-flowchart.png`
- `FINAL_REVIEW.md`
- `manifest.json`
- `deploy-manifest.json`
- `readiness-burnin-output.json`
- `warmup-output.json`
- `raw/a2a-trust-receipt.json`
- `raw/evidence-final.json`
""".strip() + "\n"


def _validate_cloud_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("packet_type") != "cloud_judge_proof":
        raise RuntimeError("cloud manifest packet_type must be cloud_judge_proof")
    if manifest.get("runtime_mode") != "cloud":
        raise RuntimeError("cloud manifest runtime_mode must be cloud")
    if manifest.get("model_mode") != "vertex":
        raise RuntimeError("cloud manifest model_mode must be vertex")
    for field in ("model", "project_label", "location", "commit_sha"):
        value = str(manifest.get(field) or "")
        if not value or value == "UNKNOWN":
            raise RuntimeError(f"cloud manifest missing {field}")
    if "gemini" not in str(manifest.get("model", "")).lower():
        raise RuntimeError("cloud manifest model must identify a Gemini/Vertex model")
    if manifest.get("corpus_backend") != "gcs":
        raise RuntimeError("cloud manifest corpus_backend must be gcs")
    if not manifest.get("corpus_manifest_hash"):
        raise RuntimeError("cloud manifest missing corpus_manifest_hash")
    for field in ("warmup_output", "readiness_burnin_output", "deploy_manifest", "image_digest", "build_id"):
        if not manifest.get(field):
            raise RuntimeError(f"cloud manifest missing {field}")
    if not str(manifest.get("image_digest", "")).startswith("sha256:"):
        raise RuntimeError("cloud manifest image_digest must be immutable sha256 digest")
    for field, expected in (
        ("identity_source", IDENTITY_SOURCE_LABEL),
        ("browser_transport", BROWSER_TRANSPORT_LABEL),
        ("verifier_transport", VERIFIER_TRANSPORT_LABEL),
    ):
        if manifest.get(field) != expected:
            raise RuntimeError(f"cloud manifest {field} must be {expected}")
    for name in REQUIRED_SERVICE_KEYS:
        if name not in manifest.get("cloud_run_service_urls", {}):
            raise RuntimeError(f"cloud manifest missing Cloud Run URL for {name}")
        if name not in manifest.get("cloud_run_revisions", {}):
            raise RuntimeError(f"cloud manifest missing Cloud Run revision for {name}")
    for name in REQUIRED_AGENT_CARD_KEYS:
        if name not in manifest.get("a2a_agent_card_urls", {}):
            raise RuntimeError(f"cloud manifest missing Agent Card URL for {name}")
    for name, url in manifest.get("cloud_run_service_urls", {}).items():
        if not url or _contains_local(str(url)) or not str(url).startswith("https://"):
            raise RuntimeError(f"cloud manifest has invalid Cloud Run URL for {name}")
    for name, revision in manifest.get("cloud_run_revisions", {}).items():
        if not revision or revision in {"UNKNOWN", "not_reported"}:
            raise RuntimeError(f"cloud manifest missing Cloud Run revision for {name}")
    min_instances = manifest.get("min_instances", {})
    for service in (
        "akretic-demo-ui",
        "akretic-root-orchestrator",
        "akretic-policy-agent",
        "akretic-knowledge-agent",
        "akretic-research-agent",
        "akretic-approval-evidence",
    ):
        if service not in min_instances:
            raise RuntimeError(f"cloud manifest missing min instance setting for {service}")
    for name, url in manifest.get("a2a_agent_card_urls", {}).items():
        if not url or _contains_local(str(url)) or not str(url).startswith("https://"):
            raise RuntimeError(f"cloud manifest has invalid Agent Card URL for {name}")
        if not str(url).endswith("/.well-known/agent-card.json"):
            raise RuntimeError(f"cloud manifest Agent Card URL for {name} is not public Agent Card route")


def _packet_readme(manifest: dict[str, Any]) -> str:
    urls = manifest["cloud_run_service_urls"]
    is_cloud = manifest["packet_type"] == "cloud_judge_proof"
    demo_url_label = "Public demo URL" if is_cloud else "Local demo URL"
    demo_url_instruction = "Open the public demo URL." if is_cloud else "Open the local demo URL."
    service_map_label = "Cloud Run Service Map" if is_cloud else "Local Service Map"
    model_path_label = "Vertex Model Path" if is_cloud else "Model Path"
    agent_cards = {
        "Policy": manifest["a2a_agent_card_urls"]["policy"],
        "Knowledge": manifest["a2a_agent_card_urls"]["knowledge"],
        "Research": manifest["a2a_agent_card_urls"]["research"],
        "Approval/Evidence": manifest["a2a_agent_card_urls"]["approval"],
    }
    service_map = "\n".join(f"- `{name}`: {url}" for name, url in urls.items())
    card_map = "\n".join(f"- {name}: {url}" for name, url in agent_cards.items())
    verifier_extra_flags = (
        f"--expect-corpus-backend {'gcs' if is_cloud else 'local'} "
        "--expect-freeform-playground --expect-corpus-explorer "
        "--expect-corpus-live-retrieval --expect-decision-receipts "
        "--expect-trust-receipt --expect-model-context-envelope --expect-red-team-cards"
    )
    cloud_flags = "--expect-vertex --fail-on-local " if is_cloud else ""
    verifier_command = (
        "python scripts/p0_verify.py "
        f"--base-url {urls['demo_ui']} --mode {manifest['mode']} "
        f"--root-url {urls['root']} --policy-url {urls['policy']} "
        f"--knowledge-url {urls['knowledge']} --research-url {urls['research']} "
        f"--approval-url {urls['approval']} {cloud_flags}{verifier_extra_flags}"
    )
    bash_verifier = (
        "export AKRETIC_CLOUD_RUN_AUTH=identity_token\n"
        f"{verifier_command}"
    )
    powershell_verifier = (
        '$env:AKRETIC_CLOUD_RUN_AUTH = "identity_token"\n'
        f"{verifier_command}"
    )
    return f"""
# Akretic A2A Trust Gateway Handoff Packet

{demo_url_label}: {urls["demo_ui"]}

Repository URL: not embedded in this packet; use the submission record or source checkout.

No login is required for the public demo UI. Use the built-in demo persona
selector for browser review; evidence and verify links require one of the
reviewer/admin demo personas listed below.

## Demo Personas

- `procurement_user`: starts the VendorNova review and is blocked from executive-only context.
- `security_reviewer`: records the approval decision and can view evidence.
- `legal_reviewer`: demo persona for legal review boundaries.
- `admin`: demo admin/reviewer evidence persona.

## Two-Minute Judge Path

1. {demo_url_instruction}
2. Keep persona `procurement_user` and start the VendorNova review.
3. Confirm Policy, Knowledge, Research, and Approval/Evidence A2A calls are visible.
4. Confirm `executive_acquisition_memo` is denied before model context.
5. Confirm `approval_required` appears before the external action.
6. Record one unauthorized reviewer attempt, then record `security_reviewer`.
7. Open the current-run evidence report and verify the hash chain.

## P0 Verifier

For Bash or Git Bash:

```bash
{bash_verifier}
```

For PowerShell:

```powershell
{powershell_verifier}
```

The exact captured Windows verifier command is recorded in `FINAL_REVIEW.md`.

## {service_map_label}

{service_map}

## {model_path_label}

- runtime mode: `{manifest["runtime_mode"]}`
- model mode: `{manifest["model_mode"]}`
- model: `{manifest["model"]}`
- project/location: `{manifest["project_label"]}` / `{manifest["location"]}`
- corpus backend: `{manifest.get("corpus_backend")}`
- corpus manifest hash: `{manifest.get("corpus_manifest_hash")}`
- corpus document count: `{manifest.get("corpus_document_count")}`

## A2A Agent Card Endpoints

{card_map}

## Identity And Transport

- identity_source: `{manifest["identity_source"]}`
- browser_transport: `{manifest["browser_transport"]}`
- verifier_transport: `{manifest["verifier_transport"]}`

## Direct Private Service Checks

The verifier supports `AKRETIC_CLOUD_RUN_AUTH=identity_token` for direct Cloud
Run checks. If a real impersonation service account is required, set
`AKRETIC_CLOUD_RUN_IMPERSONATE_SERVICE_ACCOUNT` before running either command.
The public aggregate readiness endpoint is captured in `raw/readyz-public.json`
and `raw/readyz-deep.json`. Private services remain protected by Cloud Run IAM;
authenticated private readiness artifacts are captured as
`raw/private-health-authenticated-*.json`. The four private A2A Agent Cards are
checked directly at both
`/.well-known/agent-card.json` and `/agent.json`; captured responses are under
`raw/agent-card-*.json`. External unauthenticated private Cloud Run responses
are not treated as health proof.

## Synthetic Data Statement

This packet uses the synthetic VendorNova enterprise corpus and seeded public
snippets only. Documents are Markdown files with JSON metadata, content hashes,
classification, allowed groups, vendor ID, storage URI, and index status. Prompt
chips are examples; free-form reviewer prompts are mapped to governed intents.
Gemini sees only permitted model context after identity derivation, policy
receipts, retrieval filtering, public research gating, and approval handling.
The packet does not include customer data, private third-party data, or secrets.

## Known Limitations

- Challenge prototype only; not a production certification, legal opinion, or compliance attestation.
- Approval decisions are recorded for evidence; no external egress is performed by this challenge prototype.
- Seeded public snippets are allowlisted for the Track 3 proof path.

Open `FINAL_REVIEW.md`, `manifest.json`, `verifier-output.json`, `pytest-output.json`,
`deploy-manifest.json`, `warmup-output.json`, `readiness-burnin-output.json`,
`PROCESS_FLOW.md`, `process-flowchart.html`, `raw/`, and `screenshots/` for
review evidence. Unauthorized evidence access proof is captured in
`raw/evidence-unauthorized.json` and `screenshots/07-evidence-unauthorized.png`.

Raw readiness and Agent Card artifacts are captured in:

- `raw/readyz-public.json`
- `raw/readyz-deep.json`
- `raw/private-health-authenticated-root.json`
- `raw/private-health-authenticated-policy.json`
- `raw/private-health-authenticated-knowledge.json`
- `raw/private-health-authenticated-research.json`
- `raw/private-health-authenticated-approval.json`
- `raw/agent-card-policy.json`
- `raw/agent-card-knowledge.json`
- `raw/agent-card-research.json`
- `raw/agent-card-approval.json`
- `raw/corpus-status.json`
- `raw/corpus-metadata.json`
- `raw/playground-allowed.json`
- `raw/playground-denied-executive-memo.json`
- `raw/playground-unsupported-intent.json`
- `raw/corpus-retrieval-allowed.json`
- `raw/corpus-retrieval-denied.json`
- `raw/model-context-envelope.json`
- `raw/a2a-trust-receipt.json`
- `raw/red-team-results.json`
- `raw/knowledge-no-receipt-403.json`
- `raw/knowledge-invalid-receipt-403.json`
""".strip() + "\n"


def _final_review(manifest: dict[str, Any], verifier: dict[str, Any], pytest_result: dict[str, Any] | None) -> str:
    verification = manifest["verification"]
    latest = manifest["model_metadata"]
    is_cloud = manifest["packet_type"] == "cloud_judge_proof"
    urls_label = "Cloud Run URLs" if is_cloud else "Local Service URLs"
    revisions_label = "Cloud Run Revisions" if is_cloud else "Service Revisions"
    revisions = "\n".join(
        f"- `{name}`: {revision}" for name, revision in manifest["cloud_run_revisions"].items()
    )
    urls = "\n".join(
        f"- `{name}`: {url}" for name, url in manifest["cloud_run_service_urls"].items()
    )
    agent_cards = "\n".join(
        f"- `{name}`: {url}" for name, url in manifest["a2a_agent_card_urls"].items()
    )
    min_instances = "\n".join(
        f"- `{name}`: {value}" for name, value in (manifest.get("min_instances") or {}).items()
    ) or "- not captured"
    pytest_status = "not run"
    pytest_command = "not run"
    pytest_returncode = "not run"
    if pytest_result:
        pytest_status = "passed" if pytest_result["returncode"] == 0 else "failed"
        pytest_command = " ".join(pytest_result["command"])
        pytest_returncode = str(pytest_result["returncode"])
    verifier_run = manifest.get("verifier_run_id") or "not captured"
    return f"""
# FINAL_REVIEW

Result: packet generated for `{manifest["packet_type"]}`.

- judge_run_id: `{manifest["judge_run_id"]}`
- verifier_run_id: `{verifier_run}`
- evidence valid: `{verification.get("valid")}`
- event count: `{verification.get("event_count")}`
- head hash: `{verification.get("head_hash")}`
- model mode: `{latest.get("mode")}`
- runtime mode: `{latest.get("runtime_mode")}`
- corpus backend: `{manifest.get("corpus_backend")}`
- corpus manifest hash: `{manifest.get("corpus_manifest_hash")}`
- corpus document count: `{manifest.get("corpus_document_count")}`
- prompt hash: `{latest.get("prompt_hash")}`
- output hash: `{latest.get("output_hash", latest.get("completion_hash"))}`
- commit SHA: `{manifest["commit_sha"]}`
- build ID: `{manifest.get("build_id")}`
- image digest: `{manifest.get("image_digest")}`
- identity_source: `{manifest["identity_source"]}`
- browser_transport: `{manifest["browser_transport"]}`
- verifier_transport: `{manifest["verifier_transport"]}`

## {urls_label}

{urls}

## {revisions_label}

{revisions}

## A2A Agent Card Endpoints

{agent_cards}

## Judging Runtime Settings

Min instances:

{min_instances}

- deploy manifest: `{manifest.get("deploy_manifest")}`
- warmup output: `{manifest.get("warmup_output")}`
- readiness burn-in output: `{manifest.get("readiness_burnin_output")}`

## Test Commands

- verifier command: `{" ".join(verifier["command"])}`
- verifier return code: `{verifier["returncode"]}`
- verifier timestamp: `{verifier["timestamp"]}`
- pytest command: `{pytest_command}`
- pytest return code: `{pytest_returncode}`
- pytest result: `{pytest_status}`

Detailed stdout/stderr are in `verifier-output.json`, `p0-verify-output.txt`, `pytest-output.json`, and `pytest-output.txt`.

## Corpus, Playground, Envelope, And Receipt Proof

- Review process notes: `PROCESS_FLOW.md`
- Review flowchart: `process-flowchart.html`
- Flowchart screenshot: `screenshots/process-flowchart.png`
- Synthetic corpus status: `raw/corpus-status.json`
- Synthetic corpus metadata: `raw/corpus-metadata.json`
- Free-form allowed prompt: `raw/playground-allowed.json`
- Free-form denied executive memo prompt: `raw/playground-denied-executive-memo.json`
- Free-form unsupported prompt: `raw/playground-unsupported-intent.json`
- Corpus live retrieval allowed/denied: `raw/corpus-retrieval-allowed.json`, `raw/corpus-retrieval-denied.json`
- Model context envelope: `raw/model-context-envelope.json`
- A2A Trust Receipt: `raw/a2a-trust-receipt.json`
- Red-team challenge results: `raw/red-team-results.json`
- Knowledge receipt rejection proofs: `raw/knowledge-no-receipt-403.json`, `raw/knowledge-invalid-receipt-403.json`

These artifacts show that the demo is backed by synthetic Markdown/JSON files,
free-form prompts are mapped to governed intents, unknown or unsafe requests are
denied or handled through safe fallbacks, Gemini sees only permitted context,
and policy, approval, and evidence controls run outside the model.

## Packet Files

- `README.md`
- `manifest.json`
- `verifier-output.json`
- `p0-verify-output.txt`
- `pytest-output.json`
- `pytest-output.txt`
- `forbidden-string-scan.json`
- `run-id-integrity.json`
- `deploy-manifest.json`
- `warmup-output.json`
- `readiness-burnin-output.json`
- `PROCESS_FLOW.md`
- `process-flowchart.html`
- `raw/`
  - `raw/readyz-public.json`
  - `raw/readyz-deep.json`
  - `raw/private-health-authenticated-root.json`
  - `raw/private-health-authenticated-policy.json`
  - `raw/private-health-authenticated-knowledge.json`
  - `raw/private-health-authenticated-research.json`
  - `raw/private-health-authenticated-approval.json`
  - `raw/evidence-unauthorized.json`
  - `raw/corpus-status.json`
  - `raw/corpus-metadata.json`
  - `raw/playground-allowed.json`
  - `raw/playground-denied-executive-memo.json`
  - `raw/playground-unsupported-intent.json`
  - `raw/corpus-retrieval-allowed.json`
  - `raw/corpus-retrieval-denied.json`
  - `raw/model-context-envelope.json`
  - `raw/a2a-trust-receipt.json`
  - `raw/red-team-results.json`
  - `raw/knowledge-no-receipt-403.json`
  - `raw/knowledge-invalid-receipt-403.json`
  - `raw/agent-card-policy.json`
  - `raw/agent-card-knowledge.json`
  - `raw/agent-card-research.json`
  - `raw/agent-card-approval.json`
- `screenshots/`
  - `screenshots/home.png`
  - `screenshots/guided-run.png`
  - `screenshots/evidence-before-decision.png`
  - `screenshots/approval-unauthorized.png`
  - `screenshots/approval-authorized.png`
  - `screenshots/evidence-final-after-decision.png`
  - `screenshots/corpus-explorer.png`
  - `screenshots/corpus-retrieval-allowed.png`
  - `screenshots/corpus-retrieval-denied.png`
  - `screenshots/playground.png`
  - `screenshots/playground-result-allowed.png`
  - `screenshots/playground-result-denied.png`
  - `screenshots/model-context-envelope.png`
  - `screenshots/a2a-trust-receipt.png`
  - `screenshots/red-team-executive-memo-denied.png`
  - `screenshots/red-team-procurement-approval-denied.png`
  - `screenshots/red-team-knowledge-no-receipt-403.png`
  - `screenshots/red-team-tamper-detected.png`
  - `screenshots/07-evidence-unauthorized.png`
  - `screenshots/process-flowchart.png`

## Known Limitations

- Challenge prototype only; not a production certification, legal opinion, or compliance attestation.
- Synthetic VendorNova corpus and seeded public snippets only.
- Approval decisions are recorded; no external egress is performed by this challenge prototype.
""".strip() + "\n"


def _zip_dir(packet_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in packet_dir.rglob("*"):
            if path.is_file() and path != zip_path:
                archive.write(path, path.relative_to(packet_dir))


def build_packet(args: argparse.Namespace) -> Path:
    repo_root = REPO_ROOT
    mode = args.mode.lower()
    urls = _service_urls(args)
    if mode == "cloud":
        os.environ.setdefault("AKRETIC_CLOUD_RUN_AUTH", "identity_token")
        _assert_cloud_urls(urls)
        if args.skip_pytest:
            raise RuntimeError("cloud handoff requires pytest output; do not use --skip-pytest")
        if args.skip_screenshots:
            raise RuntimeError("cloud handoff requires screenshots; do not use --skip-screenshots")

    packet_dir = Path(args.output_dir) / f"akretic-a2a-final-{mode}-handoff-{_timestamp()}"
    if packet_dir.exists():
        shutil.rmtree(packet_dir)
    packet_dir.mkdir(parents=True)

    verifier_command = [
        sys.executable,
        "scripts/p0_verify.py",
        "--base-url",
        urls["demo_ui"],
        "--mode",
        mode,
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
    ]
    if mode == "cloud":
        verifier_command.extend(["--expect-vertex", "--fail-on-local"])
    verifier_command.extend(
        [
            "--expect-corpus-backend",
            "gcs" if mode == "cloud" else "local",
            "--expect-freeform-playground",
            "--expect-corpus-explorer",
            "--expect-corpus-live-retrieval",
            "--expect-decision-receipts",
            "--expect-trust-receipt",
            "--expect-model-context-envelope",
            "--expect-red-team-cards",
        ]
    )
    verifier = _run_command(verifier_command, cwd=repo_root, timeout=args.command_timeout)
    _write_json(packet_dir / "verifier-output.json", verifier)
    _write_json(packet_dir / "p0-verify-output.json", verifier)
    _write_text(
        packet_dir / "p0-verify-output.txt",
        "\n".join(
            [
                f"timestamp: {verifier['timestamp']}",
                f"command: {' '.join(verifier['command'])}",
                f"returncode: {verifier['returncode']}",
                "",
                "STDOUT:",
                verifier["stdout"],
                "",
                "STDERR:",
                verifier["stderr"],
            ]
        ),
    )
    if verifier["returncode"] != 0:
        raise RuntimeError("p0_verify.py failed; see verifier-output.json")
    verifier_run_id = _extract_verifier_run_id(verifier)

    pytest_result = None
    if not args.skip_pytest:
        pytest_result = _run_command(
            [sys.executable, "-m", "pytest", "-q"],
            cwd=repo_root,
            timeout=args.command_timeout,
            env=_local_pytest_env(),
        )
        _write_json(packet_dir / "pytest-output.json", pytest_result)
        _write_text(
            packet_dir / "pytest-output.txt",
            "\n".join(
                [
                    f"timestamp: {pytest_result['timestamp']}",
                    f"command: {' '.join(pytest_result['command'])}",
                    f"returncode: {pytest_result['returncode']}",
                    "",
                    "STDOUT:",
                    pytest_result["stdout"],
                    "",
                    "STDERR:",
                    pytest_result["stderr"],
                ]
            ),
        )
        if pytest_result["returncode"] != 0:
            raise RuntimeError("pytest failed; see pytest-output.json")
    else:
        _write_json(
            packet_dir / "pytest-output.json",
            {
                "command": [sys.executable, "-m", "pytest", "-q"],
                "returncode": None,
                "stdout": "",
                "stderr": "pytest skipped by --skip-pytest",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        _write_text(packet_dir / "pytest-output.txt", "pytest skipped by --skip-pytest\n")
    if mode == "cloud" and (
        not pytest_result
        or pytest_result.get("returncode") != 0
        or not pytest_result.get("timestamp")
        or not pytest_result.get("command")
    ):
        raise RuntimeError("cloud handoff requires captured passing pytest command, timestamp, stdout, and stderr")

    warmup_result = None
    burnin_result = None
    if mode == "cloud":
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
            str(packet_dir / "warmup-output.json"),
        ]
        warmup_result = _run_command(warmup_command, cwd=repo_root, timeout=args.command_timeout)
        _write_json(packet_dir / "warmup-command-output.json", warmup_result)
        if warmup_result["returncode"] != 0:
            raise RuntimeError("warmup_cloud_demo.py failed; see warmup-command-output.json")

        burnin_command = [
            sys.executable,
            "scripts/readiness_burnin.py",
            "--base-url",
            urls["demo_ui"],
            "--runs",
            "5",
            "--expect-zero-5xx",
            "--expect-vertex",
            "--fail-on-local",
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
            str(packet_dir / "readiness-burnin-output.json"),
            "--warmup-output",
            str(packet_dir / "warmup-output.json"),
        ]
        burnin_result = _run_command(burnin_command, cwd=repo_root, timeout=max(args.command_timeout, 2400))
        _write_json(packet_dir / "readiness-burnin-command-output.json", burnin_result)
        if burnin_result["returncode"] != 0:
            raise RuntimeError("readiness_burnin.py failed; see readiness-burnin-command-output.json")

    service_artifacts = _capture_cloud_service_artifacts(
        urls,
        packet_dir,
        mode=mode,
        timeout=args.timeout,
    )

    judge_flow = _capture_judge_flow(
        urls["demo_ui"],
        urls["knowledge"],
        packet_dir,
        mode=mode,
        timeout=args.timeout,
    )
    judge_run_id = judge_flow["judge_run_id"]
    integrity_failures = validate_primary_run_integrity(packet_dir, judge_run_id)
    _write_json(
        packet_dir / "run-id-integrity.json",
        {"judge_run_id": judge_run_id, "failures": integrity_failures},
    )
    if integrity_failures:
        raise RuntimeError("primary packet artifacts contain mixed or missing run IDs")

    _write_text(packet_dir / "PROCESS_FLOW.md", _process_notes(mode))
    _write_text(packet_dir / "process-flowchart.html", _process_flowchart_html(mode, urls))

    screenshots = {}
    if not args.skip_screenshots:
        screenshots = _capture_screenshots_from_artifacts(packet_dir, int(args.timeout * 1000))

    latest_model = judge_flow.get("latest_model", {})
    corpus_status_manifest = json.loads((packet_dir / "raw" / "corpus-status.json").read_text(encoding="utf-8"))
    packet_generator_commit_sha = _git_commit_sha(repo_root)
    commit_sha = packet_generator_commit_sha
    revisions = _cloud_run_revisions(args)
    deploy_manifest = None
    deploy_manifest_source = Path(args.deploy_manifest)
    if deploy_manifest_source.exists():
        deploy_manifest = json.loads(deploy_manifest_source.read_text(encoding="utf-8-sig"))
        deploy_manifest["packet_filename"] = packet_dir.with_suffix(".zip").name
        _write_json(packet_dir / "deploy-manifest.json", deploy_manifest)
        if mode == "cloud":
            commit_sha = str(deploy_manifest.get("commit_sha") or packet_generator_commit_sha)
        service_revisions = deploy_manifest.get("service_revisions", {}) if isinstance(deploy_manifest, dict) else {}
        mapped_revisions = {
            "demo_ui": service_revisions.get("akretic-demo-ui"),
            "root": service_revisions.get("akretic-root-orchestrator"),
            "policy": service_revisions.get("akretic-policy-agent"),
            "knowledge": service_revisions.get("akretic-knowledge-agent"),
            "research": service_revisions.get("akretic-research-agent"),
            "approval": service_revisions.get("akretic-approval-evidence"),
        }
        revisions = {
            name: mapped_revisions.get(name) or value
            for name, value in revisions.items()
        }
    elif mode == "cloud":
        raise RuntimeError("cloud handoff requires deploy-manifest.json from the immutable deployment flow")
    agent_card_urls = _agent_card_urls(urls)
    project_label = args.project_label or latest_model.get("project_id") or "local-only"
    location = latest_model.get("location") or "local-only"
    packet_type = "cloud_judge_proof" if mode == "cloud" else "local_rehearsal_proof"
    runtime_mode = latest_model.get("runtime_mode", mode)
    model_mode = latest_model.get("mode", "local")
    model_name = latest_model.get("model", "local-deterministic-test-summary")

    manifest = {
        "packet_type": packet_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "judge_run_id": judge_run_id,
        "verifier_run_id": verifier_run_id,
        "commit_sha": commit_sha,
        "packet_generator_commit_sha": packet_generator_commit_sha,
        "runtime_mode": runtime_mode,
        "model_mode": model_mode,
        "model": model_name,
        "project_label": project_label,
        "location": location,
        "corpus_backend": corpus_status_manifest.get("backend"),
        "corpus_manifest_hash": corpus_status_manifest.get("corpus_manifest_hash"),
        "corpus_document_count": corpus_status_manifest.get("document_count"),
        "identity_source": IDENTITY_SOURCE_LABEL,
        "browser_transport": BROWSER_TRANSPORT_LABEL,
        "verifier_transport": VERIFIER_TRANSPORT_LABEL,
        "cloud_run_service_urls": urls,
        "a2a_agent_card_urls": agent_card_urls,
        "verifier_command": verifier_command,
        "pytest_command": [sys.executable, "-m", "pytest", "-q"],
        "process_notes": "PROCESS_FLOW.md",
        "process_flowchart": "process-flowchart.html",
        "warmup_output": "warmup-output.json" if mode == "cloud" else None,
        "readiness_burnin_output": "readiness-burnin-output.json" if mode == "cloud" else None,
        "deploy_manifest": "deploy-manifest.json" if deploy_manifest else None,
        "verification": judge_flow.get("verification", {}),
        "screenshots": screenshots,
        "raw_artifacts": {
            **service_artifacts,
            "home": "raw/home.html",
            "corpus_status": "raw/corpus-status.json",
            "corpus_metadata": "raw/corpus-metadata.json",
            "corpus_explorer": "raw/corpus-explorer.html",
            "playground_allowed_json": "raw/playground-allowed.json",
            "playground_allowed_html": "raw/playground-freeform-allowed.html",
            "playground_denied_executive_memo_json": "raw/playground-denied-executive-memo.json",
            "playground_denied_html": "raw/playground-freeform-denied.html",
            "playground_unsupported_intent_json": "raw/playground-unsupported-intent.json",
            "corpus_retrieval_allowed_json": "raw/corpus-retrieval-allowed.json",
            "corpus_retrieval_allowed_html": "raw/corpus-retrieval-allowed.html",
            "corpus_retrieval_denied_json": "raw/corpus-retrieval-denied.json",
            "corpus_retrieval_denied_html": "raw/corpus-retrieval-denied.html",
            "red_team_challenge": "raw/red-team-challenge.html",
            "red_team_self_assert_admin": "raw/red-team-self_assert_admin.html",
            "red_team_executive_memo": "raw/red-team-executive_memo.html",
            "red_team_retrieve_all": "raw/red-team-retrieve_all.html",
            "red_team_prompt_injection_export": "raw/red-team-prompt_injection_export.html",
            "red_team_approve_as_procurement": "raw/red-team-approve_as_procurement.html",
            "red_team_knowledge_without_receipt": "raw/red-team-knowledge_without_receipt.html",
            "red_team_unauthorized_evidence": "raw/red-team-unauthorized_evidence.html",
            "red_team_tamper_evidence": "raw/red-team-tamper_evidence.html",
            "red_team_results": "raw/red-team-results.json",
            "knowledge_no_receipt_403": "raw/knowledge-no-receipt-403.json",
            "knowledge_invalid_receipt_403": "raw/knowledge-invalid-receipt-403.json",
            "run": "raw/run.html",
            "evidence_unauthorized": "raw/evidence-unauthorized.json",
            "evidence_before_decision_json": "raw/evidence-before-decision.json",
            "evidence_before_decision_html": "raw/evidence-before-decision.html",
            "approval_unauthorized": "raw/approval-unauthorized.html",
            "approval_authorized": "raw/approval-authorized.html",
            "model_context_envelope_json": "raw/model-context-envelope.json",
            "model_context_envelope_html": "raw/model-context-envelope.html",
            "a2a_trust_receipt_json": "raw/a2a-trust-receipt.json",
            "a2a_trust_receipt_html": "raw/a2a-trust-receipt.html",
            "evidence_final_json": "raw/evidence-final.json",
            "evidence_final_html": "raw/evidence-final.html",
            "verify_final": "raw/verify-final.json",
            "process_notes": "PROCESS_FLOW.md",
            "process_flowchart": "process-flowchart.html",
        },
        "cloud_run_revisions": revisions,
        "min_instances": (deploy_manifest or {}).get("min_instances", {}),
        "image_digest": (deploy_manifest or {}).get("image_digest"),
        "build_id": (deploy_manifest or {}).get("build_id"),
        "model_metadata": latest_model,
        "final_event_count": judge_flow.get("final_report", {}).get("verification", {}).get("event_count"),
        "final_head_hash": judge_flow.get("final_report", {}).get("verification", {}).get("head_hash"),
        "limitations": [
            "Challenge prototype; not a production certification or security guarantee.",
            "Synthetic data and seeded public snippets only.",
            "Approval decisions are recorded; no external egress is performed by this demo path.",
        ],
    }
    if mode == "cloud":
        _validate_cloud_manifest(manifest)
        deploy_consistency_failures = validate_deploy_manifest_consistency(
            packet_dir,
            deploy_manifest or {},
            manifest,
            packet_zip_name=packet_dir.with_suffix(".zip").name,
            packet_generator_commit_sha=packet_generator_commit_sha,
            mode=mode,
        )
        _write_json(
            packet_dir / "deploy-manifest-integrity.json",
            {"mode": mode, "failures": deploy_consistency_failures},
        )
        if deploy_consistency_failures:
            raise RuntimeError("cloud deploy manifest disagrees with manifest, readyz, or evidence artifacts")
    _write_json(packet_dir / "manifest.json", manifest)

    _write_text(packet_dir / "FINAL_REVIEW.md", _final_review(manifest, verifier, pytest_result))
    _write_text(packet_dir / "README.md", _packet_readme(manifest))
    final_review_failures = validate_final_review_consistency(packet_dir, manifest, mode=mode)
    _write_json(
        packet_dir / "final-review-integrity.json",
        {"mode": mode, "failures": final_review_failures},
    )
    if final_review_failures:
        raise RuntimeError("cloud FINAL_REVIEW.md disagrees with manifest values")

    for canary in DENIED_CANARIES:
        for path in packet_dir.rglob("*"):
            if path.is_file() and path.suffix.lower() not in {".png", ".zip"}:
                if canary in path.read_text(encoding="utf-8", errors="ignore"):
                    raise RuntimeError(f"denied canary leaked into packet file {path}")

    findings = scan_forbidden_strings(packet_dir, mode=mode)
    _write_json(packet_dir / "forbidden-string-scan.json", {"mode": mode, "findings": findings})
    referenced_artifact_failures = validate_referenced_artifacts(packet_dir, manifest, mode=mode)
    _write_json(
        packet_dir / "referenced-artifact-integrity.json",
        {"mode": mode, "failures": referenced_artifact_failures},
    )
    missing_packet_files = validate_required_packet_files(packet_dir, mode=mode)
    if missing_packet_files:
        raise RuntimeError(
            "cloud packet missing required artifacts: " + ", ".join(missing_packet_files)
        )
    if referenced_artifact_failures:
        raise RuntimeError("cloud packet has missing referenced artifacts or no screenshots")
    if findings:
        raise RuntimeError("cloud packet contains forbidden local strings")

    zip_path = packet_dir.with_suffix(".zip")
    _zip_dir(packet_dir, zip_path)
    return zip_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create final Akretic judge handoff packet.")
    parser.add_argument("--base-url", required=True, help="Demo UI public base URL.")
    parser.add_argument("--mode", choices=["cloud", "local"], default="cloud")
    parser.add_argument("--root-url")
    parser.add_argument("--policy-url")
    parser.add_argument("--knowledge-url")
    parser.add_argument("--research-url")
    parser.add_argument("--approval-url")
    parser.add_argument("--deploy-manifest", default="deploy-manifest.json")
    parser.add_argument("--project-label", help="Project label to show in cloud packets; may be a redacted real project label.")
    parser.add_argument("--demo-ui-revision")
    parser.add_argument("--root-revision")
    parser.add_argument("--policy-revision")
    parser.add_argument("--knowledge-revision")
    parser.add_argument("--research-revision")
    parser.add_argument("--approval-revision")
    parser.add_argument("--output-dir", default="output/playwright/final-handoff")
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--command-timeout", type=int, default=600)
    parser.add_argument("--skip-pytest", action="store_true")
    parser.add_argument("--skip-screenshots", action="store_true")
    args = parser.parse_args()
    zip_path = build_packet(args)
    print(zip_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
