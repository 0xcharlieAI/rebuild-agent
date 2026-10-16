from pathlib import Path
from unittest.mock import patch

from rebuild_agent.fixer import Fixer, PatchGenerationError
from rebuild_agent.verifier import Verifier


class FakeLLM:
    def __init__(self, response: str):
        self.response = response
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


def test_fixer_writes_diff_and_applies_only_to_temporary_copy(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    original = project / "README.md"
    original.write_text("before\n", encoding="utf-8")
    llm = FakeLLM("```diff\n--- a/README.md\n+++ b/README.md\n@@ -1 +1 @@\n-before\n+after\n```")
    fixer = Fixer(project, llm, tmp_path / "patches")

    patches = fixer.generate_patches(["Document setup"])
    assert patches[0].read_text(encoding="utf-8").startswith("--- a/README.md")
    with fixer.temporary_copy(patches) as copy:
        assert (copy / "README.md").read_text(encoding="utf-8") == "after\n"
    assert original.read_text(encoding="utf-8") == "before\n"
    assert "Document setup" in llm.prompts[0]


def test_fixer_rejects_non_patch_response(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    with __import__("pytest").raises(PatchGenerationError):
        Fixer(project, FakeLLM("No changes needed")).generate_patches(["Dockerfile"])


def test_fixer_temporary_copy_fails_clearly_without_patch_binary(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    fixer = Fixer(project, FakeLLM("unused"), tmp_path / "patches")
    with patch("rebuild_agent.fixer.shutil.which", return_value=None):
        try:
            with fixer.temporary_copy([]):
                pass
        except PatchGenerationError as exc:
            assert "patch" in str(exc).lower()
            assert "apt install patch" in str(exc) or "pacman -S patch" in str(exc)
        else:
            raise AssertionError("expected PatchGenerationError when patch binary is missing")


def test_verifier_reports_missing_docker_without_running_project(tmp_path: Path) -> None:
    with patch("rebuild_agent.verifier.shutil.which", return_value=None), patch("rebuild_agent.verifier.subprocess.run") as run:
        result = Verifier(tmp_path).verify(["pytest"])
    assert not result.passed
    assert not result.available
    run.assert_not_called()


def test_verifier_constructs_docker_only_commands(tmp_path: Path) -> None:
    build = __import__("subprocess").CompletedProcess([], 0, "built", "")
    check = __import__("subprocess").CompletedProcess([], 0, "ok", "")
    with patch("rebuild_agent.verifier.shutil.which", return_value="/usr/bin/docker"), patch(
        "rebuild_agent.verifier.subprocess.run", side_effect=[build, check]
    ) as run:
        result = Verifier(tmp_path).verify(["make test"])
    assert result.passed
    assert all(call.args[0][0] == "docker" for call in run.call_args_list)
    assert "make test" in run.call_args_list[1].args[0]


def test_verifier_reuse_image_skips_build(tmp_path: Path) -> None:
    check = __import__("subprocess").CompletedProcess([], 0, "ok", "")
    with patch("rebuild_agent.verifier.shutil.which", return_value="/usr/bin/docker"), patch(
        "rebuild_agent.verifier.subprocess.run", return_value=check
    ) as run:
        result = Verifier(tmp_path, image="already-built:1", skip_build=True).verify(["make test"])
    assert result.passed
    assert run.call_count == 1
    assert "already-built:1" in run.call_args.args[0]
