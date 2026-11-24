from __future__ import annotations

import json
import sys
import types
from types import SimpleNamespace

import numpy as np
import pytest

from eclipsekit import (
    EclipseEngine,
    HorizonProfile,
    ObservationGeometry,
    Observer,
    ContactTimes,
    LocalEclipseResult,
    ShadowCorridorEdge,
    ShadowFootprint,
    shadow_footprint_to_geojson,
    write_shadow_footprint_geojson,
)
from eclipsekit.geometry import WGS84_A_KM


class FakeTime:
    tt = 2461265.25
    ut1 = 2461265.249999
    gast = 12.0

    def utc_iso(self, delimiter="T", places=3):
        return "2026-08-12T17:00:00.000Z"


class FakeAngle:
    def __init__(self, degrees):
        self.degrees = degrees
        self.radians = np.deg2rad(degrees)


class FakeApparent:
    def __init__(self, altitude, azimuth):
        self._altitude = altitude
        self._azimuth = azimuth

    def apparent(self):
        return self

    def separation_from(self, other):
        return SimpleNamespace(degrees=0.4)

    def radec(self):
        return FakeAngle(180.0), FakeAngle(10.0), None

    def altaz(self, *, pressure_mbar, temperature_C):
        assert pressure_mbar in (0.0, 1013.25)
        assert temperature_C == 12.0
        return FakeAngle(self._altitude), FakeAngle(self._azimuth), None


class FakeObserverPosition:
    def __init__(self, sun, moon):
        self.sun = sun
        self.moon = moon

    def at(self, _time):
        return SimpleNamespace(observe=lambda body: self.sun if body is SUN else self.moon)


SUN = object()
MOON = object()


def _observation_engine(monkeypatch, *, sun_altitude=12.0, sun_azimuth=90.0):
    engine = object.__new__(EclipseEngine)
    engine.sun = SUN
    engine.moon = MOON
    engine.pressure_mbar = 1013.25
    engine.temperature_c = 12.0
    engine.moon_radius_visual_km = 1737.93
    engine.moon_radius_peaks_km = 1738.75
    engine.moon_radius_valleys_km = 1736.05
    engine.time = lambda _when: FakeTime()
    observer_sf = FakeObserverPosition(
        FakeApparent(sun_altitude, sun_azimuth), FakeApparent(5.0, 120.0)
    )
    engine._observer = lambda _observer: observer_sf
    engine._angular_radii_deg = lambda *_args: (0.266, 0.272)
    monkeypatch.setattr("eclipsekit.geometry.position_angle", lambda *_args: 125.0)
    return engine, observer_sf


def test_horizon_profile_interpolates_and_wraps_zero_360():
    profile = HorizonProfile(((350.0, 10.0), (10.0, 30.0), (180.0, 0.0)))
    assert profile.altitude_at(0.0) == pytest.approx(20.0)
    assert profile.altitude_at(360.0) == pytest.approx(20.0)
    assert profile.altitude_at(5.0) == pytest.approx(25.0)
    assert profile.altitude_at(180.0) == pytest.approx(0.0)


def test_horizon_profile_rejects_duplicate_wrapped_azimuths_and_invalid_values():
    with pytest.raises(ValueError, match="unique"):
        HorizonProfile(((0.0, 1.0), (360.0, 2.0)))
    with pytest.raises(ValueError, match="at least two"):
        HorizonProfile(((0.0, 1.0),))
    with pytest.raises(ValueError, match="finite"):
        HorizonProfile(((0.0, float("nan")), (180.0, 0.0)))
    with pytest.raises(ValueError, match="within"):
        HorizonProfile(((0.0, 91.0), (180.0, 0.0)))
    with pytest.raises(ValueError, match="azimuth"):
        HorizonProfile.flat().altitude_at(float("inf"))


@pytest.mark.parametrize(
    "horizon_altitude, expected",
    [(10.0, "visible"), (12.1, "partially_obstructed"), (13.0, "obstructed")],
)
def test_calculate_observation_geometry_classifies_solar_disk_visibility(
    monkeypatch, horizon_altitude, expected
):
    engine, _ = _observation_engine(monkeypatch)
    profile = HorizonProfile.flat(horizon_altitude, name="surveyed-ridge")
    result = engine.calculate_observation_geometry(
        Observer(40.0, 0.0), "2026-08-12T17:00:00Z", horizon_profile=profile
    )
    assert isinstance(result, ObservationGeometry)
    assert result.visibility_status == expected
    assert result.horizon_profile_name == "surveyed-ridge"
    assert result.sun_azimuth_deg == pytest.approx(90.0)
    assert result.moon_altitude_deg == pytest.approx(5.0)
    assert result.position_angle_deg == pytest.approx(125.0)
    assert result.vertex_angle_deg is not None
    assert result.obscuration_percent > 0.0
    assert result.sun_upper_limb_clearance_deg == pytest.approx(
        12.0 - horizon_altitude + 0.266
    )
    json.dumps(result.to_dict(), allow_nan=False)


def test_local_result_serializes_attached_observation_geometry(monkeypatch):
    engine, _ = _observation_engine(monkeypatch)
    observer = Observer(40.0, 0.0)
    geometry = engine.calculate_observation_geometry(observer, "2026-08-12T17:00:00Z")
    result = LocalEclipseResult(
        observer=observer, eclipse_type="partial", maximum=FakeTime(),
        contacts=ContactTimes(), magnitude=0.2, obscuration_percent=10.0,
        moon_sun_radius_ratio=1.02, separation_deg=0.4, sun_altitude_deg=12.0,
        sun_azimuth_deg=90.0, duration_seconds=0.0,
        observation_geometry=geometry,
    )
    payload = result.to_dict()
    assert payload["observation_geometry"]["horizon"]["visibility_status"] == "visible"
    json.dumps(payload, allow_nan=False)


def test_calculate_observation_geometry_without_profile_uses_astronomical_horizon(monkeypatch):
    engine, _ = _observation_engine(monkeypatch, sun_altitude=-0.1)
    result = engine.calculate_observation_geometry(
        Observer(40.0, 0.0), "2026-08-12T17:00:00Z", apply_refraction=False
    )
    assert result.horizon_altitude_deg == 0.0
    assert result.visibility_status == "partially_obstructed"
    assert result.refraction_applied is False


def test_calculate_observation_geometry_validates_arguments(monkeypatch):
    engine, _ = _observation_engine(monkeypatch)
    with pytest.raises(TypeError, match="Observer"):
        engine.calculate_observation_geometry(object(), "2026-08-12")
    with pytest.raises(TypeError, match="HorizonProfile"):
        engine.calculate_observation_geometry(
            Observer(0.0, 0.0), "2026-08-12", horizon_profile=object()
        )
    with pytest.raises(TypeError, match="boolean"):
        engine.calculate_observation_geometry(
            Observer(0.0, 0.0), "2026-08-12", apply_refraction=1
        )


def test_contact_event_uses_horizon_profile_for_obstruction_metadata(monkeypatch):
    engine, observer_sf = _observation_engine(monkeypatch, sun_altitude=12.0)
    event = engine._build_contact_event(
        Observer(40.0, 0.0), observer_sf, "C1", "external", FakeTime(),
        horizon_profile=HorizonProfile.flat(12.1, name="ridge"),
    )
    assert event.visibility_status == "partially_obstructed"
    assert event.horizon_altitude_deg == pytest.approx(12.1)
    assert event.sun_upper_limb_clearance_deg == pytest.approx(0.166)
    assert "ridge" in event.visibility_note
    payload = event.to_dict()
    assert payload["horizon_altitude_deg"] == pytest.approx(12.1)


def test_shadow_footprint_builds_instantaneous_boundaries_and_geojson(monkeypatch, tmp_path):
    skyfield = types.ModuleType("skyfield")
    framelib = types.ModuleType("skyfield.framelib")
    framelib.itrs = object()
    skyfield.framelib = framelib
    monkeypatch.setitem(sys.modules, "skyfield", skyfield)
    monkeypatch.setitem(sys.modules, "skyfield.framelib", framelib)

    class FakePosition:
        def __init__(self, vector):
            self.vector = vector

        def apparent(self):
            return self

        def frame_xyz(self, _frame):
            return SimpleNamespace(km=self.vector)

    class FakeEarth:
        def at(self, _time):
            return SimpleNamespace(observe=lambda body: FakePosition(
                np.array([149_600_000.0, 0.0, 0.0]) if body is SUN
                else np.array([360_000.0, 0.0, 0.0])
            ))

    engine = object.__new__(EclipseEngine)
    engine.sun = SUN
    engine.moon = MOON
    engine.earth = FakeEarth()
    engine.sun_radius_km = 696_000.0
    engine.moon_radius_shadow_km = 1736.65
    engine.time = lambda _when: FakeTime()
    engine._shadow_state = lambda _time: {
        "latitude": 2.0, "longitude": 3.0, "cone_radius_km": 40.0,
        "shadow_kind": "umbral", "hit": np.array([WGS84_A_KM, 0.0, 0.0]),
    }
    engine._shadow_kinematics = lambda *_args: {"velocity_km_s": 0.8, "width_km": 90.0}
    engine._shadow_track_bearing = lambda *_args: 270.0

    complete = [np.array([WGS84_A_KM * np.cos(i), WGS84_A_KM * np.sin(i), 0.0])
                for i in np.linspace(0.0, 2.0 * np.pi, 16, endpoint=False)]
    partial = complete.copy()
    partial[4] = None
    partial[5] = None
    def fake_intersections(_sun, _moon, *, boundary, **_kwargs):
        return complete if boundary == "central" else partial
    monkeypatch.setattr("eclipsekit.engine.cone_ellipsoid_intersections", fake_intersections)

    footprint = engine.calculate_shadow_footprint("2026-08-12", boundary_samples=16)
    assert isinstance(footprint, ShadowFootprint)
    assert footprint.shadow_kind == "umbral"
    assert footprint.axis_latitude == pytest.approx(2.0)
    assert footprint.track_bearing_deg == pytest.approx(270.0)
    assert footprint.central_boundary_coverage == pytest.approx(1.0)
    assert footprint.penumbra_boundary_coverage == pytest.approx(14 / 16)
    assert footprint.penumbra_boundary[4] is None

    geojson = shadow_footprint_to_geojson(footprint)
    assert geojson["type"] == "FeatureCollection"
    assert any(feature["properties"]["feature"] == "shadow_axis" for feature in geojson["features"])
    assert any(feature["properties"]["feature"] == "central_shadow_boundary" for feature in geojson["features"])
    json.dumps(footprint.to_dict(), allow_nan=False)
    json.dumps(geojson, allow_nan=False)
    destination = write_shadow_footprint_geojson(footprint, tmp_path / "footprint.geojson")
    assert destination.exists()
    assert json.loads(destination.read_text(encoding="utf-8"))["type"] == "FeatureCollection"


def test_shadow_footprint_returns_none_when_penumbral_cone_misses_earth(monkeypatch):
    skyfield = types.ModuleType("skyfield")
    framelib = types.ModuleType("skyfield.framelib")
    framelib.itrs = object()
    skyfield.framelib = framelib
    monkeypatch.setitem(sys.modules, "skyfield", skyfield)
    monkeypatch.setitem(sys.modules, "skyfield.framelib", framelib)

    class FakePosition:
        def __init__(self, vector): self.vector = vector
        def apparent(self): return self
        def frame_xyz(self, _frame): return SimpleNamespace(km=self.vector)

    class FakeEarth:
        def at(self, _time):
            return SimpleNamespace(observe=lambda body: FakePosition(
                np.array([149_600_000.0, 0.0, 0.0]) if body is SUN
                else np.array([360_000.0, 0.0, 0.0])
            ))

    engine = object.__new__(EclipseEngine)
    engine.sun = SUN
    engine.moon = MOON
    engine.earth = FakeEarth()
    engine.sun_radius_km = 696_000.0
    engine.moon_radius_shadow_km = 1736.65
    engine.time = lambda _when: FakeTime()
    monkeypatch.setattr(
        "eclipsekit.engine.cone_ellipsoid_intersections", lambda *_args, **_kwargs: [None] * 8
    )
    assert engine.calculate_shadow_footprint("2026-08-12", boundary_samples=8) is None
    with pytest.raises(ValueError, match="boundary_samples"):
        engine.calculate_shadow_footprint("2026-08-12", boundary_samples=7)


def test_shadow_footprint_reports_penumbral_only_case_when_axis_misses(monkeypatch):
    skyfield = types.ModuleType("skyfield")
    framelib = types.ModuleType("skyfield.framelib")
    framelib.itrs = object()
    skyfield.framelib = framelib
    monkeypatch.setitem(sys.modules, "skyfield", skyfield)
    monkeypatch.setitem(sys.modules, "skyfield.framelib", framelib)

    class FakePosition:
        def __init__(self, vector): self.vector = vector
        def apparent(self): return self
        def frame_xyz(self, _frame): return SimpleNamespace(km=self.vector)

    class FakeEarth:
        def at(self, _time):
            return SimpleNamespace(observe=lambda body: FakePosition(
                np.array([149_600_000.0, 0.0, 0.0]) if body is SUN
                else np.array([360_000.0, 0.0, 0.0])
            ))

    engine = object.__new__(EclipseEngine)
    engine.sun, engine.moon, engine.earth = SUN, MOON, FakeEarth()
    engine.sun_radius_km, engine.moon_radius_shadow_km = 696_000.0, 1736.65
    engine.time = lambda _when: FakeTime()
    engine._shadow_state = lambda _time: None
    points = [np.array([WGS84_A_KM, 0.0, 0.0])] * 8
    monkeypatch.setattr(
        "eclipsekit.engine.cone_ellipsoid_intersections",
        lambda *_args, boundary, **_kwargs: [None] * 8 if boundary == "central" else points,
    )
    result = engine.calculate_shadow_footprint("2026-08-12", boundary_samples=8)
    assert result is not None
    assert result.shadow_kind == "axis_misses_earth"
    assert result.axis_latitude is None
    assert result.penumbra_boundary_coverage == pytest.approx(1.0)
    assert result.track_bearing_deg is None


def test_shadow_footprint_geojson_splits_at_antimeridian():
    footprint = ShadowFootprint(
        time=FakeTime(), axis_latitude=1.0, axis_longitude=179.0,
        shadow_kind="umbral", cone_radius_km=10.0,
        central_boundary=(
            ShadowCorridorEdge(0.0, 179.0), ShadowCorridorEdge(1.0, -179.0),
            ShadowCorridorEdge(2.0, -178.0), ShadowCorridorEdge(3.0, 178.0),
            ShadowCorridorEdge(4.0, 179.0), ShadowCorridorEdge(5.0, -179.0),
            ShadowCorridorEdge(6.0, -178.0), ShadowCorridorEdge(7.0, 178.0),
        ),
        penumbra_boundary=(None,) * 8, track_bearing_deg=90.0,
        shadow_velocity_km_s=1.0, cross_track_width_km=20.0,
        central_boundary_coverage=1.0, penumbra_boundary_coverage=0.0,
    )
    output = shadow_footprint_to_geojson(footprint)
    central = next(f for f in output["features"] if f["properties"]["feature"] == "central_shadow_boundary")
    assert central["geometry"]["type"] == "MultiLineString"
