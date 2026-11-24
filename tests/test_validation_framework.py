import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from eclipsekit.validation_framework import (
    PathReferenceCase,
    _interpolate_reference_track,
    load_path_reference_cases,
    render_full_validation_markdown,
    run_besselian_reference_validation,
    run_direct_besselian_diagnostic,
    run_path_reference_cases,
)


PROJECT_ROOT = Path(__file__).parents[1]
VALIDATION_DIR = PROJECT_ROOT / "data" / "validation"


def test_path_manifest_loads_four_documented_cases():
    cases = load_path_reference_cases(VALIDATION_DIR / "path_reference_manifest.json")
    assert len(cases) == 4
    assert {case.case_id for case in cases} == {
        "global-path-2017-08-21-nasa",
        "global-path-2019-07-02-nasa",
        "global-path-2020-06-21-nasa",
        "global-path-2026-08-12-nasa",
    }
    assert all(case.reference_file.is_file() for case in cases)


def test_path_manifest_rejects_duplicate_ids(tmp_path):
    manifest = {
        "schema_version": 1,
        "path_cases": [
            {
                "case_id": "same", "name": "One", "event_time_utc": "2026-08-12T17:00:00Z",
                "reference_file": "path.csv", "search_radius_hours": 1, "tolerance_km": 1,
                "source_url": "https://example.org", "source_time_step_seconds": 60,
                "source_coordinate_resolution_arcmin": 0.1,
            },
            {
                "case_id": "same", "name": "Two", "event_time_utc": "2026-08-12T17:00:00Z",
                "reference_file": "path.csv", "search_radius_hours": 1, "tolerance_km": 1,
                "source_url": "https://example.org", "source_time_step_seconds": 60,
                "source_coordinate_resolution_arcmin": 0.1,
            },
        ],
    }
    (tmp_path / "path.csv").write_text(
        "time_utc,latitude_deg,longitude_deg\n2026-08-12T17:00:00Z,0,0\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="unique"):
        load_path_reference_cases(manifest_path)


def test_path_reference_rejects_path_traversal(tmp_path):
    raw = {
        "case_id": "one", "name": "One", "event_time_utc": "2026-08-12T17:00:00Z",
        "reference_file": "../outside.csv", "search_radius_hours": 1, "tolerance_km": 1,
        "source_url": "https://example.org", "source_time_step_seconds": 60,
        "source_coordinate_resolution_arcmin": 0.1,
    }
    with pytest.raises(ValueError, match="inside the manifest directory"):
        PathReferenceCase.from_mapping(raw, base_dir=tmp_path)


def test_path_reference_rejects_non_finite_tolerance(tmp_path):
    raw = {
        "case_id": "one", "name": "One", "event_time_utc": "2026-08-12T17:00:00Z",
        "reference_file": "path.csv", "search_radius_hours": 1, "tolerance_km": float("nan"),
        "source_url": "https://example.org", "source_time_step_seconds": 60,
        "source_coordinate_resolution_arcmin": 0.1,
    }
    with pytest.raises(ValueError, match="finite"):
        PathReferenceCase.from_mapping(raw, base_dir=tmp_path)


def test_besselian_nasa_1999_reference_passes():
    report = run_besselian_reference_validation(
        VALIDATION_DIR / "besselian_1999_reference.json"
    )
    assert report["status"] == "PASS"
    assert report["checks"]["greatest_eclipse_epoch"]["delta_seconds"] == pytest.approx(-0.042, abs=0.01)
    assert report["checks"]["central_line_position"]["position_error_km"] < 0.5
    assert report["checks"]["local_contacts"]["passed"] is True


def test_besselian_reference_track_requires_strictly_increasing_offsets():
    with pytest.raises(ValueError, match="strictly increasing"):
        _interpolate_reference_track([
            {"offset_seconds": 10, "latitude_deg": 1, "longitude_deg": 2},
            {"offset_seconds": 10, "latitude_deg": 2, "longitude_deg": 3},
        ], 10)


class FakeTime:
    def __init__(self, iso_utc):
        from datetime import datetime, timezone

        parsed = datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
        self.tt = parsed.timestamp() / 86400.0


class FakePathEngine:
    def global_path_for_eclipse(self, *args, **kwargs):
        return [
            SimpleNamespace(time=FakeTime("2026-08-12T17:00:00Z"), latitude=10.0, longitude=20.0),
            SimpleNamespace(time=FakeTime("2026-08-12T17:02:00Z"), latitude=12.0, longitude=22.0),
        ]

    def time(self, value):
        return FakeTime(value)


def test_path_reference_runner_passes_complete_exact_match(tmp_path):
    reference_file = tmp_path / "path.csv"
    reference_file.write_text(
        "time_utc,latitude_deg,longitude_deg\n"
        "2026-08-12T17:01:00Z,11,21\n",
        encoding="utf-8",
    )
    case = PathReferenceCase(
        case_id="fake-path", name="Fake exact path", event_time_utc="2026-08-12T17:01:00Z",
        reference_file=reference_file, search_radius_hours=1.0, tolerance_km=0.01,
        source_url="https://example.org", source_time_step_seconds=60,
        source_coordinate_resolution_arcmin=0.1,
    )
    report = run_path_reference_cases(FakePathEngine(), [case], samples=3)
    assert report[0]["status"] == "PASS"
    assert report[0]["successful_comparisons"] == 1
    assert report[0]["max_error_km"] == pytest.approx(0.0, abs=1e-6)


def test_full_report_markdown_includes_failed_local_maximum_check():
    markdown = render_full_validation_markdown({
        "status": "FAIL",
        "generated_utc": "2026-11-22T12:00:00Z",
        "summary": {"total_cases": 1, "passed": 0, "failed": 1, "errors": 0},
        "local_cases": [{
            "name": "Broken local event", "status": "FAIL", "checks": [],
            "maximum_check": {"passed": False},
        }],
        "global_maximum_cases": [],
        "global_path_cases": [],
        "besselian_reference": None,
        "environment": {"pyeclipse_version": "0.1.0", "python_version": "3.12"},
    })
    assert "Broken local event" in markdown
    assert "maximum" in markdown
    assert "Global shadow paths" in markdown


def test_direct_vs_besselian_runner_reports_diagnostic_without_acceptance_threshold():
    from eclipsekit.besselian import BesselianElements, BesselianSolver
    from eclipsekit.models import Observer

    reference_path = VALIDATION_DIR / "besselian_1999_reference.json"
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    elements_path = reference_path.parent / reference["elements_file"]
    elements = BesselianElements.from_json(elements_path)
    observer_data = reference["local_observer"]
    observer = Observer(
        observer_data["latitude_deg"],
        observer_data["longitude_deg"],
        observer_data.get("elevation_m", 0.0),
        name=observer_data.get("name"),
    )
    local = BesselianSolver().calculate_local(
        elements, observer, delta_t_seconds=reference["delta_t_seconds"]
    )

    class FakeTimescale:
        @staticmethod
        def tt_jd(value):
            return SimpleNamespace(tt=float(value))

    class FakeContacts:
        def as_dict(self):
            return {
                name: SimpleNamespace(tt=contact.jd_tt + 5.0 / 86400.0)
                for name, contact in local.contacts.items()
            }

    direct_local = SimpleNamespace(
        contacts=FakeContacts(),
        maximum=SimpleNamespace(tt=local.maximum_jd_tt + 2.0 / 86400.0),
        eclipse_type=local.eclipse_type,
        central_phase_duration_seconds=local.central_phase_duration_seconds + 4.0,
    )

    class FakeDirectEngine:
        ts = FakeTimescale()
        config = None
        solver_config = None
        time_scale_mode = "builtin"

        def calculate_local(self, *args, **kwargs):
            assert kwargs["include_sunrise_sunset"] is False
            assert kwargs["include_shadow_metrics"] is False
            assert kwargs["include_planets"] is False
            return direct_local

    report = run_direct_besselian_diagnostic(FakeDirectEngine(), reference_path)
    assert report["status"] == "DIAGNOSTIC"
    assert report["maximum"]["delta_direct_minus_besselian_seconds"] == pytest.approx(2.0, abs=1e-4)
    assert report["contacts"]["C1"]["delta_direct_minus_besselian_seconds"] == pytest.approx(5.0, abs=1e-4)
    assert report["central_duration"]["delta_direct_minus_besselian_seconds"] == pytest.approx(4.0, abs=1e-4)
    assert report["eclipse_type"]["matches"] is True
    assert "No pass/fail tolerance" in report["interpretation"] or "No pass/fail" in report["interpretation"]


def test_full_validation_suite_refuses_to_pass_when_no_acceptance_case_selected():
    from eclipsekit.validation_framework import run_full_validation_suite

    report = run_full_validation_suite(
        SimpleNamespace(), [], [], path_cases=[], besselian_reference=None
    )
    assert report["status"] == "ERROR"
    assert report["summary"]["total_cases"] == 0
    assert "No acceptance cases" in report["summary"]["reason"]
