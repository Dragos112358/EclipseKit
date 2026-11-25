from __future__ import annotations

from datetime import date

import pytest

from eclipsekit.lunar_eclipse import (
    _contact_on_side, lunar_shadow_geometry, solve_lunar_eclipse,
)
from eclipsekit.timeutils import (
    calendar_from_julian_day,
    coerce_time,
    delta_t_seconds,
    julian_day_from_calendar,
    time_to_utc_iso,
    time_to_ut1_iso,
)


class FakeTime:
    def __init__(self, tt: float):
        self.tt = float(tt)
        self.ut1 = self.tt - 71.7 / 86400.0
        self.utc = (2025, 3, 14, 7, 0, 0.0)

    def utc_iso(self, delimiter="T", places=3):
        return "2025-03-14T07:00:00.000Z"


class FakeTimescale:
    def __init__(self):
        self.utc_calls = []

    def utc(self, *fields):
        self.utc_calls.append(fields)
        return FakeTime(2460000.0)

    def tt_jd(self, jd):
        return FakeTime(jd)


def synthetic_positions(maximum_jd: float, cross_track_at_center_km: float = 0.0):
    """Return simple geocentric Sun/Moon vectors crossing Earth's shadow."""
    def position_at(jd_tt: float):
        sun = (149_597_870.0, 0.0, 0.0)
        z = 0.5 * (jd_tt - maximum_jd) * 86400.0
        moon = (-384_400.0, cross_track_at_center_km, z)
        return sun, moon
    return position_at


def test_shadow_geometry_reports_total_partial_penumbral_and_miss():
    sun = (149_597_870.0, 0.0, 0.0)
    cases = [
        (0.0, "total"),
        (5_000.0, "partial"),
        (7_500.0, "penumbral"),
        (11_000.0, "none"),
    ]
    for offset_km, expected in cases:
        geometry = lunar_shadow_geometry(
            sun, (-384_400.0, offset_km, 0.0), shadow_enlargement=1.0
        )
        if geometry.penumbral_magnitude <= 0:
            actual = "none"
        elif geometry.umbral_magnitude >= 1:
            actual = "total"
        elif geometry.umbral_magnitude > 0:
            actual = "partial"
        else:
            actual = "penumbral"
        assert actual == expected


def test_shadow_geometry_validates_vectors_and_model_parameters():
    with pytest.raises(ValueError, match="3D vectors"):
        lunar_shadow_geometry((1.0, 2.0), (3.0, 4.0, 5.0))
    with pytest.raises(ValueError, match="finite"):
        lunar_shadow_geometry((float("nan"), 0.0, 0.0), (1.0, 2.0, 3.0))
    with pytest.raises(ValueError, match="shadow_enlargement"):
        lunar_shadow_geometry((1.0, 0.0, 0.0), (-1.0, 0.0, 0.0), shadow_enlargement=0)


def test_total_lunar_eclipse_solver_returns_ordered_p1_to_p4_contacts():
    center_jd = 2460748.79
    center = FakeTime(center_jd)
    result = solve_lunar_eclipse(
        center,
        synthetic_positions(center_jd),
        FakeTime,
        search_half_window_hours=8.0,
        contact_search_half_window_hours=8.0,
        contact_step_seconds=120.0,
    )
    assert result is not None
    assert result.eclipse_type == "total"
    assert result.penumbral_magnitude > 1.0
    assert result.umbral_magnitude >= 1.0
    contacts = result.contacts
    assert contacts.p1.tt < contacts.u1.tt < contacts.u2.tt
    assert contacts.u2.tt < contacts.greatest.tt < contacts.u3.tt
    assert contacts.u3.tt < contacts.u4.tt < contacts.p4.tt
    assert contacts.penumbral_duration_seconds > contacts.partial_duration_seconds
    assert contacts.totality_duration_seconds > 0
    payload = result.to_dict()
    assert payload["event_type"] == "lunar_eclipse"
    assert payload["contacts"]["P1"].endswith("Z")
    assert payload["scientific_status"] == "experimental_geocentric_herald_sinnott_oblate_earth_shadow_model"
    assert payload["shadow_model"] == "herald_sinnott"
    assert payload["atmospheric_nel_height_km"] == pytest.approx(87.0)
    assert payload["flattening_coefficient"] == pytest.approx(0.003353)
    assert payload["gamma"] == pytest.approx(
        result.axis_distance_km / result.earth_radius_km
    )
    assert payload["epsilon_deg"] == pytest.approx(result.axis_distance_deg)
    assert payload["earth_model"] == "WGS84 oblate Earth with Herald-Sinnott NEL"
    assert payload["radii_km"]["earth_polar_wgs84"] == pytest.approx(6356.752314245)


def test_solver_classifies_partial_and_penumbral_events():
    center_jd = 2460000.5
    for offset_km, expected in ((5_000.0, "partial"), (7_500.0, "penumbral")):
        result = solve_lunar_eclipse(
            FakeTime(center_jd),
            synthetic_positions(center_jd, offset_km),
            FakeTime,
            contact_step_seconds=120.0,
        )
        assert result is not None
        assert result.eclipse_type == expected
        assert result.contacts.p1 is not None
        assert result.contacts.p4 is not None
        if expected == "partial":
            assert result.contacts.u1 is not None
            assert result.contacts.u4 is not None
            assert result.contacts.u2 is None
            assert result.contacts.u3 is None
        else:
            assert result.umbral_magnitude < 0
            assert result.contacts.u1 is None
            assert result.contacts.u4 is None


def test_solver_returns_none_when_moon_misses_penumbra():
    center_jd = 2460000.5
    result = solve_lunar_eclipse(
        FakeTime(center_jd),
        synthetic_positions(center_jd, 11_000.0),
        FakeTime,
    )
    assert result is None


def test_calendar_historical_cutover_is_contiguous_and_skipped_dates_rejected():
    julian_last = julian_day_from_calendar(1582, 10, 4, gregorian=False)
    gregorian_first = julian_day_from_calendar(1582, 10, 15, gregorian=True)
    assert gregorian_first - julian_last == pytest.approx(1.0)
    assert calendar_from_julian_day(julian_last)[:3] == (1582, 10, 4)
    assert calendar_from_julian_day(gregorian_first)[:3] == (1582, 10, 15)
    with pytest.raises(ValueError, match="do not exist"):
        julian_day_from_calendar(1582, 10, 10)


def test_julian_and_gregorian_proleptic_dates_are_distinct():
    jd_julian = julian_day_from_calendar(2024, 1, 1, gregorian=False)
    assert calendar_from_julian_day(jd_julian, gregorian=False)[:3] == (2024, 1, 1)
    assert calendar_from_julian_day(jd_julian, gregorian=True)[:3] == (2024, 1, 14)
    assert julian_day_from_calendar(1700, 2, 29, gregorian=False) > 0
    with pytest.raises(ValueError, match="day must be valid"):
        julian_day_from_calendar(1700, 2, 29, gregorian=True)


def test_coerce_time_accepts_explicit_calendar_for_date_strings_and_date_objects():
    ts = FakeTimescale()
    coerce_time(ts, "2024-01-01", calendar="julian")
    assert ts.utc_calls[-1][:3] == (2024, 1, 14)
    coerce_time(ts, date(2024, 1, 1), calendar="gregorian")
    assert ts.utc_calls[-1][:3] == (2024, 1, 1)
    with pytest.raises(ValueError, match="do not exist"):
        coerce_time(ts, "1582-10-10", calendar="historical")


def test_time_formatter_can_emit_julian_calendar_for_modern_instant():
    gregorian_jd = julian_day_from_calendar(2025, 3, 14, 7, gregorian=True)
    tt_jd = gregorian_jd + delta_t_seconds(2025, 3) / 86400.0
    value = FakeTime(tt_jd)
    assert time_to_utc_iso(value, calendar="gregorian").startswith("2025-03-14")
    assert time_to_utc_iso(value, calendar="julian").startswith("2025-03-01")


def test_calendar_timed_iso_strings_respect_selected_julian_calendar():
    ts = FakeTimescale()
    coerce_time(ts, "2025-03-01T12:30:00", calendar="julian")
    assert len(ts.utc_calls) == 1
    assert ts.utc_calls[0][:5] == (2025, 3, 14, 12, 30)
    assert ts.utc_calls[0][5] == pytest.approx(0.0, abs=5e-5)


def test_calendar_timed_iso_strings_keep_explicit_timezone_as_absolute_instant():
    from datetime import datetime, timezone

    class DateTimeTimescale(FakeTimescale):
        def __init__(self):
            super().__init__()
            self.datetime_calls = []

        def from_datetime(self, value):
            self.datetime_calls.append(value)
            return FakeTime(2460748.0)

    ts = DateTimeTimescale()
    coerce_time(ts, "2025-03-01T12:30:00+03:00", calendar="julian")
    assert ts.datetime_calls == [datetime(2025, 3, 1, 9, 30, tzinfo=timezone.utc)]


def test_modern_utc_instant_can_be_formatted_as_proleptic_julian_date():
    value = FakeTime(tt=2460748.79)
    formatted = time_to_utc_iso(value, calendar="julian")
    assert formatted.startswith("2025-03-01T07:00:00")

def test_herald_sinnott_shadow_is_angle_dependent_and_uses_earth_flattening():
    sun = (149_597_870.0, 0.0, 0.0)
    moon_east = (-384_400.0, 5_000.0, 0.0)
    moon_north = (-384_400.0, 0.0, 5_000.0)
    east_geometry = lunar_shadow_geometry(sun, moon_east)
    north_geometry = lunar_shadow_geometry(sun, moon_north)

    assert east_geometry.shadow_model == "herald_sinnott"
    assert east_geometry.earth_radius_factor > north_geometry.earth_radius_factor
    assert east_geometry.umbra_radius_rad > north_geometry.umbra_radius_rad
    assert east_geometry.penumbra_radius_rad > north_geometry.penumbra_radius_rad
    assert east_geometry.earth_radius_factor == pytest.approx(
        1.0 + 87.0 / 6378.137, abs=1e-10
    )


def test_circular_shadow_model_is_available_for_legacy_reproduction():
    sun = (149_597_870.0, 0.0, 0.0)
    east = lunar_shadow_geometry(
        sun, (-384_400.0, 5_000.0, 0.0), shadow_model="circular"
    )
    north = lunar_shadow_geometry(
        sun, (-384_400.0, 0.0, 5_000.0), shadow_model="circular"
    )
    assert east.shadow_model == "circular"
    assert east.umbra_radius_rad == pytest.approx(north.umbra_radius_rad, abs=1e-14)
    assert east.penumbra_radius_rad == pytest.approx(north.penumbra_radius_rad, abs=1e-14)


def test_herald_sinnott_parameters_are_validated():
    sun = (149_597_870.0, 0.0, 0.0)
    moon = (-384_400.0, 100.0, 0.0)
    with pytest.raises(ValueError, match="atmospheric_nel_height_km"):
        lunar_shadow_geometry(sun, moon, atmospheric_nel_height_km=-1.0)
    with pytest.raises(ValueError, match="shadow_model"):
        lunar_shadow_geometry(sun, moon, shadow_model="unknown")


def test_result_reports_utc_ut1_and_tt_separately():
    center_jd = 2460748.79
    result = solve_lunar_eclipse(
        FakeTime(center_jd), synthetic_positions(center_jd), FakeTime,
        contact_step_seconds=300.0,
    )
    assert result is not None
    payload = result.to_dict()
    assert payload["maximum_utc"].endswith("Z")
    assert payload["maximum_ut1"].endswith("UT1")
    assert payload["maximum_jd_tt"] == pytest.approx(center_jd, abs=1e-5)
    assert payload["contacts_ut1"]["P1"].endswith("UT1")
    assert payload["contacts_jd_tt"]["P1"] is not None


def test_time_to_ut1_iso_uses_ut1_julian_day_and_calendar():
    value = FakeTime(2460748.79)
    output = time_to_ut1_iso(value, calendar="gregorian")
    assert output.endswith("UT1")
    assert output.startswith("2025-03-14T")


def test_contact_solver_uses_exact_center_when_radial_approximation_misses_grazing_case():
    maximum_jd = 2461605.0
    contact_jd = maximum_jd + 120.0 / 86400.0

    def exact_residual(jd: float) -> float:
        return (jd - contact_jd) * 86400.0

    # The approximate radial residual incorrectly starts outside and never
    # brackets the contact. The exact residual still proves the overlap at max.
    def coarse_residual(jd: float) -> float:
        return exact_residual(jd) + 180.0

    root = _contact_on_side(
        coarse_residual,
        exact_residual,
        maximum_jd,
        1,
        half_window_hours=1.0,
        step_seconds=60.0,
        tolerance_seconds=0.01,
    )

    assert root is not None
    assert (root - contact_jd) * 86400.0 == pytest.approx(0.0, abs=0.02)


def test_contact_solver_falls_back_to_exact_scan_when_coarse_curve_never_exits():
    maximum_jd = 2461605.0
    contact_jd = maximum_jd + 180.0 / 86400.0

    def exact_residual(jd: float) -> float:
        return (jd - contact_jd) * 86400.0

    root = _contact_on_side(
        lambda _jd: -1.0,
        exact_residual,
        maximum_jd,
        1,
        half_window_hours=1.0,
        step_seconds=60.0,
        tolerance_seconds=0.01,
    )

    assert root is not None
    assert (root - contact_jd) * 86400.0 == pytest.approx(0.0, abs=0.02)


def test_contact_solver_does_not_create_contact_when_exact_geometry_is_outside():
    maximum_jd = 2461605.0
    root = _contact_on_side(
        lambda _jd: -1.0,
        lambda jd: 1.0 + (jd - maximum_jd) * 86400.0,
        maximum_jd,
        1,
        half_window_hours=1.0,
        step_seconds=60.0,
        tolerance_seconds=0.01,
    )
    assert root is None
