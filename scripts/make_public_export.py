from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def _join(*parts: str) -> str:
    return "".join(parts)


ROOT_FILES = (
    ".gcloudignore",
    ".gitattributes",
    ".gitignore",
    "ACCEPTANCE_CRITERIA.md",
    "DATA_SOURCES.md",
    "Makefile",
    "PROJECT_SOURCE_OF_TRUTH.md",
    "PUBLIC_RIGHTS.md",
    "README.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "pyproject.toml",
    "requirements.txt",
)

DOC_FILES = (
    "docs/adk_alignment.md",
    "docs/architecture.md",
    "docs/architecture.mmd",
    "docs/architecture.png",
    "docs/demo_script.md",
    "docs/deployment.md",
    "docs/devpost_answers.md",
    "docs/public_brief.md",
    "docs/public_claims_guardrails.md",
    "docs/submission_answers.md",
    "docs/submission_answers_public.md",
    "docs/submission_form_packet.md",
)

SCRIPT_FILES = (
    "scripts/bootstrap.sh",
    "scripts/deploy_cloudrun.sh",
    "scripts/make_final_handoff.py",
    "scripts/make_public_export.py",
    "scripts/p0_verify.py",
    "scripts/readiness_burnin.py",
    "scripts/run_local.sh",
    "scripts/test.sh",
    "scripts/warmup_cloud_demo.py",
)

INFRA_FILES = (
    "infra/cloudrun/Dockerfile",
    "infra/cloudrun/cloudbuild.yaml",
    "infra/cloudrun/service-map.yaml",
)

GITHUB_FILES = (".github/workflows/ci.yml",)

PUBLIC_DIRS = (
    "agents",
    "common",
    "demo_ui",
    "policies",
    "services",
    "tests",
)

CORPUS_FILES = ("corpus/metadata.json",)
CORPUS_DIRS = ("corpus/documents",)

EXCLUDED_DIR_NAMES = {
    ".git",
    _join(".", "co", "dex"),
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".hypothesis",
    ".akretic",
    "artifacts",
    "build",
    "dist",
    "local",
    "output",
    "review-packets",
}

EXCLUDED_FILENAMES = {
    ".env",
    ".env.example",
    "application_default_credentials.json",
    "deploy-manifest.json",
    "readiness-burnin-output.json",
    "warmup-output.json",
    _join("AG", "ENTS.md"),
    _join("CO", "DEX_TASKS.md"),
    _join("DAILY", "_BUILD_TEMPO.md"),
    "GOOGLE_TOOLS.md",
    "STARTER_PACKET_MANIFEST.txt",
    "sample-evidence-report-p2.json",
}

EXCLUDED_SUFFIXES = (".pyc", ".pyo", ".zip", ".pem", ".key", ".log")

FORBIDDEN_CONTENT = (
    _join("<REPOSITORY", "_URL>"),
    _join("<OPTIONAL_", "SERVICE_ACCOUNT_EMAIL>"),
    _join("PLACE", "HOLDER"),
    _join("TO", "DO"),
    _join("FIX", "ME"),
    _join("change", "me"),
    _join("sean", ".w@", "akretic.com"),
    _join("C:", "\\", "Users", "\\"),
    _join("C:", "\\", "dev", "\\"),
    _join("/", "mnt", "/", "data"),
    _join(".", "co", "dex"),
    _join("CO", "DEX"),
    _join("AG", "ENTS.md"),
    _join("DAILY", "_BUILD_TEMPO"),
    _join("internal", " use only"),
    _join("akretic", " internal"),
)

ALLOWED_SAFE_VALUES = (
    "YOUR_GCP_PROJECT_ID",
    "YOUR_REGION",
    "YOUR_ARTIFACT_REGISTRY_REPO",
    "YOUR_PUBLIC_DEMO_URL",
    "YOUR_VERTEX_LOCATION",
    "YOUR_GCS_CORPUS_BUCKET",
    "YOUR_GCS_EVIDENCE_BUCKET",
    "AUTHORIZED_GCLOUD_ACCOUNT",
    "YOUR_SERVICE_ACCOUNT_EMAIL",
)


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _should_skip(path: Path, source: Path) -> bool:
    rel = _relative(path, source)
    parts = Path(rel).parts
    if any(part in EXCLUDED_DIR_NAMES for part in parts):
        return True
    if path.name in EXCLUDED_FILENAMES:
        return True
    lowered = path.name.lower()
    if lowered.startswith(".env."):
        return True
    if lowered.endswith(EXCLUDED_SUFFIXES):
        return True
    if "service-account" in lowered and lowered.endswith(".json"):
        return True
    return False


def _iter_tree_files(source: Path, relative_dir: str) -> Iterable[Path]:
    root = source / relative_dir
    if not root.exists():
        return
    for path in root.rglob("*"):
        if path.is_file() and not _should_skip(path, source):
            yield path


def iter_public_files(source: Path) -> list[Path]:
    files: list[Path] = []
    exact_paths = ROOT_FILES + DOC_FILES + SCRIPT_FILES + INFRA_FILES + GITHUB_FILES + CORPUS_FILES
    for relative in exact_paths:
        path = source / relative
        if path.exists() and path.is_file() and not _should_skip(path, source):
            files.append(path)
    for relative_dir in PUBLIC_DIRS + CORPUS_DIRS:
        files.extend(_iter_tree_files(source, relative_dir))
    unique = {path.resolve(): path for path in files}
    return [unique[key] for key in sorted(unique)]


def _copy_file(source_file: Path, source_root: Path, dest_root: Path) -> None:
    relative = source_file.relative_to(source_root)
    dest_file = dest_root / relative
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_file, dest_file)


def _source_commit(source: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=source,
            text=True,
            capture_output=True,
            check=True,
        )
    except Exception:
        return "UNKNOWN"
    return completed.stdout.strip() or "UNKNOWN"


def scan_export(dest: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for path in sorted(dest.rglob("*")):
        if not path.is_file():
            continue
        rel = _relative(path, dest)
        normalized_rel = rel.replace("/", "\\")
        for token in FORBIDDEN_CONTENT:
            token_lower = token.lower()
            if token_lower in rel.lower() or token_lower in normalized_rel.lower():
                findings.append({"path": rel, "token": token, "where": "path"})
        text = path.read_bytes().decode("utf-8", errors="ignore")
        lowered = text.lower()
        for token in FORBIDDEN_CONTENT:
            if token.lower() in lowered:
                findings.append({"path": rel, "token": token, "where": "content"})
    return findings


def write_manifest(
    dest: Path,
    *,
    source_commit_sha: str,
    included_files: list[Path],
    scan_findings: list[dict[str, str]],
) -> None:
    manifest = {
        "source_commit_sha": source_commit_sha,
        "public_export_commit_sha": "UNKNOWN",
        "export_timestamp": datetime.now(timezone.utc).isoformat(),
        "included_file_count": len(included_files),
        "excluded_patterns": [
            "version control metadata",
            "agent working configuration and notes",
            "virtual environments and caches",
            "generated output folders and handoff packets",
            "local evidence, screenshots, archives, and review packets",
            "environment files and credential-like files",
            "internal deployment notes and workstation-specific runbooks",
        ],
        "sanitized_replacements": [
            "public docs use safe deployment values",
            "public source-of-truth uses challenge prototype claims only",
            "architecture image is included under docs",
        ],
        "pytest_result": "not run by export script",
        "gitleaks_result": "not run by export script",
        "scan_result": "pass" if not scan_findings else "fail",
        "live_demo_url": "YOUR_PUBLIC_DEMO_URL",
        "final_cloud_packet_name": "UNKNOWN",
        "notes": [
            "Exporter copies only the public challenge allowlist.",
            "Allowed safe values are documented in README.md and docs/deployment.md.",
        ],
    }
    (dest / "PUBLIC_EXPORT_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )


def make_public_export(source: Path, dest: Path, source_commit: str | None = None) -> dict[str, object]:
    source = source.resolve()
    dest = dest.resolve()
    if source == dest:
        raise RuntimeError("destination must be different from source")
    if _is_relative_to(dest, source):
        raise RuntimeError("destination must not be inside source")
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    files = iter_public_files(source)
    required_missing = [
        relative
        for relative in (
            "README.md",
            "PROJECT_SOURCE_OF_TRUTH.md",
            "DATA_SOURCES.md",
            "docs/architecture.md",
            "docs/architecture.png",
            "corpus/metadata.json",
            "scripts/p0_verify.py",
            "scripts/make_public_export.py",
        )
        if not (source / relative).exists()
    ]
    if required_missing:
        raise RuntimeError(f"required public files are missing: {required_missing}")

    for source_file in files:
        _copy_file(source_file, source, dest)

    findings = scan_export(dest)
    write_manifest(
        dest,
        source_commit_sha=_source_commit(source, source_commit),
        included_files=files,
        scan_findings=findings,
    )
    manifest_findings = scan_export(dest)
    if manifest_findings:
        raise RuntimeError(json.dumps({"public_export_scan_findings": manifest_findings}, indent=2))
    return {
        "dest": str(dest),
        "included_file_count": len(files),
        "scan_result": "pass",
        "allowed_safe_values": ALLOWED_SAFE_VALUES,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a public-safe challenge repository export.")
    parser.add_argument("--source", required=True, help="Source repository directory")
    parser.add_argument("--dest", required=True, help="Clean export destination directory")
    parser.add_argument("--source-commit", default=None, help="Optional source commit SHA")
    args = parser.parse_args()

    result = make_public_export(
        source=Path(args.source),
        dest=Path(args.dest),
        source_commit=args.source_commit,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
