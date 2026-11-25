"""High-level eclipse engine. No simulator sockets, threads, geocoder, or import-time downloads."""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

import numpy as np

from .cities import CityCatalog
from .config import (
    AtmosphereConfig, ContactModelConfig, EclipseConfig, EphemerisConfig, SolverConfig,
)
from .contacts import RootResult, golden_section_minimize, solve_root
from .ephemeris import EphemerisContext
from .earth_orientation import EarthOrientationConfig, describe_time_scale
from .geometry import (
    MOON_RADIUS_PEAKS_KM, MOON_RADIUS_VALLEYS_KM, MOON_RADIUS_VISUAL_KM,
    MOON_RADIUS_XAVIER_KM, SUN_RADIUS_KM, WGS84_A_KM, WGS84_B_KM,
    angular_radius, circle_overlap_fraction, ecef_to_geodetic,
    cone_ellipsoid_intersections, ray_ellipsoid_intersection, wgs84_inverse,
)
from .models import (
    CityEclipseHit, ContactEvent, ContactTimes, CountryEclipseEvent, LimbContact,
    LocalEclipseResult, Observer, ShadowPathPoint, ShadowCorridorEdge,
    ShadowCorridorSample, ShadowCorridorResult, ShadowFootprint, SolarEclipseLocationHit,
    SolarEclipseSearchEvent, SolarEclipseSearchResult, HorizonProfile, ObservationGeometry,
)
from .timeutils import coerce_time, time_to_utc_iso
from .lunar_eclipse import MEAN_MOON_RADIUS_KM, LunarEclipseResult, solve_lunar_eclipse


def _evaluate_city_search_batch(
    batch_indices: np.ndarray,
    catalog_ecef: np.ndarray,
    catalog_up: np.ndarray,
    sun_nodes: np.ndarray,
    moon_nodes: np.ndarray,
    hours: np.ndarray,
    *,
    min_magnitude: float,
    refinement_iterations: int,
    search_radius_hours: float,
    sun_radius_km: float,
    moon_radius_km: float,
) -> list[tuple[int, float, float, float, float, float, float]]:
    """Evaluate one immutable NumPy city batch; safe to run in a worker thread.

    Returned rows contain (catalogue index, offset hours, magnitude, separation,
    solar radius, lunar radius, solar altitude). Skyfield objects and local-contact
    solvers are deliberately excluded from this pure array workload.
    """
    if len(batch_indices) == 0:
        return []
    positions = catalog_ecef[batch_indices]
    up = catalog_up[batch_indices]
    to_sun = sun_nodes[np.newaxis, :, :] - positions[:, np.newaxis, :]
    to_moon = moon_nodes[np.newaxis, :, :] - positions[:, np.newaxis, :]
    d_sun = np.linalg.norm(to_sun, axis=2)
    d_moon = np.linalg.norm(to_moon, axis=2)
    u_sun = to_sun / d_sun[:, :, np.newaxis]
    u_moon = to_moon / d_moon[:, :, np.newaxis]
    dot = np.clip(np.sum(u_sun * u_moon, axis=2), -1.0, 1.0)
    cross_norm = np.linalg.norm(np.cross(u_sun, u_moon), axis=2)
    separation = np.degrees(np.arctan2(cross_norm, dot))
    r_sun = np.degrees(np.arcsin(np.clip(sun_radius_km / d_sun, -1.0, 1.0)))
    r_moon = np.degrees(np.arcsin(np.clip(moon_radius_km / d_moon, -1.0, 1.0)))
    sun_alt_sine = np.sum(u_sun * up[:, np.newaxis, :], axis=2)
    raw_magnitude = (r_moon + r_sun - separation) / (2.0 * r_sun)
    coarse_mag = np.where(
        (sun_alt_sine > math.sin(math.radians(-0.833)))
        & (separation < r_moon + r_sun),
        raw_magnitude,
        0.0,
    )
    best_indices = np.argmax(coarse_mag, axis=1)
    best_mag = coarse_mag[np.arange(len(batch_indices)), best_indices]
    candidate_rows = np.flatnonzero(best_mag > min_magnitude)
    if len(candidate_rows) == 0:
        return []

    candidate_indices = batch_indices[candidate_rows]
    candidate_positions = positions[candidate_rows]
    candidate_up = up[candidate_rows]
    coarse_at = hours[best_indices[candidate_rows]]
    step_hours = float(hours[1] - hours[0])
    left = np.maximum(coarse_at - step_hours, -search_radius_hours)
    right = np.minimum(coarse_at + step_hours, search_radius_hours)

    def interpolate_nodes(query: np.ndarray, nodes: np.ndarray) -> np.ndarray:
        return np.column_stack(
            [np.interp(query, hours, nodes[:, axis]) for axis in range(3)]
        )

    def evaluate(dt_hours: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        sun_positions = interpolate_nodes(dt_hours, sun_nodes)
        moon_positions = interpolate_nodes(dt_hours, moon_nodes)
        to_sun_local = sun_positions - candidate_positions
        to_moon_local = moon_positions - candidate_positions
        distance_sun = np.linalg.norm(to_sun_local, axis=1)
        distance_moon = np.linalg.norm(to_moon_local, axis=1)
        unit_sun = to_sun_local / distance_sun[:, None]
        unit_moon = to_moon_local / distance_moon[:, None]
        dot_local = np.clip(np.sum(unit_sun * unit_moon, axis=1), -1.0, 1.0)
        cross_local = np.linalg.norm(np.cross(unit_sun, unit_moon), axis=1)
        separation_local = np.degrees(np.arctan2(cross_local, dot_local))
        solar_radius = np.degrees(
            np.arcsin(np.clip(sun_radius_km / distance_sun, -1.0, 1.0))
        )
        lunar_radius = np.degrees(
            np.arcsin(np.clip(moon_radius_km / distance_moon, -1.0, 1.0))
        )
        altitude_sine = np.sum(unit_sun * candidate_up, axis=1)
        day = altitude_sine > math.sin(math.radians(-0.833))
        magnitude = (lunar_radius + solar_radius - separation_local) / (2.0 * solar_radius)
        magnitude = np.where(
            day & (separation_local < lunar_radius + solar_radius), magnitude, 0.0
        )
        altitude = np.degrees(np.arcsin(np.clip(altitude_sine, -1.0, 1.0)))
        return magnitude, separation_local, solar_radius, lunar_radius, altitude

    for _ in range(refinement_iterations):
        third = (right - left) / 3.0
        x1, x2 = left + third, right - third
        magnitude1 = evaluate(x1)[0]
        magnitude2 = evaluate(x2)[0]
        move_left = magnitude2 > magnitude1
        left = np.where(move_left, x1, left)
        right = np.where(move_left, right, x2)

    best_offsets = (left + right) / 2.0
    magnitudes, separations, solar_radii, lunar_radii, altitudes = evaluate(best_offsets)
    return [
        (
            int(candidate_indices[row]),
            float(best_offsets[row]),
            float(magnitudes[row]),
            float(separations[row]),
            float(solar_radii[row]),
            float(lunar_radii[row]),
            float(altitudes[row]),
        )
        for row in range(len(candidate_indices))
        if float(magnitudes[row]) > min_magnitude
    ]


class EclipseEngine:
    """Calculate local/global eclipse circumstances with a selectable JPL SPK kernel.

    Examples::

        engine = EclipseEngine("de440s")
        result = engine.calculate_local(Observer(42.0, -5.0), "2026-08-12")

        engine = EclipseEngine("/data/kernels/de441.bsp")

    ``ephemeris`` may be a local BSP/SPK file, an in-memory Skyfield ephemeris,
    or a kernel name such as ``de432s``, ``de440s``, ``de440`` or ``de441``.
    The selected kernel is managed outside the EclipseKit package directory.
    """

    def __init__(self, ephemeris: str | Path | Any | None = None, *,
                 config: EclipseConfig | None = None,
                 cache_dir: str | Path | None = None,
                 timescale: Any | None = None,
                 earth_orientation: EarthOrientationConfig | None = None,
                 body_names: dict[str, str] | None = None,
                 sun_radius_km: float | None = None,
                 moon_radius_peaks_km: float | None = None,
                 moon_radius_valleys_km: float | None = None,
                 moon_radius_visual_km: float | None = None,
                 moon_radius_shadow_km: float | None = None,
                 pressure_mbar: float | None = None,
                 temperature_c: float | None = None) -> None:
        """Create an eclipse engine.

        New code should pass one :class:`EclipseConfig` object. The keyword
        arguments from EclipseKit 0.1.0 are retained as a backwards-compatible
        bridge; they are converted into the same immutable configuration.
        Do not mix ``config=`` with legacy overrides.
        """
        legacy_values = {
            "ephemeris": ephemeris,
            "cache_dir": cache_dir,
            "timescale": timescale,
            "earth_orientation": earth_orientation,
            "body_names": body_names,
            "sun_radius_km": sun_radius_km,
            "moon_radius_peaks_km": moon_radius_peaks_km,
            "moon_radius_valleys_km": moon_radius_valleys_km,
            "moon_radius_visual_km": moon_radius_visual_km,
            "moon_radius_shadow_km": moon_radius_shadow_km,
            "pressure_mbar": pressure_mbar,
            "temperature_c": temperature_c,
        }
        if config is not None:
            supplied_legacy = [name for name, value in legacy_values.items() if value is not None]
            if supplied_legacy:
                raise ValueError(
                    "Pass either config=EclipseConfig(...) or legacy constructor overrides, "
                    f"not both; received: {', '.join(supplied_legacy)}"
                )
            active_config = config
        else:
            ephemeris_config = EphemerisConfig(
                kernel=ephemeris if ephemeris is not None else "de440s",
                cache_dir=cache_dir,
                timescale=timescale,
                earth_orientation=(
                    earth_orientation if earth_orientation is not None
                    else (None if timescale is not None else EarthOrientationConfig.builtin())
                ),
                body_names=body_names,
            )
            contact_config = ContactModelConfig(
                sun_radius_km=SUN_RADIUS_KM if sun_radius_km is None else sun_radius_km,
                moon_radius_external_km=(
                    MOON_RADIUS_PEAKS_KM if moon_radius_peaks_km is None else moon_radius_peaks_km
                ),
                moon_radius_internal_km=(
                    MOON_RADIUS_VALLEYS_KM if moon_radius_valleys_km is None else moon_radius_valleys_km
                ),
                moon_radius_visual_km=(
                    MOON_RADIUS_VISUAL_KM if moon_radius_visual_km is None else moon_radius_visual_km
                ),
                moon_radius_shadow_km=(
                    MOON_RADIUS_XAVIER_KM if moon_radius_shadow_km is None else moon_radius_shadow_km
                ),
            )
            atmosphere_config = AtmosphereConfig(
                pressure_mbar=1013.25 if pressure_mbar is None else pressure_mbar,
                temperature_c=15.0 if temperature_c is None else temperature_c,
            )
            active_config = EclipseConfig(
                ephemeris=ephemeris_config,
                contacts=contact_config,
                solver=SolverConfig(),
                atmosphere=atmosphere_config,
            )

        if not isinstance(active_config, EclipseConfig):
            raise TypeError("config must be an EclipseConfig instance")
        self.config = active_config
        self.ephemeris_config = active_config.ephemeris
        self.contact_config = active_config.contacts
        self.solver_config = active_config.solver
        self.atmosphere_config = active_config.atmosphere

        self.context = EphemerisContext(
            self.ephemeris_config.kernel,
            cache_dir=self.ephemeris_config.cache_dir,
            timescale=self.ephemeris_config.timescale,
            earth_orientation=self.ephemeris_config.earth_orientation,
            body_names=dict(self.ephemeris_config.body_names or {}),
        )
        self.ts = self.context.ts
        self.time_scale_mode = self.context.time_scale_mode
        self.eph = self.context.ephemeris
        self.earth, self.sun, self.moon = self.context.earth, self.context.sun, self.context.moon
        self.sun_radius_km = self.contact_config.sun_radius_km
        self.moon_radius_peaks_km = self.contact_config.moon_radius_external_km
        self.moon_radius_valleys_km = self.contact_config.moon_radius_internal_km
        self.moon_radius_visual_km = self.contact_config.moon_radius_visual_km
        self.moon_radius_shadow_km = self.contact_config.moon_radius_shadow_km
        self.pressure_mbar = (
            self.atmosphere_config.pressure_mbar
            if self.atmosphere_config.refraction_enabled else 0.0
        )
        self.temperature_c = self.atmosphere_config.temperature_c
        self._planet_names = {
            "mercury barycenter": "Mercury",
            "venus barycenter": "Venus",
            "mars barycenter": "Mars",
            "jupiter barycenter": "Jupiter",
            "saturn barycenter": "Saturn",
            "uranus barycenter": "Uranus",
            "neptune barycenter": "Neptune",
        }

    @classmethod
    def from_jpl(
        cls,
        kernel: str | Path | None = None,
        *,
        config: EclipseConfig | None = None,
        **kwargs: Any,
    ) -> "EclipseEngine":
        """Create an engine from a JPL kernel or a complete public config.

        Examples::

            EclipseEngine.from_jpl("de440s")
            EclipseEngine.from_jpl(config=EclipseConfig(...))
        """
        if config is not None:
            if kernel is not None or kwargs:
                raise ValueError("When config= is supplied, do not also pass kernel or overrides")
            return cls(config=config)
        return cls(kernel or "de440s", **kwargs)

    def time(self, value: Any, *, calendar: str = "historical") -> Any:
        """Interpret dates as absolute instants using the selected civil calendar.

        Date-only inputs default to the historical Julian/Gregorian cutover.
        Pass ``calendar="julian"`` or ``calendar="gregorian"`` for a proleptic
        calendar. Existing datetime and Skyfield Time inputs remain absolute.
        """
        return coerce_time(self.ts, value, calendar=calendar)

    def calculate_local_besselian(
        self,
        elements: Any,
        observer: Observer,
        *,
        center: Any | None = None,
        search_half_window_hours: float | None = None,
        delta_t_seconds: float | None = None,
    ) -> Any:
        """Calculate local circumstances using explicit Besselian elements.

        This method is intentionally separate from :meth:`calculate_local`.
        It does not derive Besselian elements from the active ephemeris. If
        ``delta_t_seconds`` is omitted, ΔT is obtained from this engine's
        configured Skyfield time-scale source at each evaluated instant.
        """
        from .besselian import BesselianSolver

        center_jd = (
            elements.epoch_tt_jd if center is None
            else (float(center) if isinstance(center, (int, float)) else float(self.time(center).tt))
        )
        solver = BesselianSolver(config=self.config.besselian, solver_config=self.solver_config)
        if delta_t_seconds is not None:
            return solver.calculate_local(
                elements, observer, center_jd_tt=center_jd,
                search_half_window_hours=search_half_window_hours,
                delta_t_seconds=delta_t_seconds,
            )

        def delta_t_at(jd_tt: float) -> float:
            moment = self.ts.tt_jd(float(jd_tt))
            return (float(moment.tt) - float(moment.ut1)) * 86400.0

        return solver.calculate_local(
            elements, observer, center_jd_tt=center_jd,
            search_half_window_hours=search_half_window_hours,
            delta_t_seconds=delta_t_at,
        )

    def find_global_maximum_besselian(
        self, elements: Any, *, start: Any | None = None, end: Any | None = None
    ) -> Any:
        """Return the Besselian geocentric closest-approach instant as Skyfield Time."""
        from .besselian import BesselianSolver

        start_jd = (
            elements.epoch_tt_jd + elements.validity_start_hours / 24.0
            if start is None else (float(start) if isinstance(start, (int, float)) else float(self.time(start).tt))
        )
        end_jd = (
            elements.epoch_tt_jd + elements.validity_end_hours / 24.0
            if end is None else (float(end) if isinstance(end, (int, float)) else float(self.time(end).tt))
        )
        jd = BesselianSolver(
            config=self.config.besselian, solver_config=self.solver_config
        ).find_global_maximum(elements, start_jd_tt=start_jd, end_jd_tt=end_jd)
        return self.ts.tt_jd(jd)

    def besselian_global_shadow_path(
        self,
        elements: Any,
        start: Any,
        end: Any,
        *,
        samples: int = 101,
        delta_t_seconds: float | None = None,
    ) -> list[Any]:
        """Return Besselian central-line ground-track points.

        Each result retains its TT Julian Date, geodetic coordinates and
        fundamental-plane umbral radius; no path-width projection is implied.
        """
        from .besselian import BesselianSolver

        solver = BesselianSolver(config=self.config.besselian, solver_config=self.solver_config)
        start_jd = float(start) if isinstance(start, (int, float)) else float(self.time(start).tt)
        end_jd = float(end) if isinstance(end, (int, float)) else float(self.time(end).tt)
        if delta_t_seconds is not None:
            return solver.global_central_line(
                elements, start_jd, end_jd, samples=samples,
                delta_t_seconds=delta_t_seconds,
            )

        def delta_t_at(jd_tt: float) -> float:
            moment = self.ts.tt_jd(float(jd_tt))
            return (float(moment.tt) - float(moment.ut1)) * 86400.0

        return solver.global_central_line(
            elements, start_jd, end_jd, samples=samples,
            delta_t_seconds=delta_t_at,
        )

    def time_from_ut1(
        self, year: int, month: int, day: int,
        hour: int = 0, minute: int = 0, second: float = 0.0,
    ) -> Any:
        """Create a Skyfield Time from explicit UT1 calendar fields.

        Use this for reference tables whose time column is labelled UT/UT1.
        Ordinary civil timestamps should continue to use :meth:`time` (UTC).
        """
        return self.ts.ut1(year, month, day, hour, minute, second)

    def time_scale_diagnostics(self, when: Any) -> dict[str, Any]:
        """Report Delta-T, DUT1, and the fingerprint of the active EOP source."""
        provenance = getattr(
            getattr(self, "context", None), "earth_orientation_provenance", None
        )
        if provenance is None:
            # Preserve compatibility with lightweight/fake engine contexts that
            # implement the historical two-argument diagnostic function.
            return describe_time_scale(self.time(when), self.time_scale_mode)
        return describe_time_scale(
            self.time(when), self.time_scale_mode, provenance=provenance
        )

    def time_from_calendar(
        self, year: int, month: int, day: int, hour: int = 0, minute: int = 0,
        second: float = 0.0, *, calendar: str = "historical",
    ) -> Any:
        """Create a Skyfield time from Julian, Gregorian, or historical date fields."""
        from .timeutils import time_from_calendar
        if calendar == "historical":
            # Preserve compatibility with callers/tests that wrap the original
            # positional helper signature; its default is the historical calendar.
            return time_from_calendar(self.ts, year, month, day, hour, minute, second)
        return time_from_calendar(
            self.ts, year, month, day, hour, minute, second, calendar=calendar
        )

    def _observer(self, observer: Observer) -> Any:
        return observer.to_skyfield(self.earth)

    def _separation_deg(self, observer_sf: Any, jd_tt: float) -> float:
        t = self.ts.tt_jd(float(jd_tt))
        at = observer_sf.at(t)
        sun_app = at.observe(self.sun).apparent()
        moon_app = at.observe(self.moon).apparent()
        return float(sun_app.separation_from(moon_app).degrees)

    def _angular_radii_deg(self, observer_sf: Any, jd_tt: float,
                           moon_radius_km: float | None = None) -> tuple[float, float]:
        t = self.ts.tt_jd(float(jd_tt))
        at = observer_sf.at(t)
        sun_distance = at.observe(self.sun).distance().km
        moon_distance = at.observe(self.moon).distance().km
        moon_radius = moon_radius_km or self.moon_radius_visual_km
        sun_radius = math.degrees(angular_radius(self.sun_radius_km, float(sun_distance)))
        moon_radius_deg = math.degrees(angular_radius(moon_radius, float(moon_distance)))
        return sun_radius, moon_radius_deg

    def _find_minimum_separation(self, observer_sf: Any, center_jd: float,
                                 half_window_hours: float = 12.0,
                                 coarse_step_minutes: float | None = None) -> tuple[float, float]:
        if coarse_step_minutes is None:
            coarse_step_minutes = self.solver_config.coarse_step_minutes
        start = center_jd - half_window_hours / 24.0
        end = center_jd + half_window_hours / 24.0
        step_days = coarse_step_minutes / 1440.0
        grid = np.arange(start, end + step_days * 0.5, step_days, dtype=float)
        times = self.ts.tt_jd(grid)
        at = observer_sf.at(times)
        sun_app = at.observe(self.sun).apparent()
        moon_app = at.observe(self.moon).apparent()
        sep = np.asarray(sun_app.separation_from(moon_app).degrees, dtype=float)
        idx = int(np.argmin(sep))
        lo = float(grid[max(0, idx - 1)])
        hi = float(grid[min(len(grid) - 1, idx + 1)])
        if hi <= lo:
            return float(grid[idx]), float(sep[idx])
        return golden_section_minimize(
            lambda jd: self._separation_deg(observer_sf, jd), lo, hi,
            tolerance_days=self.solver_config.minimum_tolerance_seconds / 86400.0,
            max_iterations=self.solver_config.minimum_max_iterations,
        )

    def _contact_residual(self, observer_sf: Any, jd_tt: float, mode: str,
                          custom_moon_radius_km: float | None = None) -> float:
        sep = self._separation_deg(observer_sf, jd_tt)
        sun_radius, moon_radius = self._angular_radii_deg(observer_sf, jd_tt, custom_moon_radius_km)
        if mode == "external":
            return sep - (sun_radius + moon_radius)
        if mode == "internal":
            return sep - abs(moon_radius - sun_radius)
        raise ValueError("mode must be 'external' or 'internal'")

    def _solve_root_detailed(
        self,
        function: Any,
        start_jd: float,
        end_jd: float,
        *,
        auto_expand: bool = False,
        detect_tangent: bool = False,
    ) -> RootResult:
        """Solve a root in TT Julian Date and retain numerical diagnostics."""
        solver = self.solver_config
        return solve_root(
            function,
            start_jd,
            end_jd,
            method=solver.root_method,
            tolerance_days=solver.root_tolerance_seconds / 86400.0,
            value_tolerance=solver.root_value_tolerance_deg,
            max_iterations=solver.root_max_iterations,
            auto_expand=auto_expand,
            expansion_factor=solver.bracket_expansion_factor,
            max_expansions=solver.bracket_max_expansions,
            max_span_days=solver.bracket_max_span_seconds / 86400.0,
            scan_samples=solver.bracket_scan_samples,
            detect_tangent=detect_tangent,
            tangent_samples=solver.tangent_scan_samples,
            tangent_value_tolerance=solver.tangent_value_tolerance_deg,
        )

    def _solve_root(self, function: Any, start_jd: float, end_jd: float) -> float | None:
        """Compatibility helper returning a numeric root or ``None``.

        Internal local-event calculations already provide physically bounded
        ingress/egress intervals. They therefore never expand beyond those
        phase bounds and do not reinterpret a near-tangency as a normal root.
        """
        result = self._solve_root_detailed(function, start_jd, end_jd)
        return result.root if result.converged else None

    def solve_contact_detailed(
        self,
        observer: Observer,
        mode: str,
        start: Any,
        end: Any,
        *,
        moon_radius_km: float | None = None,
        auto_expand: bool | None = None,
        detect_tangent: bool | None = None,
    ) -> RootResult:
        """Solve one contact and return a detailed diagnostic result.

        The independent variable and ``RootResult.root`` are TT Julian Dates.
        Set ``auto_expand=False`` to restrict the solver strictly to the
        supplied interval. If expansion is enabled, the nearest sign-changing
        bracket to the initial interval midpoint is selected. A tangent contact
        is reported separately with ``status='tangent_contact'``.
        """
        if mode not in {"external", "internal"}:
            raise ValueError("mode must be 'external' or 'internal'")
        observer_sf = self._observer(observer)
        a = float(self.time(start).tt) if not isinstance(start, (int, float)) else float(start)
        b = float(self.time(end).tt) if not isinstance(end, (int, float)) else float(end)
        if a > b:
            a, b = b, a
        if a == b:
            raise ValueError("contact search interval must have non-zero duration")
        if moon_radius_km is None:
            moon_radius_km = (
                self.moon_radius_peaks_km if mode == "external"
                else self.moon_radius_valleys_km
            )
        if not math.isfinite(float(moon_radius_km)) or float(moon_radius_km) <= 0.0:
            raise ValueError("moon_radius_km must be finite and positive")

        use_expansion = (
            self.solver_config.auto_expand_bracket if auto_expand is None else auto_expand
        )
        use_tangent = (
            self.solver_config.detect_tangent_contacts if detect_tangent is None
            else detect_tangent
        )
        if not isinstance(use_expansion, bool) or not isinstance(use_tangent, bool):
            raise ValueError("auto_expand and detect_tangent must be bool values")
        def residual(jd: float) -> float:
            return self._contact_residual(
                observer_sf, jd, mode, float(moon_radius_km)
            )
        return self._solve_root_detailed(
            residual, a, b, auto_expand=use_expansion, detect_tangent=use_tangent
        )

    def solve_contact(
        self,
        observer: Observer,
        mode: str,
        start: Any,
        end: Any,
        *,
        moon_radius_km: float | None = None,
        auto_expand: bool | None = None,
        detect_tangent: bool | None = None,
    ) -> Any | None:
        """Solve one external/internal contact and return a Skyfield ``Time``.

        For diagnostics (status, iterations, residual and final bracket), use
        :meth:`solve_contact_detailed`. The legacy return type is preserved.
        """
        result = self.solve_contact_detailed(
            observer, mode, start, end, moon_radius_km=moon_radius_km,
            auto_expand=auto_expand, detect_tangent=detect_tangent,
        )
        return self.ts.tt_jd(result.root) if result.converged and result.root is not None else None

    def find_next_local_eclipse(self, observer: Observer, start: Any,
                                *, search_days: float = 550.0) -> Any | None:
        """Return the next local solar eclipse maximum after ``start`` or ``None``."""
        try:
            from skyfield import almanac
        except ImportError as exc:  # pragma: no cover
            raise ImportError("Skyfield is required for eclipse phase searches") from exc
        t0 = self.time(start)
        t1 = self.ts.tt_jd(t0.tt + search_days)
        phase_function = almanac.moon_phases(self.eph)
        new_moons, phase_values = almanac.find_discrete(t0, t1, phase_function)
        observer_sf = self._observer(observer)
        for phase_time, phase_value in zip(new_moons, phase_values):
            if int(phase_value) != 0:
                continue
            maximum_jd, minimum_sep = self._find_minimum_separation(
                observer_sf, float(phase_time.tt), half_window_hours=7.2, coarse_step_minutes=3.0
            )
            sun_radius, moon_radius = self._angular_radii_deg(observer_sf, maximum_jd)
            if minimum_sep < sun_radius + moon_radius:
                return self.ts.tt_jd(maximum_jd)
        return None

    def search_solar_eclipses(
        self,
        start: Any,
        end: Any,
        observers: Iterable[Observer],
        *,
        min_magnitude: float = 0.0,
        search_window_hours: float = 12.0,
        limb_corrector: Any | None = None,
        limb_model: Any | None = None,
        include_sunrise_sunset: bool = False,
        include_shadow_metrics: bool = False,
        include_planets: bool = False,
    ) -> SolarEclipseSearchResult:
        """Search a UTC interval for solar eclipses at multiple observers.

        New moons are used only to seed candidate global conjunction times. For
        every candidate, the local maximum and contacts are solved independently
        for each supplied observer. Only local maxima inside ``[start, end]``
        are returned; no "next eclipse" fallback can escape the requested
        interval. Observer coverage is limited to the explicit input locations.

        The default search window is +/- 12 hours around geocentric maximum.
        ``min_magnitude`` filters local events after their circumstances are
        calculated. Use ``limb_model`` for the Phase 5 provider API;
        ``limb_corrector`` remains a backwards-compatible alias.
        """
        if limb_corrector is not None and limb_model is not None:
            raise ValueError("Pass either limb_model or legacy limb_corrector, not both")
        if limb_model is not None:
            limb_corrector = limb_model
        if isinstance(min_magnitude, bool):
            raise ValueError("min_magnitude must be a finite non-negative number")
        try:
            magnitude_threshold = float(min_magnitude)
            window_hours = float(search_window_hours)
        except (TypeError, ValueError) as exc:
            raise ValueError("min_magnitude and search_window_hours must be numeric") from exc
        if not math.isfinite(magnitude_threshold) or magnitude_threshold < 0.0:
            raise ValueError("min_magnitude must be a finite non-negative number")
        if isinstance(search_window_hours, bool) or not math.isfinite(window_hours):
            raise ValueError("search_window_hours must be finite and > 0 and <= 24")
        if not 0.0 < window_hours <= 24.0:
            raise ValueError("search_window_hours must be > 0 and <= 24")
        for option_name, option_value in (
            ("include_sunrise_sunset", include_sunrise_sunset),
            ("include_shadow_metrics", include_shadow_metrics),
            ("include_planets", include_planets),
        ):
            if not isinstance(option_value, bool):
                raise ValueError(f"{option_name} must be bool")

        try:
            requested_observers = tuple(observers)
        except TypeError as exc:
            raise TypeError("observers must be an iterable of Observer instances") from exc
        if not requested_observers:
            raise ValueError("observers must contain at least one Observer")
        if any(not isinstance(observer, Observer) for observer in requested_observers):
            raise TypeError("observers must contain only Observer instances")

        t0, t1 = self.time(start), self.time(end)
        start_jd, end_jd = float(t0.tt), float(t1.tt)
        if not math.isfinite(start_jd) or not math.isfinite(end_jd) or end_jd <= start_jd:
            raise ValueError("end must be later than start")

        try:
            from skyfield import almanac
        except ImportError as exc:  # pragma: no cover
            raise ImportError("Skyfield is required for solar-eclipse interval searches") from exc

        # Extend the new-moon discovery interval so events near either requested
        # endpoint are not lost when local maximum differs from conjunction.
        discovery_start = self.ts.tt_jd(start_jd - 1.0)
        discovery_end = self.ts.tt_jd(end_jd + 1.0)
        phase_function = almanac.moon_phases(self.eph)
        phase_times, phase_values = almanac.find_discrete(
            discovery_start, discovery_end, phase_function
        )

        events: list[SolarEclipseSearchEvent] = []
        new_moons_examined = 0
        for phase_time, phase_value in zip(phase_times, phase_values):
            if int(phase_value) != 0:
                continue
            new_moons_examined += 1
            geocentric_maximum = self.find_global_maximum(
                phase_time, half_window_hours=7.2
            )
            local_hits: list[SolarEclipseLocationHit] = []
            for observer in requested_observers:
                local_result = self.calculate_local(
                    observer,
                    geocentric_maximum,
                    search_window_hours=window_hours,
                    find_next_if_none=False,
                    limb_corrector=limb_corrector,
                    include_sunrise_sunset=include_sunrise_sunset,
                    include_shadow_metrics=include_shadow_metrics,
                    include_planets=include_planets,
                )
                if local_result is None:
                    continue
                maximum_jd = float(local_result.maximum.tt)
                if maximum_jd < start_jd or maximum_jd > end_jd:
                    continue
                if float(local_result.magnitude) < magnitude_threshold:
                    continue
                local_hits.append(SolarEclipseLocationHit(observer, local_result))
            if local_hits:
                events.append(SolarEclipseSearchEvent(geocentric_maximum, local_hits))

        events.sort(key=lambda event: float(event.geocentric_maximum.tt))
        return SolarEclipseSearchResult(
            start_utc=time_to_utc_iso(t0),
            end_utc=time_to_utc_iso(t1),
            locations_requested=len(requested_observers),
            new_moons_examined=new_moons_examined,
            events=events,
        )

    def _global_separation_deg(self, jd_tt: float) -> float:
        t = self.ts.tt_jd(float(jd_tt))
        at = self.earth.at(t)
        return float(at.observe(self.sun).apparent().separation_from(
            at.observe(self.moon).apparent()
        ).degrees)

    def find_global_maximum(self, when: Any, *, half_window_hours: float = 12.0) -> Any:
        """Find geocentric minimum Sun-Moon separation around a supplied date/time."""
        t = self.time(when)
        jd, _ = self._find_minimum_separation(self.earth, float(t.tt), half_window_hours, 5.0)
        return self.ts.tt_jd(jd)

    def _is_global_solar_eclipse(self, t_max: Any) -> bool:
        """Return a best-effort global eclipse flag at a candidate maximum.

        A geocentric disk-overlap test alone is insufficient: lunar parallax can
        make the Sun and Moon miss from Earth's center while the shadow still
        intersects the terrestrial surface. Prefer the actual shadow-axis
        intersection, then retain the geocentric overlap as a useful fallback.
        Public city searches do not use this as a rejection filter; they test
        each supplied surface location directly.
        """
        if self._shadow_state(t_max) is not None:
            return True
        at = self.earth.at(t_max)
        s = at.observe(self.sun).apparent()
        m = at.observe(self.moon).apparent()
        rs = math.degrees(angular_radius(self.sun_radius_km, float(s.distance().km)))
        rm = math.degrees(angular_radius(self.moon_radius_visual_km, float(m.distance().km)))
        return float(s.separation_from(m).degrees) < rs + rm

    @staticmethod
    def _parallactic_angle_deg(observer: Observer, t: Any, sun_apparent: Any) -> float | None:
        """Position angle of the local zenith at the apparent solar position.

        The result is measured from celestial north toward east. It is used to
        express the contact position angle relative to the local vertical.
        """
        try:
            ra, dec, _ = sun_apparent.radec()
            hour_angle_deg = (
                float(t.gast) * 15.0 + observer.longitude - float(ra.degrees) + 180.0
            ) % 360.0 - 180.0
            hour_angle = math.radians(hour_angle_deg)
            latitude = math.radians(observer.latitude)
            declination = float(dec.radians)
            numerator = math.sin(hour_angle)
            denominator = (
                math.tan(latitude) * math.cos(declination)
                - math.sin(declination) * math.cos(hour_angle)
            )
            return math.degrees(math.atan2(numerator, denominator)) % 360.0
        except (AttributeError, TypeError, ValueError, OverflowError):
            return None

    def calculate_observation_geometry(
        self,
        observer: Observer,
        when: Any,
        *,
        horizon_profile: HorizonProfile | None = None,
        apply_refraction: bool = True,
    ) -> ObservationGeometry:
        """Calculate detailed topocentric Sun/Moon geometry at one instant.

        The default horizon is the astronomical horizon (0 degrees). A caller
        may provide an azimuth-dependent :class:`HorizonProfile` to include a
        measured or surveyed skyline. The profile is an observing constraint,
        not a terrain model inferred by EclipseKit.
        """
        if not isinstance(observer, Observer):
            raise TypeError("observer must be an Observer instance")
        if horizon_profile is not None and not isinstance(horizon_profile, HorizonProfile):
            raise TypeError("horizon_profile must be a HorizonProfile or None")
        if not isinstance(apply_refraction, bool):
            raise TypeError("apply_refraction must be a boolean")
        t = self.time(when)
        observer_sf = self._observer(observer)
        at = observer_sf.at(t)
        sun_app = at.observe(self.sun).apparent()
        moon_app = at.observe(self.moon).apparent()
        pressure = self.pressure_mbar if apply_refraction else 0.0
        sun_altitude, sun_azimuth, _ = sun_app.altaz(
            pressure_mbar=pressure, temperature_C=self.temperature_c
        )
        moon_altitude, moon_azimuth, _ = moon_app.altaz(
            pressure_mbar=pressure, temperature_C=self.temperature_c
        )
        sun_altitude_deg = float(sun_altitude.degrees)
        sun_azimuth_deg = float(sun_azimuth.degrees) % 360.0
        moon_altitude_deg = float(moon_altitude.degrees)
        moon_azimuth_deg = float(moon_azimuth.degrees) % 360.0
        separation = float(sun_app.separation_from(moon_app).degrees)
        sun_radius, moon_radius = self._angular_radii_deg(
            observer_sf, float(t.tt), self.moon_radius_visual_km
        )
        try:
            from .geometry import position_angle
            pa = float(position_angle(observer_sf, t, self.sun, self.moon))
        except Exception:
            pa = None
        parallactic = self._parallactic_angle_deg(observer, t, sun_app)
        vertex = (
            (pa - parallactic + 180.0) % 360.0 - 180.0
            if pa is not None and parallactic is not None else None
        )
        horizon_altitude = (
            horizon_profile.altitude_at(sun_azimuth_deg) if horizon_profile is not None else 0.0
        )
        center_clearance = sun_altitude_deg - horizon_altitude
        upper_clearance = center_clearance + sun_radius
        lower_clearance = center_clearance - sun_radius
        if upper_clearance <= 0.0:
            visibility = "obstructed"
        elif lower_clearance < 0.0:
            visibility = "partially_obstructed"
        else:
            visibility = "visible"
        magnitude = (moon_radius + sun_radius - separation) / (2.0 * sun_radius)
        obscuration = circle_overlap_fraction(sun_radius, moon_radius, separation) * 100.0
        return ObservationGeometry(
            observer=observer, time=t,
            sun_altitude_deg=sun_altitude_deg, sun_azimuth_deg=sun_azimuth_deg,
            moon_altitude_deg=moon_altitude_deg, moon_azimuth_deg=moon_azimuth_deg,
            separation_deg=separation, sun_angular_radius_deg=sun_radius,
            moon_angular_radius_deg=moon_radius, position_angle_deg=pa,
            parallactic_angle_deg=parallactic, vertex_angle_deg=vertex,
            magnitude=magnitude, obscuration_percent=obscuration,
            horizon_altitude_deg=horizon_altitude,
            sun_center_clearance_deg=center_clearance,
            sun_upper_limb_clearance_deg=upper_clearance,
            sun_lower_limb_clearance_deg=lower_clearance,
            visibility_status=visibility,
            horizon_profile_name=horizon_profile.name if horizon_profile is not None else None,
            refraction_applied=bool(apply_refraction and pressure > 0.0),
        )

    def _build_contact_event(
        self,
        observer: Observer,
        observer_sf: Any,
        name: str,
        event_type: str,
        event_time: Any,
        *,
        solver_result: RootResult | None = None,
        limb_correction: LimbContact | None = None,
        horizon_profile: HorizonProfile | None = None,
    ) -> ContactEvent:
        """Build a time-scale-aware, topocentric event record."""
        from .geometry import position_angle

        at = observer_sf.at(event_time)
        sun_app = at.observe(self.sun).apparent()
        moon_app = at.observe(self.moon).apparent()
        separation = float(sun_app.separation_from(moon_app).degrees)
        if event_type == "external":
            lunar_radius = self.moon_radius_peaks_km
        elif event_type == "internal":
            lunar_radius = self.moon_radius_valleys_km
        else:
            lunar_radius = self.moon_radius_visual_km
        sun_radius_deg, moon_radius_deg = self._angular_radii_deg(
            observer_sf, float(event_time.tt), lunar_radius
        )

        try:
            pa = float(position_angle(observer_sf, event_time, self.sun, self.moon))
        except Exception:
            pa = None
        parallactic = self._parallactic_angle_deg(observer, event_time, sun_app)
        vertex = (
            (pa - parallactic + 180.0) % 360.0 - 180.0
            if pa is not None and parallactic is not None else None
        )
        altitude, azimuth, _ = sun_app.altaz(
            pressure_mbar=self.pressure_mbar,
            temperature_C=self.temperature_c,
        )
        altitude_deg = float(altitude.degrees)
        azimuth_deg = float(azimuth.degrees)
        horizon_altitude = None
        upper_limb_clearance = None
        visibility_note = (
            "Based on apparent topocentric solar altitude; local terrain and observer-specific "
            "horizon obstructions are not modelled."
        )
        if horizon_profile is None:
            if altitude_deg > 0.01:
                visibility = "above_horizon"
            elif altitude_deg < -0.01:
                visibility = "below_horizon"
            else:
                visibility = "at_horizon"
        else:
            horizon_altitude = horizon_profile.altitude_at(azimuth_deg)
            upper_limb_clearance = altitude_deg - horizon_altitude + float(sun_radius_deg)
            lower_limb_clearance = altitude_deg - horizon_altitude - float(sun_radius_deg)
            if upper_limb_clearance <= 0.0:
                visibility = "obstructed"
            elif lower_limb_clearance < 0.0:
                visibility = "partially_obstructed"
            else:
                visibility = "visible"
            visibility_note = (
                f"Visibility evaluated against caller-supplied horizon profile '{horizon_profile.name}'. "
                "The profile is an azimuth mask; terrain, diffraction and local atmospheric variability "
                "are not modelled."
            )

        return ContactEvent(
            name=name,
            event_type=event_type,
            time=event_time,
            separation_deg=separation,
            sun_angular_radius_deg=float(sun_radius_deg),
            moon_angular_radius_deg=float(moon_radius_deg),
            position_angle_deg=pa,
            vertex_angle_deg=vertex,
            sun_altitude_deg=altitude_deg,
            sun_azimuth_deg=azimuth_deg,
            visibility_status=visibility,
            solver_result=solver_result,
            limb_correction=limb_correction,
            visibility_note=visibility_note,
            horizon_altitude_deg=horizon_altitude,
            sun_upper_limb_clearance_deg=upper_limb_clearance,
        )

    def calculate_local(
        self,
        observer: Observer,
        when: Any,
        *,
        search_window_hours: float = 12.0,
        find_next_if_none: bool = True,
        limb_corrector: Any | None = None,
        limb_model: Any | None = None,
        include_sunrise_sunset: bool = True,
        include_shadow_metrics: bool = True,
        include_planets: bool = True,
        horizon_profile: HorizonProfile | None = None,
    ) -> LocalEclipseResult | None:
        """Calculate local eclipse contacts and circumstances near ``when``.

        ``when`` may be an ISO timestamp/date, datetime/date, Skyfield Time, or
        Julian Date TT. Date-only strings are treated as 12:00 UTC.

        ``limb_model`` accepts any Phase 5 provider. ``limb_corrector`` remains
        as a backwards-compatible alias for the original neural corrector.
        Pass at most one of them.
        """
        if horizon_profile is not None and not isinstance(horizon_profile, HorizonProfile):
            raise TypeError("horizon_profile must be a HorizonProfile or None")
        if limb_corrector is not None and limb_model is not None:
            raise ValueError("Pass either limb_model or legacy limb_corrector, not both")
        if limb_model is not None:
            limb_corrector = limb_model
        t_ref = self.time(when)
        observer_sf = self._observer(observer)
        maximum_jd, min_sep = self._find_minimum_separation(
            observer_sf, float(t_ref.tt), search_window_hours
        )
        start_jd = float(t_ref.tt) - search_window_hours / 24.0
        end_jd = float(t_ref.tt) + search_window_hours / 24.0
        rs, rm = self._angular_radii_deg(observer_sf, maximum_jd)
        is_next = False
        if min_sep >= rs + rm:
            if not find_next_if_none:
                return None
            next_maximum = self.find_next_local_eclipse(observer, t_ref)
            if next_maximum is None:
                return None
            maximum_jd, min_sep = self._find_minimum_separation(
                observer_sf, float(next_maximum.tt), half_window_hours=8.0, coarse_step_minutes=2.0
            )
            start_jd = maximum_jd - 0.5
            end_jd = maximum_jd + 0.5
            rs, rm = self._angular_radii_deg(observer_sf, maximum_jd)
            is_next = True

        t_max = self.ts.tt_jd(maximum_jd)
        at_max = observer_sf.at(t_max)
        sun_app = at_max.observe(self.sun).apparent()
        rs, rm = self._angular_radii_deg(observer_sf, maximum_jd)
        ratio = rm / rs
        magnitude = (rm + rs - min_sep) / (2.0 * rs)
        obscuration = circle_overlap_fraction(rs, rm, min_sep) * 100.0
        central = min_sep <= abs(rm - rs) + 1e-10
        if not central:
            eclipse_type = "partial"
        elif ratio >= 1.0:
            eclipse_type = "total"
        else:
            eclipse_type = "annular"

        # External contacts always define the visible partial phase. Keep the
        # numerical diagnostics rather than reducing every solve to a float.
        c1_solver = self._solve_root_detailed(
            lambda jd: self._contact_residual(
                observer_sf, jd, "external", self.moon_radius_peaks_km
            ), start_jd, maximum_jd
        )
        c4_solver = self._solve_root_detailed(
            lambda jd: self._contact_residual(
                observer_sf, jd, "external", self.moon_radius_peaks_km
            ), maximum_jd, end_jd
        )
        c1_jd = c1_solver.root if c1_solver.converged else None
        c4_jd = c4_solver.root if c4_solver.converged else None
        c2_solver = c3_solver = None
        c2_jd = c3_jd = None
        if central:
            c2_solver = self._solve_root_detailed(
                lambda jd: self._contact_residual(
                    observer_sf, jd, "internal", self.moon_radius_valleys_km
                ),
                c1_jd if c1_jd is not None else start_jd, maximum_jd,
            )
            c3_solver = self._solve_root_detailed(
                lambda jd: self._contact_residual(
                    observer_sf, jd, "internal", self.moon_radius_valleys_km
                ),
                maximum_jd, c4_jd if c4_jd is not None else end_jd,
            )
            c2_jd = c2_solver.root if c2_solver.converged else None
            c3_jd = c3_solver.root if c3_solver.converged else None
        contacts = ContactTimes(
            c1=self.ts.tt_jd(c1_jd) if c1_jd is not None else None,
            c2=self.ts.tt_jd(c2_jd) if c2_jd is not None else None,
            c3=self.ts.tt_jd(c3_jd) if c3_jd is not None else None,
            c4=self.ts.tt_jd(c4_jd) if c4_jd is not None else None,
        )
        partial_duration = (c4_jd - c1_jd) * 86400.0 if c1_jd is not None and c4_jd is not None else None
        central_duration = (
            (c3_jd - c2_jd) * 86400.0
            if c2_jd is not None and c3_jd is not None else None
        )
        # Preserve the legacy duration value for callers of 0.1.x. The new
        # central_phase_duration_seconds field is None for partial-only events.
        duration = central_duration if central_duration is not None else 0.0

        limb_contacts: dict[str, LimbContact] = {}
        corrected_duration = None
        corrected_maximum = None
        warnings: list[str] = []
        for contact_name, root_result in (
            ("C1", c1_solver), ("C2", c2_solver),
            ("C3", c3_solver), ("C4", c4_solver),
        ):
            if root_result is not None and not root_result.converged:
                warnings.append(
                    f"{contact_name} contact solver did not converge: "
                    f"{root_result.status}: {root_result.message}"
                )
        if limb_corrector is not None:
            try:
                from .limb import (
                    LunarLimbQuery,
                    compute_moon_libration_and_axis,
                    contact_selenographic_point,
                    predict_lunar_limb,
                )
                from .geometry import position_angle

                def limb_geometry_at(jd_tt: float, contact_name: str) -> dict[str, float]:
                    """Evaluate the relevant lunar-limb point and radius at one trial time."""
                    trial_time = self.ts.tt_jd(float(jd_tt))
                    p_angle = position_angle(observer_sf, trial_time, self.sun, self.moon)
                    if contact_name in {"C2", "C3"}:
                        p_angle = (p_angle + 180.0) % 360.0
                    l_opt, b_opt, p_axis = compute_moon_libration_and_axis(
                        observer_sf, trial_time, self.moon
                    )
                    limb_angle = (p_angle - p_axis) % 360.0
                    lat_sel, lon_sel = contact_selenographic_point(
                        l_opt, b_opt, limb_angle
                    )
                    query = LunarLimbQuery(
                        selenographic_latitude_deg=float(lat_sel),
                        selenographic_longitude_deg=float(lon_sel),
                        limb_angle_deg=float(limb_angle),
                        contact_name=contact_name,
                        time_tt_jd=float(jd_tt),
                        libration_longitude_deg=float(l_opt),
                        libration_latitude_deg=float(b_opt),
                    )
                    prediction = predict_lunar_limb(limb_corrector, query)
                    altitude_m = float(prediction.altitude_m)
                    corrected_radius = self.moon_radius_visual_km + altitude_m / 1000.0
                    return {
                        "latitude": float(lat_sel),
                        "longitude": float(lon_sel),
                        "altitude_m": altitude_m,
                        "radius_km": float(corrected_radius),
                        "limb_angle_deg": float(limb_angle),
                        "model_name": prediction.model_name,
                        "model_type": prediction.model_type,
                        "model_source": prediction.source,
                        "uncertainty_m": prediction.uncertainty_m,
                        "prediction_status": prediction.status,
                    }

                corrected_times: dict[str, Any] = {}
                for name, event_time in contacts.as_dict().items():
                    if event_time is None:
                        continue

                    mode = "external" if name in {"C1", "C4"} else "internal"
                    # Use the physically appropriate ingress/egress half of the event.
                    # A fixed +/-120 s window can miss a valid root when the terrain
                    # correction moves a contact farther from its spherical estimate.
                    if name == "C1":
                        bracket_start, bracket_end = start_jd, maximum_jd
                    elif name == "C2":
                        bracket_start = c1_jd if c1_jd is not None else start_jd
                        bracket_end = maximum_jd
                    elif name == "C3":
                        bracket_start = maximum_jd
                        bracket_end = c4_jd if c4_jd is not None else end_jd
                    else:  # C4
                        bracket_start, bracket_end = maximum_jd, end_jd

                    def corrected_residual(jd: float) -> float:
                        geom = limb_geometry_at(jd, name)
                        return self._contact_residual(
                            observer_sf, jd, mode, geom["radius_km"]
                        )

                    fa = float(corrected_residual(bracket_start))
                    fb = float(corrected_residual(bracket_end))
                    corrected_jd = None
                    if math.isfinite(fa) and math.isfinite(fb) and fa * fb <= 0.0:
                        corrected_jd = self._solve_root(
                            corrected_residual, bracket_start, bracket_end
                        )
                    else:
                        warnings.append(
                            f"Lunar-limb {name}: no sign-changing root in its phase bracket "
                            f"({bracket_start:.9f}, {bracket_end:.9f} TT JD; "
                            f"residuals={fa:.6g}, {fb:.6g})."
                        )

                    # Store terrain at the corrected contact, or at the original
                    # geometric contact when no corrected root exists.
                    sample_jd = corrected_jd if corrected_jd is not None else float(event_time.tt)
                    geom = limb_geometry_at(sample_jd, name)
                    corrected_time = (
                        self.ts.tt_jd(corrected_jd) if corrected_jd is not None else None
                    )
                    delta = (
                        (corrected_jd - float(event_time.tt)) * 86400.0
                        if corrected_jd is not None else None
                    )
                    limb_contacts[name] = LimbContact(
                        contact=name, time=corrected_time, delta_seconds=delta,
                        selenographic_latitude_deg=geom["latitude"],
                        selenographic_longitude_deg=geom["longitude"],
                        predicted_terrain_altitude_m=geom["altitude_m"],
                        corrected_moon_radius_km=geom["radius_km"],
                        limb_angle_deg=geom["limb_angle_deg"],
                        model_name=geom["model_name"],
                        model_type=geom["model_type"],
                        model_source=geom["model_source"],
                        altitude_uncertainty_m=geom["uncertainty_m"],
                        prediction_status=geom["prediction_status"],
                    )
                    if corrected_time is not None:
                        corrected_times[name] = corrected_time

                if "C2" in corrected_times and "C3" in corrected_times:
                    corrected_duration = (
                        corrected_times["C3"].tt - corrected_times["C2"].tt
                    ) * 86400.0
                    d2 = corrected_times["C2"].tt - contacts.c2.tt
                    d3 = corrected_times["C3"].tt - contacts.c3.tt
                    corrected_maximum = self.ts.tt_jd(maximum_jd + (d2 + d3) / 2.0)
            except Exception as exc:
                warnings.append(f"Lunar-limb correction was not applied: {exc}")

        alt, az, _ = sun_app.altaz(
            pressure_mbar=self.pressure_mbar, temperature_C=self.temperature_c
        )
        speed = width = depth_km = depth_fraction = None
        if include_shadow_metrics and central:
            try:
                metrics = self._shadow_metrics(t_max, observer_sf)
                speed = metrics.get("velocity_km_s")
                width = metrics.get("width_km")
                depth_km = metrics.get("depth_km")
                depth_fraction = metrics.get("depth_fraction")
            except Exception as exc:
                warnings.append(f"Shadow metrics unavailable: {exc}")

        sunrise = sunset = None
        if include_sunrise_sunset and c1_jd is not None and c4_jd is not None:
            try:
                from skyfield import almanac
                from skyfield.api import wgs84
                # sunrise_sunset() adds eph['earth'] internally, so it expects
                # a GeographicPosition (wgs84.latlon), not earth + GeographicPosition.
                topos = wgs84.latlon(
                    latitude_degrees=observer.latitude,
                    longitude_degrees=observer.longitude,
                    elevation_m=observer.elevation_m,
                )
                f = almanac.sunrise_sunset(self.eph, topos)
                rise_set_times, rise_set_values = almanac.find_discrete(
                    self.ts.tt_jd(c1_jd), self.ts.tt_jd(c4_jd), f
                )
                for event_time, event_value in zip(rise_set_times, rise_set_values):
                    if int(event_value) == 1:
                        sunrise = event_time
                    else:
                        sunset = event_time
            except Exception as exc:
                warnings.append(f"Sunrise/sunset calculation unavailable: {exc}")

        zodiac = self._approximate_zodiac_sector(observer_sf, t_max)
        visible_planets = self._visible_planets(observer_sf, t_max) if include_planets else []

        contact_events: dict[str, ContactEvent] = {}
        event_specs = (
            ("C1", "external", contacts.c1, c1_solver),
            ("C2", "internal", contacts.c2, c2_solver),
            ("C3", "internal", contacts.c3, c3_solver),
            ("C4", "external", contacts.c4, c4_solver),
        )
        for event_name, event_type, event_time, solver_result in event_specs:
            if event_time is None:
                continue
            try:
                contact_events[event_name] = self._build_contact_event(
                    observer, observer_sf, event_name, event_type, event_time,
                    solver_result=solver_result,
                    limb_correction=limb_contacts.get(event_name),
                    horizon_profile=horizon_profile,
                )
            except Exception as exc:
                warnings.append(f"{event_name} event metadata unavailable: {exc}")
        try:
            contact_events["MAXIMUM"] = self._build_contact_event(
                observer, observer_sf, "MAXIMUM", "maximum", t_max,
                horizon_profile=horizon_profile,
            )
        except Exception as exc:
            warnings.append(f"Maximum event metadata unavailable: {exc}")
        # Expose the standard chronological order, including MAXIMUM.
        contact_events = {
            name: contact_events[name]
            for name in ("C1", "C2", "MAXIMUM", "C3", "C4")
            if name in contact_events
        }

        observation_geometry = None
        try:
            observation_geometry = self.calculate_observation_geometry(
                observer, t_max, horizon_profile=horizon_profile
            )
        except Exception as exc:
            warnings.append(f"Detailed observation geometry unavailable: {exc}")

        return LocalEclipseResult(
            observer=observer, eclipse_type=eclipse_type, maximum=t_max, contacts=contacts,
            magnitude=float(magnitude), obscuration_percent=float(obscuration),
            moon_sun_radius_ratio=float(ratio), separation_deg=float(min_sep),
            sun_altitude_deg=float(alt.degrees), sun_azimuth_deg=float(az.degrees),
            duration_seconds=duration, partial_phase_duration_seconds=partial_duration,
            central_phase_duration_seconds=central_duration,
            contact_events=contact_events,
            limb_corrected_contacts=limb_contacts,
            limb_corrected_duration_seconds=corrected_duration,
            limb_corrected_maximum=corrected_maximum,
            shadow_velocity_km_s=speed, shadow_path_width_km=width,
            umbral_depth_km=depth_km, umbral_depth_fraction=depth_fraction,
            sunrise=sunrise, sunset=sunset, approximate_zodiac_sector=zodiac,
            visible_planets=visible_planets, is_next_upcoming=is_next, warnings=warnings,
            observation_geometry=observation_geometry,
        )

    def _approximate_zodiac_sector(self, observer_sf: Any, t: Any) -> str | None:
        """Return the source code's approximate ecliptic sector; not an IAU constellation."""
        try:
            _, longitude, _ = observer_sf.at(t).observe(self.sun).apparent().ecliptic_latlon()
            deg = float(longitude.degrees) % 360.0
            boundaries = [
                (33, "Aries"), (52, "Taurus"), (90, "Gemini"), (118, "Cancer"),
                (138, "Leo"), (174, "Virgo"), (217, "Libra"), (242, "Scorpius"),
                (266, "Sagittarius"), (301, "Capricornus"), (329, "Aquarius"), (348, "Pisces"),
            ]
            return next((name for limit, name in boundaries if deg < limit), "Pisces")
        except Exception:
            return None

    def _visible_planets(self, observer_sf: Any, t: Any) -> list[tuple[str, float]]:
        result: list[tuple[str, float]] = []
        at = observer_sf.at(t)
        sun_app = at.observe(self.sun).apparent()
        for segment, name in self._planet_names.items():
            target = self.context.optional_body(segment)
            if target is None:
                continue
            try:
                apparent = at.observe(target).apparent()
                altitude, _, _ = apparent.altaz(
                    pressure_mbar=self.pressure_mbar, temperature_C=self.temperature_c
                )
                if altitude.degrees > 0:
                    result.append((name, float(sun_app.separation_from(apparent).degrees)))
            except Exception:
                continue
        return sorted(result, key=lambda item: item[1])

    def _shadow_state(self, t: Any) -> dict[str, Any] | None:
        """Intersect the shadow axis with WGS84 using Earth-fixed apparent vectors."""
        try:
            from skyfield.framelib import itrs
        except ImportError as exc:  # pragma: no cover
            raise ImportError("Skyfield is required") from exc
        earth_at = self.earth.at(t)
        sun_pos = np.asarray(earth_at.observe(self.sun).apparent().frame_xyz(itrs).km, dtype=float)
        moon_pos = np.asarray(earth_at.observe(self.moon).apparent().frame_xyz(itrs).km, dtype=float)
        axis = moon_pos - sun_pos  # from Sun through Moon toward Earth
        axis_norm = np.linalg.norm(axis)
        if axis_norm == 0:
            return None
        direction = axis / axis_norm
        hit = ray_ellipsoid_intersection(moon_pos, direction)
        if hit is None:
            return None
        moon_sun_distance = float(np.linalg.norm(moon_pos - sun_pos))
        moon_to_ground = float(np.linalg.norm(hit - moon_pos))
        taper = (self.sun_radius_km - self.moon_radius_shadow_km) / moon_sun_distance
        cone_radius = self.moon_radius_shadow_km - moon_to_ground * taper
        latitude, longitude, _ = ecef_to_geodetic(float(hit[0]), float(hit[1]), float(hit[2]))
        return {
            "hit": hit, "sun_position": sun_pos, "moon_position": moon_pos,
            "latitude": latitude, "longitude": longitude,
            "cone_radius_km": cone_radius,
            "shadow_kind": "umbral" if cone_radius >= 0 else "antumbral",
        }

    def calculate_shadow_footprint(
        self,
        when: Any,
        *,
        boundary_samples: int = 180,
    ) -> ShadowFootprint | None:
        """Return the instantaneous central and penumbral cone/ellipsoid footprint.

        The method returns ``None`` when no penumbral cone generatrix intersects
        the WGS84 reference ellipsoid. Boundary arrays retain ``None`` entries
        for rays that miss Earth; missing sections are never silently bridged.
        """
        if (isinstance(boundary_samples, bool) or not isinstance(boundary_samples, int)
                or boundary_samples < 8 or boundary_samples > 4096):
            raise ValueError("boundary_samples must be an integer in [8, 4096]")
        t = self.time(when)
        try:
            from skyfield.framelib import itrs
        except ImportError as exc:  # pragma: no cover - guarded by core dependency
            raise ImportError("Skyfield is required for shadow-footprint geometry") from exc
        earth_at = self.earth.at(t)
        sun_position = np.asarray(
            earth_at.observe(self.sun).apparent().frame_xyz(itrs).km, dtype=np.float64
        )
        moon_position = np.asarray(
            earth_at.observe(self.moon).apparent().frame_xyz(itrs).km, dtype=np.float64
        )
        central_hits = cone_ellipsoid_intersections(
            sun_position, moon_position,
            sun_radius_km=self.sun_radius_km,
            moon_radius_km=self.moon_radius_shadow_km,
            boundary="central", azimuth_samples=boundary_samples,
        )
        penumbra_hits = cone_ellipsoid_intersections(
            sun_position, moon_position,
            sun_radius_km=self.sun_radius_km,
            moon_radius_km=self.moon_radius_shadow_km,
            boundary="penumbra", azimuth_samples=boundary_samples,
        )
        if not any(point is not None for point in penumbra_hits):
            return None

        def to_edges(hits: list[np.ndarray | None]) -> tuple[ShadowCorridorEdge | None, ...]:
            edges: list[ShadowCorridorEdge | None] = []
            for point in hits:
                if point is None:
                    edges.append(None)
                else:
                    latitude, longitude, _ = ecef_to_geodetic(*map(float, point))
                    edges.append(ShadowCorridorEdge(float(latitude), float(longitude)))
            return tuple(edges)

        state = self._shadow_state(t)
        if state is None:
            axis_latitude = axis_longitude = cone_radius = None
            shadow_kind = "axis_misses_earth"
            kinematics = {"velocity_km_s": None, "width_km": None}
            bearing = None
        else:
            axis_latitude = float(state["latitude"])
            axis_longitude = float(state["longitude"])
            cone_radius = float(state["cone_radius_km"])
            shadow_kind = str(state["shadow_kind"])
            kinematics = self._shadow_kinematics(t, state)
            bearing = self._shadow_track_bearing(t, state)
        central = to_edges(central_hits)
        penumbra = to_edges(penumbra_hits)
        central_coverage = sum(point is not None for point in central) / boundary_samples
        penumbra_coverage = sum(point is not None for point in penumbra) / boundary_samples
        notes = [
            "Spherical Sun/Moon radii are used; the central and penumbral cones are intersected with WGS84.",
            "Terrain, atmospheric refraction, lunar limb topography and local horizon obstructions are excluded.",
            "Boundary entries marked null are rays that do not intersect the reference ellipsoid; gaps are not bridged.",
        ]
        if state is None:
            notes.append("The shadow axis does not intersect WGS84 at this instant; a penumbral footprint may still be present.")
        if central_coverage < 1.0:
            notes.append("The sampled central boundary is incomplete on WGS84.")
        if penumbra_coverage < 1.0:
            notes.append("The sampled penumbral boundary is incomplete on WGS84.")
        return ShadowFootprint(
            time=t, axis_latitude=axis_latitude, axis_longitude=axis_longitude,
            shadow_kind=shadow_kind, cone_radius_km=cone_radius,
            central_boundary=central, penumbra_boundary=penumbra,
            track_bearing_deg=bearing,
            shadow_velocity_km_s=kinematics.get("velocity_km_s"),
            cross_track_width_km=kinematics.get("width_km"),
            central_boundary_coverage=central_coverage,
            penumbra_boundary_coverage=penumbra_coverage,
            notes=tuple(notes),
        )

    def _shadow_kinematics(self, t: Any, state: dict[str, Any] | None = None) -> dict[str, float | None]:
        state = state or self._shadow_state(t)
        if state is None:
            return {"velocity_km_s": None, "width_km": None}
        dt = 0.5
        before = self._shadow_state(self.ts.tt_jd(t.tt - dt/86400.0))
        after = self._shadow_state(self.ts.tt_jd(t.tt + dt/86400.0))
        if before is None or after is None:
            return {"velocity_km_s": None, "width_km": 2.0 * abs(float(state["cone_radius_km"]))}
        delta = np.asarray(after["hit"]) - np.asarray(before["hit"])
        distance = float(np.linalg.norm(delta))
        velocity = distance / (2.0 * dt)
        if distance <= 1e-9:
            return {"velocity_km_s": velocity, "width_km": None}
        track_direction = delta / distance
        point = np.asarray(state["hit"])
        normal = np.array([
            point[0] / WGS84_A_KM**2,
            point[1] / WGS84_A_KM**2,
            point[2] / WGS84_B_KM**2,
        ])
        normal /= np.linalg.norm(normal)
        sun_direction = np.asarray(state["sun_position"]) - np.asarray(state["moon_position"])
        sun_direction /= np.linalg.norm(sun_direction)
        sin_h = max(1e-3, float(np.dot(sun_direction, normal)))
        tangent_sun = sun_direction - sin_h * normal
        tangent_norm = np.linalg.norm(tangent_sun)
        if tangent_norm > 1e-9:
            tangent_sun /= tangent_norm
            cos_alpha = max(-1.0, min(1.0, float(np.dot(track_direction, tangent_sun))))
        else:
            cos_alpha = 1.0
        sin_alpha = math.sqrt(max(0.0, 1.0 - cos_alpha*cos_alpha))
        projection = math.sqrt((sin_alpha/sin_h)**2 + cos_alpha*cos_alpha)
        width = 2.0 * abs(float(state["cone_radius_km"])) * projection
        return {"velocity_km_s": velocity, "width_km": width}

    def _shadow_metrics(self, t_max: Any, observer_sf: Any) -> dict[str, float | None]:
        state = self._shadow_state(t_max)
        if state is None:
            return {"velocity_km_s": None, "width_km": None,
                    "depth_km": None, "depth_fraction": None}
        kinematics = self._shadow_kinematics(t_max, state)
        width = kinematics.get("width_km")
        at = observer_sf.at(t_max)
        sun_app = at.observe(self.sun).apparent()
        moon_app = at.observe(self.moon).apparent()
        moon_distance = float(moon_app.distance().km)
        separation_rad = float(sun_app.separation_from(moon_app).radians)
        cone_radius = abs(float(state["cone_radius_km"]))
        depth_fraction = 0.0 if cone_radius < 0.1 else min(1.0, max(0.0, 1.0 - math.tan(separation_rad)*moon_distance/cone_radius))
        depth_km = (width / 2.0 * depth_fraction) if width is not None else None
        return {"velocity_km_s": kinematics.get("velocity_km_s"), "width_km": width,
                "depth_km": depth_km, "depth_fraction": depth_fraction}

    def global_shadow_path(self, start: Any, end: Any, *, samples: int = 101) -> list[ShadowPathPoint]:
        """Return sampled central-axis path points where the umbral/antumbral axis hits Earth."""
        if samples < 2:
            raise ValueError("samples must be at least 2")
        t0, t1 = self.time(start), self.time(end)
        if t1.tt <= t0.tt:
            raise ValueError("end must be later than start")
        jd_values = np.linspace(float(t0.tt), float(t1.tt), samples)
        result: list[ShadowPathPoint] = []
        for jd in jd_values:
            t = self.ts.tt_jd(float(jd))
            state = self._shadow_state(t)
            if state is None:
                continue
            width = self._shadow_kinematics(t, state).get("width_km")
            if width is None:
                width = 2.0 * abs(float(state["cone_radius_km"]))
            width = min(float(width), 900.0)  # retain the source engine's path-width safety cap
            result.append(ShadowPathPoint(
                time=t, latitude=float(state["latitude"]), longitude=float(state["longitude"]),
                width_km=width, shadow_kind=str(state["shadow_kind"]),
            ))
        return result

    def global_path_for_eclipse(self, when: Any, *, search_radius_hours: float = 4.0,
                                samples: int = 101) -> list[ShadowPathPoint]:
        """Find the geocentric maximum near ``when`` and sample its shadow track."""
        maximum = self.find_global_maximum(when)
        # Do not gate this on geocentric disk overlap: parallax can produce a
        # real terrestrial central path even when the geocentric disks miss.
        # global_shadow_path() itself returns [] when the axis misses Earth.
        start = self.ts.tt_jd(maximum.tt - search_radius_hours / 24.0)
        end = self.ts.tt_jd(maximum.tt + search_radius_hours / 24.0)
        return self.global_shadow_path(start, end, samples=samples)

    def _shadow_track_bearing(self, t: Any, state: dict[str, Any] | None = None,
                              *, step_seconds: float = 5.0) -> float | None:
        """Estimate the instantaneous WGS84 ground-track bearing near ``t``.

        A short symmetric time difference is used instead of the bearing between
        user-requested samples. The latter can be badly biased when samples are
        sparse and the ground track curves appreciably between them.
        """
        if state is None:
            state = self._shadow_state(t)
        if state is None:
            return None
        before = self._shadow_state(self.ts.tt_jd(float(t.tt) - step_seconds / 86400.0))
        after = self._shadow_state(self.ts.tt_jd(float(t.tt) + step_seconds / 86400.0))
        if before is not None and after is not None:
            distance, bearing = wgs84_inverse(
                float(before["latitude"]), float(before["longitude"]),
                float(after["latitude"]), float(after["longitude"]),
            )
            return float(bearing) if distance > 1e-9 else None
        if after is not None:
            distance, bearing = wgs84_inverse(
                float(state["latitude"]), float(state["longitude"]),
                float(after["latitude"]), float(after["longitude"]),
            )
            return float(bearing) if distance > 1e-9 else None
        if before is not None:
            distance, bearing = wgs84_inverse(
                float(before["latitude"]), float(before["longitude"]),
                float(state["latitude"]), float(state["longitude"]),
            )
            return float(bearing) if distance > 1e-9 else None
        return None

    @staticmethod
    def _corridor_edge_pair(center_latitude: float, center_longitude: float,
                            boundary_points: list[tuple[float, float]],
                            track_bearing_deg: float | None
                            ) -> tuple[ShadowCorridorEdge | None, ShadowCorridorEdge | None, float | None]:
        """Return left/right cross-track extrema and their local projected span."""
        if track_bearing_deg is None or len(boundary_points) < 2:
            return None, None, None
        offsets: list[tuple[float, ShadowCorridorEdge]] = []
        for latitude, longitude in boundary_points:
            distance, azimuth = wgs84_inverse(center_latitude, center_longitude, latitude, longitude)
            cross_track = distance * math.sin(math.radians(azimuth - track_bearing_deg))
            offsets.append((cross_track, ShadowCorridorEdge(latitude, longitude)))
        left = [item for item in offsets if item[0] < -1e-6]
        right = [item for item in offsets if item[0] > 1e-6]
        if not left or not right:
            return None, None, None
        left_edge = min(left, key=lambda item: item[0])
        right_edge = max(right, key=lambda item: item[0])
        width = right_edge[0] - left_edge[0]
        return left_edge[1], right_edge[1], float(width) if width > 0.0 else None

    @staticmethod
    def _corridor_track_chord(center_latitude: float, center_longitude: float,
                              boundary_points: list[tuple[float, float]],
                              track_bearing_deg: float | None) -> float | None:
        """Intersect the cone boundary with the local track line through its center.

        This is the chord traversed by a fixed center-line observer as the shadow
        translates along its local ground-track direction. It is not the bounding
        projection of the entire footprint onto that direction.
        """
        if track_bearing_deg is None or len(boundary_points) < 3:
            return None
        local_ring: list[tuple[float, float]] = []
        for latitude, longitude in boundary_points:
            distance, azimuth = wgs84_inverse(center_latitude, center_longitude, latitude, longitude)
            angle = math.radians(azimuth - track_bearing_deg)
            local_ring.append((distance * math.cos(angle), distance * math.sin(angle)))

        intersections: list[float] = []
        for index, first in enumerate(local_ring):
            second = local_ring[(index + 1) % len(local_ring)]
            along_1, cross_1 = first
            along_2, cross_2 = second
            if abs(cross_1) <= 1e-9:
                intersections.append(along_1)
            if cross_1 * cross_2 < 0.0:
                fraction = -cross_1 / (cross_2 - cross_1)
                intersections.append(along_1 + fraction * (along_2 - along_1))
        if len(intersections) < 2:
            return None
        intersections.sort()
        unique: list[float] = []
        for value in intersections:
            if not unique or abs(value - unique[-1]) > 1e-6:
                unique.append(value)
        if len(unique) < 2:
            return None
        chord = unique[-1] - unique[0]
        return float(chord) if math.isfinite(chord) and chord > 0.0 else None

    def global_shadow_corridor(self, start: Any, end: Any, *, samples: int = 101,
                               boundary_samples: int = 72) -> ShadowCorridorResult:
        """Calculate central (umbra/antumbra) and penumbral boundaries on WGS84.

        The cone boundaries are sampled by tracing rays from the lunar limb to
        the reference ellipsoid. Left/right limits are relative to the direction
        of the central ground track, not fixed geographic north/south labels.
        Only times where the shadow axis itself intersects Earth are included;
        the full sunrise/sunset penumbral footprint is outside this method's scope.
        """
        if isinstance(samples, bool) or not isinstance(samples, (int, np.integer)) or samples < 2:
            raise ValueError("samples must be an integer >= 2")
        if (isinstance(boundary_samples, bool) or not isinstance(boundary_samples, (int, np.integer))
                or boundary_samples < 16):
            raise ValueError("boundary_samples must be an integer >= 16")
        t0, t1 = self.time(start), self.time(end)
        if float(t1.tt) <= float(t0.tt):
            raise ValueError("end must be later than start")

        raw_samples: list[dict[str, Any]] = []
        for jd in np.linspace(float(t0.tt), float(t1.tt), int(samples)):
            moment = self.ts.tt_jd(float(jd))
            state = self._shadow_state(moment)
            if state is None:
                continue
            sun_position = np.asarray(state["sun_position"], dtype=np.float64)
            moon_position = np.asarray(state["moon_position"], dtype=np.float64)
            central_hits = cone_ellipsoid_intersections(
                sun_position, moon_position, sun_radius_km=self.sun_radius_km,
                moon_radius_km=self.moon_radius_shadow_km, boundary="central",
                azimuth_samples=int(boundary_samples),
            )
            penumbra_hits = cone_ellipsoid_intersections(
                sun_position, moon_position, sun_radius_km=self.sun_radius_km,
                moon_radius_km=self.moon_radius_shadow_km, boundary="penumbra",
                azimuth_samples=int(boundary_samples),
            )

            def geodetic(hits: list[np.ndarray | None]) -> list[tuple[float, float]]:
                coordinates = []
                for hit in hits:
                    if hit is not None:
                        latitude, longitude, _ = ecef_to_geodetic(*map(float, hit))
                        coordinates.append((float(latitude), float(longitude)))
                return coordinates

            raw_samples.append({
                "time": moment, "latitude": float(state["latitude"]),
                "longitude": float(state["longitude"]), "shadow_kind": str(state["shadow_kind"]),
                "central_points": geodetic(central_hits), "penumbra_points": geodetic(penumbra_hits),
                "central_coverage": sum(point is not None for point in central_hits) / int(boundary_samples),
                "penumbra_coverage": sum(point is not None for point in penumbra_hits) / int(boundary_samples),
                "kinematics": self._shadow_kinematics(moment, state),
            })

        notes = [
            "Spherical Sun/Moon radii and apparent Earth-fixed vectors are used.",
            "Cone boundaries intersect the WGS84 reference ellipsoid; terrain, atmosphere and lunar-limb relief are excluded.",
            "Left/right limits are relative to track direction and can swap geographic north/south along a curved or polar path.",
            "Duration fields are first-order estimates: along-track cone chord divided by instantaneous central-axis ground speed; they are not root-solved local contact times.",
            "Track bearing is estimated by a short symmetric time difference around each sample, independently of the requested sampling interval.",
            "Only time samples with a central-axis Earth intersection are returned; complete sunrise/sunset penumbra limits are not computed.",
        ]
        if not raw_samples:
            notes.append("No sampled shadow-axis position intersected WGS84 in the requested interval.")
            return ShadowCorridorResult((), int(samples), int(boundary_samples), notes=tuple(notes))

        output: list[ShadowCorridorSample] = []
        for index, raw in enumerate(raw_samples):
            bearing = self._shadow_track_bearing(raw["time"])
            cl, cr, cw = self._corridor_edge_pair(
                raw["latitude"], raw["longitude"], raw["central_points"], bearing
            )
            pl, pr, pw = self._corridor_edge_pair(
                raw["latitude"], raw["longitude"], raw["penumbra_points"], bearing
            )
            central_chord = self._corridor_track_chord(
                raw["latitude"], raw["longitude"], raw["central_points"], bearing
            ) if raw["central_coverage"] >= 1.0 - 1e-12 else None
            penumbral_chord = self._corridor_track_chord(
                raw["latitude"], raw["longitude"], raw["penumbra_points"], bearing
            ) if raw["penumbra_coverage"] >= 1.0 - 1e-12 else None
            speed = raw["kinematics"].get("velocity_km_s")
            speed = float(speed) if speed is not None and math.isfinite(float(speed)) and float(speed) > 1e-9 else None
            # A fixed site is swept along the local track direction. At low Sun
            # altitudes the WGS84 cone footprint is strongly elongated along-track,
            # so cross-track width / speed is not a valid totality-duration estimate.
            central_duration = central_chord / speed if central_chord is not None and speed else None
            penumbral_duration = penumbral_chord / speed if penumbral_chord is not None and speed else None
            fallback_width = raw["kinematics"].get("width_km")
            center = ShadowPathPoint(
                time=raw["time"], latitude=raw["latitude"], longitude=raw["longitude"],
                width_km=float(cw if cw is not None else (fallback_width or 0.0)),
                shadow_kind=raw["shadow_kind"],
            )
            output.append(ShadowCorridorSample(
                time=raw["time"], center=center, central_left=cl, central_right=cr,
                penumbra_left=pl, penumbra_right=pr, central_width_km=cw,
                penumbral_width_km=pw, shadow_velocity_km_s=speed,
                central_phase_duration_estimate_seconds=central_duration,
                penumbral_duration_estimate_seconds=penumbral_duration, track_bearing_deg=bearing,
                central_boundary_coverage=float(raw["central_coverage"]),
                penumbra_boundary_coverage=float(raw["penumbra_coverage"]),
                central_track_chord_km=central_chord,
                penumbral_track_chord_km=penumbral_chord,
            ))
        if any(item.central_width_km is None for item in output):
            notes.append("Some central widths are unavailable because both cross-track boundary sides were not intersected.")
        if any(item.penumbral_width_km is None for item in output):
            notes.append("Some penumbral widths are unavailable because both cross-track boundary sides were not intersected.")
        if len(output) < int(samples):
            notes.append("Time samples without a central-axis Earth intersection were omitted.")
        return ShadowCorridorResult(tuple(output), int(samples), int(boundary_samples), notes=tuple(notes))

    def global_shadow_corridor_for_eclipse(self, when: Any, *, search_radius_hours: float = 4.0,
                                           samples: int = 101, boundary_samples: int = 72
                                           ) -> ShadowCorridorResult:
        """Find the geocentric maximum near ``when`` and sample its corridor."""
        if isinstance(search_radius_hours, bool):
            raise ValueError("search_radius_hours must be finite and positive")
        try:
            radius = float(search_radius_hours)
        except (TypeError, ValueError) as exc:
            raise ValueError("search_radius_hours must be finite and positive") from exc
        if not math.isfinite(radius) or radius <= 0.0:
            raise ValueError("search_radius_hours must be finite and positive")
        maximum = self.find_global_maximum(when)
        start = self.ts.tt_jd(maximum.tt - radius / 24.0)
        end = self.ts.tt_jd(maximum.tt + radius / 24.0)
        return self.global_shadow_corridor(start, end, samples=samples,
                                            boundary_samples=boundary_samples)

    def plan_observations(
        self,
        observers: Any,
        when: Any,
        *,
        search_window_hours: float = 12.0,
        weights: Any | None = None,
        minimum_sun_altitude_deg: float = 0.0,
        full_sun_altitude_score_deg: float = 45.0,
        maximum_partial_duration_seconds: float = 3600.0,
        limb_model: Any | None = None,
        continue_on_error: bool = True,
    ) -> Any:
        """Rank candidate sites for a solar eclipse using local circumstances.

        The score is a transparent weather-agnostic heuristic based on
        obscuration, Sun altitude at local maximum, and C1-C4 event duration.
        Weather, local horizon obstructions, light pollution, access and
        transport are not modelled. Sites without an eclipse in the requested
        window are returned as ``no_eclipse``; next-eclipse search is disabled.
        """
        from .planner import build_observation_plan

        return build_observation_plan(
            self,
            observers,
            when,
            search_window_hours=search_window_hours,
            weights=weights,
            minimum_sun_altitude_deg=minimum_sun_altitude_deg,
            full_sun_altitude_score_deg=full_sun_altitude_score_deg,
            maximum_partial_duration_seconds=maximum_partial_duration_seconds,
            limb_model=limb_model,
            continue_on_error=continue_on_error,
        )

    def iter_search_cities(
        self,
        when: Any,
        catalog: CityCatalog,
        *,
        country: str | None = None,
        min_magnitude: float = 0.001,
        search_radius_hours: float = 4.0,
        coarse_steps: int = 49,
        refinement_iterations: int = 15,
        batch_size: int = 512,
        include_contacts: bool = False,
        limb_corrector: Any | None = None,
        limb_model: Any | None = None,
    ) -> Iterator[CityEclipseHit]:
        """Yield city hits in bounded batches without retaining the full result list.

        This streaming form preserves catalogue/batch order and is useful when
        result sets are large. Use :meth:`search_cities` when magnitude-sorted
        results are required. City coverage is limited to the supplied dataset.
        ``limb_model`` is the Phase 5 provider name; ``limb_corrector`` remains
        accepted for compatibility. Pass at most one.
        """
        if limb_corrector is not None and limb_model is not None:
            raise ValueError("Pass either limb_model or legacy limb_corrector, not both")
        if limb_model is not None:
            limb_corrector = limb_model
        integer_options = {
            "coarse_steps": (coarse_steps, 5),
            "refinement_iterations": (refinement_iterations, 0),
            "batch_size": (batch_size, 1),
        }
        for option_name, (option_value, minimum) in integer_options.items():
            if isinstance(option_value, bool) or not isinstance(option_value, (int, np.integer)):
                if option_name in {"coarse_steps", "batch_size"}:
                    raise ValueError(
                        "coarse_steps must be >= 5 and batch_size must be >= 1"
                    )
                raise ValueError(f"{option_name} must be an integer >= {minimum}")
            if int(option_value) < minimum:
                if option_name in {"coarse_steps", "batch_size"}:
                    raise ValueError(
                        "coarse_steps must be >= 5 and batch_size must be >= 1"
                    )
                raise ValueError(f"{option_name} must be an integer >= {minimum}")
        coarse_steps = int(coarse_steps)
        refinement_iterations = int(refinement_iterations)
        batch_size = int(batch_size)
        center = self.find_global_maximum(when)
        hours = np.linspace(-search_radius_hours, search_radius_hours, coarse_steps)
        times = self.ts.tt_jd(float(center.tt) + hours / 24.0)
        from skyfield.framelib import itrs
        earth_at = self.earth.at(times)
        sun_nodes = np.asarray(earth_at.observe(self.sun).apparent().frame_xyz(itrs).km, dtype=float).T
        moon_nodes = np.asarray(earth_at.observe(self.moon).apparent().frame_xyz(itrs).km, dtype=float).T

        def batch_indices() -> Iterator[np.ndarray]:
            yield from catalog.iter_index_batches(country, batch_size=batch_size)

        def batch_arguments() -> Iterator[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
            for current_indices in batch_indices():
                yield current_indices, catalog.ecef, catalog.up, sun_nodes, moon_nodes

        def evaluate_batch(arguments: tuple[
            np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray
        ]) -> list[tuple[int, float, float, float, float, float, float]]:
            current_indices, ecef, up_vectors, solar_nodes, lunar_nodes = arguments
            return _evaluate_city_search_batch(
                current_indices, ecef, up_vectors, solar_nodes, lunar_nodes, hours,
                min_magnitude=float(min_magnitude),
                refinement_iterations=refinement_iterations,
                search_radius_hours=float(search_radius_hours),
                sun_radius_km=self.sun_radius_km,
                moon_radius_km=self.moon_radius_visual_km,
            )

        # Each batch owns its temporary NumPy arrays. The iterator emits hits as
        # soon as a batch is evaluated, so callers need not retain every hit.
        for current_batch in batch_arguments():
            candidate_batch = evaluate_batch(current_batch)
            for global_idx, offset_hours, mag, separation, solar_radius, lunar_radius, altitude in candidate_batch:
                is_central = separation <= abs(lunar_radius - solar_radius)
                if is_central:
                    kind = "total" if lunar_radius >= solar_radius else "annular"
                else:
                    kind = "partial"
                local_time = self.ts.tt_jd(
                    float(center.tt) + offset_hours / 24.0
                )
                obscuration = circle_overlap_fraction(
                    solar_radius, lunar_radius, separation
                ) * 100.0
                city = catalog.cities[int(global_idx)]
                local_observer = Observer(
                    city.latitude, city.longitude, city.elevation_m, city.name, city.country
                )
                contacts = None
                limb_corrected_contacts: dict[str, LimbContact] = {}
                if include_contacts:
                    local_result = self.calculate_local(
                        local_observer, local_time, search_window_hours=4.0,
                        find_next_if_none=False, include_sunrise_sunset=False,
                        include_shadow_metrics=False, include_planets=False,
                        limb_corrector=limb_corrector,
                    )
                    if local_result is not None:
                        contacts = local_result.contacts
                        limb_corrected_contacts = local_result.limb_corrected_contacts
                        local_time = local_result.maximum
                        mag = local_result.magnitude
                        obscuration = local_result.obscuration_percent
                        kind = local_result.eclipse_type
                        altitude = local_result.sun_altitude_deg
                        offset_minutes = (local_time.tt - float(center.tt)) * 1440.0
                    else:
                        offset_minutes = offset_hours * 60.0
                else:
                    offset_minutes = offset_hours * 60.0
                yield CityEclipseHit(
                    city=city, maximum=local_time, magnitude=mag,
                    obscuration_percent=float(obscuration), eclipse_type=kind,
                    sun_altitude_deg=float(altitude),
                    offset_from_geocentric_maximum_minutes=float(offset_minutes),
                    contacts=contacts,
                    limb_corrected_contacts=limb_corrected_contacts,
                )

    def search_cities(
        self,
        when: Any,
        catalog: CityCatalog,
        *,
        country: str | None = None,
        min_magnitude: float = 0.001,
        search_radius_hours: float = 4.0,
        coarse_steps: int = 49,
        refinement_iterations: int = 15,
        batch_size: int = 512,
        include_contacts: bool = False,
        limb_corrector: Any | None = None,
        limb_model: Any | None = None,
    ) -> list[CityEclipseHit]:
        """Return magnitude-sorted city hits, preserving the original API contract."""
        hits = list(self.iter_search_cities(
            when, catalog, country=country, min_magnitude=min_magnitude,
            search_radius_hours=search_radius_hours, coarse_steps=coarse_steps,
            refinement_iterations=refinement_iterations, batch_size=batch_size,
            include_contacts=include_contacts, limb_corrector=limb_corrector,
            limb_model=limb_model,
        ))
        hits.sort(key=lambda hit: hit.magnitude, reverse=True)
        return hits

    def find_solar_eclipses_by_country(
        self, start: Any, end: Any, catalog: CityCatalog, country: str, *,
        min_magnitude: float = 0.001, include_contacts: bool = False,
        search_radius_hours: float = 4.0,
        limb_corrector: Any | None = None,
        limb_model: Any | None = None,
    ) -> list[CountryEclipseEvent]:
        """Search all new moons in an interval and report events visible in a country.

        The method searches the city points present in ``catalog``; it cannot infer
        visibility in unsampled locations between those points. ``limb_model`` is
        the Phase 5 provider name; ``limb_corrector`` remains a legacy alias.
        """
        if limb_corrector is not None and limb_model is not None:
            raise ValueError("Pass either limb_model or legacy limb_corrector, not both")
        if limb_model is not None:
            limb_corrector = limb_model
        try:
            from skyfield import almanac
        except ImportError as exc:  # pragma: no cover
            raise ImportError("Skyfield is required for phase searches") from exc
        t0, t1 = self.time(start), self.time(end)
        if t1.tt <= t0.tt:
            raise ValueError("end must be later than start")
        phase_fn = almanac.moon_phases(self.eph)
        phases, values = almanac.find_discrete(t0, t1, phase_fn)
        events: list[CountryEclipseEvent] = []
        for phase_time, phase_value in zip(phases, values):
            if int(phase_value) != 0:
                continue
            global_max = self.find_global_maximum(phase_time, half_window_hours=7.2)
            # Do not reject based on geocentric disk overlap. Local parallax can
            # produce eclipses at surface observers even when the geocenter sees
            # no overlap; search_cities() is the actual country-specific test.
            city_hits = self.search_cities(
                global_max, catalog, country=country, min_magnitude=min_magnitude,
                search_radius_hours=search_radius_hours, include_contacts=include_contacts,
                limb_corrector=limb_corrector,
            )
            if city_hits:
                events.append(CountryEclipseEvent(global_max, country, city_hits))
        return events

    def calculate_lunar_eclipse(
        self, when: Any, *, calendar: str = "historical",
        search_half_window_hours: float = 18.0,
        contact_search_half_window_hours: float = 8.0,
        contact_step_seconds: float = 300.0,
        contact_tolerance_seconds: float = 0.05,
        earth_radius_km: float = WGS84_A_KM,
        moon_radius_km: float | None = None,
        shadow_enlargement: float = 1.0,
        shadow_model: str = "herald_sinnott",
        atmospheric_nel_height_km: float = 87.0,
        flattening_coefficient: float = 0.003353,
        boundary_samples: int = 96,
    ) -> LunarEclipseResult | None:
        """Calculate geocentric lunar-eclipse circumstances near a full moon.

        The default ``shadow_model="herald_sinnott"`` applies the oblate-Earth
        and 87 km notional eclipse-forming-layer prescription described by
        Herald & Sinnott (2014).  It computes angle-dependent penumbral/umbral
        boundaries and solves disk-to-boundary tangencies for P1/U1/U2/U3/U4/P4.
        ``shadow_model="circular"`` remains available for reproducibility of
        the earlier spherical-cone implementation.

        ``calendar`` controls civil-date interpretation and output formatting;
        TT Julian Dates remain the continuous internal time coordinate.  The
        geocentric contacts are not local moonrise/moonset visibility times.
        """
        center = self.time(when, calendar=calendar)
        if moon_radius_km is None:
            # Lunar-eclipse shadow contacts use the mean lunar radius, not the
            # solar-eclipse contact radius configured for lunar limb peaks/valleys.
            moon_radius_km = MEAN_MOON_RADIUS_KM

        def positions_at(jd_tt: float) -> tuple[np.ndarray, np.ndarray]:
            from skyfield.framelib import itrs

            at = self.earth.at(self.ts.tt_jd(float(jd_tt)))
            sun_vector = np.asarray(
                at.observe(self.sun).apparent().frame_xyz(itrs).km, dtype=np.float64
            )
            moon_vector = np.asarray(
                at.observe(self.moon).apparent().frame_xyz(itrs).km, dtype=np.float64
            )
            return sun_vector, moon_vector

        return solve_lunar_eclipse(
            center, positions_at, self.ts.tt_jd,
            calendar=calendar,
            sun_radius_km=self.sun_radius_km,
            earth_radius_km=earth_radius_km,
            moon_radius_km=moon_radius_km,
            shadow_enlargement=shadow_enlargement,
            shadow_model=shadow_model,
            atmospheric_nel_height_km=atmospheric_nel_height_km,
            flattening_coefficient=flattening_coefficient,
            search_half_window_hours=search_half_window_hours,
            contact_search_half_window_hours=contact_search_half_window_hours,
            contact_step_seconds=contact_step_seconds,
            contact_tolerance_seconds=contact_tolerance_seconds,
            boundary_samples=boundary_samples,
        )

    def _lunar_interval_boundary(self, value: Any, *, calendar: str) -> Any:
        """Convert a lunar-search boundary, treating date-only values as midnight.

        The general ``time()`` API deliberately maps a date-only value to noon,
        which is useful as the centre of a single-day calculation window.  An
        interval has different semantics: its date-only boundaries must be at
        civil midnight so an event earlier than noon is not silently omitted.
        """
        if isinstance(value, datetime):
            return self.time(value, calendar=calendar)
        if isinstance(value, date):
            return self.time_from_calendar(
                value.year, value.month, value.day, 0, 0, 0.0, calendar=calendar
            )
        if isinstance(value, str):
            match = re.fullmatch(r"([+-]?\d{1,6})-(\d{2})-(\d{2})", value.strip())
            if match is not None:
                year, month, day = (int(part) for part in match.groups())
                return self.time_from_calendar(
                    year, month, day, 0, 0, 0.0, calendar=calendar
                )
        return self.time(value, calendar=calendar)

    def find_lunar_eclipses(
        self, start: Any, end: Any, *, calendar: str = "historical",
        search_half_window_hours: float = 18.0,
        contact_search_half_window_hours: float = 8.0,
        contact_step_seconds: float = 300.0,
        contact_tolerance_seconds: float = 0.05,
        earth_radius_km: float = WGS84_A_KM,
        moon_radius_km: float | None = None,
        shadow_enlargement: float = 1.0,
        shadow_model: str = "herald_sinnott",
        atmospheric_nel_height_km: float = 87.0,
        flattening_coefficient: float = 0.003353,
        boundary_samples: int = 96,
    ) -> list[LunarEclipseResult]:
        """Find geocentric lunar eclipses whose greatest phase is in ``[start, end)``.

        Date-only strings and ``date`` objects are interpreted as civil-midnight
        boundaries. The end is exclusive, so ``("2025-03-14", "2025-03-15")``
        searches the complete civil day of 14 March. Explicit timestamps remain
        exact instants. Skyfield full-moon phases seed the search. Each candidate is then
        independently tested with the selected Earth-shadow model. The default
        is Herald--Sinnott oblate-Earth geometry; choose ``shadow_model="circular"``
        only to reproduce older spherical-cone results.
        """
        try:
            from skyfield import almanac
        except ImportError as exc:  # pragma: no cover - Skyfield is a core dependency
            raise ImportError("Skyfield is required for lunar-eclipse searches") from exc

        t0 = self._lunar_interval_boundary(start, calendar=calendar)
        t1 = self._lunar_interval_boundary(end, calendar=calendar)
        if float(t1.tt) <= float(t0.tt):
            raise ValueError("end must be later than start")
        if not math.isfinite(search_half_window_hours) or search_half_window_hours <= 0:
            raise ValueError("search_half_window_hours must be finite and positive")

        padding_days = search_half_window_hours / 24.0 + 0.5
        phase_fn = almanac.moon_phases(self.eph)
        phase_times, phase_values = almanac.find_discrete(
            self.ts.tt_jd(float(t0.tt) - padding_days),
            self.ts.tt_jd(float(t1.tt) + padding_days),
            phase_fn,
        )
        events: list[LunarEclipseResult] = []
        for phase_time, phase_value in zip(phase_times, phase_values):
            if int(phase_value) != 2:  # Skyfield phase 2 is Full Moon.
                continue
            result = self.calculate_lunar_eclipse(
                phase_time, calendar=calendar,
                search_half_window_hours=search_half_window_hours,
                contact_search_half_window_hours=contact_search_half_window_hours,
                contact_step_seconds=contact_step_seconds,
                contact_tolerance_seconds=contact_tolerance_seconds,
                earth_radius_km=earth_radius_km,
                moon_radius_km=moon_radius_km,
                shadow_enlargement=shadow_enlargement,
                shadow_model=shadow_model,
                atmospheric_nel_height_km=atmospheric_nel_height_km,
                flattening_coefficient=flattening_coefficient,
                boundary_samples=boundary_samples,
            )
            if result is not None and float(t0.tt) <= float(result.maximum.tt) < float(t1.tt):
                events.append(result)
        events.sort(key=lambda item: float(item.maximum.tt))
        return events

    def find_next_lunar_eclipse(
        self, start: Any, *, search_days: float = 550.0,
        calendar: str = "historical", **kwargs: Any,
    ) -> LunarEclipseResult | None:
        """Find the next geocentric lunar eclipse after ``start``."""
        if not math.isfinite(search_days) or search_days <= 0:
            raise ValueError("search_days must be finite and positive")
        start_time = self._lunar_interval_boundary(start, calendar=calendar)
        end_time = self.ts.tt_jd(float(start_time.tt) + search_days)
        events = self.find_lunar_eclipses(
            start_time, end_time, calendar=calendar, **kwargs
        )
        return events[0] if events else None

    def lunar_eclipse_local_visibility(
        self,
        observer: Observer,
        when: Any,
        *,
        calendar: str = "historical",
        shadow_enlargement: float = 1.0,
        shadow_model: str = "herald_sinnott",
        atmospheric_nel_height_km: float = 87.0,
        flattening_coefficient: float = 0.003353,
        boundary_samples: int = 96,
        moon_radius_km: float = MEAN_MOON_RADIUS_KM,
        horizon_altitude_deg: float = 0.0,
        horizon_profile: HorizonProfile | None = None,
        limb_visibility: str = "upper",
        apply_refraction: bool | None = None,
        pressure_mbar: float | None = None,
        temperature_c: float | None = None,
        sample_interval_seconds: float = 300.0,
        search_margin_hours: float = 36.0,
        include_altitude_profile: bool = True,
    ) -> dict[str, Any] | None:
        """Calculate the locally observable portions of a geocentric lunar eclipse.

        Geocentric P1/U1/U2/greatest/U3/U4/P4 remain the eclipse's physical
        contacts. This method independently solves when the topocentric Moon's
        selected limb crosses the observer's horizon, then intersects those
        above-horizon intervals with the penumbral, partial and total phases.

        The observer's geodetic elevation is included by Skyfield's WGS84
        topocentric position. Refraction is enabled by default when the active
        engine atmosphere config enables it. Unless an explicit station pressure
        is supplied, Skyfield's ``"standard"`` pressure estimate is used and
        adjusted for observer elevation. ``horizon_profile`` is an optional
        caller-supplied azimuth mask; it is not a terrain model inferred by the
        package.

        ``limb_visibility`` controls the horizon-crossing definition:
        ``"upper"`` means any part of the lunar disc is visible (the usual
        moonrise/moonset convention), ``"center"`` means the lunar centre is
        above the mask, and ``"lower"`` means the entire disc is above it.
        The returned altitude profile is sampled, while horizon crossings are
        refined by bisection to ``root_tolerance_seconds``.
        """
        if not isinstance(observer, Observer):
            raise TypeError("observer must be an Observer instance")
        if horizon_profile is not None and not isinstance(horizon_profile, HorizonProfile):
            raise TypeError("horizon_profile must be a HorizonProfile or None")
        if limb_visibility not in {"upper", "center", "lower"}:
            raise ValueError("limb_visibility must be 'upper', 'center', or 'lower'")
        if not isinstance(include_altitude_profile, bool):
            raise TypeError("include_altitude_profile must be a boolean")
        if apply_refraction is None:
            atmosphere = getattr(self.config, "atmosphere", None)
            apply_refraction = bool(
                getattr(atmosphere, "refraction_enabled", self.pressure_mbar > 0.0)
            )
        if not isinstance(apply_refraction, bool):
            raise TypeError("apply_refraction must be a boolean")
        if pressure_mbar is not None:
            if isinstance(pressure_mbar, bool):
                raise ValueError("pressure_mbar must be finite and > 0 when supplied")
            pressure_mbar = float(pressure_mbar)
            if not math.isfinite(pressure_mbar) or pressure_mbar <= 0.0:
                raise ValueError("pressure_mbar must be finite and > 0 when supplied")
        if temperature_c is None:
            temperature_c = float(self.temperature_c)
        elif isinstance(temperature_c, bool):
            raise ValueError("temperature_c must be finite and above absolute zero")
        else:
            temperature_c = float(temperature_c)
        if not math.isfinite(temperature_c) or temperature_c <= -273.15:
            raise ValueError("temperature_c must be finite and above absolute zero")
        if isinstance(moon_radius_km, bool):
            raise ValueError("moon_radius_km must be finite and positive")
        moon_radius_km = float(moon_radius_km)
        if not math.isfinite(moon_radius_km) or moon_radius_km <= 0.0:
            raise ValueError("moon_radius_km must be finite and positive")
        if isinstance(horizon_altitude_deg, bool):
            raise ValueError("horizon_altitude_deg must be finite and in [-10, 90]")
        horizon_altitude_deg = float(horizon_altitude_deg)
        if not math.isfinite(horizon_altitude_deg) or not -10.0 <= horizon_altitude_deg <= 90.0:
            raise ValueError("horizon_altitude_deg must be finite and in [-10, 90]")
        numeric_options = (sample_interval_seconds, search_margin_hours)
        if any(isinstance(value, bool) for value in numeric_options):
            raise ValueError("sampling interval and search margin must be numeric")
        sample_interval_seconds = float(sample_interval_seconds)
        search_margin_hours = float(search_margin_hours)
        if not math.isfinite(sample_interval_seconds) or not 1.0 <= sample_interval_seconds <= 3600.0:
            raise ValueError("sample_interval_seconds must be between 1 and 3600")
        if not math.isfinite(search_margin_hours) or not 1.0 <= search_margin_hours <= 72.0:
            raise ValueError("search_margin_hours must be between 1 and 72")

        event = self.calculate_lunar_eclipse(
            when,
            calendar=calendar,
            shadow_enlargement=shadow_enlargement,
            shadow_model=shadow_model,
            atmospheric_nel_height_km=atmospheric_nel_height_km,
            flattening_coefficient=flattening_coefficient,
            boundary_samples=boundary_samples,
            moon_radius_km=moon_radius_km,
        )
        if event is None:
            return None
        contacts = event.contacts.as_dict()
        penumbral_start = contacts.get("P1")
        penumbral_end = contacts.get("P4")
        if penumbral_start is None or penumbral_end is None:
            raise RuntimeError("a lunar eclipse result must include P1 and P4")
        event_start_jd = float(penumbral_start.tt)
        event_end_jd = float(penumbral_end.tt)
        if event_end_jd <= event_start_jd:
            raise RuntimeError("lunar eclipse P4 must be later than P1")

        observer_sf = self._observer(observer)
        use_refraction = bool(apply_refraction)
        # "standard" asks Skyfield to estimate pressure from the observer's
        # elevation; a numeric value is interpreted as station pressure in mbar.
        if use_refraction:
            atmosphere_config = getattr(self, "atmosphere_config", None)
            configured_pressure = float(getattr(
                atmosphere_config, "pressure_mbar", self.pressure_mbar
            ))
            if pressure_mbar is not None:
                pressure_for_altaz: float | str = pressure_mbar
            elif configured_pressure > 0.0 and not math.isclose(
                configured_pressure, 1013.25, rel_tol=0.0, abs_tol=1e-6
            ):
                # A non-default engine pressure is treated as a station-pressure
                # override. The unmodified default delegates elevation scaling to Skyfield.
                pressure_for_altaz = configured_pressure
            else:
                pressure_for_altaz = "standard"
            altitude_kwargs = {
                "temperature_C": temperature_c,
                "pressure_mbar": pressure_for_altaz,
            }
        else:
            altitude_kwargs = {}

        def evaluate(jd_values: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
            times = self.ts.tt_jd(jd_values)
            observed = observer_sf.at(times).observe(self.moon).apparent()
            altitude, azimuth, distance = observed.altaz(**altitude_kwargs)
            altitude_values = np.asarray(altitude.degrees, dtype=np.float64)
            azimuth_values = np.asarray(azimuth.degrees, dtype=np.float64) % 360.0
            distance_values = np.asarray(distance.km, dtype=np.float64)
            semidiameter = np.degrees(
                np.arcsin(np.clip(moon_radius_km / distance_values, -1.0, 1.0))
            )
            if horizon_profile is None:
                horizon_values = np.full_like(altitude_values, horizon_altitude_deg)
            else:
                horizon_values = np.fromiter(
                    (horizon_altitude_deg + horizon_profile.altitude_at(float(value))
                     for value in np.ravel(azimuth_values)),
                    dtype=np.float64,
                    count=azimuth_values.size,
                ).reshape(azimuth_values.shape)
            if limb_visibility == "upper":
                limb_offset = semidiameter
            elif limb_visibility == "lower":
                limb_offset = -semidiameter
            else:
                limb_offset = np.zeros_like(semidiameter)
            clearance = altitude_values + limb_offset - horizon_values
            return altitude_values, azimuth_values, semidiameter, clearance

        def scalar_clearance(jd_value: float) -> float:
            return float(evaluate(float(jd_value))[3])

        margin_days = search_margin_hours / 24.0
        search_start_jd = event_start_jd - margin_days
        search_end_jd = event_end_jd + margin_days
        duration_seconds = (search_end_jd - search_start_jd) * 86400.0
        sample_count = max(3, int(math.ceil(duration_seconds / sample_interval_seconds)) + 1)
        sample_jds = np.linspace(search_start_jd, search_end_jd, sample_count)
        contact_jds = [
            float(value.tt) for value in contacts.values() if value is not None
        ]
        # Include every published contact and both outer eclipse boundaries exactly
        # in the time series, regardless of the selected regular sampling cadence.
        sample_jds = np.unique(np.concatenate((
            sample_jds,
            np.asarray([event_start_jd, event_end_jd, *contact_jds], dtype=np.float64),
        )))
        altitudes, azimuths, semidiameters, clearances = evaluate(sample_jds)
        if not all(np.all(np.isfinite(values)) for values in (
            altitudes, azimuths, semidiameters, clearances
        )):
            raise RuntimeError("topocentric lunar visibility returned non-finite geometry")

        def refine_crossing(left_jd: float, right_jd: float, left_value: float) -> float:
            left, right = float(left_jd), float(right_jd)
            f_left = float(left_value)
            for _ in range(80):
                middle = (left + right) / 2.0
                f_middle = scalar_clearance(middle)
                if right - left <= 0.1 / 86400.0 or abs(f_middle) <= 1e-11:
                    return middle
                if f_left * f_middle <= 0.0:
                    right = middle
                else:
                    left, f_left = middle, f_middle
            return (left + right) / 2.0

        crossings: list[dict[str, Any]] = []
        for index in range(len(sample_jds) - 1):
            left_value = float(clearances[index])
            right_value = float(clearances[index + 1])
            # Compare the visibility side rather than multiplying residuals:
            # this also catches a root that lands exactly on a sampled epoch.
            if (left_value >= 0.0) == (right_value >= 0.0):
                continue
            left_jd = float(sample_jds[index])
            right_jd = float(sample_jds[index + 1])
            if abs(left_value) <= 1e-13:
                root_jd = left_jd
            elif abs(right_value) <= 1e-13:
                root_jd = right_jd
            else:
                root_jd = refine_crossing(left_jd, right_jd, left_value)
            crossing_kind = "moonrise" if left_value < right_value else "moonset"
            crossing_alt, crossing_az, crossing_radius, crossing_clearance = evaluate(root_jd)
            crossings.append({
                "jd_tt": root_jd,
                "kind": crossing_kind,
                "time_utc": time_to_utc_iso(self.ts.tt_jd(root_jd), calendar=calendar),
                "moon_altitude_deg": float(crossing_alt),
                "moon_azimuth_deg": float(crossing_az),
                "moon_semidiameter_deg": float(crossing_radius),
                "horizon_clearance_deg": float(crossing_clearance),
            })

        # Build complete above-horizon intervals over the search window, then
        # clip them to the eclipse and to each geocentric phase interval.
        above_intervals: list[tuple[float, float]] = []
        is_above = bool(float(clearances[0]) >= 0.0)
        interval_start = search_start_jd if is_above else None
        for crossing in crossings:
            crossing_jd = float(crossing["jd_tt"])
            if crossing["kind"] == "moonset" and is_above:
                above_intervals.append((float(interval_start), crossing_jd))
                interval_start = None
                is_above = False
            elif crossing["kind"] == "moonrise" and not is_above:
                interval_start = crossing_jd
                is_above = True
        if is_above and interval_start is not None:
            above_intervals.append((float(interval_start), search_end_jd))

        def intersect_phase(
            start_jd: float | None,
            end_jd: float | None,
            start_contact: str,
            end_contact: str,
        ) -> list[dict[str, Any]]:
            if start_jd is None or end_jd is None or end_jd <= start_jd:
                return []
            visible: list[dict[str, Any]] = []
            for horizon_start, horizon_end in above_intervals:
                clipped_start = max(start_jd, horizon_start)
                clipped_end = min(end_jd, horizon_end)
                if clipped_end <= clipped_start:
                    continue
                start_source = (
                    start_contact
                    if abs(clipped_start - start_jd) <= 0.1 / 86400.0
                    else "moonrise"
                )
                end_source = (
                    end_contact
                    if abs(clipped_end - end_jd) <= 0.1 / 86400.0
                    else "moonset"
                )
                visible.append({
                    "start_utc": time_to_utc_iso(
                        self.ts.tt_jd(clipped_start), calendar=calendar
                    ),
                    "end_utc": time_to_utc_iso(
                        self.ts.tt_jd(clipped_end), calendar=calendar
                    ),
                    "duration_seconds": (clipped_end - clipped_start) * 86400.0,
                    "start_cause": start_source,
                    "end_cause": end_source,
                })
            return visible

        penumbral_intervals = intersect_phase(
            event_start_jd, event_end_jd, "P1", "P4"
        )
        partial_intervals = intersect_phase(
            float(contacts["U1"].tt) if contacts.get("U1") is not None else None,
            float(contacts["U4"].tt) if contacts.get("U4") is not None else None,
            "U1", "U4",
        )
        totality_intervals = intersect_phase(
            float(contacts["U2"].tt) if contacts.get("U2") is not None else None,
            float(contacts["U3"].tt) if contacts.get("U3") is not None else None,
            "U2", "U3",
        )

        def contact_details() -> dict[str, Any]:
            details: dict[str, Any] = {}
            for name, phase_time in contacts.items():
                if phase_time is None:
                    details[name] = None
                    continue
                alt, az, radius, clearance = evaluate(float(phase_time.tt))
                horizon_value = horizon_altitude_deg + (
                    horizon_profile.altitude_at(float(az)) if horizon_profile is not None else 0.0
                )
                details[name] = {
                    "time_utc": time_to_utc_iso(phase_time, calendar=calendar),
                    "moon_altitude_deg": float(alt),
                    "moon_azimuth_deg": float(az),
                    "moon_semidiameter_deg": float(radius),
                    "horizon_altitude_deg": float(horizon_value),
                    "horizon_clearance_deg": float(clearance),
                    "visible": bool(float(clearance) >= 0.0),
                }
            return details

        event_sample_mask = (sample_jds >= event_start_jd) & (sample_jds <= event_end_jd)
        event_sample_jds = sample_jds[event_sample_mask]
        event_altitudes = altitudes[event_sample_mask]
        event_azimuths = azimuths[event_sample_mask]
        event_semidiameters = semidiameters[event_sample_mask]
        event_clearances = clearances[event_sample_mask]
        if len(event_sample_jds):
            min_index = int(np.argmin(event_altitudes))
            max_index = int(np.argmax(event_altitudes))
            altitude_extrema = {
                "minimum_deg": float(event_altitudes[min_index]),
                "minimum_time_utc": time_to_utc_iso(
                    self.ts.tt_jd(float(event_sample_jds[min_index])), calendar=calendar
                ),
                "maximum_deg": float(event_altitudes[max_index]),
                "maximum_time_utc": time_to_utc_iso(
                    self.ts.tt_jd(float(event_sample_jds[max_index])), calendar=calendar
                ),
                "sampling_interval_seconds": sample_interval_seconds,
            }
        else:  # pragma: no cover - P1/P4 are inserted above
            altitude_extrema = None

        altitude_profile: list[dict[str, Any]] = []
        if include_altitude_profile:
            for jd_value, altitude_value, azimuth_value, radius_value, clearance_value in zip(
                event_sample_jds, event_altitudes, event_azimuths,
                event_semidiameters, event_clearances,
            ):
                altitude_profile.append({
                    "time_utc": time_to_utc_iso(
                        self.ts.tt_jd(float(jd_value)), calendar=calendar
                    ),
                    "moon_altitude_deg": float(altitude_value),
                    "moon_azimuth_deg": float(azimuth_value),
                    "moon_semidiameter_deg": float(radius_value),
                    "horizon_clearance_deg": float(clearance_value),
                    "visible": bool(float(clearance_value) >= 0.0),
                })

        visible_duration = sum(
            float(item["duration_seconds"]) for item in penumbral_intervals
        )
        event_duration = (event_end_jd - event_start_jd) * 86400.0
        if not penumbral_intervals:
            visibility_status = "not_visible"
        elif visible_duration >= event_duration - 0.2:
            visibility_status = "visible_throughout"
        else:
            visibility_status = "partially_visible"

        horizon_crossings = [
            {key: value for key, value in item.items() if key != "jd_tt"}
            for item in crossings
        ]
        moonrises = [item["time_utc"] for item in crossings if item["kind"] == "moonrise"]
        moonsets = [item["time_utc"] for item in crossings if item["kind"] == "moonset"]
        max_contact = contact_details().get("greatest")
        first_visible = penumbral_intervals[0] if penumbral_intervals else None
        last_visible = penumbral_intervals[-1] if penumbral_intervals else None
        return {
            "event_type": "lunar_eclipse_local_visibility",
            "observer": {
                "name": observer.name,
                "country": observer.country,
                "latitude_deg": observer.latitude,
                "longitude_deg": observer.longitude,
                "elevation_m": observer.elevation_m,
            },
            "visibility_status": visibility_status,
            "visible_at_greatest": bool(max_contact and max_contact["visible"]),
            "moonrise_utc": moonrises,
            "moonset_utc": moonsets,
            "horizon_crossings": horizon_crossings,
            "local_event_start_utc": (
                first_visible["start_utc"] if first_visible else None
            ),
            "local_event_end_utc": (
                last_visible["end_utc"] if last_visible else None
            ),
            "observable_intervals": penumbral_intervals,
            "phase_visibility": {
                "penumbral": {
                    "visible": bool(penumbral_intervals),
                    "intervals": penumbral_intervals,
                },
                "partial": {
                    "visible": bool(partial_intervals),
                    "intervals": partial_intervals,
                },
                "totality": {
                    "visible": bool(totality_intervals),
                    "intervals": totality_intervals,
                },
            },
            "contact_visibility": contact_details(),
            "moon_altitude_extrema_during_eclipse": altitude_extrema,
            "altitude_profile": altitude_profile,
            "visibility_model": {
                "limb_visibility": limb_visibility,
                "moon_radius_km": moon_radius_km,
                "horizon_altitude_deg": horizon_altitude_deg,
                "horizon_profile": horizon_profile.name if horizon_profile else None,
                "refraction_applied": use_refraction,
                "pressure_mbar": (
                    pressure_for_altaz if use_refraction else None
                ),
                "temperature_c": temperature_c if use_refraction else None,
                "observer_elevation_m": observer.elevation_m,
                "sample_interval_seconds": sample_interval_seconds,
                "root_tolerance_seconds": 0.1,
                "note": (
                    "Moonrise/moonset are upper-limb horizon crossings by default. "
                    "Atmospheric refraction is an approximate standard-atmosphere model; "
                    "local weather, extinction, diffraction and terrain outside the "
                    "supplied horizon profile are not modelled."
                ),
            },
            "eclipse": event.to_dict(calendar=calendar),
        }

    def lunar_eclipse_city_visibility(
        self, when: Any, catalog: CityCatalog, *, country: str | None = None,
        calendar: str = "historical", minimum_altitude_deg: float = -0.5,
        visibility_window: str = "greatest", sample_interval_seconds: float = 300.0,
        shadow_enlargement: float = 1.0, shadow_model: str = "herald_sinnott",
        atmospheric_nel_height_km: float = 87.0,
        flattening_coefficient: float = 0.003353,
    ) -> list[dict[str, Any]]:
        """Find catalogue cities where some or all of a lunar eclipse is visible.

        ``visibility_window="greatest"`` preserves the original fast filter:
        the Moon's geometric centre must exceed ``minimum_altitude_deg`` at
        greatest eclipse. ``visibility_window="any"`` samples the complete
        P1--P4 interval and includes a city when the Moon's centre exceeds that
        threshold at any sample, even when it is below the horizon at greatest
        eclipse. The latter mode is a catalogue-screening operation; call
        :meth:`lunar_eclipse_local_visibility` for refined moonrise/moonset,
        refraction, skyline masks and exact local phase intervals.
        """
        if not -90.0 <= minimum_altitude_deg <= 90.0:
            raise ValueError("minimum_altitude_deg must be in [-90, 90]")
        if visibility_window not in {"greatest", "any"}:
            raise ValueError("visibility_window must be 'greatest' or 'any'")
        if isinstance(sample_interval_seconds, bool):
            raise ValueError("sample_interval_seconds must be between 1 and 3600")
        sample_interval_seconds = float(sample_interval_seconds)
        if not math.isfinite(sample_interval_seconds) or not 1.0 <= sample_interval_seconds <= 3600.0:
            raise ValueError("sample_interval_seconds must be between 1 and 3600")
        event = self.calculate_lunar_eclipse(
            when, calendar=calendar, shadow_enlargement=shadow_enlargement,
            shadow_model=shadow_model,
            atmospheric_nel_height_km=atmospheric_nel_height_km,
            flattening_coefficient=flattening_coefficient,
        )
        if event is None:
            return []

        from skyfield.framelib import itrs

        indices = catalog.indices_for_country(country)
        if len(indices) == 0:
            return []
        selected_ecef = catalog.ecef[indices]
        selected_up = catalog.up[indices]
        phase_altitudes: dict[str, np.ndarray] = {}
        for phase_name, phase_time in event.contacts.as_dict().items():
            if phase_time is None:
                continue
            at = self.earth.at(phase_time)
            moon_position = np.asarray(
                at.observe(self.moon).apparent().frame_xyz(itrs).km, dtype=np.float64
            )
            moon_vectors = moon_position[np.newaxis, :] - selected_ecef
            distances = np.linalg.norm(moon_vectors, axis=1)
            directions = moon_vectors / distances[:, np.newaxis]
            phase_altitudes[phase_name] = np.degrees(
                np.arcsin(np.clip(np.sum(directions * selected_up, axis=1), -1.0, 1.0))
            )
        maximum_altitude = phase_altitudes.get("greatest")
        if maximum_altitude is None:
            return []

        first_visible_jd = np.full(len(indices), np.nan, dtype=np.float64)
        last_visible_jd = np.full(len(indices), np.nan, dtype=np.float64)
        highest_altitude = maximum_altitude.copy()
        if visibility_window == "greatest":
            visible_at_maximum = maximum_altitude > minimum_altitude_deg
            visible_any = visible_at_maximum.copy()
            resolution_used: float | None = None
        else:
            p1 = event.contacts.p1
            p4 = event.contacts.p4
            if p1 is None or p4 is None:
                return []
            start_jd, end_jd = float(p1.tt), float(p4.tt)
            if end_jd <= start_jd:
                raise RuntimeError("lunar eclipse P4 must be later than P1")
            duration_seconds = (end_jd - start_jd) * 86400.0
            sample_count = max(3, int(math.ceil(duration_seconds / sample_interval_seconds)) + 1)
            sample_jds = np.linspace(start_jd, end_jd, sample_count)
            # Ensure contacts and greatest eclipse are evaluated exactly.
            contact_jds = [
                float(value.tt) for value in event.contacts.as_dict().values()
                if value is not None
            ]
            sample_jds = np.unique(np.concatenate((
                sample_jds, np.asarray(contact_jds, dtype=np.float64)
            )))
            all_at = self.earth.at(self.ts.tt_jd(sample_jds))
            moon_positions = np.asarray(
                all_at.observe(self.moon).apparent().frame_xyz(itrs).km,
                dtype=np.float64,
            )
            if moon_positions.ndim == 1:
                moon_positions = moon_positions.reshape(3, 1)
            if moon_positions.shape[0] == 3:
                moon_positions = moon_positions.T
            elif moon_positions.shape[1] != 3:
                raise RuntimeError("Skyfield returned an unexpected ITRS Moon position shape")
            visible_any = np.zeros(len(indices), dtype=bool)
            for jd_value, moon_position in zip(sample_jds, moon_positions):
                moon_vectors = moon_position[np.newaxis, :] - selected_ecef
                distances = np.linalg.norm(moon_vectors, axis=1)
                directions = moon_vectors / distances[:, np.newaxis]
                altitude_values = np.degrees(np.arcsin(np.clip(
                    np.sum(directions * selected_up, axis=1), -1.0, 1.0
                )))
                highest_altitude = np.maximum(highest_altitude, altitude_values)
                visible_now = altitude_values > minimum_altitude_deg
                new_visibility = visible_now & ~visible_any
                first_visible_jd[new_visibility] = float(jd_value)
                last_visible_jd[visible_now] = float(jd_value)
                visible_any |= visible_now
            visible_at_maximum = maximum_altitude > minimum_altitude_deg
            resolution_used = sample_interval_seconds

        event_payload = event.to_dict(calendar=calendar)
        output: list[dict[str, Any]] = []
        for local_index, global_index in enumerate(indices):
            if not visible_any[local_index]:
                continue
            phase_visibility = {
                name: {
                    "moon_altitude_deg": float(values[local_index]),
                    "visible": float(values[local_index]) > minimum_altitude_deg,
                }
                for name, values in phase_altitudes.items()
            }
            visible_phases = [
                name for name, values in phase_visibility.items() if values["visible"]
            ]
            first_jd = float(first_visible_jd[local_index])
            last_jd = float(last_visible_jd[local_index])
            output.append({
                "city": catalog.cities[int(global_index)],
                "maximum": event.maximum,
                "moon_altitude_deg": float(maximum_altitude[local_index]),
                "highest_moon_altitude_deg_during_eclipse": float(
                    highest_altitude[local_index]
                ),
                "penumbral_magnitude": event.penumbral_magnitude,
                "umbral_magnitude": event.umbral_magnitude,
                "approximate_umbral_magnitude": event.umbral_magnitude,
                "eclipse_type": event.eclipse_type,
                "visible_at_maximum": bool(visible_at_maximum[local_index]),
                "visible_during_eclipse": True,
                "visibility_window": visibility_window,
                "first_visible_sample_utc": (
                    time_to_utc_iso(self.ts.tt_jd(first_jd), calendar=calendar)
                    if math.isfinite(first_jd) else None
                ),
                "last_visible_sample_utc": (
                    time_to_utc_iso(self.ts.tt_jd(last_jd), calendar=calendar)
                    if math.isfinite(last_jd) else None
                ),
                "visibility_sample_interval_seconds": resolution_used,
                "visibility_threshold": {
                    "moon_center_altitude_deg": minimum_altitude_deg,
                    "refraction_applied": False,
                    "note": (
                        "Geometric centre-altitude screening only; use "
                        "lunar_eclipse_local_visibility() for refraction, lunar-limb "
                        "rise/set and refined phase-overlap intervals."
                    ),
                },
                "phase_visibility": phase_visibility,
                "visible_contact_phases": visible_phases,
                "event": event_payload,
            })
        output.sort(
            key=lambda row: row["highest_moon_altitude_deg_during_eclipse"],
            reverse=True,
        )
        return output

    def format_report(self, result: LocalEclipseResult, *, language: str = "en") -> str:
        """Human-readable compact report; structured result remains the primary API."""
        ro = language.casefold().startswith("ro")
        labels = {
            "type": "Tip" if ro else "Type",
            "magnitude": "Magnitudine" if ro else "Magnitude",
            "obscuration": "Acoperire" if ro else "Obscuration",
            "max": "Maxim" if ro else "Maximum",
            "duration": "Durata fazei centrale" if ro else "Central-phase duration",
            "alt": "Altitudine Soare" if ro else "Sun altitude",
            "azi": "Azimut Soare" if ro else "Sun azimuth",
        }
        lines = [
            f"{labels['type']}: {result.eclipse_type}",
            f"{labels['max']}: {time_to_utc_iso(result.maximum)}",
            f"{labels['magnitude']}: {result.magnitude:.5f}",
            f"{labels['obscuration']}: {result.obscuration_percent:.2f}%",
            f"{labels['alt']}: {result.sun_altitude_deg:.2f}°",
            f"{labels['azi']}: {result.sun_azimuth_deg:.2f}°",
        ]
        if result.duration_seconds is not None and result.duration_seconds > 0:
            lines.append(f"{labels['duration']}: {result.duration_seconds:.1f} s")
        if result.partial_phase_duration_seconds is not None:
            label = "Durata totală C1-C4" if ro else "Total event span C1-C4"
            lines.append(f"{label}: {result.partial_phase_duration_seconds:.1f} s")
        for name, event_time in result.contacts.as_dict().items():
            lines.append(f"{name}: {time_to_utc_iso(event_time) if event_time is not None else '—'}")
        if result.limb_corrected_contacts:
            lines.append("Lunar-limb corrected contacts:")
            for name, data in result.limb_corrected_contacts.items():
                lines.append(
                    f"  {name}L: {time_to_utc_iso(data.time) if data.time is not None else '—'} "
                    f"(shift {data.delta_seconds if data.delta_seconds is not None else float('nan'):.3f} s)"
                )
        if result.shadow_velocity_km_s is not None:
            lines.append(f"Shadow velocity: {result.shadow_velocity_km_s:.3f} km/s")
        if result.shadow_path_width_km is not None:
            lines.append(f"Shadow width: {result.shadow_path_width_km:.1f} km")
        if result.warnings:
            lines.extend(f"Warning: {warning}" for warning in result.warnings)
        return "\n".join(lines)
