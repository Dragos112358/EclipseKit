"""Phase 7.2 regression tests for validation input and failure contracts."""
from __future__ import annotations

import json

import pytest

from eclipsekit.validation import (
    ReferenceGlobalMaximumCase,
    ReferenceLocalCase,
    load_reference_cases,
    parse_utc_datetime,
    render_validation_markdown,
    run_global_maximum_reference_cases,
    run_local_reference_cases,
    run_validation_suite,
)


BASE_LOCAL = {
    "case_id": "local-1",
    "name": "Example observer",
    "event_time_utc": "2026-08-12T16:00:00Z",
    "latitude": 42.0,
    "longitude": 23.0,
    "expected_contacts_utc": {"C1": "2026-08-12T17:00:00Z"},
    "contact_tolerance_seconds": 30,
    "source_url": "https://example.org/reference",
    "source_precision_seconds": 60,
}

BASE_GLOBAL = {
    "case_id": "global-1",
    "name": "Example maximum",
    "event_time_utc": "2026-08-12T16:00:00Z",
    "expected_maximum_utc": "2026-08-12T17:00:00Z",
    "tolerance_seconds": 30,
    "source_url": "https://example.org/reference",
}


@pytest.mark.parametrize("value", [None, "", "   ", 42])
def test_parse_utc_rejects_non_string_or_empty_values(value):
    with pytest.raises(ValueError, match="non-empty"):
        parse_utc_datetime(value)


@pytest.mark.parametrize("value", ["not-a-time", "2026-02-30T00:00:00Z", "2026-08-12T17:00:00"])
def test_parse_utc_rejects_invalid_or_timezone_naive_values(value):
    with pytest.raises(ValueError):
        parse_utc_datetime(value)


@pytest.mark.parametrize("field", ["latitude", "longitude", "elevation_m", "contact_tolerance_seconds", "source_precision_seconds"])
def test_local_case_rejects_boolean_numeric_fields(field):
    raw = dict(BASE_LOCAL)
    raw[field] = True
    with pytest.raises(ValueError, match="finite number"):
        ReferenceLocalCase.from_mapping(raw)


@pytest.mark.parametrize("field", ["latitude", "longitude", "elevation_m", "contact_tolerance_seconds", "source_precision_seconds"])
def test_local_case_rejects_non_finite_numeric_fields(field):
    raw = dict(BASE_LOCAL)
    raw[field] = float("inf")
    with pytest.raises(ValueError, match="finite number"):
        ReferenceLocalCase.from_mapping(raw)


@pytest.mark.parametrize("raw, message", [
    (None, "JSON object"),
    ({"case_id": "x"}, "missing fields"),
    ({**BASE_LOCAL, "expected_contacts_utc": []}, "JSON object"),
    ({**BASE_LOCAL, "expected_contacts_utc": {}}, "at least one contact"),
    ({**BASE_LOCAL, "expected_contacts_utc": {"C5": "2026-08-12T17:00:00Z"}}, "Unsupported contact"),
    ({**BASE_LOCAL, "expected_contacts_utc": {"C1": "2026-08-12T17:00:00"}}, "explicit UTC offset"),
    ({**BASE_LOCAL, "expected_maximum_utc": "2026-08-12T17:00:00"}, "explicit UTC offset"),
    ({**BASE_LOCAL, "latitude": 90.1}, "WGS84 bounds"),
    ({**BASE_LOCAL, "longitude": -180.1}, "WGS84 bounds"),
    ({**BASE_LOCAL, "contact_tolerance_seconds": -0.1}, "non-negative"),
    ({**BASE_LOCAL, "source_precision_seconds": 0}, "positive"),
    ({**BASE_LOCAL, "case_id": " "}, "non-empty"),
    ({**BASE_LOCAL, "name": " "}, "non-empty"),
    ({**BASE_LOCAL, "source_url": " "}, "non-empty"),
    ({**BASE_LOCAL, "expected_eclipse_type": "hybrid"}, "must be total"),
    ({**BASE_LOCAL, "maximum_tolerance_seconds": -1}, "non-negative"),
])
def test_local_case_rejects_invalid_records(raw, message):
    with pytest.raises(ValueError, match=message):
        ReferenceLocalCase.from_mapping(raw)


def test_local_case_normalizes_optional_type_and_default_elevation():
    raw = {**BASE_LOCAL, "expected_eclipse_type": "TOTAL"}
    case = ReferenceLocalCase.from_mapping(raw)
    assert case.expected_eclipse_type == "total"
    assert case.elevation_m == 0.0
    assert case.expected_maximum_utc is None
    assert case.maximum_tolerance_seconds is None


@pytest.mark.parametrize("raw, message", [
    (None, "JSON object"),
    ({"case_id": "x"}, "missing fields"),
    ({**BASE_GLOBAL, "event_time_utc": "bad"}, "Invalid ISO-8601"),
    ({**BASE_GLOBAL, "expected_maximum_utc": "2026-08-12T17:00:00"}, "explicit UTC offset"),
    ({**BASE_GLOBAL, "tolerance_seconds": True}, "finite number"),
    ({**BASE_GLOBAL, "tolerance_seconds": float("nan")}, "finite number"),
    ({**BASE_GLOBAL, "tolerance_seconds": -1}, "non-negative"),
    ({**BASE_GLOBAL, "expected_eclipse_type": "unknown"}, "global expected_eclipse_type"),
    ({**BASE_GLOBAL, "case_id": " "}, "non-empty"),
    ({**BASE_GLOBAL, "name": " "}, "non-empty"),
    ({**BASE_GLOBAL, "source_url": " "}, "non-empty"),
])
def test_global_case_rejects_invalid_records(raw, message):
    with pytest.raises(ValueError, match=message):
        ReferenceGlobalMaximumCase.from_mapping(raw)


def test_global_case_normalizes_optional_eclipse_type():
    case = ReferenceGlobalMaximumCase.from_mapping(
        {**BASE_GLOBAL, "expected_eclipse_type": "HYBRID"}
    )
    assert case.expected_eclipse_type == "hybrid"


def test_load_reference_cases_rejects_missing_file_and_non_object_root(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_reference_cases(tmp_path / "missing.json")
    path = tmp_path / "root.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="root must be a JSON object"):
        load_reference_cases(path)


@pytest.mark.parametrize("document, message", [
    ({"schema_version": 1, "local_cases": {}}, "JSON arrays"),
    ({"schema_version": 1, "global_maximum_cases": "bad"}, "JSON arrays"),
    ({"schema_version": 1, "local_cases": [], "global_maximum_cases": []}, "no local or global"),
])
def test_load_reference_cases_rejects_invalid_case_collections(tmp_path, document, message):
    path = tmp_path / "references.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_reference_cases(path)


def test_load_reference_cases_rejects_duplicate_ids_across_case_groups(tmp_path):
    local = dict(BASE_LOCAL)
    global_case = dict(BASE_GLOBAL, case_id=local["case_id"])
    path = tmp_path / "references.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "local_cases": [local],
        "global_maximum_cases": [global_case],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="unique across"):
        load_reference_cases(path)


class _FakeTime:
    def __init__(self, iso):
        from datetime import datetime
        self.value = iso
        parsed = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        self._utc = (parsed.year, parsed.month, parsed.day, parsed.hour, parsed.minute,
                     parsed.second + parsed.microsecond / 1_000_000)

    @property
    def utc(self):
        return self._utc

    def utc_iso(self, delimiter="T", places=3):
        return self.value


class _Contacts:
    def __init__(self, values):
        self.values = values

    def as_dict(self):
        return self.values


class _Local:
    eclipse_type = "total"
    warnings = ["synthetic warning"]
    maximum = _FakeTime("2026-08-12T17:00:00Z")
    contacts = _Contacts({"C1": _FakeTime("2026-08-12T17:00:00Z")})


class _Engine:
    def __init__(self, local=None, error=None, maximum=None, global_error=None):
        self.local = local
        self.error = error
        self.maximum = maximum or _FakeTime("2026-08-12T17:00:00Z")
        self.global_error = global_error

    def calculate_local(self, *args, **kwargs):
        if self.error:
            raise self.error
        return self.local

    def find_global_maximum(self, *args, **kwargs):
        if self.global_error:
            raise self.global_error
        return self.maximum


def _local_case(**kwargs):
    return ReferenceLocalCase.from_mapping({**BASE_LOCAL, **kwargs})


def _global_case(**kwargs):
    return ReferenceGlobalMaximumCase.from_mapping({**BASE_GLOBAL, **kwargs})


def test_local_validation_records_calculation_error_and_missing_event():
    case = _local_case()
    error = run_local_reference_cases(_Engine(error=RuntimeError("ephemeris")), [case])[0]
    assert error["status"] == "ERROR"
    assert "ephemeris" in error["reason"]
    missing = run_local_reference_cases(_Engine(local=None), [case])[0]
    assert missing["status"] == "FAIL"
    assert "No local solar eclipse" in missing["reason"]


def test_local_validation_records_contact_type_and_maximum_failures():
    case = _local_case(
        expected_eclipse_type="annular",
        expected_maximum_utc="2026-08-12T17:05:00Z",
        maximum_tolerance_seconds=1,
    )
    result = run_local_reference_cases(_Engine(local=_Local()), [case])[0]
    assert result["status"] == "FAIL"
    assert result["type_check"]["passed"] is False
    assert result["maximum_check"]["passed"] is False
    assert result["warnings"] == ["synthetic warning"]


def test_local_validation_marks_missing_contact_as_failed_check():
    case = _local_case(expected_contacts_utc={"C1": "2026-08-12T17:00:00Z", "C2": "2026-08-12T18:00:00Z"})
    result = run_local_reference_cases(_Engine(local=_Local()), [case])[0]
    assert result["status"] == "FAIL"
    assert result["checks"][1]["computed_utc"] is None
    assert result["checks"][1]["passed"] is False


def test_global_validation_records_fail_and_exception():
    case = _global_case()
    failed = run_global_maximum_reference_cases(
        _Engine(maximum=_FakeTime("2026-08-12T17:01:00Z")), [case]
    )[0]
    assert failed["status"] == "FAIL"
    errored = run_global_maximum_reference_cases(
        _Engine(global_error=RuntimeError("global solver")), [case]
    )[0]
    assert errored["status"] == "ERROR"
    assert "global solver" in errored["reason"]


def test_validation_suite_with_no_cases_does_not_report_pass():
    report = run_validation_suite(_Engine(), [], [])
    assert report["status"] == "FAIL"
    assert report["local_cases"] == []
    assert report["global_maximum_cases"] == []


def test_legacy_markdown_renders_failed_and_empty_results():
    markdown = render_validation_markdown({
        "status": "ERROR",
        "local_cases": [{"name": "No contact", "status": "FAIL", "checks": []}],
        "global_maximum_cases": [{"name": "Solver error", "status": "ERROR", "check": None}],
    })
    assert "No contact" in markdown and "no result" in markdown
    assert "Solver error" in markdown
    assert "do not validate every EclipseKit feature" in markdown
