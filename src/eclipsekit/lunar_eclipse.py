"""Geocentric lunar-eclipse calculations with an oblate-Earth shadow model.

The default shadow prescription implements the Herald--Sinnott (2014) model
as reproduced in Espenak's *21st Century Canon of Lunar Eclipses*: an 87 km
notional eclipse-forming atmospheric layer and an angle-dependent correction
for Earth's oblateness.  The resulting penumbral and umbral boundaries are
non-circular.  Contacts are solved as spherical tangencies between the lunar
disc and those boundaries.

The model is geocentric.  It does not by itself provide topocentric moonrise,
moonset, or local contact visibility.  Numerical root tolerances describe the
solver only; physical accuracy also depends on the ephemeris, Earth-orientation
and Delta-T data, lunar radius convention, and adopted shadow prescription.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Callable, Literal

import numpy as np

from .timeutils import time_to_utc_iso, time_to_ut1_iso

LunarEclipseType = Literal["penumbral", "partial", "total"]
CalendarName = Literal["historical", "julian", "gregorian"]
ShadowModelName = Literal["herald_sinnott", "circular"]

WGS84_EQUATORIAL_RADIUS_KM = 6378.137
WGS84_FLATTENING = 1.0 / 298.257223563
HERALD_SINNOTT_FLATTENING_COEFFICIENT = 0.003353
DEFAULT_NEL_HEIGHT_KM = 87.0
MEAN_MOON_RADIUS_KM = 1737.4
DEFAULT_SUN_RADIUS_KM = 696000.0
_BOUNDARY_SAMPLES = 96


def _finite_positive(name: str, value: float) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    return value


def _unit_vector(value: Any, name: str) -> np.ndarray:
    vector = np.asarray(value, dtype=np.float64)
    if vector.shape != (3,):
        raise ValueError(f"{name} must be a 3D vector")
    if not np.all(np.isfinite(vector)):
        raise ValueError(f"{name} must contain only finite values")
    norm = float(np.linalg.norm(vector))
    if norm <= 0.0:
        raise ValueError(f"{name} must have non-zero length")
    return vector / norm


def _golden_minimum(
    function: Callable[[float], float], left: float, right: float, *, tolerance: float,
    max_iterations: int = 100,
) -> float:
    """Minimize a unimodal scalar function over a bounded interval."""
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    x1 = right - ratio * (right - left)
    x2 = left + ratio * (right - left)
    f1, f2 = function(x1), function(x2)
    for _ in range(max_iterations):
        if right - left <= tolerance:
            break
        if f1 <= f2:
            right, x2, f2 = x2, x1, f1
            x1 = right - ratio * (right - left)
            f1 = function(x1)
        else:
            left, x1, f1 = x1, x2, f2
            x2 = left + ratio * (right - left)
            f2 = function(x2)
    return (left + right) / 2.0


def _bisect_zero(
    function: Callable[[float], float], left: float, right: float, *, tolerance_days: float
) -> float:
    f_left = function(left)
    f_right = function(right)
    if f_left == 0.0:
        return left
    if f_right == 0.0:
        return right
    if f_left * f_right > 0.0:
        raise ValueError("root interval does not bracket a sign change")
    for _ in range(100):
        middle = (left + right) / 2.0
        f_middle = function(middle)
        if abs(f_middle) <= 1e-12 or right - left <= tolerance_days:
            return middle
        if f_left * f_middle <= 0.0:
            right, f_right = middle, f_middle
        else:
            left, f_left = middle, f_middle
    return (left + right) / 2.0


def _contact_on_side(
    coarse_residual: Callable[[float], float],
    exact_residual: Callable[[float], float],
    maximum_jd: float,
    direction: int,
    *,
    half_window_hours: float,
    step_seconds: float,
    tolerance_seconds: float,
) -> float | None:
    """Find one contact on either side of greatest eclipse.

    The exact signed distance controls event/contact existence.  The inexpensive
    radial residual is only a bracket accelerator: it is never allowed to reject
    a contact by itself.  If its bracket misses (which can happen for a shallow
    grazing event when the non-circular boundary changes with position angle),
    the full interval is scanned with the exact residual before returning None.
    """
    if direction not in (-1, 1):
        raise ValueError("direction must be -1 or +1")

    step_days = step_seconds / 86400.0
    count = int(math.ceil(half_window_hours * 3600.0 / step_seconds))
    tolerance_days = tolerance_seconds / 86400.0

    exact_center = exact_residual(maximum_jd)
    if not math.isfinite(exact_center):
        raise ValueError("exact contact residual at greatest eclipse must be finite")
    if exact_center > 0.0:
        # At greatest eclipse the exact geometry says the lunar limb does not
        # reach this boundary, so this contact pair does not exist.
        return None
    if abs(exact_center) <= 1e-12:
        return maximum_jd

    def refine_if_bracketed(first_jd: float, second_jd: float) -> float | None:
        left, right = sorted((first_jd, second_jd))
        f_left = exact_residual(left)
        f_right = exact_residual(right)
        if f_left == 0.0:
            return left
        if f_right == 0.0:
            return right
        if f_left * f_right > 0.0:
            return None
        return _bisect_zero(
            exact_residual, left, right, tolerance_days=tolerance_days
        )

    # Fast path: use the radial approximation to locate a likely exit bracket.
    coarse_center = coarse_residual(maximum_jd)
    if math.isfinite(coarse_center) and coarse_center <= 0.0:
        previous_jd = maximum_jd
        for index in range(1, count + 1):
            current_jd = maximum_jd + direction * index * step_days
            current_coarse = coarse_residual(current_jd)
            if not math.isfinite(current_coarse):
                break
            if current_coarse >= 0.0:
                root = refine_if_bracketed(previous_jd, current_jd)
                if root is not None:
                    return root
                break
            previous_jd = current_jd

    # Exact fallback: do not silently lose grazing contacts when the coarse
    # curve never crosses zero or starts on the wrong side of zero.
    previous_jd = maximum_jd
    previous_exact = exact_center
    for index in range(1, count + 1):
        current_jd = maximum_jd + direction * index * step_days
        current_exact = exact_residual(current_jd)
        if not math.isfinite(current_exact):
            previous_jd = current_jd
            previous_exact = current_exact
            continue
        if current_exact == 0.0:
            return current_jd
        if math.isfinite(previous_exact) and previous_exact * current_exact < 0.0:
            root = refine_if_bracketed(previous_jd, current_jd)
            if root is not None:
                return root
        previous_jd = current_jd
        previous_exact = current_exact
    return None


def _herald_sinnott_earth_factor(
    psi_rad: float,
    sun_declination_rad: float,
    solar_semidiameter_rad: float,
    solar_parallax_rad: float,
    *,
    earth_equatorial_radius_km: float,
    atmospheric_nel_height_km: float,
    flattening_coefficient: float,
    shadow_enlargement: float,
) -> float:
    """Angle-dependent effective Earth radius in equatorial Earth radii.

    This is Eq. (2-5)'s Earth-radius term from Herald & Sinnott, as printed in
    Espenak's 21st Century Canon of Lunar Eclipses.  The fixed-point update is
    iterated twice (the source notes one iteration is sufficient).
    """
    h = atmospheric_nel_height_km / earth_equatorial_radius_km
    sin_psi = math.sin(psi_rad)
    sin2_psi = sin_psi * sin_psi
    earth_factor = 1.0 + h
    for _ in range(2):
        f_angle = solar_semidiameter_rad - earth_factor * solar_parallax_rad
        earth_factor = (
            1.0 + h
            - flattening_coefficient * sin2_psi
            * math.cos(sun_declination_rad + f_angle * sin_psi) ** 2
        )
    return earth_factor * shadow_enlargement


def _closest_angular_distance_to_boundary(
    moon_direction: np.ndarray,
    shadow_axis: np.ndarray,
    east_axis: np.ndarray,
    north_axis: np.ndarray,
    radius_at_position_angle: Callable[[float], float],
    *,
    samples: int = _BOUNDARY_SAMPLES,
) -> float:
    """Minimum great-circle distance from Moon centre to a radial shadow edge."""
    if samples < 24:
        raise ValueError("boundary_samples must be at least 24")
    angles = np.linspace(0.0, 2.0 * math.pi, samples, endpoint=False)
    radii = np.fromiter(
        (radius_at_position_angle(float(angle)) for angle in angles),
        dtype=np.float64,
        count=samples,
    )
    transverse = (
        np.cos(angles)[:, np.newaxis] * east_axis[np.newaxis, :]
        + np.sin(angles)[:, np.newaxis] * north_axis[np.newaxis, :]
    )
    boundary = (
        np.cos(radii)[:, np.newaxis] * shadow_axis[np.newaxis, :]
        + np.sin(radii)[:, np.newaxis] * transverse
    )
    dots = np.clip(boundary @ moon_direction, -1.0, 1.0)
    crosses = np.linalg.norm(np.cross(boundary, moon_direction), axis=1)
    distances = np.arctan2(crosses, dots)
    best = int(np.argmin(distances))
    step = 2.0 * math.pi / samples
    left = float(angles[best] - step)
    right = float(angles[best] + step)

    def distance(position_angle: float) -> float:
        radius = radius_at_position_angle(position_angle)
        boundary_direction = (
            math.cos(radius) * shadow_axis
            + math.sin(radius) * (
                math.cos(position_angle) * east_axis
                + math.sin(position_angle) * north_axis
            )
        )
        dot = float(np.clip(np.dot(boundary_direction, moon_direction), -1.0, 1.0))
        cross = float(np.linalg.norm(np.cross(boundary_direction, moon_direction)))
        return math.atan2(cross, dot)

    angle = _golden_minimum(distance, left, right, tolerance=1e-11, max_iterations=64)
    return distance(angle)


@dataclass(frozen=True)
class LunarShadowGeometry:
    """Instantaneous geocentric geometry of the Moon relative to Earth's shadow."""

    behind_earth: bool
    axis_distance_km: float
    moon_distance_km: float
    sun_distance_km: float
    umbra_radius_km: float
    penumbra_radius_km: float
    penumbral_magnitude: float
    umbral_magnitude: float
    shadow_axis_distance_rad: float
    moon_angular_radius_rad: float
    umbra_radius_rad: float
    penumbra_radius_rad: float
    shadow_position_angle_rad: float
    solar_declination_rad: float
    earth_radius_factor: float
    umbral_signed_distance_rad: float
    penumbral_signed_distance_rad: float
    shadow_model: str

    @property
    def axis_distance_deg(self) -> float:
        return math.degrees(self.shadow_axis_distance_rad)


def lunar_shadow_geometry(
    sun_position_km: Any,
    moon_position_km: Any,
    *,
    sun_radius_km: float = DEFAULT_SUN_RADIUS_KM,
    earth_radius_km: float = WGS84_EQUATORIAL_RADIUS_KM,
    moon_radius_km: float = MEAN_MOON_RADIUS_KM,
    shadow_enlargement: float = 1.0,
    shadow_model: ShadowModelName = "herald_sinnott",
    atmospheric_nel_height_km: float = DEFAULT_NEL_HEIGHT_KM,
    flattening_coefficient: float = HERALD_SINNOTT_FLATTENING_COEFFICIENT,
    earth_pole_vector: Any = (0.0, 0.0, 1.0),
    boundary_samples: int = _BOUNDARY_SAMPLES,
    compute_contact_distances: bool = True,
) -> LunarShadowGeometry:
    """Calculate geocentric umbra/penumbra geometry.

    Parameters
    ----------
    sun_position_km, moon_position_km:
        Apparent geocentric Cartesian vectors, in the same frame and epoch.
        The default pole vector assumes an Earth-equatorial/ITRS-like frame
        whose positive Z axis is Earth's north rotation pole.
    shadow_model:
        ``"herald_sinnott"`` (default) uses the 87 km NEL and oblate-Earth
        angle-dependent shadow radii. ``"circular"`` is retained as a
        reproducibility option for the previous spherical-cone approximation.
    shadow_enlargement:
        Additional multiplicative scale applied to the effective Earth radius.
        Leave at 1.0 for the standard 87 km Herald--Sinnott NEL prescription.
    """
    sun = np.asarray(sun_position_km, dtype=np.float64)
    moon = np.asarray(moon_position_km, dtype=np.float64)
    if sun.shape != (3,) or moon.shape != (3,):
        raise ValueError("Sun and Moon positions must each be 3D vectors")
    if not np.all(np.isfinite(sun)) or not np.all(np.isfinite(moon)):
        raise ValueError("Sun and Moon positions must contain only finite values")
    sun_radius_km = _finite_positive("sun_radius_km", sun_radius_km)
    earth_radius_km = _finite_positive("earth_radius_km", earth_radius_km)
    moon_radius_km = _finite_positive("moon_radius_km", moon_radius_km)
    shadow_enlargement = _finite_positive("shadow_enlargement", shadow_enlargement)
    atmospheric_nel_height_km = float(atmospheric_nel_height_km)
    flattening_coefficient = float(flattening_coefficient)
    if not math.isfinite(atmospheric_nel_height_km) or atmospheric_nel_height_km < 0:
        raise ValueError("atmospheric_nel_height_km must be finite and non-negative")
    if not math.isfinite(flattening_coefficient) or not 0.0 <= flattening_coefficient < 0.01:
        raise ValueError("flattening_coefficient must be finite and in [0, 0.01)")
    if shadow_model not in {"herald_sinnott", "circular"}:
        raise ValueError("shadow_model must be 'herald_sinnott' or 'circular'")
    if boundary_samples < 24:
        raise ValueError("boundary_samples must be at least 24")
    if not isinstance(compute_contact_distances, bool):
        raise ValueError("compute_contact_distances must be a bool")

    sun_distance = float(np.linalg.norm(sun))
    moon_distance = float(np.linalg.norm(moon))
    if sun_distance <= sun_radius_km or moon_distance <= max(earth_radius_km, moon_radius_km):
        raise ValueError("body distances must exceed their relevant radii")

    sun_hat = sun / sun_distance
    moon_hat = moon / moon_distance
    shadow_axis = -sun_hat
    axial_distance = float(np.dot(moon, shadow_axis))
    perpendicular = moon - axial_distance * shadow_axis
    perpendicular_norm = float(np.linalg.norm(perpendicular))
    behind_earth = axial_distance > 0.0
    gamma = math.atan2(perpendicular_norm, axial_distance)
    moon_semidiameter = math.asin(min(1.0, moon_radius_km / moon_distance))
    axis_distance_km = perpendicular_norm

    pole = _unit_vector(earth_pole_vector, "earth_pole_vector")
    north_projection = pole - float(np.dot(pole, shadow_axis)) * shadow_axis
    north_norm = float(np.linalg.norm(north_projection))
    if north_norm < 1e-12:
        # Degenerate only when the shadow axis is almost parallel to Earth's
        # spin axis; choose a stable celestial/equatorial fallback direction.
        fallback = np.array((1.0, 0.0, 0.0), dtype=np.float64)
        north_projection = fallback - float(np.dot(fallback, shadow_axis)) * shadow_axis
        north_norm = float(np.linalg.norm(north_projection))
    north_axis = north_projection / north_norm
    east_axis = np.cross(shadow_axis, north_axis)
    east_axis /= float(np.linalg.norm(east_axis))

    if perpendicular_norm > 1e-15:
        p_hat = perpendicular / perpendicular_norm
        east_component = float(np.dot(p_hat, east_axis))
        north_component = float(np.dot(p_hat, north_axis))
        psi_center = math.atan2(north_component, east_component)
    else:
        psi_center = 0.0
    sun_declination = math.asin(float(np.clip(np.dot(sun_hat, pole), -1.0, 1.0)))

    solar_semidiameter = math.asin(sun_radius_km / sun_distance)
    if shadow_model == "herald_sinnott":
        solar_parallax = math.asin(earth_radius_km / sun_distance)
        lunar_parallax = math.asin(earth_radius_km / moon_distance)

        def earth_factor_at(psi: float) -> float:
            return _herald_sinnott_earth_factor(
                psi, sun_declination, solar_semidiameter, solar_parallax,
                earth_equatorial_radius_km=earth_radius_km,
                atmospheric_nel_height_km=atmospheric_nel_height_km,
                flattening_coefficient=flattening_coefficient,
                shadow_enlargement=shadow_enlargement,
            )

        def umbra_at(psi: float) -> float:
            return earth_factor_at(psi) * lunar_parallax - solar_semidiameter + solar_parallax

        def penumbra_at(psi: float) -> float:
            return earth_factor_at(psi) * lunar_parallax + solar_semidiameter + solar_parallax
    else:
        effective_earth_radius = earth_radius_km * shadow_enlargement
        lunar_parallax = math.asin(effective_earth_radius / moon_distance)
        solar_parallax = math.asin(effective_earth_radius / sun_distance)

        def earth_factor_at(psi: float) -> float:
            return shadow_enlargement

        def umbra_at(psi: float) -> float:
            return lunar_parallax - solar_semidiameter + solar_parallax

        def penumbra_at(psi: float) -> float:
            return lunar_parallax + solar_semidiameter + solar_parallax

    if not behind_earth:
        return LunarShadowGeometry(
            behind_earth=False,
            axis_distance_km=axis_distance_km,
            moon_distance_km=moon_distance,
            sun_distance_km=sun_distance,
            umbra_radius_km=-math.inf,
            penumbra_radius_km=-math.inf,
            penumbral_magnitude=-math.inf,
            umbral_magnitude=-math.inf,
            shadow_axis_distance_rad=gamma,
            moon_angular_radius_rad=moon_semidiameter,
            umbra_radius_rad=-math.inf,
            penumbra_radius_rad=-math.inf,
            shadow_position_angle_rad=psi_center,
            solar_declination_rad=sun_declination,
            earth_radius_factor=earth_factor_at(psi_center),
            umbral_signed_distance_rad=math.inf,
            penumbral_signed_distance_rad=math.inf,
            shadow_model=shadow_model,
        )

    umbra_radius = umbra_at(psi_center)
    penumbra_radius = penumbra_at(psi_center)
    if umbra_radius <= 0.0 or penumbra_radius <= 0.0:
        raise ValueError("computed Earth-shadow radii must be positive")

    # The inexpensive radial clearance is used to bracket contact roots.  The
    # exact signed great-circle distance to the full non-circular boundary is
    # evaluated only while refining a bracket, which keeps ephemeris searches
    # responsive without weakening the final contact solution.
    if compute_contact_distances:
        umbral_signed_distance = _closest_angular_distance_to_boundary(
            moon_hat, shadow_axis, east_axis, north_axis, umbra_at, samples=boundary_samples
        )
        penumbral_signed_distance = _closest_angular_distance_to_boundary(
            moon_hat, shadow_axis, east_axis, north_axis, penumbra_at, samples=boundary_samples
        )
    else:
        umbral_signed_distance = abs(gamma - umbra_radius)
        penumbral_signed_distance = abs(gamma - penumbra_radius)
    # A polar radial boundary is star-shaped about the shadow axis.  The centre
    # lies inside precisely when its angular radius is smaller than the radial
    # edge in the Moon-centre position angle.
    if gamma < umbra_radius:
        umbral_signed_distance = -umbral_signed_distance
    if gamma < penumbra_radius:
        penumbral_signed_distance = -penumbral_signed_distance

    # Signed distance generalizes the usual circular-shadow magnitude formula
    # to the angle-dependent Herald--Sinnott boundary. For a circle it reduces
    # exactly to (shadow_radius + lunar_radius - axis_distance)/(2*lunar_radius).
    umbral_magnitude = (moon_semidiameter - umbral_signed_distance) / (2.0 * moon_semidiameter)
    penumbral_magnitude = (
        moon_semidiameter - penumbral_signed_distance
    ) / (2.0 * moon_semidiameter)

    return LunarShadowGeometry(
        behind_earth=True,
        axis_distance_km=axis_distance_km,
        moon_distance_km=moon_distance,
        sun_distance_km=sun_distance,
        umbra_radius_km=math.tan(umbra_radius) * moon_distance,
        penumbra_radius_km=math.tan(penumbra_radius) * moon_distance,
        penumbral_magnitude=penumbral_magnitude,
        umbral_magnitude=umbral_magnitude,
        shadow_axis_distance_rad=gamma,
        moon_angular_radius_rad=moon_semidiameter,
        umbra_radius_rad=umbra_radius,
        penumbra_radius_rad=penumbra_radius,
        shadow_position_angle_rad=psi_center,
        solar_declination_rad=sun_declination,
        earth_radius_factor=earth_factor_at(psi_center),
        umbral_signed_distance_rad=umbral_signed_distance,
        penumbral_signed_distance_rad=penumbral_signed_distance,
        shadow_model=shadow_model,
    )


@dataclass(frozen=True)
class LunarEclipseContacts:
    """Geocentric contact times for a lunar eclipse."""

    p1: Any | None = None
    u1: Any | None = None
    u2: Any | None = None
    greatest: Any | None = None
    u3: Any | None = None
    u4: Any | None = None
    p4: Any | None = None

    def as_dict(self) -> dict[str, Any | None]:
        return {
            "P1": self.p1,
            "U1": self.u1,
            "U2": self.u2,
            "greatest": self.greatest,
            "U3": self.u3,
            "U4": self.u4,
            "P4": self.p4,
        }

    @property
    def penumbral_duration_seconds(self) -> float | None:
        if self.p1 is None or self.p4 is None:
            return None
        return (float(self.p4.tt) - float(self.p1.tt)) * 86400.0

    @property
    def partial_duration_seconds(self) -> float | None:
        if self.u1 is None or self.u4 is None:
            return None
        return (float(self.u4.tt) - float(self.u1.tt)) * 86400.0

    @property
    def totality_duration_seconds(self) -> float | None:
        if self.u2 is None or self.u3 is None:
            return None
        return (float(self.u3.tt) - float(self.u2.tt)) * 86400.0


@dataclass(frozen=True)
class LunarEclipseResult:
    """Calculated geocentric lunar-eclipse circumstances."""

    eclipse_type: LunarEclipseType
    maximum: Any
    contacts: LunarEclipseContacts
    penumbral_magnitude: float
    umbral_magnitude: float
    axis_distance_km: float
    axis_distance_deg: float
    umbra_radius_km: float
    penumbra_radius_km: float
    moon_distance_km: float
    sun_distance_km: float
    moon_radius_km: float
    earth_radius_km: float
    sun_radius_km: float
    shadow_enlargement: float
    calendar: CalendarName = "historical"
    shadow_model: str = "herald_sinnott"
    atmospheric_nel_height_km: float = DEFAULT_NEL_HEIGHT_KM
    flattening_coefficient: float = HERALD_SINNOTT_FLATTENING_COEFFICIENT
    earth_radius_factor: float = 1.0
    shadow_axis_distance_deg: float = 0.0
    umbra_radius_deg: float = 0.0
    penumbra_radius_deg: float = 0.0
    solar_declination_deg: float = 0.0
    shadow_position_angle_deg: float = 0.0

    @property
    def is_total(self) -> bool:
        return self.eclipse_type == "total"

    def to_dict(self, *, calendar: str | None = None) -> dict[str, Any]:
        output_calendar = self.calendar if calendar is None else calendar
        values = self.contacts.as_dict()
        contact_payload = {
            name: time_to_utc_iso(value, calendar=output_calendar) if value is not None else None
            for name, value in values.items()
        }
        contact_ut1_payload = {
            name: time_to_ut1_iso(value, calendar=output_calendar) if value is not None else None
            for name, value in values.items()
        }
        contact_tt_jd_payload = {
            name: float(value.tt) if value is not None else None
            for name, value in values.items()
        }
        return {
            "event_type": "lunar_eclipse",
            "eclipse_type": self.eclipse_type,
            "calendar": output_calendar,
            "maximum_utc": time_to_utc_iso(self.maximum, calendar=output_calendar),
            "maximum_ut1": time_to_ut1_iso(self.maximum, calendar=output_calendar),
            "maximum_jd_tt": float(self.maximum.tt),
            "contacts": contact_payload,
            "contacts_ut1": contact_ut1_payload,
            "contacts_jd_tt": contact_tt_jd_payload,
            "penumbral_magnitude": self.penumbral_magnitude,
            "umbral_magnitude": self.umbral_magnitude,
            "axis_distance_km": self.axis_distance_km,
            "axis_distance_deg": self.axis_distance_deg,
            # Gamma is the minimum axis distance in equatorial Earth radii;
            # epsilon is the same separation expressed as an angle in degrees.
            "gamma": self.axis_distance_km / self.earth_radius_km,
            "epsilon_deg": self.shadow_axis_distance_deg,
            "shadow_axis_distance_deg": self.shadow_axis_distance_deg,
            "shadow_position_angle_deg": self.shadow_position_angle_deg,
            "umbra_radius_km": self.umbra_radius_km,
            "penumbra_radius_km": self.penumbra_radius_km,
            "umbra_radius_deg": self.umbra_radius_deg,
            "penumbra_radius_deg": self.penumbra_radius_deg,
            "moon_distance_km": self.moon_distance_km,
            "sun_distance_km": self.sun_distance_km,
            "radii_km": {
                "earth_equatorial": self.earth_radius_km,
                "earth_polar_wgs84": self.earth_radius_km * (1.0 - WGS84_FLATTENING),
                "moon": self.moon_radius_km,
                "sun": self.sun_radius_km,
            },
            "shadow_model": self.shadow_model,
            "earth_model": (
                "WGS84 oblate Earth with Herald-Sinnott NEL"
                if self.shadow_model == "herald_sinnott"
                else "spherical effective Earth (legacy model)"
            ),
            "shadow_enlargement": self.shadow_enlargement,
            "atmospheric_nel_height_km": self.atmospheric_nel_height_km,
            "flattening_coefficient": self.flattening_coefficient,
            "wgs84_flattening": WGS84_FLATTENING,
            "earth_effective_radius_factor_at_moon_position": self.earth_radius_factor,
            "solar_declination_deg": self.solar_declination_deg,
            "durations_seconds": {
                "penumbral": self.contacts.penumbral_duration_seconds,
                "partial": self.contacts.partial_duration_seconds,
                "totality": self.contacts.totality_duration_seconds,
            },
            "scientific_status": (
                "experimental_geocentric_herald_sinnott_oblate_earth_shadow_model"
                if self.shadow_model == "herald_sinnott"
                else "experimental_geocentric_circular_shadow_model"
            ),
            "warnings": [
                "Geocentric contacts; local moonrise/moonset and phase visibility must be computed separately.",
                "The 87 km notional eclipse-forming layer is an empirical shadow prescription, not a resolved atmospheric model."
                if self.shadow_model == "herald_sinnott"
                else "Uses a circular shadow and spherical effective Earth-radius approximation.",
                "Results depend on the selected ephemeris and Earth-orientation/time-scale data.",
            ],
        }


def solve_lunar_eclipse(
    center: Any,
    position_at_jd: Callable[[float], tuple[Any, Any]],
    time_from_tt_jd: Callable[[float], Any],
    *,
    calendar: CalendarName = "historical",
    sun_radius_km: float = DEFAULT_SUN_RADIUS_KM,
    earth_radius_km: float = WGS84_EQUATORIAL_RADIUS_KM,
    moon_radius_km: float = MEAN_MOON_RADIUS_KM,
    shadow_enlargement: float = 1.0,
    shadow_model: ShadowModelName = "herald_sinnott",
    atmospheric_nel_height_km: float = DEFAULT_NEL_HEIGHT_KM,
    flattening_coefficient: float = HERALD_SINNOTT_FLATTENING_COEFFICIENT,
    search_half_window_hours: float = 8.0,
    contact_search_half_window_hours: float = 8.0,
    contact_step_seconds: float = 300.0,
    contact_tolerance_seconds: float = 0.05,
    boundary_samples: int = _BOUNDARY_SAMPLES,
) -> LunarEclipseResult | None:
    """Solve one lunar eclipse near ``center`` using apparent geocentric vectors.

    ``position_at_jd`` receives TT Julian Date and returns geocentric apparent
    Cartesian vectors ``(sun_km, moon_km)`` in the same Earth-equatorial/ITRS
    frame. Contacts are roots of signed spherical distance to the non-circular
    shadow boundary, not circular-radius approximations.
    """
    numeric_options = (
        search_half_window_hours, contact_search_half_window_hours,
        contact_step_seconds, contact_tolerance_seconds,
    )
    if not all(math.isfinite(value) and value > 0 for value in numeric_options):
        raise ValueError("search windows, contact step, and tolerance must be finite and positive")
    if calendar not in {"historical", "julian", "gregorian"}:
        raise ValueError("calendar must be 'historical', 'julian', or 'gregorian'")
    if boundary_samples < 24:
        raise ValueError("boundary_samples must be at least 24")

    center_jd = float(center.tt)
    vector_cache: dict[float, tuple[Any, Any]] = {}
    geometry_cache: dict[float, LunarShadowGeometry] = {}
    exact_geometry_cache: dict[float, LunarShadowGeometry] = {}

    def vectors_at(jd_tt: float) -> tuple[Any, Any]:
        key = round(float(jd_tt), 12)
        if key not in vector_cache:
            vector_cache[key] = position_at_jd(float(jd_tt))
        return vector_cache[key]

    def geometry_at(jd_tt: float, *, exact_contacts: bool = False) -> LunarShadowGeometry:
        key = round(float(jd_tt), 12)
        if key not in geometry_cache:
            sun_vector, moon_vector = vectors_at(float(jd_tt))
            geometry_cache[key] = lunar_shadow_geometry(
                sun_vector, moon_vector,
                sun_radius_km=sun_radius_km,
                earth_radius_km=earth_radius_km,
                moon_radius_km=moon_radius_km,
                shadow_enlargement=shadow_enlargement,
                shadow_model=shadow_model,
                atmospheric_nel_height_km=atmospheric_nel_height_km,
                flattening_coefficient=flattening_coefficient,
                boundary_samples=boundary_samples,
                compute_contact_distances=False,
            )
        if not exact_contacts:
            return geometry_cache[key]
        if key not in exact_geometry_cache:
            sun_vector, moon_vector = vectors_at(float(jd_tt))
            exact_geometry_cache[key] = lunar_shadow_geometry(
                sun_vector, moon_vector,
                sun_radius_km=sun_radius_km,
                earth_radius_km=earth_radius_km,
                moon_radius_km=moon_radius_km,
                shadow_enlargement=shadow_enlargement,
                shadow_model=shadow_model,
                atmospheric_nel_height_km=atmospheric_nel_height_km,
                flattening_coefficient=flattening_coefficient,
                boundary_samples=boundary_samples,
                compute_contact_distances=True,
            )
        return exact_geometry_cache[key]

    left = center_jd - search_half_window_hours / 24.0
    right = center_jd + search_half_window_hours / 24.0
    # Greatest eclipse is the instant when the Moon's geocentric centre is
    # closest to the shadow axis (minimum gamma / perpendicular distance), not
    # merely the minimum angular separation. The distinction is small but the
    # former is the standard lunar-eclipse gamma definition.
    maximum_jd = _golden_minimum(
        lambda jd: geometry_at(jd).axis_distance_km,
        left, right, tolerance=0.05 / 86400.0,
    )
    # Re-evaluate the maximum with the full non-circular boundary. This keeps
    # the eclipse classification and published magnitudes consistent with the
    # exact geometry used to refine the contact times (rather than the radial
    # approximation used only to accelerate the search).
    maximum_geometry = geometry_at(maximum_jd, exact_contacts=True)
    if not maximum_geometry.behind_earth or maximum_geometry.penumbral_magnitude <= 0.0:
        return None

    if maximum_geometry.umbral_magnitude >= 1.0:
        eclipse_type: LunarEclipseType = "total"
    elif maximum_geometry.umbral_magnitude > 0.0:
        eclipse_type = "partial"
    else:
        eclipse_type = "penumbral"

    def penumbral_external_coarse(jd: float) -> float:
        geometry = geometry_at(jd)
        if not geometry.behind_earth:
            return math.inf
        return geometry.penumbral_signed_distance_rad - geometry.moon_angular_radius_rad

    def penumbral_external_exact(jd: float) -> float:
        geometry = geometry_at(jd, exact_contacts=True)
        if not geometry.behind_earth:
            return math.inf
        return geometry.penumbral_signed_distance_rad - geometry.moon_angular_radius_rad

    def umbral_external_coarse(jd: float) -> float:
        geometry = geometry_at(jd)
        if not geometry.behind_earth:
            return math.inf
        return geometry.umbral_signed_distance_rad - geometry.moon_angular_radius_rad

    def umbral_external_exact(jd: float) -> float:
        geometry = geometry_at(jd, exact_contacts=True)
        if not geometry.behind_earth:
            return math.inf
        return geometry.umbral_signed_distance_rad - geometry.moon_angular_radius_rad

    def umbral_internal_coarse(jd: float) -> float:
        geometry = geometry_at(jd)
        if not geometry.behind_earth:
            return math.inf
        return geometry.umbral_signed_distance_rad + geometry.moon_angular_radius_rad

    def umbral_internal_exact(jd: float) -> float:
        geometry = geometry_at(jd, exact_contacts=True)
        if not geometry.behind_earth:
            return math.inf
        return geometry.umbral_signed_distance_rad + geometry.moon_angular_radius_rad

    contact_options = {
        "half_window_hours": contact_search_half_window_hours,
        "step_seconds": contact_step_seconds,
        "tolerance_seconds": contact_tolerance_seconds,
    }
    p1 = _contact_on_side(
        penumbral_external_coarse, penumbral_external_exact, maximum_jd, -1, **contact_options
    )
    p4 = _contact_on_side(
        penumbral_external_coarse, penumbral_external_exact, maximum_jd, 1, **contact_options
    )
    u1 = u4 = u2 = u3 = None
    if maximum_geometry.umbral_magnitude > 0.0:
        u1 = _contact_on_side(
            umbral_external_coarse, umbral_external_exact, maximum_jd, -1, **contact_options
        )
        u4 = _contact_on_side(
            umbral_external_coarse, umbral_external_exact, maximum_jd, 1, **contact_options
        )
    if maximum_geometry.umbral_magnitude >= 1.0:
        u2 = _contact_on_side(
            umbral_internal_coarse, umbral_internal_exact, maximum_jd, -1, **contact_options
        )
        u3 = _contact_on_side(
            umbral_internal_coarse, umbral_internal_exact, maximum_jd, 1, **contact_options
        )

    contacts = LunarEclipseContacts(
        p1=time_from_tt_jd(p1) if p1 is not None else None,
        u1=time_from_tt_jd(u1) if u1 is not None else None,
        u2=time_from_tt_jd(u2) if u2 is not None else None,
        greatest=time_from_tt_jd(maximum_jd),
        u3=time_from_tt_jd(u3) if u3 is not None else None,
        u4=time_from_tt_jd(u4) if u4 is not None else None,
        p4=time_from_tt_jd(p4) if p4 is not None else None,
    )
    return LunarEclipseResult(
        eclipse_type=eclipse_type,
        maximum=time_from_tt_jd(maximum_jd),
        contacts=contacts,
        penumbral_magnitude=maximum_geometry.penumbral_magnitude,
        umbral_magnitude=maximum_geometry.umbral_magnitude,
        axis_distance_km=maximum_geometry.axis_distance_km,
        axis_distance_deg=maximum_geometry.axis_distance_deg,
        umbra_radius_km=maximum_geometry.umbra_radius_km,
        penumbra_radius_km=maximum_geometry.penumbra_radius_km,
        moon_distance_km=maximum_geometry.moon_distance_km,
        sun_distance_km=maximum_geometry.sun_distance_km,
        moon_radius_km=moon_radius_km,
        earth_radius_km=earth_radius_km,
        sun_radius_km=sun_radius_km,
        shadow_enlargement=shadow_enlargement,
        calendar=calendar,
        shadow_model=shadow_model,
        atmospheric_nel_height_km=atmospheric_nel_height_km,
        flattening_coefficient=flattening_coefficient,
        earth_radius_factor=maximum_geometry.earth_radius_factor,
        shadow_axis_distance_deg=math.degrees(maximum_geometry.shadow_axis_distance_rad),
        umbra_radius_deg=math.degrees(maximum_geometry.umbra_radius_rad),
        penumbra_radius_deg=math.degrees(maximum_geometry.penumbra_radius_rad),
        solar_declination_deg=math.degrees(maximum_geometry.solar_declination_rad),
        shadow_position_angle_deg=math.degrees(maximum_geometry.shadow_position_angle_rad),
    )
