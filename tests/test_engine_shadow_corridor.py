import math

import numpy as np
import pytest

import eclipsekit.engine as engine_module
from eclipsekit.engine import EclipseEngine
from eclipsekit.geometry import wgs84_geodetic_to_ecef


class FakeTime:
    def __init__(self, tt):
        self.tt = float(tt)


class FakeTimescale:
    @staticmethod
    def tt_jd(value):
        return FakeTime(value)


def bare_engine(monkeypatch):
    engine = object.__new__(EclipseEngine)
    engine.ts = FakeTimescale()
    engine.sun_radius_km = 696000.0
    engine.moon_radius_shadow_km = 1736.65
    start_jd = 2457987.2083333335
    end_jd = start_jd + 40.0 / 1440.0
    engine.time = lambda value: FakeTime(start_jd if value == "start" else end_jd)

    def shadow_state(moment):
        fraction = (moment.tt - start_jd) / (end_jd - start_jd)
        longitude = float(fraction * 2.0)
        return {
            "sun_position": np.array([longitude, 0.0, 0.0]),
            "moon_position": np.array([360000.0, 0.0, 0.0]),
            "latitude": 0.0,
            "longitude": longitude,
            "shadow_kind": "umbral",
            "cone_radius_km": 50.0,
        }

    engine._shadow_state = shadow_state
    engine._shadow_kinematics = lambda moment, state=None: {
        "velocity_km_s": 2.0, "width_km": 100.0,
    }

    def fake_cone(sun, moon, *, boundary, azimuth_samples, **kwargs):
        center_lon = float(sun[0])
        cross_radius, along_radius = (0.1, 0.15) if boundary == "central" else (0.3, 0.5)
        return [
            wgs84_geodetic_to_ecef(
                cross_radius * math.sin(theta), center_lon + along_radius * math.cos(theta)
            )
            for theta in np.linspace(0.0, 2.0 * math.pi, azimuth_samples, endpoint=False)
        ]

    monkeypatch.setattr(engine_module, "cone_ellipsoid_intersections", fake_cone)
    return engine


def test_global_shadow_corridor_builds_core_and_penumbra_edges(monkeypatch):
    engine = bare_engine(monkeypatch)
    corridor = engine.global_shadow_corridor("start", "end", samples=3, boundary_samples=36)
    assert len(corridor.samples) == 3
    middle = corridor.samples[1]
    assert middle.central_left is not None and middle.central_right is not None
    assert middle.penumbra_left is not None and middle.penumbra_right is not None
    assert middle.central_width_km == pytest.approx(22.0, rel=0.02)
    assert middle.penumbral_width_km > middle.central_width_km
    assert middle.track_bearing_deg == pytest.approx(90.0, abs=0.1)
    assert middle.central_track_chord_km > middle.central_width_km * 1.4
    assert middle.central_phase_duration_estimate_seconds == pytest.approx(
        middle.central_track_chord_km / 2.0
    )
    assert "WGS84" in corridor.geometry_model



def test_corridor_local_track_bearing_uses_short_symmetric_difference(monkeypatch):
    engine = bare_engine(monkeypatch)
    start = engine.time("start")
    state = engine._shadow_state(start)
    bearing = engine._shadow_track_bearing(start, state, step_seconds=5.0)
    assert bearing == pytest.approx(90.0, abs=0.1)


def test_corridor_track_chord_is_centerline_intersection_not_projection():
    # Ellipse with 20 km / 10 km semi-axes rotated 45 degrees to the track.
    # Its bounding projection along-track is ~31.6 km, while the actual
    # centerline chord is ~25.3 km; duration needs the latter.
    points = []
    major, minor = 20.0, 10.0
    rotation = math.radians(45.0)
    km_per_degree = 111.195
    for theta in np.linspace(0.0, 2.0 * math.pi, 360, endpoint=False):
        x = major * math.cos(theta)
        y = minor * math.sin(theta)
        along = x * math.cos(rotation) - y * math.sin(rotation)
        cross = x * math.sin(rotation) + y * math.cos(rotation)
        points.append((cross / km_per_degree, along / km_per_degree))
    chord = EclipseEngine._corridor_track_chord(0.0, 0.0, points, 90.0)
    left, right, width = EclipseEngine._corridor_edge_pair(0.0, 0.0, points, 90.0)
    assert chord == pytest.approx(25.30, rel=0.01)
    assert width == pytest.approx(31.62, rel=0.01)
    assert chord < width
    assert left is not None and right is not None

def test_global_shadow_corridor_reports_no_axis_intersections(monkeypatch):
    engine = bare_engine(monkeypatch)
    engine._shadow_state = lambda moment: None
    corridor = engine.global_shadow_corridor("start", "end", samples=3)
    assert corridor.samples == ()
    assert any("No sampled" in note for note in corridor.notes)


def test_global_shadow_corridor_validates_sampling_parameters():
    engine = object.__new__(EclipseEngine)
    with pytest.raises(ValueError, match="samples"):
        engine.global_shadow_corridor("start", "end", samples=True)
    with pytest.raises(ValueError, match="boundary_samples"):
        engine.global_shadow_corridor("start", "end", boundary_samples=8)


def test_global_shadow_corridor_for_eclipse_rejects_invalid_search_radius():
    engine = object.__new__(EclipseEngine)
    with pytest.raises(ValueError, match="search_radius_hours"):
        engine.global_shadow_corridor_for_eclipse("x", search_radius_hours=0)


def test_global_shadow_corridor_omits_nonintersecting_times_and_reports_partial(monkeypatch):
    engine = bare_engine(monkeypatch)
    original_state = engine._shadow_state

    def state(moment):
        if moment.tt < 2457987.2083333335 + 0.001:
            return None
        return original_state(moment)

    engine._shadow_state = state

    def partial_cone(sun, moon, *, boundary, azimuth_samples, **kwargs):
        if boundary == "central":
            return [None] * azimuth_samples
        return [
            wgs84_geodetic_to_ecef(0.3 * math.sin(theta), float(sun[0]) + 0.3 * math.cos(theta))
            for theta in np.linspace(0.0, 2.0 * math.pi, azimuth_samples, endpoint=False)
        ]

    monkeypatch.setattr(engine_module, "cone_ellipsoid_intersections", partial_cone)
    corridor = engine.global_shadow_corridor("start", "end", samples=3, boundary_samples=36)
    assert 1 <= len(corridor.samples) < 3
    assert any("omitted" in note for note in corridor.notes)
    assert all(sample.central_width_km is None for sample in corridor.samples)
    assert all(sample.central_boundary_coverage == 0.0 for sample in corridor.samples)
    assert all(sample.penumbra_boundary_coverage == 1.0 for sample in corridor.samples)


def test_global_shadow_corridor_rejects_non_increasing_time_range(monkeypatch):
    engine = bare_engine(monkeypatch)
    with pytest.raises(ValueError, match="later"):
        engine.global_shadow_corridor("end", "start", samples=3)


def test_global_shadow_corridor_for_eclipse_validates_boolean_radius_and_delegates(monkeypatch):
    engine = bare_engine(monkeypatch)
    with pytest.raises(ValueError, match="search_radius_hours"):
        engine.global_shadow_corridor_for_eclipse("x", search_radius_hours=True)

    maximum = FakeTime(2457987.5)
    engine.find_global_maximum = lambda when: maximum
    captured = {}

    def corridor(start, end, *, samples, boundary_samples):
        captured.update(start=start.tt, end=end.tt, samples=samples, boundary_samples=boundary_samples)
        return "corridor-result"

    engine.global_shadow_corridor = corridor
    result = engine.global_shadow_corridor_for_eclipse(
        "test", search_radius_hours=2.0, samples=7, boundary_samples=24
    )
    assert result == "corridor-result"
    assert captured["start"] == pytest.approx(maximum.tt - 2.0 / 24.0)
    assert captured["end"] == pytest.approx(maximum.tt + 2.0 / 24.0)
    assert captured["samples"] == 7 and captured["boundary_samples"] == 24
