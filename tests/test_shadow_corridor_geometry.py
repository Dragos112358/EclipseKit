import math

import numpy as np
import pytest

from eclipsekit.geometry import (
    WGS84_A_KM,
    WGS84_B_KM,
    cone_ellipsoid_intersections,
    ecef_to_geodetic,
    wgs84_inverse,
)


def test_wgs84_inverse_equatorial_and_zero_distance():
    distance, bearing = wgs84_inverse(0.0, 0.0, 0.0, 1.0)
    assert distance == pytest.approx(111.31949, abs=0.002)
    assert bearing == pytest.approx(90.0, abs=1e-8)
    assert wgs84_inverse(45.0, 10.0, 45.0, 10.0) == (0.0, 0.0)


def test_wgs84_inverse_handles_antimeridian_and_polar_track():
    distance, bearing = wgs84_inverse(10.0, 179.8, 10.0, -179.8)
    assert 40.0 < distance < 45.0
    assert 80.0 < bearing < 100.0
    polar_distance, polar_bearing = wgs84_inverse(89.0, 0.0, 89.0, 90.0)
    assert polar_distance > 100.0
    assert math.isfinite(polar_bearing)


def test_cone_boundary_intersections_land_on_wgs84_and_return_full_rings():
    sun = np.array([149_600_000.0, 0.0, 0.0])
    moon = np.array([360_000.0, 0.0, 0.0])
    central = cone_ellipsoid_intersections(sun, moon, boundary="central", azimuth_samples=48)
    penumbra = cone_ellipsoid_intersections(sun, moon, boundary="penumbra", azimuth_samples=48)
    assert len(central) == len(penumbra) == 48
    assert all(point is not None for point in central)
    assert all(point is not None for point in penumbra)
    for point in central + penumbra:
        x, y, z = point
        ellipsoid_value = (x*x + y*y) / (WGS84_A_KM**2) + z*z / (WGS84_B_KM**2)
        assert ellipsoid_value == pytest.approx(1.0, abs=2e-9)


def test_penumbra_boundary_is_outside_central_boundary_in_synthetic_case():
    sun = np.array([149_600_000.0, 0.0, 0.0])
    moon = np.array([360_000.0, 0.0, 0.0])
    central = cone_ellipsoid_intersections(sun, moon, boundary="central", azimuth_samples=72)
    penumbra = cone_ellipsoid_intersections(sun, moon, boundary="penumbra", azimuth_samples=72)
    center_latitude, center_longitude, _ = ecef_to_geodetic(6378.137, 0.0, 0.0)
    central_distances = [
        wgs84_inverse(center_latitude, center_longitude, *ecef_to_geodetic(*point)[:2])[0]
        for point in central if point is not None
    ]
    penumbral_distances = [
        wgs84_inverse(center_latitude, center_longitude, *ecef_to_geodetic(*point)[:2])[0]
        for point in penumbra if point is not None
    ]
    assert np.mean(central_distances) == pytest.approx(91.6, abs=1.0)
    assert np.mean(penumbral_distances) == pytest.approx(3580.8, abs=5.0)
    assert min(penumbral_distances) > max(central_distances)


@pytest.mark.parametrize("kwargs, message", [
    ({"boundary": "unknown"}, "boundary"),
    ({"azimuth_samples": 7}, "azimuth_samples"),
    ({"sun_radius_km": float("nan")}, "sun_radius_km"),
    ({"moon_radius_km": -1.0}, "moon_radius_km"),
])
def test_cone_intersection_rejects_invalid_options(kwargs, message):
    with pytest.raises(ValueError, match=message):
        cone_ellipsoid_intersections(np.array([149_600_000.0, 0, 0]), np.array([360_000.0, 0, 0]), **kwargs)


def test_cone_intersection_rejects_invalid_position_vectors():
    with pytest.raises(ValueError, match="three-dimensional"):
        cone_ellipsoid_intersections(np.array([1.0, 2.0]), np.array([3.0, 4.0, 5.0]))
    with pytest.raises(ValueError, match="finite"):
        cone_ellipsoid_intersections(np.array([1.0, 2.0, np.inf]), np.array([3.0, 4.0, 5.0]))


def test_wgs84_inverse_rejects_out_of_range_longitudes():
    with pytest.raises(ValueError, match="longitudes"):
        wgs84_inverse(0.0, -181.0, 0.0, 0.0)
    with pytest.raises(ValueError, match="longitudes"):
        wgs84_inverse(0.0, 0.0, 0.0, 181.0)


def test_wgs84_inverse_antipodal_fallback_is_finite_and_reasonable():
    distance, azimuth = wgs84_inverse(0.0, 0.0, 0.0, 180.0)
    assert 20_000.0 < distance < 20_100.0
    assert math.isfinite(azimuth)


def test_cone_intersection_returns_none_when_axis_points_away_from_earth():
    sun = np.array([149_600_000.0, 0.0, 0.0])
    moon = np.array([-360_000.0, 0.0, 0.0])
    hits = cone_ellipsoid_intersections(sun, moon, azimuth_samples=24)
    assert len(hits) == 24
    assert all(hit is None for hit in hits)
