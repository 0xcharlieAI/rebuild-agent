import json
import sys

import pytest

from rebuild_agent import cli
from rebuild_agent.report import REPORT_ITEMS, Report, ReportItem, format_json, format_markdown


def sample_report() -> Report:
    return Report("demo", (ReportItem("Lockfile present", "PASS", ("uv.lock",)), ReportItem("No absolute paths detected", "FIXED")))


def test_markdown_formatter_includes_status_and_score() -> None:
    rendered = format_markdown(sample_report())
    assert "| Lockfile present | PASS | uv.lock |" in rendered
    assert "| No absolute paths detected | FIXED | — |" in rendered
    assert "**Score: 2/2 passed**" in rendered


def test_json_formatter_is_structured_and_preserves_statuses() -> None:
    payload = json.loads(format_json(sample_report()))
    assert payload["score"] == {"passed": 2, "total": 2}
    assert payload["items"][1]["status"] == "FIXED"
    assert payload["items"][0]["evidence"] == ["uv.lock"]


def test_report_checklist_matches_required_items() -> None:
    assert len(REPORT_ITEMS) == 8
    assert REPORT_ITEMS[6] == ".env.example present, no secrets detected"


def _report_with_score(passed: int, total: int = 8) -> Report:
    items = tuple(
        ReportItem(f"item-{index}", "PASS" if index < passed else "FAIL")
        for index in range(total)
    )
    return Report("demo", items)


def test_report_fail_under_passes_when_score_is_enough(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "build_report", lambda *args, **kwargs: _report_with_score(8))
    monkeypatch.setattr(sys, "argv", ["rebuild-agent", "report", str(tmp_path), "--fail-under", "8"])
    cli.main()


def test_report_fail_under_exits_when_score_is_low(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "build_report", lambda *args, **kwargs: _report_with_score(5))
    monkeypatch.setattr(sys, "argv", ["rebuild-agent", "report", str(tmp_path), "--fail-under", "8"])
    with pytest.raises(SystemExit) as excinfo:
        cli.main()
    assert excinfo.value.code == 1
