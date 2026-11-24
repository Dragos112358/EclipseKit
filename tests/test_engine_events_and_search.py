from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from eclipsekit import EclipseEngine, Observer
from eclipsekit.cities import CityCatalog
from eclipsekit.models import City

from test_engine_helpers import FakeObserved, FakeObserver, FakeTime, bare_engine


def install_fake_almanac(monkeypatch, *, phases, values):
    skyfield = ModuleType("skyfield")
    almanac = ModuleType("skyfield.almanac")
    almanac.moon_phases = lambda eph: "moon-phase-function"
    almanac.find_discrete = lambda start, end, function: (phases, values)
    skyfield.almanac = almanac
    monkeypatch.setitem(sys.modules, "skyfield", skyfield)
    monkeypatch.setitem(sys.modules, "skyfield.almanac", almanac)


@pytest.mark.parametrize("altitude, expected", [(10.0, "above_horizon"), (0.0, "at_horizon"), (-1.0, "below_horizon")])
def test_build_contact_event_assigns_visibility_and_contact_radius(monkeypatch, altitude, expected):
    from eclipsekit.models import ContactEvent
    import eclipsekit.geometry as geometry

    engine = bare_engine()
    engine._angular_radii_deg = lambda observer, jd, radius=None: (0.25, 0.3 if radius == engine.moon_radius_valleys_km else 0.31)
    app = SimpleNamespace(
        apparent=lambda: app,
        separation_from=lambda other: SimpleNamespace(degrees=0.15),
        radec=lambda: (SimpleNamespace(degrees=0.0), SimpleNamespace(radians=0.0), None),
        altaz=lambda **kwargs: (
            SimpleNamespace(degrees=altitude), SimpleNamespace(degrees=180.0), None,
        ),
    )
    at = SimpleNamespace(observe=lambda body: app)
    observer_sf = SimpleNamespace(at=lambda when: at)
    monkeypatch.setattr(geometry, "position_angle", lambda *args: 120.0)

    event = engine._build_contact_event(
        Observer(10.0, 20.0), observer_sf, "C2", "internal", FakeTime(2.0)
    )
    assert isinstance(event, ContactEvent)
    assert event.visibility_status == expected
    assert event.moon_angular_radius_deg == 0.3
    assert event.position_angle_deg == 120.0


def test_build_contact_event_uses_visual_radius_for_maximum_and_survives_position_angle_error(monkeypatch):
    import eclipsekit.geometry as geometry

    engine = bare_engine()
    radii = []
    engine._angular_radii_deg = lambda observer, jd, radius=None: radii.append(radius) or (0.25, 0.29)
    app = SimpleNamespace(
        apparent=lambda: app,
        separation_from=lambda other: SimpleNamespace(degrees=0.1),
        radec=lambda: (SimpleNamespace(degrees=0), SimpleNamespace(radians=0), None),
        altaz=lambda **kwargs: (SimpleNamespace(degrees=5), SimpleNamespace(degrees=90), None),
    )
    observer_sf = SimpleNamespace(at=lambda when: SimpleNamespace(observe=lambda body: app))
    monkeypatch.setattr(geometry, "position_angle", lambda *args: (_ for _ in ()).throw(RuntimeError("PA unavailable")))

    event = engine._build_contact_event(
        Observer(10, 20), observer_sf, "MAXIMUM", "maximum", FakeTime(2.0)
    )
    assert radii == [engine.moon_radius_visual_km]
    assert event.position_angle_deg is None
    assert event.vertex_angle_deg is None
    assert event.visibility_status == "above_horizon"


def test_parallactic_angle_returns_none_when_apparent_coordinates_fail():
    assert EclipseEngine._parallactic_angle_deg(
        Observer(0, 0), FakeTime(1), object()
    ) is None


def test_find_next_local_eclipse_skips_non_new_moon_phases_and_finds_overlap(monkeypatch):
    first, second = FakeTime(5.0), FakeTime(10.0)
    install_fake_almanac(monkeypatch, phases=[first, second], values=[1, 0])
    engine = bare_engine()
    engine.eph = object()
    engine.time = lambda value: FakeTime(1.0)
    engine._observer = lambda observer: FakeObserver()
    engine._find_minimum_separation = lambda *args, **kwargs: (args[1], 0.05)
    engine._angular_radii_deg = lambda *args, **kwargs: (0.2, 0.3)

    result = engine.find_next_local_eclipse(Observer(0, 0), "start", search_days=30)
    assert result.tt == 10.0


def test_find_next_local_eclipse_returns_none_when_no_candidate_overlaps(monkeypatch):
    phase = FakeTime(5.0)
    install_fake_almanac(monkeypatch, phases=[phase], values=[0])
    engine = bare_engine()
    engine.eph = object()
    engine.time = lambda value: FakeTime(1.0)
    engine._observer = lambda observer: FakeObserver()
    engine._find_minimum_separation = lambda *args, **kwargs: (args[1], 1.0)
    engine._angular_radii_deg = lambda *args, **kwargs: (0.2, 0.3)

    assert engine.find_next_local_eclipse(Observer(0, 0), "start") is None


def test_shadow_metrics_calculates_depth_from_kinematics(monkeypatch):
    engine = bare_engine()
    state = {"cone_radius_km": 100.0}
    monkeypatch.setattr(engine, "_shadow_state", lambda t: state)
    monkeypatch.setattr(engine, "_shadow_kinematics", lambda *args: {"velocity_km_s": 2.5, "width_km": 200.0})

    result = engine._shadow_metrics(FakeTime(2.0), FakeObserver())
    assert result["velocity_km_s"] == 2.5
    assert result["width_km"] == 200.0
    assert result["depth_fraction"] == pytest.approx(1.0)
    assert result["depth_km"] == pytest.approx(100.0)


def test_find_solar_eclipses_by_country_rejects_ambiguous_limb_arguments():
    engine = bare_engine()
    with pytest.raises(ValueError, match="either limb_model"):
        engine.find_solar_eclipses_by_country(
            1, 2, None, "Romania", limb_model=object(), limb_corrector=object(),
        )


def test_find_solar_eclipses_by_country_rejects_reversed_interval(monkeypatch):
    install_fake_almanac(monkeypatch, phases=[], values=[])
    engine = bare_engine()
    engine.eph = object()
    engine.time = lambda value: FakeTime(float(value))
    with pytest.raises(ValueError, match="end must be later"):
        engine.find_solar_eclipses_by_country(2.0, 1.0, None, "Romania")


def test_find_solar_eclipses_by_country_returns_empty_when_no_new_moon(monkeypatch):
    install_fake_almanac(monkeypatch, phases=[FakeTime(1.5)], values=[1])
    engine = bare_engine()
    engine.eph = object()
    engine.time = lambda value: FakeTime(float(value))
    assert engine.find_solar_eclipses_by_country(1.0, 2.0, None, "Romania") == []


def test_find_solar_eclipses_by_country_returns_country_event_for_city_hits(monkeypatch):
    phase = FakeTime(1.5)
    install_fake_almanac(monkeypatch, phases=[phase], values=[0])
    engine = bare_engine()
    engine.eph = object()
    engine.time = lambda value: FakeTime(float(value))
    engine.find_global_maximum = lambda value, **kwargs: FakeTime(1.6)
    sentinel_hit = object()
    captured = {}
    def search_cities(when, catalog, **kwargs):
        captured.update(when=when.tt, kwargs=kwargs)
        return [sentinel_hit]
    engine.search_cities = search_cities

    results = engine.find_solar_eclipses_by_country(
        1.0, 2.0, object(), "Romania", min_magnitude=0.02,
        include_contacts=True, search_radius_hours=3.0, limb_model="provider",
    )
    assert len(results) == 1
    assert results[0].country == "Romania"
    assert results[0].city_hits == [sentinel_hit]
    assert captured["kwargs"]["limb_corrector"] == "provider"


def test_lunar_eclipse_city_visibility_filters_below_horizon_locations(monkeypatch):
    skyfield = ModuleType("skyfield")
    framelib = ModuleType("skyfield.framelib")
    framelib.itrs = object()
    skyfield.framelib = framelib
    monkeypatch.setitem(sys.modules, "skyfield", skyfield)
    monkeypatch.setitem(sys.modules, "skyfield.framelib", framelib)
    monkeypatch.setattr(
        FakeObserved, "separation_from",
        lambda self, other: SimpleNamespace(degrees=180.0),
    )

    engine = bare_engine()
    engine.earth = FakeObserver()
    engine.time = lambda when: FakeTime(2.0)
    engine.sun_radius_km = 695700.0
    # Earth-fixed positions from the geocenter: Sun and Moon are opposite.
    vectors = {engine.sun: np.array([150_000_000.0, 0.0, 0.0]),
               engine.moon: np.array([-384_000.0, 0.0, 0.0])}
    class EarthAt:
        def observe(self, body):
            return FakeObserved(vectors[body])
    engine.earth = SimpleNamespace(at=lambda t: EarthAt())
    catalog = CityCatalog([
        City("Night side", "Test", 0.0, 0.0),
        City("Moon visible", "Test", 0.0, 180.0),
    ])

    results = engine.lunar_eclipse_city_visibility("date", catalog)
    assert len(results) == 1
    assert results[0]["city"].name == "Moon visible"
    assert results[0]["moon_altitude_deg"] > 89.0
    assert results[0]["eclipse_type"] == "total"
