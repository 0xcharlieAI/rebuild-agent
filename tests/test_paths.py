from pathlib import Path


def test_repository_has_no_absolute_paths() -> None:
    """Reject machine-specific absolute paths in repository text files."""
    repository_root = Path(__file__).resolve().parents[1]
    forbidden_fragments = ("/" + "home/", "C:" + "\\")
    ignored_directories = {".git", ".venv", "__pycache__", "*.egg-info"}
    violations: list[str] = []

    for path in repository_root.rglob("*"):
        if not path.is_file() or any(
            directory in path.parts or any(
                part.endswith(".egg-info") for part in path.parts
            )
            for directory in ignored_directories
        ):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for fragment in forbidden_fragments:
            if fragment in content:
                violations.append(f"{path.relative_to(repository_root)} contains {fragment!r}")

    assert not violations, "Absolute paths found:\n" + "\n".join(violations)
