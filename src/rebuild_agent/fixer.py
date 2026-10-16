"""Generate and safely trial reproducibility fixes.

The fixer deliberately never writes to the project being analyzed.  Patches are
saved as reviewable artifacts and, when requested, applied to a temporary copy.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Iterator, Protocol, Sequence


class LLMClient(Protocol):
    """Minimal language-model boundary, suitable for a small test double."""

    def complete(self, prompt: str) -> str:
        """Return an answer containing a unified diff."""


class PatchGenerationError(ValueError):
    """Raised when an LLM response does not contain a usable unified diff."""


def _diff_from_response(response: str) -> str:
    """Extract a unified diff from either plain text or a markdown code block."""
    match = re.search(r"```(?:diff|patch)?\s*\n(.*?)```", response, re.DOTALL | re.IGNORECASE)
    diff = match.group(1).strip("\n") if match else response.strip()
    if "diff --git " not in diff and not re.search(r"^--- .+\n\+\+\+ .+", diff, re.MULTILINE):
        raise PatchGenerationError("LLM response did not contain a unified diff")
    return diff + "\n"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug[:60] or "check"


class Fixer:
    """Create proposed patches and trial them without changing ``project_root``."""

    def __init__(self, project_root: Path | str, llm_client: LLMClient, patch_dir: Path | str | None = None):
        self.project_root = Path(project_root).resolve()
        if not self.project_root.is_dir():
            raise ValueError(f"project root is not a directory: {project_root}")
        self.llm_client = llm_client
        self.patch_dir = Path(patch_dir) if patch_dir else self.project_root / ".rebuild-agent" / "patches"

    def generate_patches(self, missing_items: Sequence[str | object]) -> list[Path]:
        """Ask the model for one diff per missing checklist item and save each one."""
        self.patch_dir.mkdir(parents=True, exist_ok=True)
        result: list[Path] = []
        for raw_item in missing_items:
            # Accept CheckResult-like objects as a convenience for callers that
            # pass the output of checks.run_checks directly.
            if hasattr(raw_item, "present") and raw_item.present:
                continue
            item = str(getattr(raw_item, "name", raw_item))
            prompt = (
                "Create a minimal unified-diff patch for the following missing "
                "reproducibility checklist item. Use paths relative to the project "
                "root, preserve existing behavior, and return only the diff.\n\n"
                f"Checklist item: {item}\nProject files: {', '.join(sorted(p.name for p in self.project_root.iterdir()))}"
            )
            diff = _diff_from_response(self.llm_client.complete(prompt))
            destination = self.patch_dir / f"{_slug(item)}.patch"
            destination.write_text(diff, encoding="utf-8")
            result.append(destination)
        return result

    @contextmanager
    def temporary_copy(self, patches: Sequence[Path | str] = ()) -> Iterator[Path]:
        """Yield a patched temporary project and remove it on exit."""
        if shutil.which("patch") is None:
            raise PatchGenerationError(
                "The 'patch' command is required but was not found. "
                "Install it (e.g., apt install patch or pacman -S patch)."
            )
        with tempfile.TemporaryDirectory(prefix="rebuild-agent-") as directory:
            copy = Path(directory) / self.project_root.name
            shutil.copytree(self.project_root, copy, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"))
            for patch in patches:
                patch_path = Path(patch)
                completed = subprocess.run(
                    ["patch", "-p1", "--batch", "--forward", "-i", str(patch_path)],
                    cwd=copy,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if completed.returncode:
                    detail = (completed.stderr or completed.stdout).strip()
                    raise PatchGenerationError(f"could not apply {patch_path.name}: {detail}")
            yield copy


def generate_patches(project_root: Path | str, missing_items: Sequence[str], llm_client: LLMClient, patch_dir: Path | str | None = None) -> list[Path]:
    """Functional convenience wrapper around :class:`Fixer`."""
    return Fixer(project_root, llm_client, patch_dir).generate_patches(missing_items)
