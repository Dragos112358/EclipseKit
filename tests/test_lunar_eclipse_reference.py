from __future__ import annotations

import math

import numpy as np
import pytest

from eclipsekit.lunar_eclipse import lunar_shadow_geometry


def _equatorial_vector(ra_hours: float, dec_degrees: float, distance_km: float) -> np.ndarray:
    ra = math.radians(15.0 * ra_hours)
    dec = math.radians(dec_degrees)
    return distance_km * np.array((
        math.cos(dec) * math.cos(ra),
        math.cos(dec) * math.sin(ra),
        math.sin(dec),
    ))


def test_herald_sinnott_geometry_reconstructs_published_2025_total_eclipse_magnitudes():
    """Regression using rounded geocentric data published for 2025-03-14.

    Inputs are intentionally reconstructed from the rounded RA/Dec, horizontal
    parallaxes and semidiameters in the EclipseWise table.  This is a geometry
    regression, not a full ephemeris/contact-time validation.
    """
    earth_equatorial_radius_km = 6378.137
    moon_parallax = math.radians((54.0 + 36.8 / 60.0) / 60.0)
    sun_parallax = math.radians(8.8 / 3600.0)
    moon_semidiameter = math.radians((14.0 + 52.8 / 60.0) / 60.0)
    sun_semidiameter = math.radians((16.0 + 5.2 / 60.0) / 60.0)
    moon_distance = earth_equatorial_radius_km / math.sin(moon_parallax)
    sun_distance = earth_equatorial_radius_km / math.sin(sun_parallax)
    moon_radius = moon_distance * math.sin(moon_semidiameter)
    sun_radius = sun_distance * math.sin(sun_semidiameter)

    sun = _equatorial_vector(
        23.0 + 37.0 / 60.0 + 46.0 / 3600.0,
        -(2.0 + 24.0 / 60.0 + 16.8 / 3600.0),
        sun_distance,
    )
    moon = _equatorial_vector(
        11.0 + 38.0 / 60.0 + 23.0 / 3600.0,
        2.0 + 40.0 / 60.0 + 54.6 / 3600.0,
        moon_distance,
    )

    result = lunar_shadow_geometry(
        sun,
        moon,
        sun_radius_km=sun_radius,
        moon_radius_km=moon_radius,
        shadow_model="herald_sinnott",
    )

    assert result.axis_distance_deg == pytest.approx(0.3171, abs=3e-5)
    assert result.umbral_magnitude == pytest.approx(1.18038, abs=3e-4)
    assert result.penumbral_magnitude == pytest.approx(2.26146, abs=3e-4)
    assert result.earth_radius_factor == pytest.approx(1.01108, abs=2e-5)
    assert result.axis_distance_km / earth_equatorial_radius_km == pytest.approx(
        0.34846, abs=2e-4
    )
