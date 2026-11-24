"""Public value objects used by EclipseKit."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Any

from .contacts import RootResult


@dataclass(frozen=True, slots=True)
class Observer:
    """A ground observer. Longitude is east-positive; elevation is metres above sea level."""

    latitude: float
    longitude: float
    elevation_m: float = 0.0
    name: str | None = None
    country: str | None = None

    def __post_init__(self) -> None:
        if not -90.0 <= self.latitude <= 90.0:
            raise ValueError("latitude must be between -90 and +90 degrees")
        if not -180.0 <= self.longitude <= 180.0:
            raise ValueError("longitude must be between -180 and +180 degrees")
        if self.elevation_m < -12000 or self.elevation_m > 100000:
            raise ValueError("elevation_m is outside a plausible range")

    def to_skyfield(self, earth: Any) -> Any:
        try:
            from skyfield.api import wgs84
        except ImportError as exc:  # pragma: no cover - depends on optional install
            raise ImportError("Install EclipseKit with its core dependencies: pip install eclipsekit") from exc
        return earth + wgs84.latlon(
            latitude_degrees=self.latitude,
            longitude_degrees=self.longitude,
            elevation_m=self.elevation_m,
        )


@dataclass(slots=True)
class ContactTimes:
    c1: Any | None = None
    c2: Any | None = None
    c3: Any | None = None
    c4: Any | None = None

    def as_dict(self) -> dict[str, Any | None]:
        return {"C1": self.c1, "C2": self.c2, "C3": self.c3, "C4": self.c4}


@dataclass(slots=True)
class LimbContact:
    contact: str
    time: Any | None
    delta_seconds: float | None
    selenographic_latitude_deg: float
    selenographic_longitude_deg: float
    predicted_terrain_altitude_m: float
    corrected_moon_radius_km: float
    limb_angle_deg: float
    model_name: str | None = None
    model_type: str | None = None
    model_source: str | None = None
    altitude_uncertainty_m: float | None = None
    prediction_status: str = "ok"


@dataclass(frozen=True, slots=True)
class HorizonProfile:
    """Azimuth-dependent local horizon mask in degrees above the astronomical horizon.

    ``points`` are ``(azimuth_deg, altitude_deg)`` pairs. Azimuths are normalized
    to [0, 360) and linearly interpolated across the 0/360 seam. The profile is
    supplied by the caller; EclipseKit does not infer terrain obstructions.
    """

    points: tuple[tuple[float, float], ...]
    name: str = "custom"

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("horizon profile name must be a non-empty string")
        try:
            raw_points = tuple(self.points)
        except TypeError as exc:
            raise TypeError("horizon points must be an iterable of (azimuth, altitude) pairs") from exc
        if len(raw_points) < 2:
            raise ValueError("horizon profile requires at least two points")
        normalized: list[tuple[float, float]] = []
        for point in raw_points:
            try:
                if isinstance(point, (str, bytes)) or len(point) != 2:
                    raise ValueError("each horizon point must contain azimuth and altitude")
                azimuth, altitude = point
            except TypeError as exc:
                raise ValueError("each horizon point must contain azimuth and altitude") from exc
            if isinstance(azimuth, bool) or isinstance(altitude, bool):
                raise ValueError("horizon coordinates must be numeric, not boolean")
            try:
                azimuth_value, altitude_value = float(azimuth), float(altitude)
            except (TypeError, ValueError) as exc:
                raise ValueError("horizon coordinates must be numeric") from exc
            if not math.isfinite(azimuth_value) or not math.isfinite(altitude_value):
                raise ValueError("horizon coordinates must be finite")
            if not -10.0 <= altitude_value <= 90.0:
                raise ValueError("horizon altitude must be within [-10, 90] degrees")
            normalized.append((azimuth_value % 360.0, altitude_value))
        normalized.sort(key=lambda item: item[0])
        azimuths = [item[0] for item in normalized]
        if any(abs(right - left) <= 1e-12 for left, right in zip(azimuths, azimuths[1:])):
            raise ValueError("horizon profile azimuths must be unique modulo 360 degrees")
        object.__setattr__(self, "points", tuple(normalized))
        object.__setattr__(self, "name", self.name.strip())

    @classmethod
    def flat(cls, altitude_deg: float = 0.0, *, name: str = "flat") -> "HorizonProfile":
        """Create a constant-altitude horizon profile."""
        return cls(((0.0, altitude_deg), (180.0, altitude_deg)), name=name)

    def altitude_at(self, azimuth_deg: float) -> float:
        """Linearly interpolate the horizon altitude at an azimuth in degrees."""
        if isinstance(azimuth_deg, bool):
            raise ValueError("azimuth must be finite and numeric")
        try:
            azimuth = float(azimuth_deg)
        except (TypeError, ValueError) as exc:
            raise ValueError("azimuth must be finite and numeric") from exc
        if not math.isfinite(azimuth):
            raise ValueError("azimuth must be finite and numeric")
        azimuth %= 360.0
        points = self.points
        azimuths = [point[0] for point in points]
        right_index = next((i for i, value in enumerate(azimuths) if value >= azimuth), None)
        if right_index is None:
            left_az, left_alt = points[-1]
            right_az, right_alt = points[0][0] + 360.0, points[0][1]
            query = azimuth if azimuth >= left_az else azimuth + 360.0
        elif right_index == 0:
            left_az, left_alt = points[-1][0] - 360.0, points[-1][1]
            right_az, right_alt = points[0]
            query = azimuth
        else:
            left_az, left_alt = points[right_index - 1]
            right_az, right_alt = points[right_index]
            query = azimuth
        if abs(query - right_az) <= 1e-12:
            return float(right_alt)
        fraction = (query - left_az) / (right_az - left_az)
        return float(left_alt + fraction * (right_alt - left_alt))


@dataclass(frozen=True, slots=True)
class ObservationGeometry:
    """Topocentric Sun/Moon geometry and horizon-aware visibility at one instant."""

    observer: Observer
    time: Any
    sun_altitude_deg: float
    sun_azimuth_deg: float
    moon_altitude_deg: float
    moon_azimuth_deg: float
    separation_deg: float
    sun_angular_radius_deg: float
    moon_angular_radius_deg: float
    position_angle_deg: float | None
    parallactic_angle_deg: float | None
    vertex_angle_deg: float | None
    magnitude: float
    obscuration_percent: float
    horizon_altitude_deg: float
    sun_center_clearance_deg: float
    sun_upper_limb_clearance_deg: float
    sun_lower_limb_clearance_deg: float
    visibility_status: str
    horizon_profile_name: str | None = None
    refraction_applied: bool = False

    def __post_init__(self) -> None:
        numeric_fields = (
            "sun_altitude_deg", "sun_azimuth_deg", "moon_altitude_deg", "moon_azimuth_deg",
            "separation_deg", "sun_angular_radius_deg", "moon_angular_radius_deg",
            "magnitude", "obscuration_percent", "horizon_altitude_deg",
            "sun_center_clearance_deg", "sun_upper_limb_clearance_deg",
            "sun_lower_limb_clearance_deg",
        )
        for name in numeric_fields:
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite")
        for name in ("position_angle_deg", "parallactic_angle_deg", "vertex_angle_deg"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not math.isfinite(float(value))):
                raise ValueError(f"{name} must be finite when supplied")
        if self.visibility_status not in {"visible", "partially_obstructed", "obstructed"}:
            raise ValueError("unsupported observation visibility status")
        if self.sun_angular_radius_deg <= 0.0 or self.moon_angular_radius_deg <= 0.0:
            raise ValueError("apparent solar and lunar angular radii must be positive")
        if not 0.0 <= self.separation_deg <= 180.0:
            raise ValueError("separation_deg must be within [0, 180]")
        if not 0.0 <= self.obscuration_percent <= 100.0:
            raise ValueError("obscuration_percent must be within [0, 100]")
        if not -90.0 <= self.sun_altitude_deg <= 90.0 or not -90.0 <= self.moon_altitude_deg <= 90.0:
            raise ValueError("apparent altitudes must be within [-90, 90]")
        if not 0.0 <= self.sun_azimuth_deg < 360.0 or not 0.0 <= self.moon_azimuth_deg < 360.0:
            raise ValueError("apparent azimuths must be within [0, 360)")
        if not isinstance(self.refraction_applied, bool):
            raise ValueError("refraction_applied must be a boolean")
        if self.horizon_profile_name is not None and (
            not isinstance(self.horizon_profile_name, str) or not self.horizon_profile_name.strip()
        ):
            raise ValueError("horizon_profile_name must be a non-empty string when supplied")

    def to_dict(self) -> dict[str, Any]:
        from .timeutils import time_to_utc_iso
        return {
            "observer": asdict(self.observer),
            "time_utc": time_to_utc_iso(self.time),
            "sun": {"altitude_deg": self.sun_altitude_deg, "azimuth_deg": self.sun_azimuth_deg,
                    "angular_radius_deg": self.sun_angular_radius_deg},
            "moon": {"altitude_deg": self.moon_altitude_deg, "azimuth_deg": self.moon_azimuth_deg,
                     "angular_radius_deg": self.moon_angular_radius_deg},
            "separation_deg": self.separation_deg,
            "position_angle_deg": self.position_angle_deg,
            "parallactic_angle_deg": self.parallactic_angle_deg,
            "vertex_angle_deg": self.vertex_angle_deg,
            "magnitude": self.magnitude,
            "obscuration_percent": self.obscuration_percent,
            "horizon": {
                "profile_name": self.horizon_profile_name,
                "altitude_deg": self.horizon_altitude_deg,
                "sun_center_clearance_deg": self.sun_center_clearance_deg,
                "sun_upper_limb_clearance_deg": self.sun_upper_limb_clearance_deg,
                "sun_lower_limb_clearance_deg": self.sun_lower_limb_clearance_deg,
                "visibility_status": self.visibility_status,
            },
            "refraction_applied": self.refraction_applied,
        }


@dataclass(slots=True)
class ContactEvent:
    """One topocentric eclipse event (C1-C4 or maximum).

    ``time`` is a Skyfield Time. UTC is the civil display scale; TT and UT1
    Julian Dates are retained explicitly so callers can compare reference
    tables without silently conflating time scales. Contact position angle is
    measured from celestial north through east. Vertex angle is the signed
    position angle relative to the local vertical (zenith), wrapped to
    [-180, 180) degrees.

    ``uncertainty_seconds`` is intentionally ``None`` until a separately
    validated uncertainty model is supplied. Numerical root residuals are
    diagnostics, not estimates of the physical prediction uncertainty.
    """

    name: str
    event_type: str
    time: Any
    separation_deg: float
    sun_angular_radius_deg: float
    moon_angular_radius_deg: float
    position_angle_deg: float | None
    vertex_angle_deg: float | None
    sun_altitude_deg: float
    sun_azimuth_deg: float
    visibility_status: str
    solver_result: RootResult | None = None
    limb_correction: LimbContact | None = None
    uncertainty_seconds: float | None = None
    uncertainty_note: str = "Not quantified by the current model."
    visibility_note: str = (
        "Based on apparent topocentric solar altitude; local terrain and observer-specific "
        "horizon obstructions are not modelled."
    )
    horizon_altitude_deg: float | None = None
    sun_upper_limb_clearance_deg: float | None = None

    def __post_init__(self) -> None:
        if self.name not in {"C1", "C2", "MAXIMUM", "C3", "C4"}:
            raise ValueError("name must be C1, C2, MAXIMUM, C3, or C4")
        if self.event_type not in {"external", "internal", "maximum"}:
            raise ValueError("event_type must be external, internal, or maximum")
        if self.name == "MAXIMUM" and self.event_type != "maximum":
            raise ValueError("MAXIMUM must use event_type='maximum'")
        if self.name in {"C1", "C4"} and self.event_type != "external":
            raise ValueError("C1 and C4 must use event_type='external'")
        if self.name in {"C2", "C3"} and self.event_type != "internal":
            raise ValueError("C2 and C3 must use event_type='internal'")
        if self.uncertainty_seconds is not None:
            value = float(self.uncertainty_seconds)
            if not math.isfinite(value) or value < 0.0:
                raise ValueError("uncertainty_seconds must be finite and >= 0")
            self.uncertainty_seconds = value
        for name in ("horizon_altitude_deg", "sun_upper_limb_clearance_deg"):
            value = getattr(self, name)
            if value is not None:
                if isinstance(value, bool):
                    raise ValueError(f"{name} must be numeric, not boolean")
                number = float(value)
                if not math.isfinite(number):
                    raise ValueError(f"{name} must be finite when supplied")
                setattr(self, name, number)

    @property
    def time_utc(self) -> str:
        from .timeutils import time_to_utc_iso
        return time_to_utc_iso(self.time)

    @property
    def time_tt_jd(self) -> float:
        return float(self.time.tt)

    @property
    def time_ut1_jd(self) -> float:
        return float(self.time.ut1)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-friendly event data with UTC/UT1/TT kept distinct."""
        limb = self.limb_correction
        limb_data = None
        if limb is not None:
            from .timeutils import time_to_utc_iso
            limb_data = {
                "contact": limb.contact,
                "time_utc": time_to_utc_iso(limb.time) if limb.time is not None else None,
                "delta_seconds": limb.delta_seconds,
                "selenographic_latitude_deg": limb.selenographic_latitude_deg,
                "selenographic_longitude_deg": limb.selenographic_longitude_deg,
                "predicted_terrain_altitude_m": limb.predicted_terrain_altitude_m,
                "corrected_moon_radius_km": limb.corrected_moon_radius_km,
                "limb_angle_deg": limb.limb_angle_deg,
                "model_name": limb.model_name,
                "model_type": limb.model_type,
                "model_source": limb.model_source,
                "altitude_uncertainty_m": limb.altitude_uncertainty_m,
                "prediction_status": limb.prediction_status,
            }
        return {
            "name": self.name,
            "event_type": self.event_type,
            "time_utc": self.time_utc,
            "time_tt_jd": self.time_tt_jd,
            "time_ut1_jd": self.time_ut1_jd,
            "geometry": {
                "separation_deg": self.separation_deg,
                "sun_angular_radius_deg": self.sun_angular_radius_deg,
                "moon_angular_radius_deg": self.moon_angular_radius_deg,
                "position_angle_deg": self.position_angle_deg,
                "vertex_angle_deg": self.vertex_angle_deg,
            },
            "sun_altitude_deg": self.sun_altitude_deg,
            "sun_azimuth_deg": self.sun_azimuth_deg,
            "visibility_status": self.visibility_status,
            "visibility_note": self.visibility_note,
            "horizon_altitude_deg": self.horizon_altitude_deg,
            "sun_upper_limb_clearance_deg": self.sun_upper_limb_clearance_deg,
            "solver": self.solver_result.to_dict() if self.solver_result is not None else None,
            "limb_correction": limb_data,
            "uncertainty_seconds": self.uncertainty_seconds,
            "uncertainty_note": self.uncertainty_note,
        }


@dataclass(slots=True)
class LocalEclipseResult:
    observer: Observer
    eclipse_type: str
    maximum: Any
    contacts: ContactTimes
    magnitude: float
    obscuration_percent: float
    moon_sun_radius_ratio: float
    separation_deg: float
    sun_altitude_deg: float
    sun_azimuth_deg: float
    duration_seconds: float | None
    partial_phase_duration_seconds: float | None = None
    limb_corrected_contacts: dict[str, LimbContact] = field(default_factory=dict)
    limb_corrected_duration_seconds: float | None = None
    limb_corrected_maximum: Any | None = None
    shadow_velocity_km_s: float | None = None
    shadow_path_width_km: float | None = None
    umbral_depth_km: float | None = None
    umbral_depth_fraction: float | None = None
    sunrise: Any | None = None
    sunset: Any | None = None
    approximate_zodiac_sector: str | None = None
    visible_planets: list[tuple[str, float]] = field(default_factory=list)
    is_next_upcoming: bool = False
    warnings: list[str] = field(default_factory=list)
    contact_events: dict[str, ContactEvent] = field(default_factory=dict)
    central_phase_duration_seconds: float | None = None
    observation_geometry: ObservationGeometry | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-friendly values; times are UTC ISO strings."""
        from .timeutils import time_to_utc_iso

        return {
            "observer": asdict(self.observer),
            "eclipse_type": self.eclipse_type,
            "maximum_utc": time_to_utc_iso(self.maximum),
            "contacts_utc": {
                name: time_to_utc_iso(value) if value is not None else None
                for name, value in self.contacts.as_dict().items()
            },
            "magnitude": self.magnitude,
            "obscuration_percent": self.obscuration_percent,
            "moon_sun_radius_ratio": self.moon_sun_radius_ratio,
            "separation_deg": self.separation_deg,
            "sun_altitude_deg": self.sun_altitude_deg,
            "sun_azimuth_deg": self.sun_azimuth_deg,
            # ``duration_seconds`` retains the 0.1.x compatibility convention
            # (0.0 for partial-only events). The explicit field is None when no
            # central phase exists.
            "duration_seconds": self.duration_seconds,
            "central_phase_duration_seconds": self.central_phase_duration_seconds,
            "partial_phase_duration_seconds": self.partial_phase_duration_seconds,
            "contact_events": {
                name: event.to_dict() for name, event in self.contact_events.items()
            },
            "observation_geometry": (
                self.observation_geometry.to_dict() if self.observation_geometry is not None else None
            ),
            "limb_corrected_contacts": {
                key: {
                    "time_utc": time_to_utc_iso(value.time) if value.time is not None else None,
                    "delta_seconds": value.delta_seconds,
                    "selenographic_latitude_deg": value.selenographic_latitude_deg,
                    "selenographic_longitude_deg": value.selenographic_longitude_deg,
                    "predicted_terrain_altitude_m": value.predicted_terrain_altitude_m,
                    "corrected_moon_radius_km": value.corrected_moon_radius_km,
                    "limb_angle_deg": value.limb_angle_deg,
                    "model_name": value.model_name,
                    "model_type": value.model_type,
                    "model_source": value.model_source,
                    "altitude_uncertainty_m": value.altitude_uncertainty_m,
                    "prediction_status": value.prediction_status,
                }
                for key, value in self.limb_corrected_contacts.items()
            },
            "limb_corrected_duration_seconds": self.limb_corrected_duration_seconds,
            "limb_corrected_maximum_utc": (
                time_to_utc_iso(self.limb_corrected_maximum)
                if self.limb_corrected_maximum is not None else None
            ),
            "shadow_velocity_km_s": self.shadow_velocity_km_s,
            "shadow_path_width_km": self.shadow_path_width_km,
            "umbral_depth_km": self.umbral_depth_km,
            "umbral_depth_fraction": self.umbral_depth_fraction,
            "sunrise_utc": time_to_utc_iso(self.sunrise) if self.sunrise is not None else None,
            "sunset_utc": time_to_utc_iso(self.sunset) if self.sunset is not None else None,
            "approximate_zodiac_sector": self.approximate_zodiac_sector,
            "visible_planets": [list(item) for item in self.visible_planets],
            "is_next_upcoming": self.is_next_upcoming,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class City:
    name: str
    country: str
    latitude: float
    longitude: float
    elevation_m: float = 0.0


@dataclass(slots=True)
class CityEclipseHit:
    city: City
    maximum: Any
    magnitude: float
    obscuration_percent: float
    eclipse_type: str
    sun_altitude_deg: float
    offset_from_geocentric_maximum_minutes: float
    contacts: ContactTimes | None = None
    limb_corrected_contacts: dict[str, LimbContact] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from .timeutils import time_to_utc_iso

        return {
            "city": asdict(self.city),
            "maximum_utc": time_to_utc_iso(self.maximum),
            "magnitude": self.magnitude,
            "obscuration_percent": self.obscuration_percent,
            "eclipse_type": self.eclipse_type,
            "sun_altitude_deg": self.sun_altitude_deg,
            "offset_from_geocentric_maximum_minutes": self.offset_from_geocentric_maximum_minutes,
            "contacts_utc": (
                {k: time_to_utc_iso(v) if v is not None else None for k, v in self.contacts.as_dict().items()}
                if self.contacts else None
            ),
            "limb_corrected_contacts": {
                key: {
                    "time_utc": time_to_utc_iso(value.time) if value.time is not None else None,
                    "delta_seconds": value.delta_seconds,
                    "selenographic_latitude_deg": value.selenographic_latitude_deg,
                    "selenographic_longitude_deg": value.selenographic_longitude_deg,
                    "predicted_terrain_altitude_m": value.predicted_terrain_altitude_m,
                    "corrected_moon_radius_km": value.corrected_moon_radius_km,
                    "limb_angle_deg": value.limb_angle_deg,
                    "model_name": value.model_name,
                    "model_type": value.model_type,
                    "model_source": value.model_source,
                    "altitude_uncertainty_m": value.altitude_uncertainty_m,
                    "prediction_status": value.prediction_status,
                }
                for key, value in self.limb_corrected_contacts.items()
            },
        }


@dataclass(slots=True)
class CountryEclipseEvent:
    geocentric_maximum: Any
    country: str
    city_hits: list[CityEclipseHit]

    def to_dict(self) -> dict[str, Any]:
        from .timeutils import time_to_utc_iso
        return {
            "country": self.country,
            "geocentric_maximum_utc": time_to_utc_iso(self.geocentric_maximum),
            "cities_affected": len(self.city_hits),
            "cities": [hit.to_dict() for hit in self.city_hits],
        }


@dataclass(slots=True)
class SolarEclipseLocationHit:
    """Local eclipse circumstances for one observer in a searched event."""

    observer: Observer
    local_result: LocalEclipseResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "observer": asdict(self.observer),
            "local_circumstances": self.local_result.to_dict(),
        }


@dataclass(slots=True)
class SolarEclipseSearchEvent:
    """One new-moon eclipse candidate with all requested observers that see it."""

    geocentric_maximum: Any
    locations: list[SolarEclipseLocationHit]

    @property
    def maximum_magnitude(self) -> float:
        return max((hit.local_result.magnitude for hit in self.locations), default=0.0)

    def to_dict(self) -> dict[str, Any]:
        from .timeutils import time_to_utc_iso
        return {
            "geocentric_maximum_utc": time_to_utc_iso(self.geocentric_maximum),
            "locations_affected": len(self.locations),
            "maximum_local_magnitude": self.maximum_magnitude,
            "locations": [hit.to_dict() for hit in self.locations],
        }


@dataclass(slots=True)
class SolarEclipseSearchResult:
    """Summary of a bounded solar-eclipse search across multiple observers."""

    start_utc: str
    end_utc: str
    locations_requested: int
    new_moons_examined: int
    events: list[SolarEclipseSearchEvent]

    @property
    def event_count(self) -> int:
        return len(self.events)

    @property
    def location_event_count(self) -> int:
        return sum(len(event.locations) for event in self.events)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_utc": self.start_utc,
            "end_utc": self.end_utc,
            "locations_requested": self.locations_requested,
            "new_moons_examined": self.new_moons_examined,
            "events_found": self.event_count,
            "location_events_found": self.location_event_count,
            "events": [event.to_dict() for event in self.events],
        }


@dataclass(frozen=True, slots=True)
class ShadowPathPoint:
    time: Any
    latitude: float
    longitude: float
    width_km: float
    shadow_kind: str


@dataclass(frozen=True, slots=True)
class ShadowFootprint:
    """Instantaneous spherical shadow-cone intersections with the WGS84 ellipsoid."""

    time: Any
    axis_latitude: float | None
    axis_longitude: float | None
    shadow_kind: str
    cone_radius_km: float | None
    central_boundary: tuple[ShadowCorridorEdge | None, ...]
    penumbra_boundary: tuple[ShadowCorridorEdge | None, ...]
    track_bearing_deg: float | None
    shadow_velocity_km_s: float | None
    cross_track_width_km: float | None
    central_boundary_coverage: float
    penumbra_boundary_coverage: float
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.shadow_kind not in {"umbral", "antumbral", "axis_misses_earth"}:
            raise ValueError("unsupported shadow_kind")
        central_boundary = tuple(self.central_boundary)
        penumbra_boundary = tuple(self.penumbra_boundary)
        if len(central_boundary) < 8 or len(penumbra_boundary) < 8:
            raise ValueError("shadow boundaries must retain at least eight angular samples")
        if len(central_boundary) != len(penumbra_boundary):
            raise ValueError("central and penumbral boundaries must use the same angular sample count")
        if any(point is not None and not isinstance(point, ShadowCorridorEdge)
               for point in central_boundary + penumbra_boundary):
            raise TypeError("shadow boundary samples must be ShadowCorridorEdge or None")
        object.__setattr__(self, "central_boundary", central_boundary)
        object.__setattr__(self, "penumbra_boundary", penumbra_boundary)
        for name in ("central_boundary_coverage", "penumbra_boundary_coverage"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be a finite fraction in [0, 1]")
            object.__setattr__(self, name, value)
        optional_nonnegative = ("shadow_velocity_km_s", "cross_track_width_km")
        for name in optional_nonnegative:
            value = getattr(self, name)
            if value is not None:
                if isinstance(value, bool):
                    raise ValueError(f"{name} must be numeric, not boolean")
                number = float(value)
                if not math.isfinite(number) or number < 0.0:
                    raise ValueError(f"{name} must be finite and non-negative")
                object.__setattr__(self, name, number)
        if self.track_bearing_deg is not None:
            if isinstance(self.track_bearing_deg, bool):
                raise ValueError("track_bearing_deg must be numeric, not boolean")
            bearing = float(self.track_bearing_deg)
            if not math.isfinite(bearing) or not 0.0 <= bearing < 360.0:
                raise ValueError("track_bearing_deg must be within [0, 360)")
            object.__setattr__(self, "track_bearing_deg", bearing)
        if self.cone_radius_km is not None:
            radius = float(self.cone_radius_km)
            if not math.isfinite(radius):
                raise ValueError("cone_radius_km must be finite when supplied")
            object.__setattr__(self, "cone_radius_km", radius)
        if (self.axis_latitude is None) != (self.axis_longitude is None):
            raise ValueError("axis latitude and longitude must both be set or both be None")
        if self.axis_latitude is not None:
            if isinstance(self.axis_latitude, bool) or isinstance(self.axis_longitude, bool):
                raise ValueError("axis coordinates must be numeric, not boolean")
            latitude, longitude = float(self.axis_latitude), float(self.axis_longitude)
            if not math.isfinite(latitude) or not -90.0 <= latitude <= 90.0:
                raise ValueError("axis_latitude must be finite and within [-90, 90]")
            if not math.isfinite(longitude) or not -180.0 <= longitude <= 180.0:
                raise ValueError("axis_longitude must be finite and within [-180, 180]")
            object.__setattr__(self, "axis_latitude", latitude)
            object.__setattr__(self, "axis_longitude", longitude)
        if self.shadow_kind == "axis_misses_earth" and self.axis_latitude is not None:
            raise ValueError("axis_misses_earth must not include an axis intersection")
        if self.shadow_kind != "axis_misses_earth" and self.axis_latitude is None:
            raise ValueError("umbral and antumbral footprints require an axis intersection")
        if any(not isinstance(note, str) or not note.strip() for note in self.notes):
            raise ValueError("shadow footprint notes must be non-empty strings")
        object.__setattr__(self, "notes", tuple(self.notes))

    def to_dict(self) -> dict[str, Any]:
        from .timeutils import time_to_utc_iso

        def boundary_to_dict(boundary: tuple["ShadowCorridorEdge | None", ...]):
            return [point.to_dict() if point is not None else None for point in boundary]

        return {
            "time_utc": time_to_utc_iso(self.time),
            "axis": (
                {"latitude": self.axis_latitude, "longitude": self.axis_longitude}
                if self.axis_latitude is not None else None
            ),
            "shadow_kind": self.shadow_kind,
            "cone_radius_km": self.cone_radius_km,
            "central_boundary": boundary_to_dict(self.central_boundary),
            "penumbra_boundary": boundary_to_dict(self.penumbra_boundary),
            "track_bearing_deg": self.track_bearing_deg,
            "shadow_velocity_km_s": self.shadow_velocity_km_s,
            "cross_track_width_km": self.cross_track_width_km,
            "central_boundary_coverage": self.central_boundary_coverage,
            "penumbra_boundary_coverage": self.penumbra_boundary_coverage,
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class ShadowCorridorEdge:
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if isinstance(self.latitude, bool) or isinstance(self.longitude, bool):
            raise ValueError("shadow boundary coordinates must be numeric, not boolean")
        try:
            latitude = float(self.latitude)
            longitude = float(self.longitude)
        except (TypeError, ValueError) as exc:
            raise ValueError("shadow boundary coordinates must be numeric") from exc
        if not math.isfinite(latitude) or not -90.0 <= latitude <= 90.0:
            raise ValueError("shadow boundary latitude must be finite and within [-90, 90]")
        if not math.isfinite(longitude) or not -180.0 <= longitude <= 180.0:
            raise ValueError("shadow boundary longitude must be finite and within [-180, 180]")
        object.__setattr__(self, "latitude", latitude)
        object.__setattr__(self, "longitude", longitude)

    def to_dict(self) -> dict[str, float]:
        return {"latitude": float(self.latitude), "longitude": float(self.longitude)}


@dataclass(frozen=True, slots=True)
class ShadowCorridorSample:
    """One cross-section; left/right are relative to central-track direction."""
    time: Any
    center: ShadowPathPoint
    central_left: ShadowCorridorEdge | None
    central_right: ShadowCorridorEdge | None
    penumbra_left: ShadowCorridorEdge | None
    penumbra_right: ShadowCorridorEdge | None
    central_width_km: float | None
    penumbral_width_km: float | None
    shadow_velocity_km_s: float | None
    central_phase_duration_estimate_seconds: float | None
    penumbral_duration_estimate_seconds: float | None
    track_bearing_deg: float | None
    central_boundary_coverage: float
    penumbra_boundary_coverage: float
    central_track_chord_km: float | None = None
    penumbral_track_chord_km: float | None = None

    def __post_init__(self) -> None:
        optional_nonnegative = (
            "central_width_km", "penumbral_width_km", "shadow_velocity_km_s",
            "central_phase_duration_estimate_seconds", "penumbral_duration_estimate_seconds",
            "central_track_chord_km", "penumbral_track_chord_km",
        )
        for name in optional_nonnegative:
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool):
                raise ValueError(f"{name} must be a finite non-negative number")
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be a finite non-negative number") from exc
            if not math.isfinite(number) or number < 0.0:
                raise ValueError(f"{name} must be a finite non-negative number")
            object.__setattr__(self, name, number)

        for name in ("central_boundary_coverage", "penumbra_boundary_coverage"):
            value = getattr(self, name)
            if isinstance(value, bool):
                raise ValueError(f"{name} must be a finite fraction in [0, 1]")
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be a finite fraction in [0, 1]") from exc
            if not math.isfinite(number) or not 0.0 <= number <= 1.0:
                raise ValueError(f"{name} must be a finite fraction in [0, 1]")
            object.__setattr__(self, name, number)

        if self.track_bearing_deg is not None:
            if isinstance(self.track_bearing_deg, bool):
                raise ValueError("track_bearing_deg must be finite and within [0, 360)")
            bearing = float(self.track_bearing_deg)
            if not math.isfinite(bearing) or not 0.0 <= bearing < 360.0:
                raise ValueError("track_bearing_deg must be finite and within [0, 360)")
            object.__setattr__(self, "track_bearing_deg", bearing)

        if (self.central_width_km is not None
                and (self.central_left is None or self.central_right is None)):
            raise ValueError("central_width_km requires both central boundary edges")
        if (self.penumbral_width_km is not None
                and (self.penumbra_left is None or self.penumbra_right is None)):
            raise ValueError("penumbral_width_km requires both penumbral boundary edges")

    def to_dict(self) -> dict[str, Any]:
        from .timeutils import time_to_utc_iso
        return {
            "time_utc": time_to_utc_iso(self.time),
            "center": {"latitude": self.center.latitude, "longitude": self.center.longitude,
                       "shadow_kind": self.center.shadow_kind},
            "central_left": self.central_left.to_dict() if self.central_left else None,
            "central_right": self.central_right.to_dict() if self.central_right else None,
            "penumbra_left": self.penumbra_left.to_dict() if self.penumbra_left else None,
            "penumbra_right": self.penumbra_right.to_dict() if self.penumbra_right else None,
            "central_width_km": self.central_width_km,
            "penumbral_width_km": self.penumbral_width_km,
            "shadow_velocity_km_s": self.shadow_velocity_km_s,
            "central_phase_duration_estimate_seconds": self.central_phase_duration_estimate_seconds,
            "penumbral_duration_estimate_seconds": self.penumbral_duration_estimate_seconds,
            "central_track_chord_km": self.central_track_chord_km,
            "penumbral_track_chord_km": self.penumbral_track_chord_km,
            "track_bearing_deg": self.track_bearing_deg,
            "central_boundary_coverage": self.central_boundary_coverage,
            "penumbra_boundary_coverage": self.penumbra_boundary_coverage,
        }


@dataclass(frozen=True, slots=True)
class ShadowCorridorResult:
    samples: tuple[ShadowCorridorSample, ...]
    requested_sample_count: int
    boundary_sample_count: int
    geometry_model: str = "spherical Sun/Moon cones intersected with WGS84"
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (isinstance(self.requested_sample_count, bool)
                or not isinstance(self.requested_sample_count, int)
                or self.requested_sample_count < 2):
            raise ValueError("requested_sample_count must be an integer >= 2")
        if (isinstance(self.boundary_sample_count, bool)
                or not isinstance(self.boundary_sample_count, int)
                or self.boundary_sample_count < 16):
            raise ValueError("boundary_sample_count must be an integer >= 16")
        if len(self.samples) > self.requested_sample_count:
            raise ValueError("valid sample count cannot exceed requested_sample_count")
        if not isinstance(self.geometry_model, str) or not self.geometry_model.strip():
            raise ValueError("geometry_model must be a non-empty description")
        if any(not isinstance(note, str) or not note.strip() for note in self.notes):
            raise ValueError("notes must contain only non-empty strings")

    @property
    def central_path(self) -> list[ShadowPathPoint]:
        return [sample.center for sample in self.samples]

    def to_dict(self) -> dict[str, Any]:
        return {
            "geometry_model": self.geometry_model,
            "requested_sample_count": self.requested_sample_count,
            "boundary_sample_count": self.boundary_sample_count,
            "valid_sample_count": len(self.samples),
            "notes": list(self.notes),
            "samples": [sample.to_dict() for sample in self.samples],
        }
