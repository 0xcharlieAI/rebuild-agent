from pathlib import Path

from rebuild_agent.detector import detect_stacks, detected_stack_names


FIXTURES = Path(__file__).parent / "fixtures"


def test_detects_all_supported_stacks_from_root_manifests() -> None:
    root = FIXTURES / "stacks"

    detections = detect_stacks(root)

    assert [d.name for d in detections] == ["python", "node", "flutter", "rust", "go"]
    assert all(len(d.evidence) == 1 for d in detections)
    assert detected_stack_names(root) == {"python", "node", "flutter", "rust", "go"}


def test_detector_does_not_report_nested_manifests(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "package.json").write_text("{}", encoding="utf-8")

    assert detect_stacks(tmp_path) == ()
