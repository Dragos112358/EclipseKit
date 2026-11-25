from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from scripts.validate_lunar_references import (
    compare_case, load_reference, parse_ut1, reference_moon_radius_overrides, validate_events,
)

REFERENCE_PATH = (
    Path(__file__).parent
    / "reference_data"
    / "lunar_eclipse_eclipsewise_2022_2028.json"
)


def test_parse_ut1_accepts_variable_fractional_precision():
    expected = datetime(2025, 9, 7, 15, 28, 6, 100000)

    assert parse_ut1("2025-09-07T15:28:06.1") == expected
    assert parse_ut1("2025-09-07T15:28:06.100 UT1") == expected
    assert parse_ut1("2025-09-07T15:28:06.100000Z") == expected


def test_parse_ut1_rejects_malformed_timestamp():
    with pytest.raises(ValueError, match="invalid UT1 timestamp"):
        parse_ut1("2025-09-07 15:28")


def test_external_reference_matrix_is_well_formed_and_covers_all_types():
    references = load_reference(REFERENCE_PATH)
    cases = references["cases"]

    assert len(cases) == 16
    assert {case["eclipse_type"] for case in cases} == {"penumbral", "partial", "total"}
    assert len({case["date"] for case in cases}) == len(cases)
    assert all(case["source_url"].startswith("https://") for case in cases)


def _matching_actual(reference: dict) -> dict:
    contacts = {
        name: (f"{value} UT1" if value is not None else None)
        for name, value in reference["contacts_ut1"].items()
    }
    return {
        "eclipse_type": reference["eclipse_type"],
        "maximum_ut1": f"{reference['greatest_ut1']} UT1",
        "contacts_ut1": contacts,
        "penumbral_magnitude": reference["penumbral_magnitude"] + 0.0001,
        "umbral_magnitude": reference["umbral_magnitude"] - 0.0001,
        "gamma": abs(reference["gamma_signed"]) + 0.0001,
    }


def test_reference_comparator_accepts_a_matching_event():
    reference = load_reference(REFERENCE_PATH)["cases"][7]
    report = compare_case(reference, _matching_actual(reference))

    assert report["status"] == "PASS"
    assert report["max_time_error_seconds"] == 0.0
    assert report["failures"] == []


def test_reference_comparator_detects_wrong_type_and_missing_contact():
    reference = load_reference(REFERENCE_PATH)["cases"][7]
    actual = _matching_actual(reference)
    actual["eclipse_type"] = "partial"
    actual["contacts_ut1"]["U2"] = None

    report = compare_case(reference, actual)

    assert report["status"] == "FAIL"
    assert any("type" in failure for failure in report["failures"])
    assert any("U2 is missing" in failure for failure in report["failures"])


def test_reference_comparator_preserves_abs_gamma_contract():
    reference = load_reference(REFERENCE_PATH)["cases"][7]
    actual = _matching_actual(reference)
    actual["gamma"] = abs(reference["gamma_signed"])

    report = compare_case(reference, actual)

    assert report["status"] == "PASS"
    assert report["gamma_abs_error"] == 0.0


def test_matrix_report_flags_missing_and_unreferenced_events():
    references = load_reference(REFERENCE_PATH)
    first = references["cases"][0]
    last = references["cases"][-1]
    report = validate_events(
        references,
        [_matching_actual(first), _matching_actual(last), {
            "maximum_ut1": "2028-06-01T00:00:00.000 UT1"
        }],
    )

    assert report["summary"]["passed"] == 2
    assert report["summary"]["failed"] == 14
    assert report["summary"]["unexpected_actual_events"] == ["2028-06-01"]
    assert report["summary"]["all_passed"] is False


def test_reference_comparator_reports_signed_contact_residuals():
    reference = load_reference(REFERENCE_PATH)["cases"][7]
    actual = _matching_actual(reference)
    actual["contacts_ut1"]["P1"] = "2025-09-07T15:28:18.000 UT1"

    report = compare_case(reference, actual)

    assert report["status"] == "PASS"
    assert report["time_deltas_seconds"]["P1"] == 12.0
    assert report["contact_details"]["P1"]["actual_ut1"] == "2025-09-07T15:28:18.000 UT1"


def test_reference_radius_override_is_limited_to_the_2027_source_case():
    references = load_reference(REFERENCE_PATH)
    overrides = reference_moon_radius_overrides(references)

    assert set(overrides) == {"2027-07-18"}
    assert overrides["2027-07-18"] == pytest.approx(1737.9791264853177)


def test_reference_radius_override_rejects_non_positive_or_non_finite_values():
    import pytest

    for value in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="finite and positive"):
            reference_moon_radius_overrides({
                "cases": [{"date": "2099-01-01", "moon_radius_km": value}]
            })
