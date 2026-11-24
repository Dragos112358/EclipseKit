import json
from pathlib import Path

from eclipsekit.unified_validation import (
    _run_component,
    aggregate_component_statuses,
    main,
)


def test_aggregate_status_requires_clean_pass_for_pass():
    assert aggregate_component_statuses(["PASS", "PASS"]) == "PASS"
    assert aggregate_component_statuses(["PASS", "UNVERIFIED"]) == "PARTIAL"
    assert aggregate_component_statuses(["PASS", "FAIL"]) == "FAIL"
    assert aggregate_component_statuses(["FAIL", "ERROR"]) == "ERROR"
    assert aggregate_component_statuses([]) == "ERROR"


def test_component_runner_reads_report_status(tmp_path):
    report = tmp_path / "component.json"
    report.write_text(json.dumps({"status": "PASS", "summary": {"passed": 3}}), encoding="utf-8")
    def write_report(argv):
        report.write_text(json.dumps({"status": "PASS", "summary": {"passed": 3}}), encoding="utf-8")
        return 0

    outcome = _run_component(
        name="test", function=write_report, arguments=[], report_path=report
    )
    assert outcome["status"] == "PASS"
    assert outcome["summary"] == {"passed": 3}


def test_component_runner_does_not_reuse_stale_report(tmp_path):
    report = tmp_path / "component.json"
    report.write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
    outcome = _run_component(
        name="test", function=lambda argv: 2, arguments=[], report_path=report
    )
    assert outcome["status"] == "ERROR"
    assert "did not produce" in outcome["error"]


def test_unified_cli_writes_aggregate_report(tmp_path, monkeypatch):
    from eclipsekit import unified_validation as module

    def option(args, name):
        return Path(args[args.index(name) + 1])

    def fake_phase6(args):
        path = option(args, "--json-out")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"status": "PASS", "summary": {"passed": 9}}), encoding="utf-8")
        return 0

    def fake_corridor(args):
        out_dir = option(args, "--output-dir")
        stem = args[args.index("--stem") + 1]
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{stem}.json").write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
        return 0

    def fake_matrix(args):
        out_dir = option(args, "--output-dir")
        stem = args[args.index("--stem") + 1]
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{stem}.json").write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
        return 0

    def fake_eop(args):
        path = option(args, "--json-out")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
        return 0

    monkeypatch.setattr(module.validation_framework, "main", fake_phase6)
    monkeypatch.setattr(module.corridor_cli, "main", fake_corridor)
    monkeypatch.setattr(module.reference_matrix, "main", fake_matrix)
    monkeypatch.setattr(module.earth_orientation, "main", fake_eop)

    output = tmp_path / "phase8_4"
    result = main(["--validation-dir", str(tmp_path / "validation"), "--output-dir", str(output)])
    assert result == 0
    report = json.loads((output / "unified-validation.json").read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["summary"]["passed"] == 4
    assert len(report["components"]) == 4
    assert (output / "unified-validation.md").is_file()
