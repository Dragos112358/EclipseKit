from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
import math
from types import SimpleNamespace

import pytest

from eclipsekit.timeutils import (
    calendar_from_julian_day,
    coerce_time,
    delta_t_seconds,
    julian_day_from_calendar,
    time_from_calendar,
    time_to_utc_iso,
)


class FakeTime:
    def __init__(self, tt=2460000.0, *, utc_tuple=(2026, 1, 1, 0, 0, 0.0), iso=None):
        self.tt = tt
        self.ut1 = tt - 70.0 / 86400.0
        self.utc = utc_tuple
        self._iso = iso or "2026-01-01T00:00:00.000Z"

    def utc_iso(self, delimiter="T", places=3):
        return self._iso


class FakeTimescale:
    def __init__(self):
        self.calls = []

    def utc(self, *args):
        self.calls.append(("utc", args))
        return ("utc", args)

    def tt_jd(self, value):
        self.calls.append(("tt_jd", value))
        return FakeTime(float(value))

    def from_datetime(self, value):
        self.calls.append(("from_datetime", value))
        return ("datetime", value)


def test_julian_day_validates_invalid_month_and_time_fields():
    with pytest.raises(ValueError, match="month"):
        julian_day_from_calendar(2026, 13, 1)
    with pytest.raises(ValueError, match="time of day"):
        julian_day_from_calendar(2026, 1, 1, 24, 0, 0)
    with pytest.raises(ValueError, match="time of day"):
        julian_day_from_calendar(2026, 1, 1, 0, 60, 0)
    with pytest.raises(ValueError, match="time of day"):
        julian_day_from_calendar(2026, 1, 1, 0, 0, 61)


@pytest.mark.parametrize("year, month", [(-1000, 6), (0, 6), (1000, 6), (1650, 6),
                                             (1750, 6), (1830, 6), (1880, 6), (1910, 6),
                                             (1930, 6), (1955, 6), (1970, 6), (1995, 6),
                                             (2026, 6), (2075, 6), (2200, 6)])
def test_delta_t_piecewise_regions_are_finite(year, month):
    value = delta_t_seconds(year, month)
    assert isinstance(value, float)
    assert math.isfinite(value)  # all polynomial branches must remain finite


def test_calendar_round_trip_before_and_after_gregorian_reform():
    for fields in ((1500, 3, 1, 12, 30, 0.0), (1582, 10, 4, 23, 59, 59.0),
                   (1582, 10, 15, 0, 0, 0.0), (2000, 2, 29, 6, 7, 8.5)):
        jd = julian_day_from_calendar(*fields)
        actual = calendar_from_julian_day(jd)
        assert actual[:5] == fields[:5]
        assert actual[5] == pytest.approx(fields[5], abs=2e-3)


def test_time_from_calendar_uses_skyfield_for_modern_years():
    ts = FakeTimescale()
    result = time_from_calendar(ts, 2026, 8, 12, 17, 30, 0.25)
    assert result[0] == "utc"
    assert ts.calls == [("utc", (2026, 8, 12, 17, 30, 0.25))]


def test_time_from_calendar_uses_delta_t_outside_skyfield_range():
    ts = FakeTimescale()
    result = time_from_calendar(ts, 1800, 1, 1, 0, 0, 0)
    assert isinstance(result, FakeTime)
    assert ts.calls[0][0] == "tt_jd"


def test_coerce_time_passes_through_skyfield_like_time():
    ts = FakeTimescale()
    value = FakeTime()
    assert coerce_time(ts, value) is value
    assert ts.calls == []


def test_coerce_time_accepts_julian_date():
    ts = FakeTimescale()
    result = coerce_time(ts, 2460000.5)
    assert isinstance(result, FakeTime)
    assert ts.calls == [("tt_jd", 2460000.5)]


def test_coerce_time_normalizes_naive_and_aware_datetimes_to_utc():
    ts = FakeTimescale()
    naive = datetime(2026, 8, 12, 17, 0, 0)
    aware = datetime(2026, 8, 12, 20, 0, 0, tzinfo=timezone(timedelta(hours=3)))
    naive_result = coerce_time(ts, naive)
    aware_result = coerce_time(ts, aware)
    assert naive_result[1] == aware_result[1]
    assert naive_result[1].utcoffset() == timedelta(0)


def test_coerce_time_date_uses_noon_utc_for_local_searches():
    ts = FakeTimescale()
    coerce_time(ts, date(2026, 8, 12))
    assert ts.calls[0][0] == "utc"
    assert ts.calls[0][1][:4] == (2026, 8, 12, 12)


def test_coerce_time_accepts_iso_date_and_timezone_offset():
    ts = FakeTimescale()
    coerce_time(ts, "2026-08-12")
    coerce_time(ts, "2026-08-12T20:00:00+03:00")
    assert ts.calls[0][1][:4] == (2026, 8, 12, 12)
    assert ts.calls[1][1].hour == 17
    assert ts.calls[1][1].tzinfo == timezone.utc


def test_coerce_time_rejects_malformed_strings_and_unsupported_types():
    ts = FakeTimescale()
    with pytest.raises(ValueError, match="Unsupported date/time"):
        coerce_time(ts, "not-a-date")
    with pytest.raises(TypeError, match="time must be"):
        coerce_time(ts, object())


def test_time_to_utc_iso_uses_skyfield_utc_iso_for_modern_epochs():
    assert time_to_utc_iso(FakeTime()) == "2026-01-01T00:00:00.000Z"


def test_time_to_utc_iso_appends_z_when_skyfield_omits_it():
    value = FakeTime(iso="2026-01-01T00:00:00.000")
    assert time_to_utc_iso(value).endswith("Z")


def test_time_to_utc_iso_falls_back_for_ancient_epochs():
    value = FakeTime(
        tt=1000000.0,
        utc_tuple=(-1000, 1, 1, 0, 0, 0.0),
        iso="should-not-be-used",
    )
    formatted = time_to_utc_iso(value)
    assert formatted.startswith("-")
    assert len(formatted.split("T", 1)[0]) == 11
    assert formatted.endswith("Z")


def test_time_to_utc_iso_handles_utc_property_failure_and_tt_fallback():
    value = SimpleNamespace(tt=2451545.0)
    formatted = time_to_utc_iso(value)
    assert formatted.endswith("Z")
