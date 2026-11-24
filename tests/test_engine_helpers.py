"""Focused unit tests for engine branches using deterministic astronomy fakes.

These tests deliberately avoid downloading kernels: numerical primitives are tested
with controlled vectors and the published-kernel integration remains in Phase 6.
"""

from __future__ import annotations

import math
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from eclipsekit import EclipseConfig, EclipseEngine, Observer, SolverConfig
from eclipsekit import engine as engine_module
from eclipsekit.contacts import RootResult
from eclipsekit.geometry import WGS84_A_KM


class FakeTime:
    def __init__(self, tt):
        self.tt = np.asarray(tt, dtype=float) if isinstance(tt, (list, tuple, np.ndarray)) else float(tt)
        self.ut1 = self.tt - 70.0 / 86400.0
        self.gast = 0.0


class FakeTimescale:
    def tt_jd(self, value):
        return FakeTime(value)

    def ut1(self, *args):
        return ("ut1", args)


class FakeObserved:
    def __init__(self, body, degrees=0.0, distance_km=150_000_000.0, times=None):
        self.body = body
        self._degrees = degrees
        self._distance = distance_km
        self.times = times

    def apparent(self):
        return self

    def separation_from(self, other):
        if self.times is not None:
            return SimpleNamespace(degrees=np.abs(np.asarray(self.times) - 2.0))
        return SimpleNamespace(degrees=self._degrees, radians=math.radians(self._degrees))

    def distance(self):
        return SimpleNamespace(km=self._distance)

    def altaz(self, **kwargs):
        return (SimpleNamespace(degrees=10.0), SimpleNamespace(degrees=180.0), None)

    def ecliptic_latlon(self):
        return (None, SimpleNamespace(degrees=self._degrees), None)

    def frame_xyz(self, frame):
        return SimpleNamespace(km=np.asarray(self.body, dtype=float))

    def radec(self):
        return (SimpleNamespace(degrees=0.0), SimpleNamespace(radians=0.0), None)


class FakeAt:
    def __init__(self, times=None):
        self.times = None
        if times is not None:
            values = np.asarray(getattr(times, "tt", times), dtype=float)
            self.times = values if values.ndim > 0 else None

    def observe(self, body):
        if self.times is not None:
            return FakeObserved(body, times=self.times)
        if isinstance(body, np.ndarray) or isinstance(body, list):
            return FakeObserved(body)
        return FakeObserved(body)


class FakeObserver:
    def at(self, times):
        return FakeAt(times)


def bare_engine():
    engine = object.__new__(EclipseEngine)
    engine.ts = FakeTimescale()
    engine.solver_config = SolverConfig()
    engine.sun = object()
    engine.moon = object()
    engine.earth = FakeObserver()
    engine.sun_radius_km = 695700.0
    engine.moon_radius_peaks_km = 1738.0
    engine.moon_radius_valleys_km = 1736.0
    engine.moon_radius_visual_km = 1737.4
    engine.moon_radius_shadow_km = 1736.0
    engine.pressure_mbar = 1013.25
    engine.temperature_c = 15.0
    engine._planet_names = {"venus barycenter": "Venus", "mars barycenter": "Mars"}
    engine.context = SimpleNamespace(optional_body=lambda key: object() if key.startswith("venus") else None)
    engine.time_scale_mode = "builtin"
    engine.config = EclipseConfig()
    return engine


def test_engine_time_helpers_forward_to_timescale_and_diagnostics(monkeypatch):
    engine = bare_engine()
    monkeypatch.setattr(engine, "time", lambda value: FakeTime(2460000.0))
    monkeypatch.setattr(engine_module, "describe_time_scale", lambda t, mode: {"mode": mode, "tt": t.tt})
    assert engine.time_from_ut1(2026, 8, 12, 17) == ("ut1", (2026, 8, 12, 17, 0, 0.0))
    assert engine.time_scale_diagnostics("now") == {"mode": "builtin", "tt": 2460000.0}


def test_engine_time_from_calendar_delegates_to_timeutils(monkeypatch):
    engine = bare_engine()
    expected = object()
    monkeypatch.setattr("eclipsekit.timeutils.time_from_calendar", lambda *args: expected)
    assert engine.time_from_calendar(2026, 8, 12, 17) is expected


def test_engine_observer_conversion_and_separation_helpers():
    engine = bare_engine()
    observer = Observer(10, 20)
    sentinel = object()
    original = Observer.to_skyfield
    try:
        Observer.to_skyfield = lambda self, earth: sentinel
        assert engine._observer(observer) is sentinel
    finally:
        Observer.to_skyfield = original
    assert engine._separation_deg(FakeObserver(), 2.0) == pytest.approx(0.0)


def test_engine_angular_radii_and_contact_residual_modes(monkeypatch):
    engine = bare_engine()
    # Distances are deterministic and both angular radii must be positive.
    sun_radius, moon_radius = engine._angular_radii_deg(FakeObserver(), 2460000.0)
    assert sun_radius > 0
    assert moon_radius > 0

    monkeypatch.setattr(engine, "_separation_deg", lambda observer, jd: 0.5)
    monkeypatch.setattr(engine, "_angular_radii_deg", lambda observer, jd, radius=None: (0.2, 0.1))
    assert engine._contact_residual("observer", 1.0, "external") == pytest.approx(0.2)
    assert engine._contact_residual("observer", 1.0, "internal") == pytest.approx(0.4)
    with pytest.raises(ValueError, match="mode must"):
        engine._contact_residual("observer", 1.0, "invalid")


def test_find_minimum_separation_returns_edge_sample_without_refinement():
    engine = bare_engine()
    result = engine._find_minimum_separation(FakeObserver(), 2.0, half_window_hours=0.001, coarse_step_minutes=1)
    assert result[0] == pytest.approx(2.0 - 0.001 / 24)
    assert result[1] >= 0


def test_find_minimum_separation_refines_bracket(monkeypatch):
    engine = bare_engine()
    calls = {}

    def fake_minimize(function, lo, hi, **kwargs):
        calls.update(lo=lo, hi=hi, kwargs=kwargs)
        return 2.0, 0.0

    monkeypatch.setattr(engine_module, "golden_section_minimize", fake_minimize)
    result = engine._find_minimum_separation(FakeObserver(), 2.0, half_window_hours=2 / 60, coarse_step_minutes=1)
    assert result == (2.0, 0.0)
    assert calls["lo"] < 2.0 < calls["hi"]
    assert calls["kwargs"]["max_iterations"] == engine.solver_config.minimum_max_iterations


def test_compatibility_root_helper_returns_none_for_nonconvergence(monkeypatch):
    engine = bare_engine()
    failed = RootResult(
        root=None, converged=False, status="not_bracketed", method="brent", iterations=0,
        function_calls=2, bracket_start=1.0, bracket_end=2.0, residual=None,
    )
    monkeypatch.setattr(engine, "_solve_root_detailed", lambda *args, **kwargs: failed)
    assert engine._solve_root(lambda x: x, 1.0, 2.0) is None


def test_solve_contact_detailed_rejects_invalid_inputs():
    engine = bare_engine()
    engine._observer = lambda observer: "observer"
    with pytest.raises(ValueError, match="mode"):
        engine.solve_contact_detailed(Observer(0, 0), "bad", 1, 2)
    with pytest.raises(ValueError, match="non-zero duration"):
        engine.solve_contact_detailed(Observer(0, 0), "external", 1, 1)
    with pytest.raises(ValueError, match="finite and positive"):
        engine.solve_contact_detailed(Observer(0, 0), "external", 1, 2, moon_radius_km=float("nan"))
    with pytest.raises(ValueError, match="bool values"):
        engine.solve_contact_detailed(Observer(0, 0), "external", 1, 2, auto_expand=1)


def test_solve_contact_legacy_returns_none_when_detailed_solver_fails(monkeypatch):
    engine = bare_engine()
    failed = RootResult(
        root=None, converged=False, status="no_root", method="brent", iterations=2,
        function_calls=3, bracket_start=1.0, bracket_end=2.0, residual=1.0,
    )
    monkeypatch.setattr(engine, "solve_contact_detailed", lambda *args, **kwargs: failed)
    assert engine.solve_contact(Observer(0, 0), "external", 1, 2) is None


def test_global_maximum_and_global_separation_delegation(monkeypatch):
    engine = bare_engine()
    monkeypatch.setattr(engine, "time", lambda value: FakeTime(10.0))
    monkeypatch.setattr(engine, "_find_minimum_separation", lambda *args, **kwargs: (12.5, 0.2))
    result = engine.find_global_maximum("date", half_window_hours=5)
    assert result.tt == 12.5
    assert engine._global_separation_deg(2.0) == pytest.approx(0.0)


def test_global_eclipse_flag_uses_shadow_state_first(monkeypatch):
    engine = bare_engine()
    monkeypatch.setattr(engine, "_shadow_state", lambda t: {"hit": [1, 2, 3]})
    assert engine._is_global_solar_eclipse(FakeTime(2.0)) is True


def test_global_eclipse_flag_falls_back_to_geocentric_overlap(monkeypatch):
    engine = bare_engine()
    monkeypatch.setattr(engine, "_shadow_state", lambda t: None)
    engine.earth = FakeObserver()
    assert engine._is_global_solar_eclipse(FakeTime(2.0)) is True


def test_zodiac_sector_maps_longitude_and_returns_none_on_failure():
    engine = bare_engine()
    assert engine._approximate_zodiac_sector(FakeObserver(), FakeTime(1.0)) == "Aries"

    class BrokenObserver:
        def at(self, t):
            raise RuntimeError("bad ephemeris")

    assert engine._approximate_zodiac_sector(BrokenObserver(), FakeTime(1.0)) is None


def test_visible_planets_filters_missing_below_horizon_and_sorts(monkeypatch):
    engine = bare_engine()
    engine.context = SimpleNamespace(optional_body=lambda key: object() if key.startswith("venus") else None)
    engine._planet_names = {"venus barycenter": "Venus", "mars barycenter": "Mars"}
    # The fake visible Venus is above the horizon. Missing Mars is skipped.
    assert engine._visible_planets(FakeObserver(), FakeTime(2.0)) == [("Venus", 0.0)]


def test_shadow_state_returns_none_for_zero_axis_and_for_missed_earth(monkeypatch):
    skyfield = ModuleType("skyfield")
    framelib = ModuleType("skyfield.framelib")
    framelib.itrs = object()
    skyfield.framelib = framelib
    monkeypatch.setitem(sys.modules, "skyfield", skyfield)
    monkeypatch.setitem(sys.modules, "skyfield.framelib", framelib)

    engine = bare_engine()
    zero_at = SimpleNamespace(observe=lambda body: FakeObserved([1, 1, 1]))
    engine.earth = SimpleNamespace(at=lambda t: zero_at)
    assert engine._shadow_state(FakeTime(1)) is None

    sun_pos, moon_pos = np.array([1.0, 2.0, 3.0]), np.array([4.0, 5.0, 6.0])
    class At:
        def observe(self, body):
            return FakeObserved(sun_pos if body is engine.sun else moon_pos)
    engine.earth = SimpleNamespace(at=lambda t: At())
    monkeypatch.setattr(engine_module, "ray_ellipsoid_intersection", lambda moon, direction: None)
    assert engine._shadow_state(FakeTime(1)) is None


def test_shadow_state_builds_wgs84_intersection_metadata(monkeypatch):
    skyfield = ModuleType("skyfield")
    framelib = ModuleType("skyfield.framelib")
    framelib.itrs = object()
    skyfield.framelib = framelib
    monkeypatch.setitem(sys.modules, "skyfield", skyfield)
    monkeypatch.setitem(sys.modules, "skyfield.framelib", framelib)

    engine = bare_engine()
    sun_pos = np.array([-149_000_000.0, 0.0, 0.0])
    moon_pos = np.array([-384_000.0, 0.0, 0.0])
    class At:
        def observe(self, body):
            return FakeObserved(sun_pos if body is engine.sun else moon_pos)
    engine.earth = SimpleNamespace(at=lambda t: At())
    hit = np.array([WGS84_A_KM, 0.0, 0.0])
    monkeypatch.setattr(engine_module, "ray_ellipsoid_intersection", lambda moon, direction: hit)
    monkeypatch.setattr(engine_module, "ecef_to_geodetic", lambda *xyz: (0.0, 0.0, 0.0))

    state = engine._shadow_state(FakeTime(1))
    assert state is not None
    assert state["latitude"] == 0.0
    assert state["longitude"] == 0.0
    assert state["shadow_kind"] in {"umbral", "antumbral"}
    assert state["hit"] is hit


def test_shadow_kinematics_handles_missing_and_stationary_states(monkeypatch):
    engine = bare_engine()
    monkeypatch.setattr(engine, "_shadow_state", lambda t: None)
    assert engine._shadow_kinematics(FakeTime(1), None) == {"velocity_km_s": None, "width_km": None}

    state = {"hit": np.array([WGS84_A_KM, 0.0, 0.0]), "cone_radius_km": 40.0,
             "sun_position": np.array([100.0, 0.0, 100.0]), "moon_position": np.array([0.0, 0.0, 0.0])}
    monkeypatch.setattr(engine, "_shadow_state", lambda t: None)
    missing = engine._shadow_kinematics(FakeTime(1), state)
    assert missing["velocity_km_s"] is None
    assert missing["width_km"] == 80.0

    same_state = {**state, "hit": np.array([WGS84_A_KM, 0.0, 0.0])}
    monkeypatch.setattr(engine, "_shadow_state", lambda t: same_state)
    stationary = engine._shadow_kinematics(FakeTime(1), same_state)
    assert stationary["velocity_km_s"] == 0.0
    assert stationary["width_km"] is None


def test_shadow_kinematics_computes_velocity_and_width(monkeypatch):
    engine = bare_engine()
    state = {"hit": np.array([WGS84_A_KM, 0.0, 0.0]), "cone_radius_km": 50.0,
             "sun_position": np.array([8000.0, 0.0, 6000.0]),
             "moon_position": np.array([7000.0, 0.0, 6000.0])}
    def shadow_at(t):
        direction = -5.0 if t.tt < 1.0 else 5.0
        return {**state, "hit": np.array([WGS84_A_KM, direction, 0.0])}
    monkeypatch.setattr(engine, "_shadow_state", shadow_at)
    metrics = engine._shadow_kinematics(FakeTime(1), state)
    assert metrics["velocity_km_s"] == pytest.approx(10.0)
    assert metrics["width_km"] > 0


def test_shadow_metrics_handles_no_intersection(monkeypatch):
    engine = bare_engine()
    monkeypatch.setattr(engine, "_shadow_state", lambda t: None)
    assert engine._shadow_metrics(FakeTime(1), FakeObserver()) == {
        "velocity_km_s": None, "width_km": None, "depth_km": None, "depth_fraction": None,
    }


def test_global_shadow_path_validates_interval_and_returns_intersections(monkeypatch):
    engine = bare_engine()
    engine.time = lambda value: FakeTime(float(value))
    with pytest.raises(ValueError, match="at least 2"):
        engine.global_shadow_path(1.0, 2.0, samples=1)
    with pytest.raises(ValueError, match="later"):
        engine.global_shadow_path(2.0, 1.0, samples=2)

    def state(t):
        if abs(t.tt - 1.5) < 0.01:
            return None
        return {"latitude": 10.0, "longitude": 20.0, "cone_radius_km": 600.0,
                "shadow_kind": "umbral"}
    monkeypatch.setattr(engine, "_shadow_state", state)
    monkeypatch.setattr(engine, "_shadow_kinematics", lambda *args: {"width_km": None, "velocity_km_s": None})
    points = engine.global_shadow_path(1.0, 2.0, samples=3)
    assert len(points) == 2
    assert all(point.width_km == 900.0 for point in points)  # documented safety cap


def test_global_path_for_eclipse_centers_requested_search_window(monkeypatch):
    engine = bare_engine()
    engine.find_global_maximum = lambda when: FakeTime(100.0)
    captured = {}
    engine.global_shadow_path = lambda start, end, **kwargs: captured.update(
        start=start.tt, end=end.tt, samples=kwargs["samples"]
    ) or ["path"]
    assert engine.global_path_for_eclipse("when", search_radius_hours=2, samples=7) == ["path"]
    assert captured["start"] == pytest.approx(100.0 - 2 / 24)
    assert captured["end"] == pytest.approx(100.0 + 2 / 24)
    assert captured["samples"] == 7


def test_calculate_local_rejects_ambiguous_limb_arguments_and_can_return_none(monkeypatch):
    engine = bare_engine()
    with pytest.raises(ValueError, match="either limb_model"):
        engine.calculate_local(Observer(0, 0), "date", limb_model=object(), limb_corrector=object())

    engine.time = lambda value: FakeTime(100.0)
    engine._observer = lambda observer: "observer"
    engine._find_minimum_separation = lambda *args, **kwargs: (100.0, 2.0)
    engine._angular_radii_deg = lambda *args, **kwargs: (0.2, 0.1)
    assert engine.calculate_local(Observer(0, 0), "date", find_next_if_none=False) is None


def test_search_cities_argument_validation_happens_before_ephemeris_access():
    engine = bare_engine()
    with pytest.raises(ValueError, match="either limb_model"):
        engine.search_cities("date", None, limb_model=object(), limb_corrector=object())
    with pytest.raises(ValueError, match="coarse_steps"):
        engine.search_cities("date", None, coarse_steps=4)
    with pytest.raises(ValueError, match="coarse_steps"):
        engine.search_cities("date", None, batch_size=0)


def test_format_report_supports_romanian_and_english():
    engine = bare_engine()
    from eclipsekit.models import ContactTimes, LocalEclipseResult
    result = LocalEclipseResult(
        observer=Observer(42.6, -5.57), eclipse_type="partial", maximum=FakeTime(2460000),
        contacts=ContactTimes(), magnitude=0.5, obscuration_percent=30.0,
        moon_sun_radius_ratio=0.95, separation_deg=0.1, sun_altitude_deg=20.0,
        sun_azimuth_deg=180.0, duration_seconds=0.0,
        partial_phase_duration_seconds=120.0,
    )
    english = engine.format_report(result)
    romanian = engine.format_report(result, language="ro")
    assert "Type: partial" in english
    assert "Tip: partial" in romanian
    assert "Total event span C1-C4" in english
    assert "Durata totală C1-C4" in romanian
