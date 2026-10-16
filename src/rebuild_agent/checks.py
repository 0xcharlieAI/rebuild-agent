"""Checks for files and commands needed for reproducible project builds."""

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class CheckResult:
    """The outcome of one reproducibility check."""

    name: str
    present: bool
    evidence: tuple[str, ...] = ()


_LOCKFILES = (
    "uv.lock", "poetry.lock", "Pipfile.lock", "requirements.lock",
    "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml",
    "Cargo.lock", "go.sum", "pubspec.lock",
)
_RUNTIME_FILES = (".python-version", ".nvmrc", ".node-version", "rust-toolchain.toml", "rust-toolchain")


def _files(root: Path, names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(name for name in names if (root / name).is_file())


def _has_test_command(root: Path) -> tuple[str, ...]:
    evidence: list[str] = []
    makefile = root / "Makefile"
    if makefile.is_file() and re.search(r"(?m)^test\s*:", makefile.read_text(encoding="utf-8")):
        evidence.append("Makefile:test target")
    package_json = root / "package.json"
    if package_json.is_file():
        text = package_json.read_text(encoding="utf-8")
        if re.search(r'"test"\s*:', text):
            evidence.append("package.json:scripts.test")
    pyproject = root / "pyproject.toml"
    if pyproject.is_file() and re.search(r"(?mi)^\s*(test|pytest)\s*=", pyproject.read_text(encoding="utf-8")):
        evidence.append("pyproject.toml:test command")
    return tuple(evidence)


def _runtime_evidence(root: Path) -> tuple[str, ...]:
    """Find runtime pin files and version declarations in root manifests."""

    evidence = list(_files(root, _RUNTIME_FILES))
    manifest_patterns = (
        ("pyproject.toml", r"(?mi)^\s*requires-python\s*=", "pyproject.toml:requires-python"),
        ("package.json", r'"engines"\s*:\s*\{[^}]*"node"\s*:', "package.json:engines.node"),
        ("pubspec.yaml", r"(?mi)^\s*(sdk|flutter)\s*:", "pubspec.yaml:environment"),
        ("Cargo.toml", r"(?mi)^\s*rust-version\s*=", "Cargo.toml:rust-version"),
        ("go.mod", r"(?mi)^\s*go\s+\d", "go.mod:go version"),
    )
    for filename, pattern, label in manifest_patterns:
        path = root / filename
        if path.is_file() and re.search(pattern, path.read_text(encoding="utf-8")):
            evidence.append(label)
    return tuple(evidence)


def run_checks(project_root: Path | str) -> tuple[CheckResult, ...]:
    """Run the standard reproducibility checks against *project_root*."""

    root = Path(project_root)
    lockfiles = _files(root, _LOCKFILES)
    runtime_files = _runtime_evidence(root)
    dockerfiles = tuple(name for name in ("Dockerfile", "dockerfile") if (root / name).is_file())
    test_evidence = _has_test_command(root)
    readmes = (
        tuple(path.name for path in root.iterdir() if path.is_file() and path.name.lower().startswith("readme"))
        if root.is_dir()
        else ()
    )
    env_examples = tuple(name for name in (".env.example", ".env.sample") if (root / name).is_file())
    return (
        CheckResult("lockfile", bool(lockfiles), lockfiles),
        CheckResult("pinned_runtime", bool(runtime_files), runtime_files),
        CheckResult("dockerfile", bool(dockerfiles), dockerfiles),
        CheckResult("test_command", bool(test_evidence), test_evidence),
        CheckResult("readme", bool(readmes), readmes),
        CheckResult("env_example", bool(env_examples), env_examples),
    )


def check_project(project_root: Path | str) -> tuple[CheckResult, ...]:
    """Backward-friendly alias for :func:`run_checks`."""

    return run_checks(project_root)
