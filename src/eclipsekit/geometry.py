"""Numerical geometry helpers for apparent solar/lunar discs and the Earth ellipsoid."""

from __future__ import annotations

import math
import numpy as np

SUN_RADIUS_KM = 696_000.0
MOON_RADIUS_PEAKS_KM = 1738.75
MOON_RADIUS_VALLEYS_KM = 1736.05
MOON_RADIUS_VISUAL_KM = 1737.93
MOON_RADIUS_XAVIER_KM = 1736.65
WGS84_A_KM = 6378.137
WGS84_B_KM = 6356.752314245


def angular_radius(radius_km: float, distance_km: float) -> float:
    if radius_km <= 0 or distance_km <= radius_km:
        raise ValueError("radius must be positive and smaller than distance")
    return math.asin(radius_km / distance_km)


def circle_overlap_fraction(radius_a: float, radius_b: float, separation: float) -> float:
    """Area overlap / area of circle A (the Sun); all inputs use the same angular unit."""
    if radius_a <= 0 or radius_b <= 0 or separation < 0:
        raise ValueError("circle radii must be positive and separation non-negative")
    if separation >= radius_a + radius_b:
        return 0.0
    if separation <= abs(radius_a - radius_b):
        return min(1.0, (radius_b / radius_a) ** 2)

    x = (separation**2 + radius_a**2 - radius_b**2) / (2.0 * separation * radius_a)
    y = (separation**2 + radius_b**2 - radius_a**2) / (2.0 * separation * radius_b)
    x = min(1.0, max(-1.0, x))
    y = min(1.0, max(-1.0, y))
    radicand = max(
        0.0,
        (-separation + radius_a + radius_b)
        * (separation + radius_a - radius_b)
        * (separation - radius_a + radius_b)
        * (separation + radius_a + radius_b),
    )
    overlap = radius_a**2 * math.acos(x) + radius_b**2 * math.acos(y) - 0.5 * math.sqrt(radicand)
    return min(1.0, max(0.0, overlap / (math.pi * radius_a**2)))


def wgs84_geodetic_to_ecef(latitude_deg: float, longitude_deg: float, elevation_m: float = 0.0) -> np.ndarray:
    lat = math.radians(latitude_deg)
    lon = math.radians(longitude_deg)
    h = elevation_m / 1000.0
    a, b = WGS84_A_KM, WGS84_B_KM
    e2 = 1.0 - (b * b) / (a * a)
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    n = a / math.sqrt(1.0 - e2 * sin_lat * sin_lat)
    return np.array([
        (n + h) * cos_lat * math.cos(lon),
        (n + h) * cos_lat * math.sin(lon),
        (n * (1.0 - e2) + h) * sin_lat,
    ], dtype=np.float64)


def wgs84_up_vector(latitude_deg: float, longitude_deg: float) -> np.ndarray:
    lat, lon = math.radians(latitude_deg), math.radians(longitude_deg)
    return np.array([math.cos(lat)*math.cos(lon), math.cos(lat)*math.sin(lon), math.sin(lat)], dtype=np.float64)


def ecef_to_geodetic(x_km: float, y_km: float, z_km: float) -> tuple[float, float, float]:
    """WGS84 ECEF to geodetic latitude/longitude/height using iterative latitude."""
    a, b = WGS84_A_KM, WGS84_B_KM
    e2 = 1.0 - b*b/(a*a)
    lon = math.atan2(y_km, x_km)
    p = math.hypot(x_km, y_km)
    lat = math.atan2(z_km, p * (1.0 - e2))
    for _ in range(12):
        sin_lat = math.sin(lat)
        n = a / math.sqrt(1.0 - e2 * sin_lat * sin_lat)
        h = p / max(math.cos(lat), 1e-15) - n
        next_lat = math.atan2(z_km, p * (1.0 - e2 * n / (n + h)))
        if abs(next_lat - lat) < 1e-13:
            lat = next_lat
            break
        lat = next_lat
    sin_lat = math.sin(lat)
    n = a / math.sqrt(1.0 - e2 * sin_lat * sin_lat)
    h = p / max(math.cos(lat), 1e-15) - n
    return math.degrees(lat), (math.degrees(lon) + 180.0) % 360.0 - 180.0, h * 1000.0


def ray_ellipsoid_intersection(origin: np.ndarray, direction: np.ndarray) -> np.ndarray | None:
    """Nearest forward intersection of a ray with the WGS84 reference ellipsoid."""
    o = np.asarray(origin, dtype=float)
    d = np.asarray(direction, dtype=float)
    norm = np.linalg.norm(d)
    if norm == 0:
        raise ValueError("ray direction cannot be zero")
    d = d / norm
    a, b = WGS84_A_KM, WGS84_B_KM
    qa = (d[0]**2 + d[1]**2) / a**2 + d[2]**2 / b**2
    qb = 2.0 * ((o[0]*d[0] + o[1]*d[1]) / a**2 + o[2]*d[2] / b**2)
    qc = (o[0]**2 + o[1]**2) / a**2 + o[2]**2 / b**2 - 1.0
    disc = qb*qb - 4.0*qa*qc
    if disc < 0:
        return None
    roots = [r for r in ((-qb-math.sqrt(disc))/(2*qa), (-qb+math.sqrt(disc))/(2*qa)) if r > 0]
    if not roots:
        return None
    return o + min(roots) * d


def position_angle(observer: object, t: object, sun: object, moon: object) -> float:
    """Position angle of lunar center relative to solar center, degrees from celestial north."""
    s = observer.at(t).observe(sun)
    m = observer.at(t).observe(moon)
    ra_s, dec_s, _ = s.radec()
    ra_m, dec_m, _ = m.radec()
    a1, d1, a2, d2 = ra_s.radians, dec_s.radians, ra_m.radians, dec_m.radians
    y = math.sin(a2-a1) * math.cos(d2)
    x = math.cos(d1)*math.sin(d2) - math.sin(d1)*math.cos(d2)*math.cos(a2-a1)
    return math.degrees(math.atan2(y, x)) % 360.0


def wgs84_inverse(latitude1_deg: float, longitude1_deg: float,
                  latitude2_deg: float, longitude2_deg: float) -> tuple[float, float]:
    """Return WGS84 inverse distance (km) and initial azimuth (degrees).

    Vincenty's inverse iteration is used for ordinary pairs. For nearly
    antipodal points, where that iteration may not converge, a spherical
    great-circle fallback returns a stable approximate distance and azimuth.
    """
    values = (latitude1_deg, longitude1_deg, latitude2_deg, longitude2_deg)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("geodesic coordinates must be finite")
    latitude_values = (float(latitude1_deg), float(latitude2_deg))
    longitude_values = (float(longitude1_deg), float(longitude2_deg))
    lat1, lat2 = map(math.radians, latitude_values)
    lon1, lon2 = map(math.radians, longitude_values)
    if not all(-90.0 <= value <= 90.0 for value in latitude_values):
        raise ValueError("geodesic latitudes must be within [-90, 90] degrees")
    if not all(-180.0 <= value <= 180.0 for value in longitude_values):
        raise ValueError("geodesic longitudes must be within [-180, 180] degrees")
    a, b = WGS84_A_KM, WGS84_B_KM
    flattening = (a - b) / a
    u1 = math.atan((1.0 - flattening) * math.tan(lat1))
    u2 = math.atan((1.0 - flattening) * math.tan(lat2))
    su1, cu1, su2, cu2 = math.sin(u1), math.cos(u1), math.sin(u2), math.cos(u2)
    L = (lon2 - lon1 + math.pi) % (2.0 * math.pi) - math.pi
    lam = L
    for _ in range(100):
        sl, cl = math.sin(lam), math.cos(lam)
        ss = math.hypot(cu2 * sl, cu1 * su2 - su1 * cu2 * cl)
        if ss == 0.0:
            return 0.0, 0.0
        cs = su1 * su2 + cu1 * cu2 * cl
        sigma = math.atan2(ss, cs)
        sin_alpha = cu1 * cu2 * sl / ss
        cos2_alpha = max(0.0, 1.0 - sin_alpha * sin_alpha)
        cos2sm = 0.0 if cos2_alpha < 1e-15 else cs - 2.0 * su1 * su2 / cos2_alpha
        C = flattening / 16.0 * cos2_alpha * (4.0 + flattening * (4.0 - 3.0 * cos2_alpha))
        old = lam
        lam = L + (1.0 - C) * flattening * sin_alpha * (
            sigma + C * ss * (cos2sm + C * cs * (-1.0 + 2.0 * cos2sm**2))
        )
        if abs(lam - old) <= 1e-12:
            break
    else:
        central = math.acos(max(-1.0, min(1.0,
            math.sin(lat1) * math.sin(lat2) + math.cos(lat1) * math.cos(lat2) * math.cos(L)
        )))
        azimuth = math.degrees(math.atan2(
            math.sin(L) * math.cos(lat2),
            math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(L),
        )) % 360.0
        return 6371.0088 * central, azimuth
    u_sq = cos2_alpha * (a*a - b*b) / (b*b)
    A = 1.0 + u_sq/16384.0 * (4096.0 + u_sq*(-768.0 + u_sq*(320.0 - 175.0*u_sq)))
    B = u_sq/1024.0 * (256.0 + u_sq*(-128.0 + u_sq*(74.0 - 47.0*u_sq)))
    delta = B * ss * (cos2sm + B/4.0 * (
        cs*(-1.0 + 2.0*cos2sm**2) - B/6.0*cos2sm*(-3.0 + 4.0*ss**2)*(-3.0 + 4.0*cos2sm**2)
    ))
    distance = b * A * (sigma - delta)
    azimuth = math.degrees(math.atan2(cu2 * math.sin(lam), cu1 * su2 - su1 * cu2 * math.cos(lam))) % 360.0
    return float(distance), float(azimuth)


def cone_ellipsoid_intersections(
    sun_position_km: np.ndarray,
    moon_position_km: np.ndarray,
    *,
    sun_radius_km: float = SUN_RADIUS_KM,
    moon_radius_km: float = MOON_RADIUS_XAVIER_KM,
    boundary: str = "central",
    azimuth_samples: int = 72,
) -> list[np.ndarray | None]:
    """Trace central (umbra/antumbra) or outer penumbral cone rays to WGS84.

    The model treats the Sun and Moon as spheres. At each lunar-limb azimuth a
    cone generatrix is intersected with the WGS84 ellipsoid; misses are ``None``.
    It does not model terrain, atmosphere, or limb topography.
    """
    sun = np.asarray(sun_position_km, dtype=np.float64)
    moon = np.asarray(moon_position_km, dtype=np.float64)
    if sun.shape != (3,) or moon.shape != (3,):
        raise ValueError("Sun and Moon positions must be three-dimensional ECEF vectors")
    if not np.all(np.isfinite(sun)) or not np.all(np.isfinite(moon)):
        raise ValueError("Sun and Moon positions must contain only finite values")
    rs, rm = float(sun_radius_km), float(moon_radius_km)
    if not math.isfinite(rs) or rs <= 0.0:
        raise ValueError("sun_radius_km must be finite and positive")
    if not math.isfinite(rm) or rm <= 0.0:
        raise ValueError("moon_radius_km must be finite and positive")
    if rs <= rm:
        raise ValueError("sun_radius_km must exceed moon_radius_km")
    if boundary not in {"central", "penumbra"}:
        raise ValueError("boundary must be 'central' or 'penumbra'")
    if isinstance(azimuth_samples, bool) or int(azimuth_samples) != azimuth_samples or azimuth_samples < 8:
        raise ValueError("azimuth_samples must be an integer >= 8")
    axis_vector = moon - sun
    distance = float(np.linalg.norm(axis_vector))
    if not math.isfinite(distance) or distance <= rs + rm:
        raise ValueError("Sun-Moon centre distance is invalid for shadow-cone construction")
    axis = axis_vector / distance
    reference = np.array([0.0, 0.0, 1.0])
    if abs(float(np.dot(axis, reference))) > 0.9:
        reference = np.array([1.0, 0.0, 0.0])
    first = np.cross(axis, reference)
    norm = float(np.linalg.norm(first))
    if norm <= 1e-15:
        raise ValueError("Could not construct a stable shadow-cone basis")
    first /= norm
    second = np.cross(axis, first)
    slope = ((rs + rm) if boundary == "penumbra" else (rs - rm)) / distance
    sign = 1.0 if boundary == "penumbra" else -1.0
    output: list[np.ndarray | None] = []
    for angle in np.linspace(0.0, 2.0 * math.pi, int(azimuth_samples), endpoint=False):
        radial = math.cos(float(angle)) * first + math.sin(float(angle)) * second
        origin = moon + rm * radial
        output.append(ray_ellipsoid_intersection(origin, axis + sign * slope * radial))
    return output
