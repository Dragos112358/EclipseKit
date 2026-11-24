from __future__ import annotations

from types import ModuleType, SimpleNamespace
import sys

import pytest

from eclipsekit import Observer
from eclipsekit import engine as engine_module
from eclipsekit.engine import EclipseEngine


class FakeTime:
    def __init__(self, tt: float):
        self.tt = float(tt)


class FakeLocalResult:
    def __init__(self, maximum: float, magnitude: float):
        self.maximum = FakeTime(maximum)
        self.magnitude = magnitude

    def to_dict(self):
        return {"maximum_tt": self.maximum.tt, "magnitude": self.magnitude}


def make_search_engine(monkeypatch, phase_times=(100.0,), phase_values=(0,)):
    engine = object.__new__(EclipseEngine)
    engine.eph = object()
    almanac = SimpleNamespace()
    skyfield_stub = ModuleType("skyfield")
    skyfield_stub.almanac = almanac
    monkeypatch.setitem(sys.modules, "skyfield", skyfield_stub)
    engine.ts = SimpleNamespace(tt_jd=lambda value: FakeTime(float(value)))
    engine.time = lambda value: value if isinstance(value, FakeTime) else FakeTime(float(value))
    engine.find_global_maximum = lambda phase_time, half_window_hours: FakeTime(phase_time.tt + 0.01)
    monkeypatch.setattr(almanac, "moon_phases", lambda eph: object(), raising=False)
    monkeypatch.setattr(
        almanac, "find_discrete",
        lambda start, end, fn: ([FakeTime(value) for value in phase_times], phase_values),
        raising=False,
    )
    monkeypatch.setattr(engine_module, "time_to_utc_iso", lambda value: f"TT:{value.tt:.3f}")
    return engine


def test_search_solar_eclipses_groups_local_hits_for_multiple_observers(monkeypatch):
    engine = make_search_engine(monkeypatch)
    observers = [Observer(10, 20, name="A"), Observer(30, 40, name="B"), Observer(-10, 5, name="C")]
    calls = []

    def calculate_local(observer, when, **kwargs):
        calls.append((observer.name, when.tt, kwargs))
        if observer.name == "A":
            return FakeLocalResult(100.2, 0.7)
        if observer.name == "B":
            return FakeLocalResult(100.4, 0.3)
        return None

    engine.calculate_local = calculate_local
    result = engine.search_solar_eclipses(99.0, 101.0, observers, min_magnitude=0.2)
    assert result.locations_requested == 3
    assert result.new_moons_examined == 1
    assert result.event_count == 1
    assert result.location_event_count == 2
    assert [hit.observer.name for hit in result.events[0].locations] == ["A", "B"]
    assert result.events[0].maximum_magnitude == pytest.approx(0.7)
    assert all(call[2]["find_next_if_none"] is False for call in calls)


def test_search_solar_eclipses_enforces_interval_and_minimum_magnitude(monkeypatch):
    engine = make_search_engine(monkeypatch)
    observers = [Observer(0, 0, name="outside"), Observer(1, 1, name="faint")]

    def calculate_local(observer, when, **kwargs):
        if observer.name == "outside":
            return FakeLocalResult(101.001, 0.9)
        return FakeLocalResult(100.5, 0.09)

    engine.calculate_local = calculate_local
    result = engine.search_solar_eclipses(99.0, 101.0, observers, min_magnitude=0.1)
    assert result.new_moons_examined == 1
    assert result.events == []


def test_search_solar_eclipses_ignores_non_new_moon_phase_values(monkeypatch):
    engine = make_search_engine(monkeypatch, phase_times=(100.0, 101.0), phase_values=(1, 2))
    calls = []
    engine.calculate_local = lambda *args, **kwargs: calls.append(args) or None
    result = engine.search_solar_eclipses(99.0, 102.0, [Observer(0, 0)])
    assert result.new_moons_examined == 0
    assert result.events == []
    assert calls == []


def test_search_solar_eclipses_passes_optional_detail_and_limb_settings(monkeypatch):
    engine = make_search_engine(monkeypatch)
    observer = Observer(0, 0)
    expected_model = object()
    received = {}

    def calculate_local(target, when, **kwargs):
        received.update(kwargs)
        return FakeLocalResult(100.0, 0.5)

    engine.calculate_local = calculate_local
    result = engine.search_solar_eclipses(
        99.0, 101.0, [observer], limb_model=expected_model,
        include_sunrise_sunset=True, include_shadow_metrics=True, include_planets=True,
    )
    assert result.event_count == 1
    assert received["limb_corrector"] is expected_model
    assert received["include_sunrise_sunset"] is True
    assert received["include_shadow_metrics"] is True
    assert received["include_planets"] is True


def test_search_solar_eclipses_serializes_summary_and_event(monkeypatch):
    engine = make_search_engine(monkeypatch)
    engine.calculate_local = lambda *args, **kwargs: FakeLocalResult(100.5, 0.42)
    result = engine.search_solar_eclipses(99.0, 101.0, [Observer(12, 13, name="Test")])
    payload = result.to_dict()
    assert payload["start_utc"] == "TT:99.000"
    assert payload["end_utc"] == "TT:101.000"
    assert payload["events_found"] == 1
    assert payload["location_events_found"] == 1
    assert payload["events"][0]["locations"][0]["local_circumstances"]["magnitude"] == 0.42


def test_search_solar_eclipses_validates_interval_observers_and_options(monkeypatch):
    engine = make_search_engine(monkeypatch)
    with pytest.raises(ValueError, match="at least one Observer"):
        engine.search_solar_eclipses(99.0, 101.0, [])
    with pytest.raises(TypeError, match="iterable of Observer"):
        engine.search_solar_eclipses(99.0, 101.0, None)
    with pytest.raises(TypeError, match="only Observer"):
        engine.search_solar_eclipses(99.0, 101.0, [object()])
    with pytest.raises(ValueError, match="later than start"):
        engine.search_solar_eclipses(101.0, 99.0, [Observer(0, 0)])
    with pytest.raises(ValueError, match="search_window_hours"):
        engine.search_solar_eclipses(99.0, 101.0, [Observer(0, 0)], search_window_hours=0)
    with pytest.raises(ValueError, match="min_magnitude"):
        engine.search_solar_eclipses(99.0, 101.0, [Observer(0, 0)], min_magnitude=-0.1)
    with pytest.raises(ValueError, match="include_planets"):
        engine.search_solar_eclipses(99.0, 101.0, [Observer(0, 0)], include_planets=1)
