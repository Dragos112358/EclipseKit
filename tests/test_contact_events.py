from __future__ import annotations

import json

import pytest

from eclipsekit import ContactEvent, ContactTimes, LocalEclipseResult, Observer
from eclipsekit.contacts import RootResult


class FakeTime:
    def __init__(self, tt: float = 2461265.25, ut1: float = 2461265.249999):
        self.tt = tt
        self.ut1 = ut1
        self.utc = (2026, 8, 12, 17, 0, 0.0)

    def utc_iso(self, delimiter="T", places=3):
        return "2026-08-12T17:00:00.000Z"


def _event(**overrides):
    values = {
        "name": "C1",
        "event_type": "external",
        "time": FakeTime(),
        "separation_deg": 0.52,
        "sun_angular_radius_deg": 0.266,
        "moon_angular_radius_deg": 0.272,
        "position_angle_deg": 125.0,
        "vertex_angle_deg": -35.0,
        "sun_altitude_deg": 14.2,
        "sun_azimuth_deg": 248.1,
        "visibility_status": "above_horizon",
        "solver_result": RootResult(
            root=2461265.25,
            converged=True,
            status="converged",
            method="brent",
            iterations=7,
            function_calls=9,
            bracket_start=2461265.249,
            bracket_end=2461265.251,
            residual=2.0e-10,
        ),
    }
    values.update(overrides)
    return ContactEvent(**values)


def test_contact_event_serializes_distinct_time_scales_and_solver_diagnostics():
    event = _event()
    payload = event.to_dict()

    assert payload["name"] == "C1"
    assert payload["event_type"] == "external"
    assert payload["time_utc"] == "2026-08-12T17:00:00.000Z"
    assert payload["time_tt_jd"] == pytest.approx(2461265.25)
    assert payload["time_ut1_jd"] == pytest.approx(2461265.249999)
    assert payload["geometry"]["position_angle_deg"] == pytest.approx(125.0)
    assert payload["geometry"]["vertex_angle_deg"] == pytest.approx(-35.0)
    assert payload["solver"]["method"] == "brent"
    assert payload["solver"]["iterations"] == 7
    assert payload["uncertainty_seconds"] is None
    json.dumps(payload)


def test_contact_event_validates_contact_name_and_type_pairing():
    with pytest.raises(ValueError, match="C1 and C4"):
        _event(event_type="internal")
    with pytest.raises(ValueError, match="name must be"):
        _event(name="C5")
    with pytest.raises(ValueError, match="uncertainty_seconds"):
        _event(uncertainty_seconds=-0.1)


def test_maximum_event_has_no_root_solver_diagnostic_by_default():
    event = _event(
        name="MAXIMUM",
        event_type="maximum",
        solver_result=None,
    )
    assert event.to_dict()["solver"] is None


def test_local_result_exposes_explicit_missing_central_duration_without_breaking_legacy_value():
    event = _event()
    result = LocalEclipseResult(
        observer=Observer(0.0, 0.0),
        eclipse_type="partial",
        maximum=FakeTime(),
        contacts=ContactTimes(),
        magnitude=0.2,
        obscuration_percent=10.0,
        moon_sun_radius_ratio=1.02,
        separation_deg=0.7,
        sun_altitude_deg=14.2,
        sun_azimuth_deg=248.1,
        duration_seconds=0.0,
        partial_phase_duration_seconds=1200.0,
        contact_events={"C1": event, "MAXIMUM": _event(name="MAXIMUM", event_type="maximum")},
        central_phase_duration_seconds=None,
    )

    payload = result.to_dict()
    assert payload["duration_seconds"] == 0.0
    assert payload["central_phase_duration_seconds"] is None
    assert list(payload["contact_events"]) == ["C1", "MAXIMUM"]
    json.dumps(payload)


def test_parallactic_angle_is_zero_when_sun_is_on_local_meridian():
    from types import SimpleNamespace
    from eclipsekit.engine import EclipseEngine

    apparent = SimpleNamespace(
        radec=lambda: (
            SimpleNamespace(degrees=180.0),
            SimpleNamespace(radians=0.2),
            None,
        )
    )
    skyfield_time = SimpleNamespace(gast=12.0)
    angle = EclipseEngine._parallactic_angle_deg(
        Observer(40.0, 0.0), skyfield_time, apparent
    )
    assert angle == pytest.approx(0.0)


def test_engine_builds_contact_geometry_and_visibility_metadata(monkeypatch):
    from types import SimpleNamespace
    from eclipsekit.engine import EclipseEngine

    class FakeApparent:
        def apparent(self):
            return self

        def separation_from(self, other):
            return SimpleNamespace(degrees=0.51)

        def radec(self):
            return (
                SimpleNamespace(degrees=180.0),
                SimpleNamespace(radians=0.2),
                None,
            )

        def altaz(self, *, pressure_mbar, temperature_C):
            assert pressure_mbar == 0.0
            assert temperature_C == 12.0
            return SimpleNamespace(degrees=15.0), SimpleNamespace(degrees=245.0), None

    class FakeObserverPosition:
        def at(self, time):
            return SimpleNamespace(observe=lambda body: FakeApparent())

    monkeypatch.setattr("eclipsekit.geometry.position_angle", lambda *args: 125.0)
    engine = object.__new__(EclipseEngine)
    engine.sun = object()
    engine.moon = object()
    engine.pressure_mbar = 0.0
    engine.temperature_c = 12.0
    engine.moon_radius_peaks_km = 1738.0
    engine.moon_radius_valleys_km = 1736.0
    engine.moon_radius_visual_km = 1737.4
    engine._angular_radii_deg = lambda *args: (0.266, 0.272)

    event = engine._build_contact_event(
        Observer(40.0, 0.0),
        FakeObserverPosition(),
        "C1",
        "external",
        SimpleNamespace(tt=2461265.25, ut1=2461265.249999, gast=12.0),
    )

    assert event.position_angle_deg == pytest.approx(125.0)
    assert event.vertex_angle_deg == pytest.approx(125.0)
    assert event.sun_altitude_deg == pytest.approx(15.0)
    assert event.sun_azimuth_deg == pytest.approx(245.0)
    assert event.visibility_status == "above_horizon"
