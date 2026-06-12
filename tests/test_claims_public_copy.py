from pathlib import Path


BANNED_PHRASES = [
    "unhackable",
    "guaranteed compliance",
    "mathematically impossible",
    "universal data-leak prevention",
    "fully autonomous enterprise action",
    "blockchain-grade",
    "legal non-repudiation",
    "marketplace-approved",
    "certified",
    "production-ready",
]


def test_public_copy_excludes_overclaims():
    docs_dir = Path(__file__).resolve().parents[1] / "docs"
    public_copy_paths = [
        docs_dir / "submission_answers_public.md",
        docs_dir / "submission_form_packet.md",
        docs_dir / "devpost_answers.md",
        docs_dir / "public_brief.md",
    ]
    text = "\n".join(path.read_text(encoding="utf-8").lower() for path in public_copy_paths)
    for phrase in BANNED_PHRASES:
        assert phrase not in text
