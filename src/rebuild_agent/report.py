"""Generate reproducibility reports without running project code on the host."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import subprocess
from typing import Callable, Sequence

from rebuild_agent.checks import CheckResult, run_checks
from rebuild_agent.verifier import VerificationResult, Verifier


REPORT_ITEMS = (
    "Git repository with commits",
    "Lockfile present",
    "Pinned runtime version",
    "Dockerfile builds successfully",
    "Test command passes",
    "README with setup, run, and test steps",
    ".env.example present, no secrets detected",
    "No absolute paths detected",
)


@dataclass(frozen=True)
class ReportItem:
    """One report checklist outcome."""

    name: str
    status: str
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in {"PASS", "FAIL", "FIXED"}:
            raise ValueError(f"invalid report status: {self.status}")


@dataclass(frozen=True)
class Report:
    """A report that can be rendered independently of project inspection."""

    project: str
    items: tuple[ReportItem, ...]

    @property
    def passed(self) -> int:
        return sum(item.status in {"PASS", "FIXED"} for item in self.items)

    @property
    def total(self) -> int:
        return len(self.items)


def format_markdown(report: Report) -> str:
    """Render *report* as stable, human-readable Markdown."""
    lines = [f"# Reproducibility report: `{report.project}`", "", "| Checklist item | Status | Evidence |", "| --- | --- | --- |"]
    for item in report.items:
        evidence = ", ".join(item.evidence) or "—"
        lines.append(f"| {item.name} | {item.status} | {evidence} |")
    lines.extend(("", f"**Score: {report.passed}/{report.total} passed**"))
    return "\n".join(lines) + "\n"


def format_json(report: Report) -> str:
    """Render *report* as JSON suitable for scripts and integrations."""
    payload = {
        "project": report.project,
        "items": [asdict(item) for item in report.items],
        "score": {"passed": report.passed, "total": report.total},
    }
    return json.dumps(payload, indent=2) + "\n"


def _git_has_commits(root: Path) -> tuple[bool, tuple[str, ...]]:
    if not (root / ".git").exists():
        return False, ()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False, ()
    if result.returncode:
        return False, ()
    return True, (result.stdout.strip(),)


def _readme_has_steps(root: Path) -> tuple[bool, tuple[str, ...]]:
    readmes = sorted(path for path in root.iterdir() if path.is_file() and path.name.lower().startswith("readme"))
    for readme in readmes:
        text = readme.read_text(encoding="utf-8", errors="replace")
        headings = {match.group(1).lower() for match in re.finditer(r"^#+\s+(.+?)\s*$", text, re.MULTILINE)}
        if {"setup", "run", "test"}.issubset(headings):
            return True, (readme.name,)
    return False, tuple(path.name for path in readmes)


_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?([A-Za-z0-9_./+\-=]{8,})"
)
_SECRET_PATTERNS = (
    re.compile(r"\b(?:sk|gh[pousr])_[A-Za-z0-9_\-]{16,}\b"),
)
# Flag machine-specific absolute paths, while allowing normal container paths
# such as /app and /var/lib in a Dockerfile.
_ABSOLUTE_PATH = re.compile(
    r"(?i)(?:" + "/" + "home/|" + "/" + "users/|(?<![A-Za-z])[A-Za-z]:[\\/])"
)


def _contains_secret(text: str) -> bool:
    placeholders = {"example", "placeholder", "changeme", "none", "null"}
    for match in _SECRET_ASSIGNMENT.finditer(text):
        value = match.group(2).lower()
        if value in placeholders or value.startswith("your-") or value.startswith("your_"):
            continue
        return True
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS)


def _scan_files(root: Path, patterns: re.Pattern[str] | Sequence[re.Pattern[str]]) -> tuple[str, ...]:
    matches: list[str] = []
    ignored = {".git", ".venv", "__pycache__", ".pytest_cache", ".rebuild-agent"}
    for path in root.rglob("*"):
        if not path.is_file() or ignored.intersection(path.relative_to(root).parts) or any(
            part.endswith(".egg-info") for part in path.relative_to(root).parts
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        patterns_to_check = (patterns,) if isinstance(patterns, re.Pattern) else patterns
        if patterns_to_check is _SECRET_PATTERNS:
            matched = _contains_secret(text)
        else:
            matched = any(pattern.search(text) for pattern in patterns_to_check)
        if matched:
            matches.append(str(path.relative_to(root)))
    return tuple(sorted(matches))


def _test_commands(root: Path, checks: Sequence[CheckResult]) -> tuple[str, ...]:
    if any(result.name == "test_command" and result.present for result in checks) and (root / "Makefile").is_file():
        return ("make test",)
    if (root / "package.json").is_file():
        return ("npm test",)
    return ("uv run pytest",)


def build_report(
    project_root: Path | str,
    verifier_factory: Callable[[Path], Verifier] = Verifier,
    fixed_items: Sequence[str] = (),
) -> Report:
    """Inspect a project and verify its Docker build/test command in Docker."""
    root = Path(project_root).resolve()
    checks = run_checks(root)
    by_name = {result.name: result for result in checks}
    git_ok, git_evidence = _git_has_commits(root)
    readme_ok, readme_evidence = _readme_has_steps(root)
    secrets = _scan_files(root, _SECRET_PATTERNS)
    absolute_paths = _scan_files(root, _ABSOLUTE_PATH)

    verification: VerificationResult | None = None
    if by_name.get("dockerfile", CheckResult("dockerfile", False)).present:
        verification = verifier_factory(root).verify(_test_commands(root, checks))
    docker_ok = verification is not None and verification.available and verification.passed
    test_ok = docker_ok
    docker_evidence = ("Docker build and test verification",) if docker_ok else ((verification.error,) if verification and verification.error else ())

    outcomes = {
        "Git repository with commits": (git_ok, git_evidence),
        "Lockfile present": (by_name["lockfile"].present, by_name["lockfile"].evidence),
        "Pinned runtime version": (by_name["pinned_runtime"].present, by_name["pinned_runtime"].evidence),
        "Dockerfile builds successfully": (docker_ok, docker_evidence),
        "Test command passes": (test_ok, docker_evidence),
        "README with setup, run, and test steps": (readme_ok, readme_evidence),
        ".env.example present, no secrets detected": (
            by_name["env_example"].present and not secrets,
            by_name["env_example"].evidence + tuple(f"secret found in {path}" for path in secrets),
        ),
        "No absolute paths detected": (not absolute_paths, absolute_paths),
    }
    fixed = set(fixed_items)
    return Report(
        str(root),
        tuple(
            ReportItem(
                name,
                "FIXED" if name in fixed and passed else "PASS" if passed else "FAIL",
                tuple(evidence),
            )
            for name in REPORT_ITEMS
            for passed, evidence in (outcomes[name],)
        ),
    )
