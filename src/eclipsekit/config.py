"""Public, validated configuration objects for EclipseKit.

The configuration layer keeps numerical assumptions visible and reproducible.
It deliberately contains no Skyfield imports and performs no I/O at import time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Mapping

from .earth_orientation import EarthOrientationConfig
from .geometry import (
    MOON_RADIUS_PEAKS_KM,
    MOON_RADIUS_VALLEYS_KM,
    MOON_RADIUS_VISUAL_KM,
    MOON_RADIUS_XAVIER_KM,
    SUN_RADIUS_KM,
)

IAU_MEAN_MOON_RADIUS_KM = 1737.4


@dataclass(frozen=True, slots=True)
class EphemerisConfig:
    """Select the planetary ephemeris and its time-scale source.

    ``kernel`` can be a JPL kernel name, local BSP path, HTTP(S) URL, or an
    already-open Skyfield ephemeris object. A ``timescale`` can be supplied for
    advanced integrations; it cannot be combined with ``earth_orientation``.
    """

    kernel: Any = "de440s"
    cache_dir: Path | str | None = None
    earth_orientation: EarthOrientationConfig | None = field(
        default_factory=EarthOrientationConfig.builtin
    )
    timescale: Any | None = None
    body_names: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if self.kernel is None:
            raise ValueError("ephemeris kernel/source cannot be None")
        if self.cache_dir is not None:
            object.__setattr__(self, "cache_dir", Path(self.cache_dir).expanduser())
        if self.timescale is not None and self.earth_orientation is not None:
            raise ValueError(
                "Pass either EphemerisConfig.timescale or earth_orientation, not both"
            )
        if self.body_names is not None:
            allowed = {"earth", "sun", "moon"}
            unknown = set(self.body_names) - allowed
            if unknown:
                raise ValueError(
                    "body_names keys must be drawn from 'earth', 'sun', 'moon'; "
                    f"unknown: {sorted(unknown)}"
                )
            if any(not str(value).strip() for value in self.body_names.values()):
                raise ValueError("body_names values must be non-empty strings")
            object.__setattr__(self, "body_names", MappingProxyType(dict(self.body_names)))

    @classmethod
    def jpl(
        cls,
        kernel: str = "de440s",
        *,
        cache_dir: Path | str | None = None,
        earth_orientation: EarthOrientationConfig | None = None,
    ) -> "EphemerisConfig":
        return cls(
            kernel=kernel,
            cache_dir=cache_dir,
            earth_orientation=earth_orientation or EarthOrientationConfig.builtin(),
        )

    @classmethod
    def local(
        cls,
        path: Path | str,
        *,
        cache_dir: Path | str | None = None,
        earth_orientation: EarthOrientationConfig | None = None,
    ) -> "EphemerisConfig":
        return cls(
            kernel=Path(path).expanduser(),
            cache_dir=cache_dir,
            earth_orientation=earth_orientation or EarthOrientationConfig.builtin(),
        )


@dataclass(frozen=True, slots=True)
class ContactModelConfig:
    """Physical radii used by the current spherical-disc contact model.

    The labels ``external`` and ``internal`` are explicit because the engine
    uses separate adopted lunar radii for C1/C4 and C2/C3. This is still a
    spherical-radius model; DEM/Watts/LOLA limb profiles are configured in the
    later lunar-limb framework rather than being implied by these values.
    """

    sun_radius_km: float = SUN_RADIUS_KM
    moon_radius_external_km: float = MOON_RADIUS_PEAKS_KM
    moon_radius_internal_km: float = MOON_RADIUS_VALLEYS_KM
    moon_radius_visual_km: float = MOON_RADIUS_VISUAL_KM
    moon_radius_shadow_km: float = MOON_RADIUS_XAVIER_KM

    def __post_init__(self) -> None:
        for name in (
            "sun_radius_km",
            "moon_radius_external_km",
            "moon_radius_internal_km",
            "moon_radius_visual_km",
            "moon_radius_shadow_km",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be a finite positive number")
            object.__setattr__(self, name, value)

    @classmethod
    def iau_mean_moon(cls, *, sun_radius_km: float = SUN_RADIUS_KM) -> "ContactModelConfig":
        """Use the IAU adopted mean lunar radius for all four disc contacts.

        This is a conventional spherical-disc setting, not a topographic limb
        correction. The standard project defaults remain available separately.
        """
        return cls(
            sun_radius_km=sun_radius_km,
            moon_radius_external_km=IAU_MEAN_MOON_RADIUS_KM,
            moon_radius_internal_km=IAU_MEAN_MOON_RADIUS_KM,
            moon_radius_visual_km=IAU_MEAN_MOON_RADIUS_KM,
        )


@dataclass(frozen=True, slots=True)
class SolverConfig:
    """Numerical settings for contact roots and eclipse-maximum refinement.

    ``bisection`` remains the compatibility default. ``brent`` enables the
    safeguarded Brent-Dekker implementation. Automatic bracket expansion and
    tangent-contact detection are configurable and are used by the detailed
    public contact solver; the engine's already phase-bounded internal solves
    do not expand outside their physical phase intervals.
    """

    root_method: Literal["bisection", "brent"] = "bisection"
    minimum_method: Literal["golden_section"] = "golden_section"
    root_tolerance_seconds: float = 8.64e-6
    root_value_tolerance_deg: float = 1.0e-10
    root_max_iterations: int = 100
    minimum_tolerance_seconds: float = 0.05
    minimum_max_iterations: int = 100
    coarse_step_minutes: float = 5.0
    auto_expand_bracket: bool = True
    bracket_expansion_factor: float = 1.8
    bracket_max_expansions: int = 8
    bracket_max_span_seconds: float = 21600.0
    bracket_scan_samples: int = 81
    detect_tangent_contacts: bool = True
    tangent_scan_samples: int = 101
    tangent_value_tolerance_deg: float = 1.0e-7

    def __post_init__(self) -> None:
        if self.root_method not in {"bisection", "brent"}:
            raise ValueError("root_method must be 'bisection' or 'brent'")
        if self.minimum_method != "golden_section":
            raise ValueError("minimum_method must be 'golden_section'")
        for name in (
            "root_tolerance_seconds",
            "root_value_tolerance_deg",
            "minimum_tolerance_seconds",
            "coarse_step_minutes",
            "bracket_expansion_factor",
            "bracket_max_span_seconds",
            "tangent_value_tolerance_deg",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
            object.__setattr__(self, name, value)
        if self.bracket_expansion_factor <= 1.0:
            raise ValueError("bracket_expansion_factor must be greater than 1")
        for name in (
            "root_max_iterations", "minimum_max_iterations", "bracket_scan_samples",
            "tangent_scan_samples",
        ):
            value = int(getattr(self, name))
            minimum = 3 if name in {"bracket_scan_samples", "tangent_scan_samples"} else 1
            if value < minimum:
                raise ValueError(f"{name} must be at least {minimum}")
            object.__setattr__(self, name, value)
        expansions = int(self.bracket_max_expansions)
        if expansions < 0:
            raise ValueError("bracket_max_expansions must be >= 0")
        object.__setattr__(self, "bracket_max_expansions", expansions)
        if not isinstance(self.auto_expand_bracket, bool):
            raise ValueError("auto_expand_bracket must be a bool")
        if not isinstance(self.detect_tangent_contacts, bool):
            raise ValueError("detect_tangent_contacts must be a bool")


@dataclass(frozen=True, slots=True)
class AtmosphereConfig:
    """Atmospheric assumptions for apparent altitude/azimuth reporting."""

    refraction_enabled: bool = True
    pressure_mbar: float = 1013.25
    temperature_c: float = 15.0

    def __post_init__(self) -> None:
        pressure = float(self.pressure_mbar)
        temperature = float(self.temperature_c)
        if not math.isfinite(pressure) or pressure < 0:
            raise ValueError("pressure_mbar must be finite and >= 0")
        if not math.isfinite(temperature) or temperature <= -273.15:
            raise ValueError("temperature_c must be finite and above absolute zero")
        object.__setattr__(self, "pressure_mbar", pressure)
        object.__setattr__(self, "temperature_c", temperature)
        if not isinstance(self.refraction_enabled, bool):
            raise ValueError("refraction_enabled must be a bool")
        # The physical station pressure is retained as metadata. When refraction
        # is disabled, EclipseEngine passes zero pressure to Skyfield altaz().


@dataclass(frozen=True, slots=True)
class BesselianConfig:
    """Geodetic and numerical settings for the independent Besselian backend."""

    earth_equatorial_radius_km: float = 6378.1366
    earth_flattening: float = 1.0 / 298.257223563
    search_half_window_hours: float = 2.0
    maximum_tolerance_seconds: float = 0.05
    root_scan_samples: int = 121

    def __post_init__(self) -> None:
        for name in (
            "earth_equatorial_radius_km",
            "earth_flattening",
            "search_half_window_hours",
            "maximum_tolerance_seconds",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
            object.__setattr__(self, name, value)
        if self.earth_flattening >= 1.0:
            raise ValueError("earth_flattening must be smaller than 1")
        if isinstance(self.root_scan_samples, bool) or int(self.root_scan_samples) != self.root_scan_samples:
            raise ValueError("root_scan_samples must be an integer >= 5")
        samples = int(self.root_scan_samples)
        if samples < 5:
            raise ValueError("root_scan_samples must be an integer >= 5")
        object.__setattr__(self, "root_scan_samples", samples)


@dataclass(frozen=True, slots=True)
class EclipseConfig:
    """Top-level immutable configuration for an :class:`EclipseEngine`.

    This object groups ephemerides, Earth orientation, contact radii, numerical
    solver tolerances, and atmospheric assumptions in one inspectable object.
    """

    ephemeris: EphemerisConfig = field(default_factory=EphemerisConfig)
    contacts: ContactModelConfig = field(default_factory=ContactModelConfig)
    solver: SolverConfig = field(default_factory=SolverConfig)
    atmosphere: AtmosphereConfig = field(default_factory=AtmosphereConfig)
    besselian: BesselianConfig = field(default_factory=BesselianConfig)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly summary of the active assumptions."""
        kernel = self.ephemeris.kernel
        if isinstance(kernel, (str, Path)):
            kernel_description = str(kernel)
        else:
            kernel_description = f"<{type(kernel).__name__} object>"
        return {
            "ephemeris": {
                "kernel": kernel_description,
                "cache_dir": str(self.ephemeris.cache_dir) if self.ephemeris.cache_dir else None,
                "earth_orientation": (
                    self.ephemeris.earth_orientation.mode
                    if self.ephemeris.earth_orientation is not None else "explicit_timescale"
                ),
                "fixed_delta_t_seconds": (
                    self.ephemeris.earth_orientation.fixed_delta_t_seconds
                    if self.ephemeris.earth_orientation is not None else None
                ),
                "body_names": dict(self.ephemeris.body_names or {}),
            },
            "contacts": {
                "sun_radius_km": self.contacts.sun_radius_km,
                "moon_radius_external_km": self.contacts.moon_radius_external_km,
                "moon_radius_internal_km": self.contacts.moon_radius_internal_km,
                "moon_radius_visual_km": self.contacts.moon_radius_visual_km,
                "moon_radius_shadow_km": self.contacts.moon_radius_shadow_km,
                "geometry": "spherical_discs",
            },
            "solver": {
                "root_method": self.solver.root_method,
                "minimum_method": self.solver.minimum_method,
                "root_tolerance_seconds": self.solver.root_tolerance_seconds,
                "root_value_tolerance_deg": self.solver.root_value_tolerance_deg,
                "root_max_iterations": self.solver.root_max_iterations,
                "minimum_tolerance_seconds": self.solver.minimum_tolerance_seconds,
                "minimum_max_iterations": self.solver.minimum_max_iterations,
                "coarse_step_minutes": self.solver.coarse_step_minutes,
                "auto_expand_bracket": self.solver.auto_expand_bracket,
                "bracket_expansion_factor": self.solver.bracket_expansion_factor,
                "bracket_max_expansions": self.solver.bracket_max_expansions,
                "bracket_max_span_seconds": self.solver.bracket_max_span_seconds,
                "bracket_scan_samples": self.solver.bracket_scan_samples,
                "detect_tangent_contacts": self.solver.detect_tangent_contacts,
                "tangent_scan_samples": self.solver.tangent_scan_samples,
                "tangent_value_tolerance_deg": self.solver.tangent_value_tolerance_deg,
            },
            "atmosphere": {
                "refraction_enabled": self.atmosphere.refraction_enabled,
                "pressure_mbar": self.atmosphere.pressure_mbar,
                "temperature_c": self.atmosphere.temperature_c,
            },
            "besselian": {
                "earth_equatorial_radius_km": self.besselian.earth_equatorial_radius_km,
                "earth_flattening": self.besselian.earth_flattening,
                "search_half_window_hours": self.besselian.search_half_window_hours,
                "maximum_tolerance_seconds": self.besselian.maximum_tolerance_seconds,
                "root_scan_samples": self.besselian.root_scan_samples,
            },
        }
