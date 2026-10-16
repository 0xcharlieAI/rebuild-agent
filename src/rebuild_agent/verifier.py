"""Run reproducibility checks inside Docker containers only."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from typing import Sequence


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    available: bool
    commands: tuple[str, ...]
    output: tuple[str, ...] = ()
    error: str | None = None


class Verifier:
    """Build and execute checks using Docker, never a host shell."""

    def __init__(self, project_root: Path | str, image: str = "rebuild-agent-verification", timeout: int = 300):
        self.project_root = Path(project_root).resolve()
        self.image = image
        self.timeout = timeout

    def verify(self, commands: Sequence[str]) -> VerificationResult:
        commands = tuple(commands)
        if not shutil.which("docker"):
            return VerificationResult(False, False, commands, error="Docker is not installed or not available on PATH")
        if not self.project_root.is_dir():
            return VerificationResult(False, True, commands, error="project root is not a directory")
        build = self._run(["docker", "build", "-t", self.image, str(self.project_root)])
        if build.returncode:
            return VerificationResult(False, True, commands, (build.stdout + build.stderr,), "Docker image build failed")
        output: list[str] = []
        for command in commands:
            run = self._run([
                "docker", "run", "--rm", "-v", f"{self.project_root}:/workspace:ro",
                "-w", "/workspace", self.image, "sh", "-lc", command,
            ])
            output.append(run.stdout + run.stderr)
            if run.returncode:
                return VerificationResult(False, True, commands, tuple(output), f"command failed: {command}")
        return VerificationResult(True, True, commands, tuple(output))

    def _run(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(argv, check=False, capture_output=True, text=True, timeout=self.timeout)
        except subprocess.TimeoutExpired as exc:
            return subprocess.CompletedProcess(argv, 124, exc.stdout or "", exc.stderr or " timed out")
        except OSError as exc:
            return subprocess.CompletedProcess(argv, 127, "", str(exc))


def verify_in_docker(project_root: Path | str, commands: Sequence[str], image: str = "rebuild-agent-verification") -> VerificationResult:
    return Verifier(project_root, image=image).verify(commands)
