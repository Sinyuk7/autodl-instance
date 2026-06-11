from pathlib import Path


ACTIVE_DOCS = [
    Path("README.md"),
    Path("CONTRIBUTING.md"),
    Path("src/README.md"),
    Path("tests/README.md"),
    Path("tests/integration/README.md"),
]

BANNED_PATTERNS = [
    "./init.sh",
    "python -m src.main",
    "python -m src.cli",
    "git clone https://github.com/Sinyuk7/autodl-instance",
    "src/addons/userdata/manifest.yaml",
    "src/addons/git_config/manifest.yaml",
    "src/lib/download/secrets.yaml",
]


def test_active_docs_do_not_advertise_source_runtime_entries():
    root = Path(__file__).resolve().parent.parent.parent
    offenders = []

    for relative_path in ACTIVE_DOCS:
        path = root / relative_path
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in BANNED_PATTERNS:
            if pattern in text:
                offenders.append(f"{relative_path}: {pattern}")

    assert offenders == []
