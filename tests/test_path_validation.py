from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from eclipsekit.path_validation import (
    compare_shadow_path,
    great_circle_distance_km,
    interpolate_shadow_position,
    load_path_reference,
)


class FakeTime:
    def __init__(self, iso_utc):
        parsed = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
        self.tt = parsed.replace(tzinfo=timezone.utc).timestamp() / 86400.0


class FakeEngine:
    def time(self, value):
        return FakeTime(value)


def point(iso_utc, latitude, longitude):
    return SimpleNamespace(
        time=FakeTime(iso_utc), latitude=latitude, longitude=longitude
    )


def test_interpolate_shadow_position_across_antimeridian():
    points = [
        point("2026-08-12T17:00:00Z", 10.0, 179.0),
        point("2026-08-12T17:02:00Z", 12.0, -179.0),
    ]
    target = FakeTime("2026-08-12T17:01:00Z").tt
    latitude, longitude = interpolate_shadow_position(points, target)
    assert latitude == pytest.approx(11.0)
    assert abs(abs(longitude) - 180.0) < 1e-7


def test_interpolate_shadow_position_rejects_outside_range():
    points = [
        point("2026-08-12T17:00:00Z", 10.0, 20.0),
        point("2026-08-12T17:02:00Z", 12.0, 22.0),
    ]
    with pytest.raises(ValueError, match="outside"):
        interpolate_shadow_position(points, FakeTime("2026-08-12T17:03:00Z").tt)


def test_great_circle_distance_zero_for_same_position():
    assert great_circle_distance_km(65.0, -25.0, 65.0, -25.0) == pytest.approx(0.0)


def test_compare_shadow_path_returns_error_metrics():
    points = [
        point("2026-08-12T17:00:00Z", 10.0, 20.0),
        point("2026-08-12T17:02:00Z", 12.0, 22.0),
    ]
    rows = [{
        "time_utc": "2026-08-12T17:01:00Z",
        "latitude_deg": 11.0,
        "longitude_deg": 21.0,
    }]
    result = compare_shadow_path(FakeEngine(), points, rows)
    assert result["reference_count"] == 1
    assert result["max_error_km"] == pytest.approx(0.0, abs=1e-6)


def test_load_path_reference_rejects_invalid_coordinates(tmp_path):
    path = tmp_path / "path.csv"
    path.write_text(
        "time_utc,latitude_deg,longitude_deg\n"
        "2026-08-12T17:00:00Z,91,20\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="WGS84"):
        load_path_reference(path)


class FakeUt1Engine(FakeEngine):
    def __init__(self):
        self.ut1_calls = []

    def time_from_ut1(self, year, month, day, hour=0, minute=0, second=0.0):
        value = (
            f"{year:04d}-{month:02d}-{day:02d}T"
            f"{hour:02d}:{minute:02d}:{int(second):02d}Z"
        )
        self.ut1_calls.append(value)
        return FakeTime(value)


def test_load_path_reference_accepts_time_ut1_column(tmp_path):
    path = tmp_path / "path-ut1.csv"
    path.write_text(
        "time_ut1,latitude_deg,longitude_deg\n"
        "2026-08-12T17:00:00Z,10,20\n",
        encoding="utf-8",
    )
    rows = load_path_reference(path)
    assert rows[0]["time_ut1"] == "2026-08-12T17:00:00Z"


def test_compare_shadow_path_auto_uses_ut1_column():
    engine = FakeUt1Engine()
    points = [
        point("2026-08-12T17:00:00Z", 10.0, 20.0),
        point("2026-08-12T17:02:00Z", 12.0, 22.0),
    ]
    rows = [{
        "time_ut1": "2026-08-12T17:01:00Z",
        "latitude_deg": 11.0,
        "longitude_deg": 21.0,
    }]
    report = compare_shadow_path(engine, points, rows)
    assert engine.ut1_calls == ["2026-08-12T17:01:00Z"]
    assert report["reference_clocks"] == ["ut1"]
    assert report["successful_comparisons"] == 1
    assert report["max_error_km"] == pytest.approx(0.0, abs=1e-6)


def test_compare_shadow_path_records_out_of_range_instead_of_raising():
    points = [
        point("2026-08-12T17:00:00Z", 10.0, 20.0),
        point("2026-08-12T17:02:00Z", 12.0, 22.0),
    ]
    rows = [{
        "time_utc": "2026-08-12T17:03:00Z",
        "latitude_deg": 13.0,
        "longitude_deg": 23.0,
    }]
    report = compare_shadow_path(FakeEngine(), points, rows)
    assert report["error_count"] == 1
    assert report["successful_comparisons"] == 0
    assert report["comparisons"][0]["status"] == "ERROR"
    assert "outside" in report["comparisons"][0]["error"]
