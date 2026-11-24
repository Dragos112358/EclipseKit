from datetime import datetime

import pytest
from pathlib import Path

from eclipsekit.models import (
    ShadowCorridorEdge, ShadowCorridorResult, ShadowCorridorSample, ShadowPathPoint,
)
from eclipsekit.shadow_corridor_validation import (
    load_corridor_reference_csv,
    validate_shadow_corridor_reference,
)

DATA = Path(__file__).parents[1] / "data" / "validation" / "global_corridor_2017_nasa.csv"


class FakeTime:
    def __init__(self, iso):
        self.iso = iso
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        self.utc = (dt.year, dt.month, dt.day, dt.hour, dt.minute, float(dt.second))

    def utc_iso(self, delimiter="T", places=3):
        return self.iso


def make_reference_corridor(swapped=False):
    references = load_corridor_reference_csv(DATA)
    samples = []
    for row in references:
        north = ShadowCorridorEdge(row.north_latitude_deg, row.north_longitude_deg)
        south = ShadowCorridorEdge(row.south_latitude_deg, row.south_longitude_deg)
        left, right = (south, north) if swapped else (north, south)
        moment = FakeTime(row.time_utc.isoformat().replace("+00:00", "Z"))
        center = ShadowPathPoint(moment, row.center_latitude_deg, row.center_longitude_deg,
                                 row.path_width_km, "umbral")
        samples.append(ShadowCorridorSample(
            time=moment, center=center,
            central_left=left, central_right=right,
            penumbra_left=None, penumbra_right=None,
            central_width_km=row.path_width_km, penumbral_width_km=None,
            shadow_velocity_km_s=1.0,
            central_phase_duration_estimate_seconds=row.central_duration_seconds,
            penumbral_duration_estimate_seconds=None, track_bearing_deg=90.0,
            central_boundary_coverage=1.0, penumbra_boundary_coverage=0.0,
        ))
    return ShadowCorridorResult(tuple(samples), len(samples), 72)


def test_load_nasa_2017_corridor_reference_fixture():
    rows = load_corridor_reference_csv(DATA)
    assert len(rows) == 3
    assert rows[0].path_width_km == 87
    assert rows[-1].central_duration_seconds == pytest.approx(143.3)


def test_corridor_reference_validation_exact_match_passes():
    report = validate_shadow_corridor_reference(
        make_reference_corridor(), DATA, source_id="NASA GSFC 2017 path table sample"
    )
    assert report.status == "PASS"
    assert report.passed_count == 3 and report.failed_count == 0
    assert report.maximum_boundary_error_km == pytest.approx(0.0)
    assert "PASS" in report.to_markdown()


def test_corridor_reference_validation_matches_left_right_independent_of_compass_side():
    report = validate_shadow_corridor_reference(
        make_reference_corridor(swapped=True), DATA, source_id="NASA table swapped-edge test"
    )
    assert report.status == "PASS"


def test_corridor_reference_validation_fails_when_edge_or_width_is_unavailable():
    corridor = make_reference_corridor()
    sample = corridor.samples[0]
    altered = ShadowCorridorSample(
        time=sample.time, center=sample.center, central_left=None, central_right=None,
        penumbra_left=None, penumbra_right=None, central_width_km=None,
        penumbral_width_km=None, shadow_velocity_km_s=None,
        central_phase_duration_estimate_seconds=None, penumbral_duration_estimate_seconds=None,
        track_bearing_deg=None, central_boundary_coverage=0.0, penumbra_boundary_coverage=0.0,
    )
    report = validate_shadow_corridor_reference(
        ShadowCorridorResult((altered, *corridor.samples[1:]), 3, 72),
        DATA, source_id="missing-edge test",
    )
    assert report.status == "FAIL"
    assert report.rows[0].status == "FAIL"
    assert "central left/right edge unavailable" in report.rows[0].message


def test_corridor_validation_rejects_missing_or_nonpositive_tolerances():
    with pytest.raises(ValueError, match="source_id"):
        validate_shadow_corridor_reference(make_reference_corridor(), DATA, source_id=" ")
    with pytest.raises(ValueError, match="width_tolerance_km"):
        validate_shadow_corridor_reference(make_reference_corridor(), DATA,
                                            source_id="test", width_tolerance_km=0)


def test_corridor_reference_loader_rejects_non_monotonic_times(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text(
        "time_utc,north_latitude_deg,north_longitude_deg,south_latitude_deg,south_longitude_deg,"
        "center_latitude_deg,center_longitude_deg,path_width_km,central_duration_seconds\n"
        "2026-01-01T00:00:00Z,1,2,0,2,0.5,2,10,20\n"
        "2026-01-01T00:00:00Z,1,2,0,2,0.5,2,10,20\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="strictly increasing"):
        load_corridor_reference_csv(path)


def test_corridor_validation_fails_rows_outside_time_matching_tolerance():
    corridor = make_reference_corridor()
    shifted_samples = []
    for sample in corridor.samples:
        shifted = FakeTime("2017-08-21T18:30:00.000Z")
        center = ShadowPathPoint(shifted, sample.center.latitude, sample.center.longitude,
                                 sample.center.width_km, sample.center.shadow_kind)
        shifted_samples.append(ShadowCorridorSample(
            time=shifted, center=center, central_left=sample.central_left,
            central_right=sample.central_right, penumbra_left=sample.penumbra_left,
            penumbra_right=sample.penumbra_right, central_width_km=sample.central_width_km,
            penumbral_width_km=sample.penumbral_width_km,
            shadow_velocity_km_s=sample.shadow_velocity_km_s,
            central_phase_duration_estimate_seconds=sample.central_phase_duration_estimate_seconds,
            penumbral_duration_estimate_seconds=sample.penumbral_duration_estimate_seconds,
            track_bearing_deg=sample.track_bearing_deg,
            central_boundary_coverage=sample.central_boundary_coverage,
            penumbra_boundary_coverage=sample.penumbra_boundary_coverage,
        ))
    report = validate_shadow_corridor_reference(
        ShadowCorridorResult(tuple(shifted_samples), 3, 72), DATA,
        source_id="time mismatch", max_time_offset_seconds=1.0,
    )
    assert report.status == "FAIL"
    assert report.failed_count == 3
    assert all("no sample within time tolerance" in row.message for row in report.rows)


def test_corridor_validation_handles_empty_corridor_without_metrics():
    report = validate_shadow_corridor_reference(
        ShadowCorridorResult((), 3, 72), DATA, source_id="empty corridor"
    )
    assert report.status == "FAIL"
    assert report.passed_count == 0 and report.failed_count == 3
    assert report.mean_center_error_km is None
    assert all(row.message == "corridor is empty" for row in report.rows)


def test_corridor_reference_loader_rejects_malformed_values_and_bad_coordinates(tmp_path):
    header = (
        "time_utc,north_latitude_deg,north_longitude_deg,south_latitude_deg,south_longitude_deg,"
        "center_latitude_deg,center_longitude_deg,path_width_km,central_duration_seconds\n"
    )
    path = tmp_path / "bad_values.csv"
    path.write_text(header + "2026-01-01T00:00:00Z,91,2,0,2,0.5,2,10,20\n", encoding="utf-8")
    with pytest.raises(ValueError, match="latitude"):
        load_corridor_reference_csv(path)
    path.write_text(header + "2026-01-01T00:00:00Z,1,2,0,2,0.5,2,nan,20\n", encoding="utf-8")
    with pytest.raises(ValueError, match="finite"):
        load_corridor_reference_csv(path)
    path.write_text(header + "2026-01-01T00:00:00Z,1,2,0,2,0.5,2,10,20\n", encoding="utf-8")
    with pytest.raises(ValueError, match="source_id"):
        validate_shadow_corridor_reference(make_reference_corridor(), path, source_id="")


def test_corridor_validation_rejects_non_numeric_or_boolean_tolerances():
    for value in (True, float("nan"), float("inf"), 0.0):
        with pytest.raises(ValueError, match="coordinate_tolerance_km"):
            validate_shadow_corridor_reference(
                make_reference_corridor(), DATA, source_id="invalid tolerance",
                coordinate_tolerance_km=value,
            )


def test_corridor_validation_objects_and_helpers_are_publicly_exported():
    from eclipsekit import (
        CorridorReferenceRow,
        CorridorValidationReport,
        CorridorValidationRow,
        load_corridor_reference_csv as public_loader,
        validate_shadow_corridor_reference as public_validator,
    )

    rows = public_loader(DATA)
    report = public_validator(
        make_reference_corridor(), DATA, source_id="public API import check"
    )
    assert isinstance(rows[0], CorridorReferenceRow)
    assert isinstance(report, CorridorValidationReport)
    assert isinstance(report.rows[0], CorridorValidationRow)
