"""Phase 7.2 branch and orchestration tests for scientific validation."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import eclipsekit.validation_framework as vf
from eclipsekit.validation_framework import (
    PathReferenceCase,
    _engine_metadata,
    _interpolate_reference_track,
    load_path_reference_cases,
    render_full_validation_markdown,
    run_besselian_reference_validation,
    run_full_validation_suite,
    run_path_reference_cases,
)

ROOT = Path(__file__).parents[1]
DATA = ROOT / "data" / "validation"


def _raw_path(**updates):
    raw = {
        "case_id": "case-1", "name": "Case one",
        "event_time_utc": "2026-08-12T17:00:00Z",
        "reference_file": "path.csv", "search_radius_hours": 1.0,
        "tolerance_km": 1.0, "source_url": "https://example.org",
        "source_time_step_seconds": 60.0,
        "source_coordinate_resolution_arcmin": 0.1,
    }
    raw.update(updates)
    return raw


def _case(path: Path) -> PathReferenceCase:
    return PathReferenceCase(
        case_id="case-1", name="Case one", event_time_utc="2026-08-12T17:00:00Z",
        reference_file=path, search_radius_hours=1.0, tolerance_km=2.0,
        source_url="https://example.org", source_time_step_seconds=60.0,
        source_coordinate_resolution_arcmin=0.1,
    )


@pytest.mark.parametrize("raw, message", [
    (None, "JSON object"),
    ({"case_id": "only"}, "missing fields"),
    (_raw_path(search_radius_hours=0), "must be positive"),
    (_raw_path(tolerance_km=-1), "must be positive"),
    (_raw_path(source_time_step_seconds=0), "must be positive"),
    (_raw_path(source_coordinate_resolution_arcmin=0), "must be positive"),
    (_raw_path(case_id=" "), "non-empty"),
    (_raw_path(name=" "), "non-empty"),
    (_raw_path(source_url=" "), "non-empty"),
    (_raw_path(reference_file=" "), "non-empty"),
    (_raw_path(event_time_utc="2026-08-12T17:00:00"), "explicit UTC offset"),
    (_raw_path(tolerance_km=True), "not bool"),
    (_raw_path(source_time_step_seconds=float("inf")), "finite number"),
])
def test_path_case_rejects_invalid_mapping(tmp_path, raw, message):
    with pytest.raises(ValueError, match=message):
        PathReferenceCase.from_mapping(raw, base_dir=tmp_path)


def test_path_case_stores_resolved_path_and_optional_notes(tmp_path):
    case = PathReferenceCase.from_mapping(_raw_path(source_notes="table rounded to minute"), base_dir=tmp_path)
    assert case.reference_file == (tmp_path / "path.csv").resolve()
    assert case.source_notes == "table rounded to minute"


def test_path_manifest_rejects_missing_file_bad_root_and_empty_list(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_path_reference_cases(tmp_path / "missing.json")
    path = tmp_path / "manifest.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="schema_version"):
        load_path_reference_cases(path)
    path.write_text(json.dumps({"schema_version": 1, "path_cases": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty"):
        load_path_reference_cases(path)


def test_path_manifest_rejects_missing_reference_asset(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"schema_version": 1, "path_cases": [_raw_path()]}), encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="path.csv"):
        load_path_reference_cases(path)


@pytest.mark.parametrize("samples", [True, 2, 2.5, 0])
def test_path_reference_runner_rejects_invalid_sample_count(samples):
    with pytest.raises(ValueError, match="integer >= 3"):
        run_path_reference_cases(SimpleNamespace(), [], samples=samples)


def test_path_reference_runner_reports_fail_and_exception(tmp_path, monkeypatch):
    from eclipsekit import path_validation

    reference_file = tmp_path / "ref.csv"
    reference_file.write_text("time_utc,latitude_deg,longitude_deg\n2026-08-12T17:00:00Z,0,0\n", encoding="utf-8")
    case = _case(reference_file)
    monkeypatch.setattr(path_validation, "load_path_reference", lambda _path: [{"dummy": True}])
    monkeypatch.setattr(path_validation, "compare_shadow_path", lambda *a, **k: {
        "error_count": 0, "successful_comparisons": 0, "reference_count": 1,
        "max_error_km": None, "comparisons": [],
    })

    class NoPathEngine:
        def global_path_for_eclipse(self, *args, **kwargs):
            return []

    failed = run_path_reference_cases(NoPathEngine(), [case])[0]
    assert failed["status"] == "FAIL"
    assert failed["computed_path_points"] == 0

    class BrokenEngine:
        def global_path_for_eclipse(self, *args, **kwargs):
            raise RuntimeError("path computation failed")

    error = run_path_reference_cases(BrokenEngine(), [case])[0]
    assert error["status"] == "ERROR"
    assert "path computation failed" in error["reason"]
    assert error["comparisons"] == []


def test_interpolate_reference_track_checks_length_range_and_coordinates():
    with pytest.raises(ValueError, match="at least two"):
        _interpolate_reference_track([], 0)
    samples = [
        {"offset_seconds": 0, "latitude_deg": 0, "longitude_deg": 179},
        {"offset_seconds": 10, "latitude_deg": 10, "longitude_deg": -179},
    ]
    lat, lon = _interpolate_reference_track(samples, 5)
    assert lat == pytest.approx(5)
    assert abs(abs(lon) - 180.0) < 1e-9
    with pytest.raises(ValueError, match="does not bracket"):
        _interpolate_reference_track(samples, 11)
    bad_lat = [dict(samples[0], latitude_deg=91), samples[1]]
    with pytest.raises(ValueError, match="latitude"):
        _interpolate_reference_track(bad_lat, 5)
    bad_lon = [dict(samples[0], longitude_deg=181), samples[1]]
    with pytest.raises(ValueError, match="longitude"):
        _interpolate_reference_track(bad_lon, 5)


def _copy_besselian_fixture(tmp_path):
    raw = json.loads((DATA / "besselian_1999_reference.json").read_text(encoding="utf-8"))
    elements_src = DATA / raw["elements_file"]
    elements_name = Path(raw["elements_file"]).name
    (tmp_path / elements_name).write_bytes(elements_src.read_bytes())
    raw["elements_file"] = elements_name
    fixture = tmp_path / "reference.json"
    fixture.write_text(json.dumps(raw), encoding="utf-8")
    return fixture, raw


@pytest.mark.parametrize("mutation, message", [
    (lambda d: d.update(schema_version=99), "schema_version"),
    (lambda d: d.update(elements_file="../escape.json"), "inside the reference directory"),
    (lambda d: d.update(elements_file=" "), "name an elements_file"),
    (lambda d: d.update(delta_t_seconds=float("nan")), "finite number"),
    (lambda d: d.update(maximum_offset_tolerance_seconds=-1), "non-negative"),
    (lambda d: d.update(central_line_reference_samples={}), "JSON array"),
    (lambda d: d.update(local_observer=[]), "JSON object"),
    (lambda d: d.update(expected_eclipse_type="hybrid"), "expected_eclipse_type"),
    (lambda d: d.update(central_phase_duration_tolerance_seconds=-1), "must be non-negative"),
    (lambda d: d.update(case_id=" "), "non-empty case_id"),
])
def test_besselian_reference_rejects_invalid_descriptors(tmp_path, mutation, message):
    fixture, raw = _copy_besselian_fixture(tmp_path)
    mutation(raw)
    fixture.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises((ValueError, KeyError), match=message):
        run_besselian_reference_validation(fixture)


def test_besselian_reference_reports_fail_when_axis_has_no_earth_intersection(tmp_path, monkeypatch):
    from eclipsekit.besselian import BesselianElements

    fixture, raw = _copy_besselian_fixture(tmp_path)
    elements = BesselianElements.from_json(tmp_path / raw["elements_file"])

    class FakeContact:
        def __init__(self, name, jd, converged=True):
            self.name = name
            self.jd_tt = jd
            self.root_result = SimpleNamespace(converged=converged)

    class FakeSolver:
        def __init__(self, *args, **kwargs):
            pass

        def find_global_maximum(self, _elements):
            return elements.epoch_tt_jd + raw["expected_maximum_offset_seconds"] / 86400.0

        def central_line_point(self, *args, **kwargs):
            return None

        def calculate_local(self, *args, **kwargs):
            return SimpleNamespace(
                eclipse_type="partial", central_phase_duration_seconds=None,
                contacts={"C1": FakeContact("C1", 1.0, False)}, warnings=["no totality"],
            )

    monkeypatch.setattr("eclipsekit.besselian.BesselianSolver", FakeSolver)
    report = run_besselian_reference_validation(fixture)
    assert report["status"] == "FAIL"
    assert report["checks"]["central_line_position"]["passed"] is False
    assert report["checks"]["local_eclipse_type"]["passed"] is False
    assert report["checks"]["central_duration"]["passed"] is False
    assert report["checks"]["local_contacts"]["passed"] is False
    assert report["warnings"] == ["no totality"]


def test_direct_diagnostic_reports_not_available_for_incomplete_engine():
    report = vf.run_direct_besselian_diagnostic(SimpleNamespace(), DATA / "besselian_1999_reference.json")
    assert report["status"] == "NOT_AVAILABLE"


def test_direct_diagnostic_reports_not_comparable_when_besselian_has_no_local_maximum(tmp_path, monkeypatch):
    fixture, _ = _copy_besselian_fixture(tmp_path)

    class FakeSolver:
        def __init__(self, *args, **kwargs):
            pass

        def calculate_local(self, *args, **kwargs):
            return SimpleNamespace(maximum_jd_tt=None)

    monkeypatch.setattr("eclipsekit.besselian.BesselianSolver", FakeSolver)
    engine = SimpleNamespace(calculate_local=lambda *a, **k: None, ts=SimpleNamespace())
    report = vf.run_direct_besselian_diagnostic(engine, fixture)
    assert report["status"] == "NOT_COMPARABLE"


def test_direct_diagnostic_reports_not_comparable_when_direct_engine_finds_no_event(tmp_path, monkeypatch):
    fixture, _ = _copy_besselian_fixture(tmp_path)
    class FakeTimescale:
        def tt_jd(self, value):
            return value

    engine = SimpleNamespace(
        calculate_local=lambda *a, **k: None,
        ts=FakeTimescale(), config=None, solver_config=None, time_scale_mode="builtin",
    )
    report = vf.run_direct_besselian_diagnostic(engine, fixture)
    assert report["status"] == "NOT_COMPARABLE"
    assert "direct engine returned no local event" in report["reason"]


def test_engine_metadata_includes_config_and_falls_back_to_source_tree(monkeypatch):
    config = SimpleNamespace(
        to_dict=lambda: {"ephemeris": {"kernel": "de440s"}},
        ephemeris=SimpleNamespace(kernel="de440s"),
    )
    engine = SimpleNamespace(config=config, time_scale_mode="builtin")
    monkeypatch.setattr(vf.importlib.metadata, "version", lambda _name: "0.1.2")
    metadata = _engine_metadata(engine)
    assert metadata["pyeclipse_version"] == "0.1.2"
    assert metadata["kernel"] == "de440s"
    assert metadata["configuration"] == {"ephemeris": {"kernel": "de440s"}}
    monkeypatch.setattr(vf.importlib.metadata, "version", lambda _name: (_ for _ in ()).throw(vf.importlib.metadata.PackageNotFoundError()))
    assert _engine_metadata(SimpleNamespace())["pyeclipse_version"] == "source-tree"


def test_full_validation_suite_accounts_for_path_and_besselian_failures(monkeypatch):
    monkeypatch.setattr(vf, "run_validation_suite", lambda *a: {
        "local_cases": [{"status": "PASS"}],
        "global_maximum_cases": [{"status": "PASS"}],
    })
    monkeypatch.setattr(vf, "run_path_reference_cases", lambda *a, **k: [{"status": "FAIL"}])
    monkeypatch.setattr(vf, "run_besselian_reference_validation", lambda *a: {"status": "ERROR"})
    monkeypatch.setattr(vf, "run_direct_besselian_diagnostic", lambda *a: {"status": "DIAGNOSTIC"})
    report = run_full_validation_suite(SimpleNamespace(), [1], [2], path_cases=[3], besselian_reference="fixture.json")
    assert report["status"] == "ERROR"
    assert report["summary"]["passed"] == 2
    assert report["summary"]["failed"] == 1
    assert report["summary"]["errors"] == 1


def test_full_validation_suite_captures_path_and_diagnostic_errors(monkeypatch):
    monkeypatch.setattr(vf, "run_validation_suite", lambda *a: {
        "local_cases": [{"status": "FAIL"}], "global_maximum_cases": [],
    })
    monkeypatch.setattr(vf, "run_path_reference_cases", lambda *a, **k: [])
    monkeypatch.setattr(vf, "run_besselian_reference_validation", lambda *a: {"status": "PASS"})
    monkeypatch.setattr(vf, "run_direct_besselian_diagnostic", lambda *a: (_ for _ in ()).throw(RuntimeError("diag failed")))
    report = run_full_validation_suite(SimpleNamespace(), [1], [], path_cases=[], besselian_reference="fixture.json")
    assert report["status"] == "FAIL"
    assert report["direct_vs_besselian_diagnostic"]["status"] == "DIAGNOSTIC_ERROR"
    assert "diag failed" in report["direct_vs_besselian_diagnostic"]["reason"]
    assert "global_path" in report["summary"]["not_run_groups"]


def test_full_report_markdown_renders_path_besselian_and_diagnostic_sections():
    markdown = render_full_validation_markdown({
        "status": "FAIL", "summary": {"total_cases": 2, "passed": 1, "failed": 1,
        "errors": 0, "not_run_groups": ["paths"]},
        "environment": {"kernel": "de440s", "time_scale_mode": "builtin"},
        "local_cases": [{"name": "Local", "status": "FAIL", "checks": [
            {"label": "C1", "passed": False}]}],
        "global_maximum_cases": [{"name": "Global", "status": "PASS", "check": {"label": "maximum", "passed": True}}],
        "global_path_cases": [{"name": "Path", "status": "PASS", "successful_comparisons": 3,
            "reference_count": 3, "mean_error_km": 0.2, "rms_error_km": 0.3,
            "max_error_km": 0.4, "tolerance_km": 1.0}],
        "besselian_reference": {"status": "FAIL", "checks": {"epoch": {"passed": False, "delta_seconds": 1.2}}, "reason": "bad reference"},
        "direct_vs_besselian_diagnostic": {"status": "DIAGNOSTIC", "reason": "comparison", 
            "maximum": {"delta_direct_minus_besselian_seconds": 0.2},
            "contacts": {"C1": {"status": "COMPARED", "delta_direct_minus_besselian_seconds": None}},
            "central_duration": {"delta_direct_minus_besselian_seconds": None},
            "interpretation": "Diagnostic only."},
    })
    assert "Global shadow paths" in markdown
    assert "Besselian reference regression" in markdown
    assert "bad reference" in markdown
    assert "DIAGNOSTIC" in markdown
    assert "comparison" in markdown


def test_main_writes_json_and_markdown_reports(tmp_path, monkeypatch, capsys):
    from eclipsekit.engine import EclipseEngine

    monkeypatch.setattr(EclipseEngine, "from_jpl", classmethod(lambda cls, *a, **k: SimpleNamespace()))
    monkeypatch.setattr(vf, "run_full_validation_suite", lambda *a, **k: {
        "status": "PASS", "summary": {"total_cases": 1, "passed": 1, "failed": 0,
        "errors": 0, "not_run_groups": []}, "local_cases": [],
        "global_maximum_cases": [], "global_path_cases": [],
        "besselian_reference": None, "direct_vs_besselian_diagnostic": None,
        "environment": {},
    })
    json_out, md_out = tmp_path / "report.json", tmp_path / "report.md"
    code = vf.main([
        "--references", str(DATA / "reference_cases.json"), "--skip-paths", "--skip-besselian",
        "--json-out", str(json_out), "--markdown-out", str(md_out),
    ])
    assert code == 0
    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert payload["inputs"]["path_manifest"] is None
    assert md_out.is_file()
    assert "Overall status" in capsys.readouterr().out


@pytest.mark.parametrize("args", [
    ["--path-samples", "2"],
    ["--time-scale-mode", "fixed_delta_t"],
    ["--delta-t-seconds", "70"],
])
def test_main_rejects_inconsistent_cli_options(args):
    with pytest.raises(SystemExit) as exc:
        vf.main(args)
    assert exc.value.code == 2


def test_main_reports_initialization_errors(tmp_path, monkeypatch):
    from eclipsekit.engine import EclipseEngine
    monkeypatch.setattr(EclipseEngine, "from_jpl", classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(RuntimeError("kernel unavailable"))))
    with pytest.raises(SystemExit) as exc:
        vf.main([
            "--references", str(DATA / "reference_cases.json"), "--skip-paths", "--skip-besselian",
            "--json-out", str(tmp_path / "report.json"), "--markdown-out", str(tmp_path / "report.md"),
        ])
    assert exc.value.code == 2
