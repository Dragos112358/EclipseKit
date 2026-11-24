import numpy as np
import pytest

from eclipsekit.geometry import (
    circle_overlap_fraction,
    ecef_to_geodetic,
    ray_ellipsoid_intersection,
    wgs84_geodetic_to_ecef,
)


def test_circle_overlap_no_contact():
    assert circle_overlap_fraction(1.0, 1.0, 2.1) == 0.0


def test_circle_overlap_total_solar_cover():
    # A smaller Moon entirely inside the apparent solar disc.
    assert circle_overlap_fraction(1.0, 0.5, 0.0) == pytest.approx(0.25)


def test_circle_overlap_full_solar_cover():
    assert circle_overlap_fraction(1.0, 1.2, 0.0) == pytest.approx(1.0)


def test_circle_overlap_partial_between_zero_and_one():
    result = circle_overlap_fraction(1.0, 0.9, 0.8)
    assert 0.0 < result < 1.0


def test_wgs84_equator_round_trip():
    ecef = wgs84_geodetic_to_ecef(0.0, 0.0, 0.0)
    assert ecef == pytest.approx(np.array([6378.137, 0.0, 0.0]), abs=1e-6)
    lat, lon, height = ecef_to_geodetic(*ecef)
    assert lat == pytest.approx(0.0, abs=1e-8)
    assert lon == pytest.approx(0.0, abs=1e-8)
    assert height == pytest.approx(0.0, abs=1e-5)


def test_ray_hits_wgs84():
    hit = ray_ellipsoid_intersection(np.array([7000.0, 0.0, 0.0]), np.array([-1.0, 0.0, 0.0]))
    assert hit is not None
    assert hit[0] == pytest.approx(6378.137, abs=1e-6)


def test_ray_misses_wgs84():
    hit = ray_ellipsoid_intersection(np.array([7000.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]))
    assert hit is None
