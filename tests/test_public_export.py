from __future__ import annotations

import json
from pathlib import Path

from scripts.make_public_export import make_public_export, scan_export


def _join(*parts: str) -> str:
    return "".join(parts)


def _write(path: Path, text: str = "public\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _minimal_source(root: Path) -> None:
    for relative in (
        "README.md",
        "PROJECT_SOURCE_OF_TRUTH.md",
        "DATA_SOURCES.md",
        "PUBLIC_RIGHTS.md",
        "SECURITY.md",
        "THIRD_PARTY_NOTICES.md",
        "ACCEPTANCE_CRITERIA.md",
        "pyproject.toml",
        "requirements.txt",
        "docs/architecture.md",
        "docs/demo_script.md",
        "docs/deployment.md",
        "docs/submission_answers.md",
        "corpus/metadata.json",
        "scripts/p0_verify.py",
        "scripts/make_public_export.py",
        "common/__init__.py",
        "tests/test_example.py",
    ):
        _write(root / relative)
    (root / "docs" / "architecture.png").parent.mkdir(parents=True, exist_ok=True)
    (root / "docs" / "architecture.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    _write(root / "corpus" / "documents" / "vendornova_profile.md")


def test_public_export_copies_allowlist_and_writes_manifest(tmp_path):
    source = tmp_path / "source"
    dest = tmp_path / "dest"
    _minimal_source(source)
    _write(source / _join("AG", "ENTS.md"), "private agent notes\n")
    _write(source / _join("CO", "DEX_TASKS.md"), "agent tasks\n")
    _write(source / "output" / "packet.txt", "generated\n")
    _write(source / ".env.example", "PROJECT_ID=value\n")
    _write(source / "demo_ui" / "sample-evidence-report-p2.json", "{}\n")

    result = make_public_export(source, dest, "abc123")

    assert result["scan_result"] == "pass"
    assert (dest / "README.md").exists()
    assert (dest / "docs" / "architecture.png").exists()
    assert (dest / "corpus" / "documents" / "vendornova_profile.md").exists()
    assert not (dest / _join("AG", "ENTS.md")).exists()
    assert not (dest / _join("CO", "DEX_TASKS.md")).exists()
    assert not (dest / "output").exists()
    assert not (dest / ".env.example").exists()
    assert not (dest / "demo_ui" / "sample-evidence-report-p2.json").exists()

    manifest = json.loads((dest / "PUBLIC_EXPORT_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["source_commit_sha"] == "abc123"
    assert manifest["scan_result"] == "pass"
    assert manifest["included_file_count"] == result["included_file_count"]


def test_public_export_scan_flags_unsafe_markers(tmp_path):
    dirty = tmp_path / "dirty"
    dirty.mkdir()
    marker = _join("sean", ".w@", "akretic.com")
    _write(dirty / "README.md", f"{marker}\n")

    findings = scan_export(dirty)

    assert findings == [{"path": "README.md", "token": marker, "where": "content"}]
