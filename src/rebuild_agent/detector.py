"""Detect language and framework stacks from project manifest files."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StackDetection:
    """A detected stack and the manifest files that support the detection."""

    name: str
    evidence: tuple[Path, ...]


_MANIFESTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("python", ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile")),
    ("node", ("package.json",)),
    ("flutter", ("pubspec.yaml",)),
    ("rust", ("Cargo.toml",)),
    ("go", ("go.mod",)),
)


def detect_stacks(project_root: Path | str) -> tuple[StackDetection, ...]:
    """Return all recognized stacks in *project_root*, in stable order.

    Only files at the project root are considered manifests.  This avoids
    reporting a stack merely because a vendored or nested example project is
    present, while still allowing a project to be polyglot.
    """

    root = Path(project_root)
    return tuple(
        StackDetection(name, tuple(root / filename for filename in filenames if (root / filename).is_file()))
        for name, filenames in _MANIFESTS
        if any((root / filename).is_file() for filename in filenames)
    )


def detected_stack_names(project_root: Path | str) -> frozenset[str]:
    """Return only the names of stacks detected in *project_root*."""

    return frozenset(detection.name for detection in detect_stacks(project_root))
