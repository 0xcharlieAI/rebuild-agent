from pathlib import Path

from rebuild_agent.checks import run_checks


FIXTURES = Path(__file__).parent / "fixtures"


def test_checks_report_presence_and_evidence() -> None:
    results = run_checks(FIXTURES / "checks")

    assert {result.name for result in results} == {
        "lockfile", "pinned_runtime", "dockerfile", "test_command", "readme", "env_example"
    }
    assert all(result.present for result in results)
    assert {evidence for result in results for evidence in result.evidence} >= {
        "uv.lock", ".python-version", "Dockerfile", "Makefile:test target", "README.md", ".env.example"
    }


def test_checks_report_missing_items(tmp_path: Path) -> None:
    results = run_checks(tmp_path)

    assert all(not result.present and not result.evidence for result in results)
