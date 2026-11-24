import json

import pytest

from eclipsekit.validation import (
    ReferenceGlobalMaximumCase,
    ReferenceLocalCase,
    load_reference_cases,
    parse_utc_datetime,
    time_difference_seconds,
    render_validation_markdown,
)


def test_parse_utc_accepts_z_and_offsets():
    assert parse_utc_datetime("2026-08-12T17:00:00Z").isoformat() == "2026-08-12T17:00:00+00:00"
    assert parse_utc_datetime("2026-08-12T20:00:00+03:00").isoformat() == "2026-08-12T17:00:00+00:00"


def test_parse_utc_accepts_python310_single_digit_fractional_seconds():
    parsed = parse_utc_datetime("2023-04-20T04:16:44.8Z")
    assert parsed.isoformat() == "2023-04-20T04:16:44.800000+00:00"


def test_parse_utc_pads_and_truncates_fractional_seconds_to_microseconds():
    assert parse_utc_datetime("2023-04-20T04:16:44.12Z").microsecond == 120000
    assert parse_utc_datetime("2023-04-20T04:16:44.12345Z").microsecond == 123450
    assert parse_utc_datetime("2023-04-20T04:16:44.123456789Z").microsecond == 123456


def test_parse_utc_accepts_fractional_seconds_with_explicit_offset():
    parsed = parse_utc_datetime("2023-04-20T07:16:44.8+03:00")
    assert parsed.isoformat() == "2023-04-20T04:16:44.800000+00:00"


def test_parse_utc_rejects_naive_timestamp():
    with pytest.raises(ValueError, match="explicit UTC offset"):
        parse_utc_datetime("2026-08-12T17:00:00")


def test_time_difference_is_signed():
    assert time_difference_seconds("2026-08-12T17:00:02Z", "2026-08-12T17:00:00Z") == 2.0
    assert time_difference_seconds("2026-08-12T16:59:58Z", "2026-08-12T17:00:00Z") == -2.0


def test_reference_local_case_validates_coordinates_and_times():
    case = ReferenceLocalCase.from_mapping({
        "case_id": "sample",
        "name": "Sample",
        "event_time_utc": "2026-08-12T16:00:00Z",
        "latitude": 10,
        "longitude": 20,
        "expected_contacts_utc": {"C1": "2026-08-12T17:00:00Z"},
        "contact_tolerance_seconds": 90,
        "source_url": "https://example.org/reference",
        "source_precision_seconds": 60,
    })
    assert case.latitude == 10
    assert case.expected_contacts_utc["C1"].endswith("Z")


def test_reference_local_case_rejects_unknown_contact():
    raw = {
        "case_id": "sample",
        "name": "Sample",
        "event_time_utc": "2026-08-12T16:00:00Z",
        "latitude": 10,
        "longitude": 20,
        "expected_contacts_utc": {"C5": "2026-08-12T17:00:00Z"},
        "contact_tolerance_seconds": 90,
        "source_url": "https://example.org/reference",
        "source_precision_seconds": 60,
    }
    with pytest.raises(ValueError, match="Unsupported contact"):
        ReferenceLocalCase.from_mapping(raw)


def test_reference_suite_fixture_has_four_local_and_two_global_cases():
    import pathlib

    fixture = pathlib.Path(__file__).parents[1] / "data" / "validation" / "reference_cases.json"
    local, global_cases = load_reference_cases(fixture)
    assert len(local) == 4
    assert {case.case_id for case in local} == {
        "solar-2026-08-12-leon",
        "solar-2024-04-08-dallas",
        "solar-2023-10-14-albuquerque",
        "solar-2022-10-25-london-partial",
    }
    assert len(global_cases) == 2
    assert {case.case_id for case in global_cases} == {
        "solar-2026-08-12-global-maximum",
        "solar-2023-04-20-hybrid-global-maximum",
    }
    assert global_cases[0].expected_maximum_utc == "2026-08-12T17:46:00Z"


def test_load_reference_cases_rejects_unknown_schema(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schema_version": 99, "local_cases": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported reference-case schema"):
        load_reference_cases(path)


def test_global_reference_case_validates_non_negative_tolerance():
    with pytest.raises(ValueError, match="non-negative"):
        ReferenceGlobalMaximumCase.from_mapping({
            "case_id": "x",
            "name": "x",
            "event_time_utc": "2026-08-12T17:00:00Z",
            "expected_maximum_utc": "2026-08-12T17:45:53.8Z",
            "tolerance_seconds": -1,
            "source_url": "https://example.org",
        })


def test_markdown_renderer_handles_calculation_error_case():
    report = {
        "status": "FAIL",
        "local_cases": [],
        "global_maximum_cases": [{"name": "broken case", "status": "ERROR", "check": None}],
    }
    text = render_validation_markdown(report)
    assert "broken case" in text
    assert "ERROR" in text


class _FakeTime:
    def __init__(self, value):
        self.value = value
        parsed = parse_utc_datetime(value)
        self._utc_tuple = (
            parsed.year, parsed.month, parsed.day,
            parsed.hour, parsed.minute, parsed.second + parsed.microsecond / 1_000_000,
        )

    @property
    def utc(self):
        return self._utc_tuple

    def utc_iso(self, delimiter="T", places=3):
        return self.value.replace("+00:00", "Z")


class _FakeContacts:
    def __init__(self, **values):
        self.values = values

    def as_dict(self):
        return self.values


class _FakeLocalResult:
    eclipse_type = "total"
    warnings = []
    maximum = _FakeTime("2026-08-12T17:45:00Z")
    contacts = _FakeContacts(
        C1=_FakeTime("2026-08-12T17:32:00Z"),
        C2=_FakeTime("2026-08-12T18:28:00Z"),
        C3=_FakeTime("2026-08-12T18:30:00Z"),
        C4=_FakeTime("2026-08-12T19:22:00Z"),
    )


class _FakeEngine:
    def calculate_local(self, *args, **kwargs):
        return _FakeLocalResult()

    def find_global_maximum(self, *args, **kwargs):
        return _FakeTime("2026-08-12T17:46:01Z")


def test_run_validation_suite_with_fake_engine_passes():
    from eclipsekit.validation import run_validation_suite

    local = [ReferenceLocalCase.from_mapping({
        "case_id": "sample-local",
        "name": "Sample total eclipse",
        "event_time_utc": "2026-08-12T16:00:00Z",
        "latitude": 42.6,
        "longitude": -5.5,
        "expected_eclipse_type": "total",
        "expected_contacts_utc": {
            "C1": "2026-08-12T17:32:00Z",
            "C2": "2026-08-12T18:28:00Z",
            "C3": "2026-08-12T18:30:00Z",
            "C4": "2026-08-12T19:22:00Z",
        },
        "contact_tolerance_seconds": 60,
        "source_url": "https://example.org/local",
        "source_precision_seconds": 60,
    })]
    global_cases = [ReferenceGlobalMaximumCase.from_mapping({
        "case_id": "sample-global",
        "name": "Sample geocentric maximum",
        "event_time_utc": "2026-08-12T17:00:00Z",
        "expected_maximum_utc": "2026-08-12T17:46:00Z",
        "tolerance_seconds": 10,
        "source_url": "https://example.org/global",
    })]
    report = run_validation_suite(_FakeEngine(), local, global_cases)
    assert report["status"] == "PASS"
    assert report["local_cases"][0]["status"] == "PASS"
    assert report["global_maximum_cases"][0]["status"] == "PASS"
