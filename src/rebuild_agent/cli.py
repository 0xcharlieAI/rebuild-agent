"""Command-line entry point for rebuild-agent."""

import argparse
from pathlib import Path
import re
from difflib import unified_diff

from rebuild_agent.checks import CheckResult, run_checks
from rebuild_agent.detector import detect_stacks
from rebuild_agent.fixer import Fixer, LLMClient
from rebuild_agent.verifier import Verifier
from rebuild_agent.report import build_report, format_json, format_markdown


_PATCH_CONTENT = {
    "lockfile": (
        "version = 1\n"
        "revision = 5\n"
        "requires-python = \"==3.12.*\"\n"
    ),
    "pinned_runtime": "3.12\n",
    "dockerfile": (
        "FROM python:3.12.15-slim\n\n"
        "COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /uvx /bin/\n"
        "WORKDIR /app\n"
        "COPY . .\n"
        "RUN uv sync --frozen --no-dev\n"
        "ENV PATH=\"/app/.venv/bin:$PATH\"\n"
        "CMD [\"make\", \"test\"]\n"
    ),
    "test_command": ".PHONY: test\n\ntest:\n\tuv run pytest\n",
    "readme": "# Project\n\n## Setup\n\nSee the project manifest for setup instructions.\n",
    "env_example": "LLM_API_KEY=your-key-here\n",
}


class HeuristicLLMClient:
    """Offline fallback client that proposes conservative starter patches."""

    def complete(self, prompt: str) -> str:
        item_match = re.search(r"Checklist item: ([a-z_]+)", prompt)
        item = item_match.group(1) if item_match else ""
        content = _PATCH_CONTENT.get(item, f"# Proposed fix for {item}\n")
        filename = {
            "lockfile": "uv.lock",
            "pinned_runtime": ".python-version",
            "dockerfile": "Dockerfile",
            "test_command": "Makefile",
            "readme": "README.md",
            "env_example": ".env.example",
        }.get(item, f"{item}.txt")
        lines = content.splitlines(keepends=True)
        diff = unified_diff(
            (), lines, fromfile="/dev/null", tofile=f"b/{filename}"
        )
        return "".join(diff)


def _test_commands(project_root: Path, checks: tuple[CheckResult, ...]) -> tuple[str, ...]:
    """Select the project's declared test command without executing it locally."""
    names = {result.name for result in checks if result.present}
    makefile = project_root / "Makefile"
    if "test_command" in names and makefile.is_file():
        return ("make test",)
    if (project_root / "package.json").is_file():
        return ("npm test",)
    return ("uv run pytest",)


def _print_report(project_root: Path) -> None:
    detections = detect_stacks(project_root)
    checks = run_checks(project_root)
    print(f"Project: {project_root}")
    print("Stack: " + (", ".join(d.name for d in detections) or "unknown"))
    print("Checklist:")
    for result in checks:
        status = "pass" if result.present else "missing"
        evidence = f" ({', '.join(result.evidence)})" if result.evidence else ""
        print(f"  [{status}] {result.name}{evidence}")

    missing = tuple(result for result in checks if not result.present)
    if not missing:
        print("No fixes needed.")
        return

    print("Missing items: " + ", ".join(result.name for result in missing))
    patch_dir = project_root / ".rebuild-agent" / "patches"
    patches = Fixer(project_root, HeuristicLLMClient(), patch_dir).generate_patches(missing)
    print("Proposed patches:")
    for patch in patches:
        print(f"  {patch.relative_to(project_root)}")

    fixer = Fixer(project_root, HeuristicLLMClient(), patch_dir)
    with fixer.temporary_copy(patches) as temporary_project:
        result = Verifier(temporary_project).verify(_test_commands(temporary_project, checks))
        if result.passed:
            print("Verification: passed in Docker")
            print("Accepted fixes: " + ", ".join(patch.name for patch in patches))
        elif not result.available:
            print(f"Verification: unavailable ({result.error})")
            print("Accepted fixes: none")
        else:
            print(f"Verification: failed ({result.error})")
            print("Accepted fixes: none")


def main() -> None:
    """Run the rebuild-agent command."""
    parser = argparse.ArgumentParser(
        prog="rebuild-agent",
        description="Analyze software projects and improve their reproducibility.",
    )
    subparsers = parser.add_subparsers(dest="command")
    analyze = subparsers.add_parser("analyze", help="analyze and propose reproducibility fixes")
    analyze.add_argument("path", type=Path, help="project directory to analyze")
    report = subparsers.add_parser("report", help="report reproducibility checklist status")
    report.add_argument("path", type=Path, help="project directory to report")
    report.add_argument("--format", choices=("markdown", "json"), default="markdown")
    report.add_argument("--image", default="rebuild-agent-verification", help="Docker image tag used for verification")
    report.add_argument("--reuse-image", action="store_true", help="reuse an already built image instead of rebuilding it")
    args = parser.parse_args()
    if args.command == "analyze":
        project_root = args.path.resolve()
        if not project_root.is_dir():
            parser.error(f"project path is not a directory: {args.path}")
        _print_report(project_root)
        return
    if args.command == "report":
        project_root = args.path.resolve()
        if not project_root.is_dir():
            parser.error(f"project path is not a directory: {args.path}")
        result = build_report(project_root, image=args.image, reuse_image=args.reuse_image)
        print(format_json(result) if args.format == "json" else format_markdown(result), end="")
        return
    parser.print_help()


if __name__ == "__main__":
    main()
