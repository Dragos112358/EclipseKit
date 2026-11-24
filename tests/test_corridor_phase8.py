from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from eclipsekit import (
    ShadowCorridorEdge,
    ShadowCorridorResult,
    ShadowCorridorSample,
    ShadowPathPoint,
    compare_shadow_corridor_resolutions,
)
from eclipsekit.corridor_cli import main, parse_sample_counts
from eclipsekit.engine import EclipseEngine


class FakeTime:
    def __init__(self, value: datetime):
        self.value = value.astimezone(timezone.utc)
        self.utc = (
            self.value.year, self.value.month, self.value.day,
            self.value.hour, self.value.minute,
            self.value.second + self.value.microsecond / 1_000_000,
        )

    def utc_iso(self, delimiter="T", places=3):
        return self.value.strftime(f"%Y-%m-%d{delimiter}%H:%M:%S.%f")[:-3] + "Z"


def _make_corridor(count: int, *, center_shift_km: float = 0.0):
    start = datetime(2017, 8, 21, 17, 0, tzinfo=timezone.utc)
    samples = []
    for index in range(count):
        moment = FakeTime(start + timedelta(minutes=40 * index / (count - 1)))
        # Keep the fixture intentionally simple: the synthetic reference is
        # designed to test matching, reporting and output plumbing, not physics.
        fraction = index / (count - 1)
        center_lat = 1.0 + 0.1 * __import__("math").sin(2.0 * __import__("math").pi * fraction)
        center_lat += center_shift_km / 111.0
        width = 111.0 + 10.0 * __import__("math").sin(2.0 * __import__("math").pi * fraction) ** 2
        center = ShadowPathPoint(moment, center_lat, 0.0, width, "umbral")
        left = ShadowCorridorEdge(center_lat + 0.5, 0.0)
        right = ShadowCorridorEdge(center_lat - 0.5, 0.0)
        samples.append(ShadowCorridorSample(
            time=moment,
            center=center,
            central_left=left,
            central_right=right,
            penumbra_left=ShadowCorridorEdge(3.0, 0.0),
            penumbra_right=ShadowCorridorEdge(-1.0, 0.0),
            central_width_km=width,
            penumbral_width_km=444.0,
            shadow_velocity_km_s=1.0,
            central_phase_duration_estimate_seconds=60.0,
            penumbral_duration_estimate_seconds=240.0,
            track_bearing_deg=90.0,
            central_boundary_coverage=1.0,
            penumbra_boundary_coverage=1.0,
        ))
    return ShadowCorridorResult(tuple(samples), count, 36)


def _write_reference(path: Path):
    header = (
        "time_utc,north_latitude_deg,north_longitude_deg,south_latitude_deg,"
        "south_longitude_deg,center_latitude_deg,center_longitude_deg,"
        "path_width_km,central_duration_seconds\n"
    )
    rows = [
        "2017-08-21T17:00:00Z,1.5,0,0.5,0,1,0,111,60",
        "2017-08-21T17:20:00Z,1.5,0,0.5,0,1,0,111,60",
        "2017-08-21T17:40:00Z,1.5,0,0.5,0,1,0,111,60",
    ]
    path.write_text(header + "\n".join(rows) + "\n", encoding="utf-8")


def test_parse_sample_counts_requires_strictly_nested_grids():
    assert parse_sample_counts("3,11,21,51,101") == [3, 11, 21, 51, 101]
    with pytest.raises(Exception, match="nested uniform grids"):
        parse_sample_counts("3,10,21")
    with pytest.raises(Exception, match="strictly increasing"):
        parse_sample_counts("3,3,5")


def test_convergence_diagnostic_compares_nested_runs():
    result = compare_shadow_corridor_resolutions(
        {3: _make_corridor(3), 5: _make_corridor(5, center_shift_km=0.01)}
    )
    assert result["status"] == "DIAGNOSTIC"
    comparison = result["comparisons"][0]
    assert comparison["summary"]["valid_sample_count"] == 3
    differences = comparison["absolute_differences_from_finest"]
    assert differences["centerline_length_difference_km"] > 0.0
    assert differences["mean_central_width_difference_km"] > 0.0


def test_convergence_diagnostic_rejects_non_nested_sample_counts():
    with pytest.raises(ValueError, match="nested uniform grids"):
        compare_shadow_corridor_resolutions(
            {4: _make_corridor(4), 8: _make_corridor(8)}
        )


def test_corridor_cli_writes_json_markdown_and_gis_exports(tmp_path, monkeypatch):
    reference = tmp_path / "reference.csv"
    _write_reference(reference)

    class FakeEngine:
        context = type("Context", (), {"kernel_source": "fake-de440s.bsp"})()

        def global_shadow_corridor(self, start, end, *, samples, boundary_samples):
            assert boundary_samples == 36
            return _make_corridor(samples)

        def time_scale_diagnostics(self, when):
            return {
                "mode": "builtin",
                "utc": when,
                "delta_t_seconds": 69.0,
                "dut1_seconds": 0.1,
                "dut1_within_utc_limit": True,
            }

    monkeypatch.setattr(
        EclipseEngine,
        "from_jpl",
        classmethod(lambda cls, kernel, **kwargs: FakeEngine()),
    )
    output = tmp_path / "reports"
    code = main([
        "--reference", str(reference),
        "--convergence-samples", "3,5",
        "--boundary-samples", "36",
        "--output-dir", str(output),
    ])
    assert code == 0
    expected = [
        "shadow-corridor-2017.json",
        "shadow-corridor-2017.md",
        "shadow-corridor-2017.geojson",
        "shadow-corridor-2017.csv",
        "shadow-corridor-2017.kml",
    ]
    assert all((output / name).is_file() for name in expected)
    payload = json.loads((output / expected[0]).read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert payload["validation"]["passed_count"] == 3
    assert payload["convergence"]["reference_sample_count"] == 5
    assert payload["convergence"]["comparisons"][0]["absolute_differences_from_finest"][
        "centerline_length_difference_km"
    ] > 0.0


def test_corridor_cli_rejects_missing_reference(tmp_path):
    with pytest.raises(SystemExit) as exc:
        main(["--reference", str(tmp_path / "missing.csv")])
    assert exc.value.code == 2
