from __future__ import annotations

import sys
from datetime import date
from types import ModuleType, SimpleNamespace

import numpy as np

from eclipsekit.engine import EclipseEngine


class FakeTime:
    def __init__(self, tt: float):
        self.tt = float(tt)
        self.utc = (2025, 3, 14, 7, 0, 0.0)

    def utc_iso(self, delimiter="T", places=3):
        return "2025-03-14T07:00:00.000Z"


class FakeTimescale:
    def tt_jd(self, value):
        return FakeTime(float(value))


class FakeObserved:
    def __init__(self, vector):
        self.km = np.asarray(vector, dtype=float)

    def apparent(self):
        return self

    def frame_xyz(self, frame):
        return SimpleNamespace(km=self.km)


class FakeAt:
    def __init__(self, jd, sun, moon):
        self.jd = jd
        self.vectors = {
            sun: (149_597_870.0, 0.0, 0.0),
            moon: (-384_400.0, 0.0, 0.5 * (jd - 2460748.79) * 86400.0),
        }

    def observe(self, body):
        return FakeObserved(self.vectors[body])


def bare_engine(monkeypatch):
    skyfield = ModuleType("skyfield")
    framelib = ModuleType("skyfield.framelib")
    framelib.itrs = object()
    skyfield.framelib = framelib
    monkeypatch.setitem(sys.modules, "skyfield", skyfield)
    monkeypatch.setitem(sys.modules, "skyfield.framelib", framelib)

    engine = object.__new__(EclipseEngine)
    engine.ts = FakeTimescale()
    engine.sun = object()
    engine.moon = object()
    engine.sun_radius_km = 695700.0
    engine.moon_radius_shadow_km = 1737.4
    engine.earth = SimpleNamespace(
        at=lambda t: FakeAt(t.tt, engine.sun, engine.moon)
    )
    engine.time = lambda value, calendar="historical": FakeTime(2460748.79)
    return engine


def test_engine_calculate_lunar_eclipse_uses_geocentric_skyfield_vectors(monkeypatch):
    engine = bare_engine(monkeypatch)
    result = engine.calculate_lunar_eclipse("2025-03-14")
    assert result is not None
    assert result.eclipse_type == "total"
    assert result.contacts.p1 is not None
    assert result.contacts.u1 is not None
    assert result.contacts.u2 is not None
    assert result.contacts.u3 is not None
    assert result.contacts.u4 is not None
    assert result.contacts.p4 is not None



def test_engine_uses_mean_lunar_radius_for_lunar_eclipse_not_solar_contact_radius(monkeypatch):
    engine = bare_engine(monkeypatch)
    engine.moon_radius_shadow_km = 1700.0
    result = engine.calculate_lunar_eclipse("2025-03-14")
    assert result is not None
    assert result.moon_radius_km == 1737.4


def test_engine_calendar_argument_is_forwarded_to_date_parser(monkeypatch):
    engine = bare_engine(monkeypatch)
    captured = {}

    def parse(value, *, calendar="historical"):
        captured["value"] = value
        captured["calendar"] = calendar
        return FakeTime(2460748.79)

    engine.time = parse
    result = engine.calculate_lunar_eclipse("1500-02-29", calendar="julian")
    assert result is not None
    assert captured == {"value": "1500-02-29", "calendar": "julian"}


def test_find_lunar_eclipses_uses_full_moon_phase_and_interval(monkeypatch):
    skyfield = ModuleType("skyfield")
    almanac = ModuleType("skyfield.almanac")
    skyfield.almanac = almanac
    monkeypatch.setitem(sys.modules, "skyfield", skyfield)
    monkeypatch.setitem(sys.modules, "skyfield.almanac", almanac)

    class SearchTime(FakeTime):
        pass

    full_inside = SearchTime(100.0)
    full_outside = SearchTime(101.0)
    almanac.moon_phases = lambda ephemeris: object()
    end_boundary_candidate = SearchTime(100.7)
    almanac.find_discrete = lambda start, end, phase_fn: (
        [full_inside, full_outside, SearchTime(100.5), end_boundary_candidate],
        [2, 0, 2, 2],
    )

    engine = object.__new__(EclipseEngine)
    engine.eph = object()
    engine.ts = FakeTimescale()
    engine.time = lambda value, calendar="historical": SearchTime(99.0)

    def calendar_boundary(
        year, month, day, hour=0, minute=0, second=0.0, *, calendar="historical"
    ):
        assert (year, month, hour, minute, second) == (2025, 3, 0, 0, 0.0)
        return SearchTime(99.0 if day == 14 else 100.4)

    engine.time_from_calendar = calendar_boundary

    def calculate(when, **kwargs):
        if when.tt == 100.0:
            return SimpleNamespace(maximum=SearchTime(100.2))
        if when.tt == 100.5:
            return SimpleNamespace(maximum=SearchTime(100.6))
        if when.tt == 100.7:
            # The end boundary is exclusive.
            return SimpleNamespace(maximum=SearchTime(100.4))
        return None

    engine.calculate_lunar_eclipse = calculate
    results = engine.find_lunar_eclipses("2025-03-14", "2025-03-15")
    assert len(results) == 1
    assert results[0].maximum.tt == 100.2


def test_lunar_interval_date_object_uses_civil_midnight():
    engine = object.__new__(EclipseEngine)
    captured = {}

    def from_calendar(year, month, day, hour=0, minute=0, second=0.0, *, calendar="historical"):
        captured.update(
            year=year, month=month, day=day, hour=hour,
            minute=minute, second=second, calendar=calendar,
        )
        return FakeTime(100.0)

    engine.time_from_calendar = from_calendar
    engine.time = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("date-only boundaries must not be parsed at noon")
    )

    result = engine._lunar_interval_boundary(date(2025, 3, 14), calendar="julian")
    assert result.tt == 100.0
    assert captured == {
        "year": 2025, "month": 3, "day": 14, "hour": 0,
        "minute": 0, "second": 0.0, "calendar": "julian",
    }


def test_find_next_lunar_eclipse_delegates_to_interval_search():
    engine = object.__new__(EclipseEngine)
    engine.ts = FakeTimescale()
    engine.time = lambda value, calendar="historical": FakeTime(100.0)
    engine.time_from_calendar = lambda *args, **kwargs: FakeTime(100.0)
    expected = object()
    captured = {}

    def search(start, end, **kwargs):
        captured.update(start=start.tt, end=end.tt, kwargs=kwargs)
        return [expected]

    engine.find_lunar_eclipses = search
    assert engine.find_next_lunar_eclipse("2025-03-14", search_days=400) is expected
    assert captured["start"] == 100.0
    assert captured["end"] == 500.0


def test_engine_time_from_calendar_forwards_nondefault_calendar(monkeypatch):
    engine = bare_engine(monkeypatch)
    captured = {}

    def parse(ts, year, month, day, hour=0, minute=0, second=0.0, *, calendar="historical"):
        captured.update(
            year=year, month=month, day=day, hour=hour, calendar=calendar
        )
        return FakeTime(2460000.0)

    monkeypatch.setattr("eclipsekit.timeutils.time_from_calendar", parse)
    result = engine.time_from_calendar(1500, 2, 29, 12, calendar="julian")
    assert isinstance(result, FakeTime)
    assert captured == {
        "year": 1500, "month": 2, "day": 29, "hour": 12, "calendar": "julian"
    }
