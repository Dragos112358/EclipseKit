import pytest
from eclipsekit.timeutils import (
    calendar_from_julian_day,
    delta_t_seconds,
    julian_day_from_calendar,
)


def test_calendar_jd_round_trip_modern():
    jd = julian_day_from_calendar(2024, 4, 8, 18, 0, 0)
    y, m, d, hh, mm, ss = calendar_from_julian_day(jd)
    assert (y, m, d, hh, mm) == (2024, 4, 8, 18, 0)
    assert ss == pytest.approx(0.0, abs=1e-5)


def test_calendar_jd_round_trip_julian_epoch():
    jd = julian_day_from_calendar(1000, 1, 1, 0, 0, 0)
    y, m, d, hh, mm, ss = calendar_from_julian_day(jd)
    assert (y, m, d, hh, mm) == (1000, 1, 1, 0, 0)


def test_delta_t_is_finite():
    for year in (-10000, -500, 0, 1000, 1800, 2200):
        assert abs(delta_t_seconds(year)) < 10_000_000


def test_delta_t_modern_2026_uses_2005_2050_branch():
    # Espenak-Meeus 2005–2050 polynomial at the midpoint of August 2026.
    assert delta_t_seconds(2026, 8) == pytest.approx(75.4597659531, abs=1e-9)


def test_delta_t_piecewise_historical_and_future_branches_are_finite():
    for year in (1650, 1750, 1830, 1880, 1910, 1930, 1955, 1975, 1995, 2040, 2075, 2200):
        assert abs(delta_t_seconds(year, 6)) < 1_000_000
