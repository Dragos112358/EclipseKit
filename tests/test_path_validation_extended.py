from __future__ import annotations

from types import SimpleNamespace

import pytest

from eclipsekit.path_validation import (
    _parse_reference_time,
    compare_shadow_path,
    great_circle_distance_km,
    interpolate_shadow_position,
    load_path_reference,
)


class FakeTime:
    def __init__(self, value: float):
        self.tt = float(value)


class UtcEngine:
    def __init__(self):
        self.calls = []

    def time(self, value):
        self.calls.append(value)
        return FakeTime(100.0)


class Ut1MethodEngine:
    def __init__(self):
        self.calls = []

    def time_from_ut1(self, *fields):
        self.calls.append(fields)
        return FakeTime(101.0)


class Ut1TimescaleEngine:
    def __init__(self):
        self.ts = SimpleNamespace(ut1=lambda *fields: FakeTime(102.0))


def path_point(tt, lat=0.0, lon=0.0):
    return SimpleNamespace(time=FakeTime(tt), latitude=lat, longitude=lon)


def test_parse_reference_time_normalizes_offset_to_utc():
    engine = UtcEngine()
    assert _parse_reference_time(engine, "2026-08-12T20:00:00+03:00") == 100.0
    assert engine.calls == ["2026-08-12T17:00:00Z"]


def test_parse_reference_time_uses_engine_ut1_method_and_preserves_fractional_seconds():
    engine = Ut1MethodEngine()
    value = _parse_reference_time(engine, "2026-08-12T17:00:12.250Z", "ut1")
    assert value == 101.0
    assert engine.calls == [(2026, 8, 12, 17, 0, 12.25)]


def test_parse_reference_time_falls_back_to_engine_timescale_ut1():
    engine = Ut1TimescaleEngine()
    assert _parse_reference_time(engine, "2026-08-12T17:00:00Z", "ut1") == 102.0


@pytest.mark.parametrize("value", [None, "", "   ", 123])
def test_parse_reference_time_rejects_empty_or_non_string_values(value):
    with pytest.raises(ValueError, match="non-empty ISO-8601"):
        _parse_reference_time(UtcEngine(), value)


def test_parse_reference_time_rejects_naive_and_invalid_clock():
    with pytest.raises(ValueError, match="include Z or an offset"):
        _parse_reference_time(UtcEngine(), "2026-08-12T17:00:00")
    with pytest.raises(ValueError, match="reference clock"):
        _parse_reference_time(UtcEngine(), "2026-08-12T17:00:00Z", "local")


def test_interpolate_shadow_position_rejects_duplicate_times():
    points = [path_point(10.0, 1, 2), path_point(10.0, 3, 4)]
    with pytest.raises(ValueError, match="duplicate/non-increasing"):
        interpolate_shadow_position(points, 10.0)


def test_interpolate_shadow_position_accepts_exact_endpoints_and_sorts_input():
    points = [path_point(20, 20, 40), path_point(10, 10, 30)]
    assert interpolate_shadow_position(points, 10) == (10.0, 30.0)
    assert interpolate_shadow_position(points, 20) == (20.0, 40.0)


def test_great_circle_distance_has_expected_equatorial_arc():
    distance = great_circle_distance_km(0, 0, 0, 1)
    assert distance == pytest.approx(111.195, rel=2e-4)
    assert great_circle_distance_km(0, 179.5, 0, -179.5) < 112.0


def test_load_path_reference_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_path_reference(tmp_path / "absent.csv")


@pytest.mark.parametrize(
    "header, row",
    [
        ("time_utc,latitude_deg,longitude_deg", ""),
        ("time_utc,time_ut1,latitude_deg,longitude_deg", "2026-08-12T17:00:00Z,2026-08-12T17:00:00Z,1,2"),
        ("latitude_deg,longitude_deg", "1,2"),
    ],
)
def test_load_path_reference_rejects_empty_or_ambiguous_schema(tmp_path, header, row):
    path = tmp_path / "bad.csv"
    path.write_text(header + "\n" + row + ("\n" if row else ""), encoding="utf-8")
    with pytest.raises(ValueError):
        load_path_reference(path)


def test_load_path_reference_rejects_missing_and_naive_timestamps(tmp_path):
    missing = tmp_path / "missing-time.csv"
    missing.write_text("time_utc,latitude_deg,longitude_deg\n,1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Missing reference time"):
        load_path_reference(missing)

    naive = tmp_path / "naive.csv"
    naive.write_text(
        "time_utc,latitude_deg,longitude_deg\n2026-08-12T17:00:00,1,2\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="include Z or an offset"):
        load_path_reference(naive)


def test_load_path_reference_rejects_non_numeric_coordinates(tmp_path):
    path = tmp_path / "nonnumeric.csv"
    path.write_text(
        "time_utc,latitude_deg,longitude_deg\n2026-08-12T17:00:00Z,north,2\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_path_reference(path)


def test_load_path_reference_rejects_duplicate_time_column_values(tmp_path):
    path = tmp_path / "ut1.csv"
    path.write_text(
        "time_ut1,latitude_deg,longitude_deg\n2026-08-12T17:00:00Z,1,2\n",
        encoding="utf-8",
    )
    rows = load_path_reference(path)
    assert rows == [{
        "time_ut1": "2026-08-12T17:00:00Z", "latitude_deg": 1.0, "longitude_deg": 2.0,
    }]


def test_compare_shadow_path_rejects_invalid_clock_and_empty_inputs():
    with pytest.raises(ValueError, match="reference_clock"):
        compare_shadow_path(UtcEngine(), [path_point(1), path_point(2)], [{"time_utc": "x"}], reference_clock="bad")
    with pytest.raises(ValueError, match="at least two"):
        compare_shadow_path(UtcEngine(), [path_point(1)], [{"time_utc": "x"}])
    with pytest.raises(ValueError, match="empty"):
        compare_shadow_path(UtcEngine(), [path_point(1), path_point(2)], [])


def test_compare_shadow_path_supports_explicit_ut1_override_on_utc_column():
    engine = Ut1MethodEngine()
    points = [path_point(100, 10, 20), path_point(102, 12, 22)]
    rows = [{"time_utc": "2026-08-12T17:00:00Z", "latitude_deg": 11, "longitude_deg": 21}]
    report = compare_shadow_path(engine, points, rows, reference_clock="ut1")
    assert report["reference_clocks"] == ["ut1"]
    assert report["successful_comparisons"] == 1


def test_compare_shadow_path_records_malformed_row_and_reports_none_metrics():
    points = [path_point(100), path_point(102)]
    report = compare_shadow_path(UtcEngine(), points, [{"time_utc": "not-a-time"}])
    assert report["error_count"] == 1
    assert report["successful_comparisons"] == 0
    assert report["mean_error_km"] is None
    assert report["rms_error_km"] is None
    assert report["max_error_km"] is None


def test_compare_shadow_path_missing_time_key_is_reported_not_raised():
    points = [path_point(100), path_point(102)]
    report = compare_shadow_path(UtcEngine(), points, [{"latitude_deg": 1, "longitude_deg": 2}])
    assert report["error_count"] == 1
    assert report["comparisons"][0]["status"] == "ERROR"


def test_path_validation_cli_generates_success_report(tmp_path, monkeypatch, capsys):
    from eclipsekit import path_validation

    class CliEngine:
        time_scale_mode = "builtin"

        def time(self, value):
            return FakeTime(101.0)

        def global_path_for_eclipse(self, date, **kwargs):
            assert date == "2026-08-12"
            assert kwargs["samples"] == 5
            return [path_point(100, 10, 20), path_point(102, 12, 22)]

        def time_scale_diagnostics(self, date):
            return {"delta_t_seconds": 75.0, "dut1_seconds": 0.1}

    engine = CliEngine()
    monkeypatch.setattr(
        path_validation.EclipseEngine, "from_jpl",
        classmethod(lambda cls, kernel, **kwargs: engine),
    )
    reference = tmp_path / "reference.csv"
    reference.write_text(
        "time_utc,latitude_deg,longitude_deg\n2026-08-12T17:00:00Z,11,21\n",
        encoding="utf-8",
    )
    output = tmp_path / "reports" / "path.json"
    status = path_validation.main([
        "--reference", str(reference), "--json-out", str(output), "--samples", "5",
        "--tolerance-km", "1",
    ])
    assert status == 0
    report = __import__("json").loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["successful_comparisons"] == 1
    assert "Global path validation: PASS" in capsys.readouterr().out


def test_path_validation_cli_returns_nonzero_when_reference_fails(tmp_path, monkeypatch):
    from eclipsekit import path_validation

    class CliEngine:
        time_scale_mode = "builtin"

        def time(self, value):
            return FakeTime(101.0)

        def global_path_for_eclipse(self, date, **kwargs):
            return [path_point(100, 10, 20), path_point(102, 12, 22)]

        def time_scale_diagnostics(self, date):
            return {"delta_t_seconds": 75.0, "dut1_seconds": 0.1}

    monkeypatch.setattr(
        path_validation.EclipseEngine, "from_jpl",
        classmethod(lambda cls, kernel, **kwargs: CliEngine()),
    )
    reference = tmp_path / "reference.csv"
    reference.write_text(
        "time_utc,latitude_deg,longitude_deg\n2026-08-12T17:00:00Z,40,70\n",
        encoding="utf-8",
    )
    status = path_validation.main([
        "--reference", str(reference), "--json-out", str(tmp_path / "fail.json"),
        "--samples", "5", "--tolerance-km", "1",
    ])
    assert status == 1


def test_path_validation_cli_fixed_delta_t_requires_explicit_value():
    from eclipsekit.path_validation import main

    with pytest.raises(SystemExit) as error:
        main(["--time-scale-mode", "fixed_delta_t"])
    assert error.value.code == 2


def test_path_validation_cli_rejects_delta_t_for_builtin_mode():
    from eclipsekit.path_validation import main

    with pytest.raises(SystemExit) as error:
        main(["--time-scale-mode", "builtin", "--delta-t-seconds", "71.4"])
    assert error.value.code == 2


def test_path_validation_cli_reports_engine_initialization_error(monkeypatch):
    from eclipsekit import path_validation

    def fail(cls, kernel, **kwargs):
        raise RuntimeError("synthetic initialization failure")

    monkeypatch.setattr(path_validation.EclipseEngine, "from_jpl", classmethod(fail))
    with pytest.raises(SystemExit) as error:
        path_validation.main([])
    assert error.value.code == 2


def test_path_validation_cli_rejects_invalid_numerical_arguments():
    from eclipsekit.path_validation import main

    with pytest.raises(SystemExit) as error:
        main(["--samples", "2"])
    assert error.value.code == 2
