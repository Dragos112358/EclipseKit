"""Independent solar-eclipse calculations from published Besselian elements.

The implementation accepts explicit, already-derived Besselian coefficients.
It does not silently derive elements from the active planetary ephemeris.
Polynomial independent variable ``t`` is hours from ``epoch_tt_jd``; angular
coefficients are in degrees, distances/radii are Earth-equatorial radii, and
``tan_f1``/``tan_f2`` are dimensionless cone-angle tangents.

The local reduction follows the fundamental-plane geometry in the Explanatory
Supplement and the published NASA/Stellarium Besselian convention. See
``docs/BESSELIAN_BACKEND.md`` for conventions and limitations.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path
from typing import Any, Callable, Literal, Mapping

from .config import BesselianConfig, SolverConfig
from .contacts import RootResult, golden_section_minimize, solve_root
from .models import Observer

MuConvention = Literal["ephemeris", "ut1"]
_ELEMENT_NAMES = ("x", "y", "d", "mu", "l1", "l2")


@dataclass(frozen=True, slots=True)
class BesselianPolynomial:
    """Polynomial coefficients in ascending order: c0 + c1*t + ... ."""

    coefficients: tuple[float, ...]

    def __post_init__(self) -> None:
        values = tuple(float(value) for value in self.coefficients)
        if not 1 <= len(values) <= 4:
            raise ValueError("Besselian polynomials require 1 to 4 coefficients")
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Besselian polynomial coefficients must be finite")
        object.__setattr__(self, "coefficients", values)

    def evaluate(self, hours: float) -> float:
        """Evaluate the polynomial with Horner's method."""
        value = float(hours)
        if not math.isfinite(value):
            raise ValueError("polynomial time must be finite")
        result = 0.0
        for coefficient in reversed(self.coefficients):
            result = result * value + coefficient
        return result

    def derivative(self, hours: float) -> float:
        """Evaluate the first derivative per hour."""
        value = float(hours)
        if not math.isfinite(value):
            raise ValueError("polynomial time must be finite")
        result = 0.0
        for power in range(len(self.coefficients) - 1, 0, -1):
            result = result * value + power * self.coefficients[power]
        return result


@dataclass(frozen=True, slots=True)
class BesselianElements:
    """Six polynomial elements plus the two constant cone-angle tangents.

    ``mu_convention='ephemeris'`` is appropriate for the NASA/GSFC published
    polynomial tables. The local reduction applies the ΔT correction to μ.
    Set ``mu_convention='ut1'`` only when μ has already been reduced to UT1.
    """

    epoch_tt_jd: float
    x: BesselianPolynomial | tuple[float, ...]
    y: BesselianPolynomial | tuple[float, ...]
    d: BesselianPolynomial | tuple[float, ...]
    mu: BesselianPolynomial | tuple[float, ...]
    l1: BesselianPolynomial | tuple[float, ...]
    l2: BesselianPolynomial | tuple[float, ...]
    tan_f1: float
    tan_f2: float
    validity_start_hours: float = -3.0
    validity_end_hours: float = 3.0
    mu_convention: MuConvention = "ephemeris"
    source: str | None = None
    ephemeris: str | None = None

    def __post_init__(self) -> None:
        epoch = float(self.epoch_tt_jd)
        if not math.isfinite(epoch):
            raise ValueError("epoch_tt_jd must be finite")
        object.__setattr__(self, "epoch_tt_jd", epoch)
        for name in _ELEMENT_NAMES:
            value = getattr(self, name)
            polynomial = value if isinstance(value, BesselianPolynomial) else BesselianPolynomial(tuple(value))
            object.__setattr__(self, name, polynomial)
        for name in ("tan_f1", "tan_f2"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and >= 0")
            object.__setattr__(self, name, value)
        start = float(self.validity_start_hours)
        end = float(self.validity_end_hours)
        if not (math.isfinite(start) and math.isfinite(end) and start < end):
            raise ValueError("validity_start_hours must be finite and smaller than validity_end_hours")
        object.__setattr__(self, "validity_start_hours", start)
        object.__setattr__(self, "validity_end_hours", end)
        if self.mu_convention not in {"ephemeris", "ut1"}:
            raise ValueError("mu_convention must be 'ephemeris' or 'ut1'")
        if self.source is not None and not str(self.source).strip():
            raise ValueError("source must be a non-empty string or None")
        if self.ephemeris is not None and not str(self.ephemeris).strip():
            raise ValueError("ephemeris must be a non-empty string or None")

    def hours_from_epoch(self, jd_tt: float) -> float:
        """Return decimal hours from the TT/TDT reference epoch."""
        hours = (float(jd_tt) - self.epoch_tt_jd) * 24.0
        if not math.isfinite(hours):
            raise ValueError("jd_tt must be finite")
        return hours

    def evaluate(self, jd_tt: float, *, check_validity: bool = True) -> "BesselianSnapshot":
        """Evaluate all elements and their first derivatives at a TT Julian Date."""
        hours = self.hours_from_epoch(jd_tt)
        if check_validity and not self.validity_start_hours <= hours <= self.validity_end_hours:
            raise ValueError(
                f"Requested time is {hours:.6f} h from epoch; published validity is "
                f"[{self.validity_start_hours:.6f}, {self.validity_end_hours:.6f}] h"
            )
        values = {name: getattr(self, name).evaluate(hours) for name in _ELEMENT_NAMES}
        rates = {name: getattr(self, name).derivative(hours) for name in _ELEMENT_NAMES}
        if values["l1"] <= 0.0:
            raise ValueError("evaluated penumbral radius l1 must be positive")
        return BesselianSnapshot(
            jd_tt=float(jd_tt),
            hours_from_epoch=hours,
            x=values["x"], y=values["y"], d_deg=values["d"], mu_deg=values["mu"],
            l1=values["l1"], l2=values["l2"], tan_f1=self.tan_f1, tan_f2=self.tan_f2,
            rates_per_hour=rates,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "epoch_tt_jd": self.epoch_tt_jd,
            "coefficients": {
                name: list(getattr(self, name).coefficients) for name in _ELEMENT_NAMES
            },
            "tan_f1": self.tan_f1,
            "tan_f2": self.tan_f2,
            "validity_start_hours": self.validity_start_hours,
            "validity_end_hours": self.validity_end_hours,
            "mu_convention": self.mu_convention,
            "source": self.source,
            "ephemeris": self.ephemeris,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BesselianElements":
        """Create elements from the documented JSON mapping format."""
        if not isinstance(payload, Mapping):
            raise TypeError("Besselian element payload must be a mapping")
        coefficients = payload.get("coefficients")
        if not isinstance(coefficients, Mapping):
            raise ValueError("Besselian payload requires a 'coefficients' mapping")
        missing = [name for name in _ELEMENT_NAMES if name not in coefficients]
        if missing:
            raise ValueError(f"Besselian coefficients are missing: {', '.join(missing)}")
        return cls(
            epoch_tt_jd=payload["epoch_tt_jd"],
            **{name: tuple(coefficients[name]) for name in _ELEMENT_NAMES},
            tan_f1=payload["tan_f1"], tan_f2=payload["tan_f2"],
            validity_start_hours=payload.get("validity_start_hours", -3.0),
            validity_end_hours=payload.get("validity_end_hours", 3.0),
            mu_convention=payload.get("mu_convention", "ephemeris"),
            source=payload.get("source"), ephemeris=payload.get("ephemeris"),
        )

    @classmethod
    def from_json(cls, path: str | Path) -> "BesselianElements":
        with Path(path).expanduser().open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return cls.from_dict(payload)

    def to_json(self, path: str | Path) -> None:
        destination = Path(path).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")


@dataclass(frozen=True, slots=True)
class BesselianSnapshot:
    jd_tt: float
    hours_from_epoch: float
    x: float
    y: float
    d_deg: float
    mu_deg: float
    l1: float
    l2: float
    tan_f1: float
    tan_f2: float
    rates_per_hour: Mapping[str, float] = field(default_factory=dict)

    @property
    def gamma(self) -> float:
        """Geocentric distance of the shadow axis from Earth's centre (Earth radii)."""
        return math.hypot(self.x, self.y)

    def to_dict(self) -> dict[str, Any]:
        return {
            "jd_tt": self.jd_tt,
            "hours_from_epoch": self.hours_from_epoch,
            "x": self.x, "y": self.y, "d_deg": self.d_deg, "mu_deg": self.mu_deg,
            "l1": self.l1, "l2": self.l2,
            "tan_f1": self.tan_f1, "tan_f2": self.tan_f2,
            "gamma": self.gamma,
            "rates_per_hour": dict(self.rates_per_hour),
        }


@dataclass(frozen=True, slots=True)
class BesselianObserverState:
    jd_tt: float
    delta_t_seconds: float
    mu_ut1_deg: float
    hour_angle_deg: float
    xi: float
    eta: float
    zeta: float
    u: float
    v: float
    distance: float
    l1_effective: float
    l2_effective: float
    external_residual: float
    internal_residual: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BesselianContact:
    name: str
    jd_tt: float
    root_result: RootResult

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "jd_tt": self.jd_tt, "solver": self.root_result.to_dict()}


@dataclass(frozen=True, slots=True)
class BesselianLocalResult:
    observer: Observer
    eclipse_type: str
    maximum_jd_tt: float | None
    maximum_state: BesselianObserverState | None
    contacts: Mapping[str, BesselianContact]
    partial_phase_duration_seconds: float | None
    central_phase_duration_seconds: float | None
    delta_t_seconds_at_maximum: float | None
    elements_source: str | None
    elements_ephemeris: str | None
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "observer": asdict(self.observer),
            "eclipse_type": self.eclipse_type,
            "maximum_jd_tt": self.maximum_jd_tt,
            "maximum_state": self.maximum_state.to_dict() if self.maximum_state else None,
            "contacts": {name: contact.to_dict() for name, contact in self.contacts.items()},
            "partial_phase_duration_seconds": self.partial_phase_duration_seconds,
            "central_phase_duration_seconds": self.central_phase_duration_seconds,
            "delta_t_seconds_at_maximum": self.delta_t_seconds_at_maximum,
            "elements_source": self.elements_source,
            "elements_ephemeris": self.elements_ephemeris,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class BesselianGlobalPoint:
    jd_tt: float
    latitude: float
    longitude: float
    umbral_radius_fundamental_km: float
    shadow_kind: str
    gamma: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DeltaTProvider = float | Callable[[float], float]


class BesselianSolver:
    """Evaluate published Besselian elements and solve local/global circumstances.

    The solver is independent of Skyfield and accepts TT Julian Dates directly.
    ``delta_t_seconds`` may be a scalar or a callable of TT Julian Date. The
    scalar form is useful for reproducing the ΔT used by a published catalogue.
    """

    def __init__(
        self,
        *,
        config: BesselianConfig | None = None,
        solver_config: SolverConfig | None = None,
    ) -> None:
        self.config = config or BesselianConfig()
        self.solver_config = solver_config or SolverConfig()

    @staticmethod
    def _delta_t(provider: DeltaTProvider, jd_tt: float) -> float:
        value = provider(float(jd_tt)) if callable(provider) else provider
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("delta_t_seconds must evaluate to a finite value")
        return result

    def observer_state(
        self,
        elements: BesselianElements,
        observer: Observer,
        jd_tt: float,
        *,
        delta_t_seconds: DeltaTProvider = 0.0,
    ) -> BesselianObserverState:
        """Project a WGS84 observer into the Besselian fundamental plane."""
        if not isinstance(elements, BesselianElements):
            raise TypeError("elements must be a BesselianElements instance")
        if not isinstance(observer, Observer):
            raise TypeError("observer must be an Observer instance")
        snapshot = elements.evaluate(jd_tt)
        delta_t = self._delta_t(delta_t_seconds, jd_tt)
        mu_ut1 = snapshot.mu_deg
        if elements.mu_convention == "ephemeris":
            # Earth rotation: 1.002738 sidereal turns per solar day.
            mu_ut1 -= delta_t * (1.002738 * 15.0 / 3600.0)

        latitude = math.radians(observer.latitude)
        declination = math.radians(snapshot.d_deg)
        hour_angle_deg = mu_ut1 + observer.longitude
        hour_angle = math.radians(hour_angle_deg)

        flattening = self.config.earth_flattening
        eccentricity_sq = flattening * (2.0 - flattening)
        sin_lat = math.sin(latitude)
        cos_lat = math.cos(latitude)
        c_ellipsoid = 1.0 / math.sqrt(1.0 - eccentricity_sq * sin_lat * sin_lat)
        s_ellipsoid = (1.0 - eccentricity_sq) * c_ellipsoid
        height = observer.elevation_m / (self.config.earth_equatorial_radius_km * 1000.0)
        rho_sin_phi = (s_ellipsoid + height) * sin_lat
        rho_cos_phi = (c_ellipsoid + height) * cos_lat

        sin_d, cos_d = math.sin(declination), math.cos(declination)
        sin_h, cos_h = math.sin(hour_angle), math.cos(hour_angle)
        xi = rho_cos_phi * sin_h
        eta = rho_sin_phi * cos_d - rho_cos_phi * sin_d * cos_h
        zeta = rho_sin_phi * sin_d + rho_cos_phi * cos_d * cos_h
        u = snapshot.x - xi
        v = snapshot.y - eta
        distance = math.hypot(u, v)
        l1_effective = snapshot.l1 - zeta * snapshot.tan_f1
        l2_effective = snapshot.l2 - zeta * snapshot.tan_f2
        return BesselianObserverState(
            jd_tt=float(jd_tt), delta_t_seconds=delta_t, mu_ut1_deg=mu_ut1,
            hour_angle_deg=hour_angle_deg, xi=xi, eta=eta, zeta=zeta,
            u=u, v=v, distance=distance,
            l1_effective=l1_effective, l2_effective=l2_effective,
            external_residual=distance - l1_effective,
            internal_residual=distance - abs(l2_effective),
        )

    def _root_settings(self) -> dict[str, Any]:
        return {
            "method": self.solver_config.root_method,
            "tolerance_days": self.solver_config.root_tolerance_seconds / 86400.0,
            "value_tolerance": 1.0e-12,
            "max_iterations": self.solver_config.root_max_iterations,
            "auto_expand": False,
            "detect_tangent": False,
        }

    def _find_boundary_roots(
        self,
        function: Callable[[float], float],
        start_jd: float,
        end_jd: float,
    ) -> list[RootResult]:
        count = self.config.root_scan_samples
        step = (end_jd - start_jd) / (count - 1)
        roots: list[RootResult] = []
        settings = self._root_settings()
        previous_x = start_jd
        previous_y = float(function(previous_x))
        for index in range(1, count):
            current_x = start_jd + index * step
            current_y = float(function(current_x))
            if not (math.isfinite(previous_y) and math.isfinite(current_y)):
                raise ValueError("Besselian contact residual is non-finite")
            if previous_y == 0.0:
                result = RootResult(
                    previous_x, True, "endpoint_root", self.solver_config.root_method,
                    0, 0, previous_x, current_x, previous_y,
                    message="A sampled Besselian boundary point is an exact root.",
                )
                roots.append(result)
            elif previous_y * current_y < 0.0:
                result = solve_root(function, previous_x, current_x, **settings)
                if result.converged and result.root is not None:
                    roots.append(result)
            previous_x, previous_y = current_x, current_y
        if previous_y == 0.0:
            roots.append(RootResult(
                previous_x, True, "endpoint_root", self.solver_config.root_method,
                0, 0, previous_x, previous_x, previous_y,
                message="The final Besselian boundary sample is an exact root.",
            ))
        unique: list[RootResult] = []
        for result in sorted(roots, key=lambda item: float(item.root or 0.0)):
            if result.root is None:
                continue
            if not unique or abs(result.root - float(unique[-1].root)) > 1.0e-7 / 86400.0:
                unique.append(result)
        if not unique:
            # A grazing boundary has no sign change. Keep it explicitly distinct
            # from a normal contact rather than manufacturing a pair of roots.
            tangent = solve_root(
                function, start_jd, end_jd,
                method=self.solver_config.root_method,
                tolerance_days=self.solver_config.root_tolerance_seconds / 86400.0,
                value_tolerance=1.0e-12,
                max_iterations=self.solver_config.root_max_iterations,
                detect_tangent=True,
                tangent_samples=self.solver_config.tangent_scan_samples,
                tangent_value_tolerance=1.0e-9,
            )
            if tangent.converged and tangent.root is not None and tangent.tangent:
                unique.append(tangent)
        return unique

    def calculate_local(
        self,
        elements: BesselianElements,
        observer: Observer,
        *,
        center_jd_tt: float | None = None,
        search_half_window_hours: float | None = None,
        delta_t_seconds: DeltaTProvider = 0.0,
    ) -> BesselianLocalResult:
        """Calculate approximate local C1-C4 and maximum from Besselian elements.

        ``maximum`` is the minimum of the penumbral fundamental-plane residual
        (closest approach adjusted by the linearly changing penumbral radius).
        It is not a topocentric apparent-disc maximum and should be compared
        against a direct backend only after matching element/radius/time-scale
        conventions.
        """
        if not isinstance(elements, BesselianElements):
            raise TypeError("elements must be a BesselianElements instance")
        if not isinstance(observer, Observer):
            raise TypeError("observer must be an Observer instance")
        center = elements.epoch_tt_jd if center_jd_tt is None else float(center_jd_tt)
        half_window = (
            self.config.search_half_window_hours
            if search_half_window_hours is None else float(search_half_window_hours)
        )
        if not math.isfinite(half_window) or half_window <= 0.0:
            raise ValueError("search_half_window_hours must be finite and positive")
        start = max(
            center - half_window / 24.0,
            elements.epoch_tt_jd + elements.validity_start_hours / 24.0,
        )
        end = min(
            center + half_window / 24.0,
            elements.epoch_tt_jd + elements.validity_end_hours / 24.0,
        )
        if not start < end:
            raise ValueError("search window does not overlap the Besselian validity interval")

        def external_residual(jd: float) -> float:
            return self.observer_state(
                elements, observer, jd, delta_t_seconds=delta_t_seconds
            ).external_residual

        maximum_jd, minimum_residual = golden_section_minimize(
            external_residual,
            start,
            end,
            tolerance_days=self.config.maximum_tolerance_seconds / 86400.0,
            max_iterations=self.solver_config.minimum_max_iterations,
        )
        max_state = self.observer_state(
            elements, observer, maximum_jd, delta_t_seconds=delta_t_seconds
        )
        if minimum_residual > 1.0e-9:
            return BesselianLocalResult(
                observer=observer, eclipse_type="none", maximum_jd_tt=None,
                maximum_state=None, contacts={}, partial_phase_duration_seconds=None,
                central_phase_duration_seconds=None, delta_t_seconds_at_maximum=None,
                elements_source=elements.source, elements_ephemeris=elements.ephemeris,
                warnings=("No penumbral eclipse occurs at this observer within the search window.",),
            )

        external_roots = self._find_boundary_roots(external_residual, start, end)
        contacts: dict[str, BesselianContact] = {}
        warnings: list[str] = []
        if len(external_roots) >= 2:
            first, last = external_roots[0], external_roots[-1]
            contacts["C1"] = BesselianContact("C1", float(first.root), first)
            contacts["C4"] = BesselianContact("C4", float(last.root), last)
        elif len(external_roots) == 1 and external_roots[0].tangent:
            root = external_roots[0]
            contacts["C1"] = BesselianContact("C1", float(root.root), root)
            contacts["C4"] = BesselianContact("C4", float(root.root), root)
            warnings.append("External grazing contact: C1 and C4 are represented by one tangent root.")
        else:
            warnings.append("Could not bracket both external contacts inside the search window.")

        # NASA's signed L2 convention: negative L2 means the umbral cone
        # reaches the fundamental plane (totality); positive L2 is antumbral
        # (annularity). The contact radius itself is always |L2_effective|.
        central_kind = "total" if max_state.l2_effective < 0.0 else "annular"
        central_margin = abs(max_state.l2_effective) - max_state.distance
        eclipse_type = central_kind if central_margin > 0.0 else "partial"
        if eclipse_type != "partial":
            sign = 1.0 if max_state.l2_effective >= 0.0 else -1.0

            def internal_residual(jd: float) -> float:
                state = self.observer_state(
                    elements, observer, jd, delta_t_seconds=delta_t_seconds
                )
                return state.distance - sign * state.l2_effective

            internal_roots = self._find_boundary_roots(internal_residual, start, end)
            if len(internal_roots) >= 2:
                first, last = internal_roots[0], internal_roots[-1]
                contacts["C2"] = BesselianContact("C2", float(first.root), first)
                contacts["C3"] = BesselianContact("C3", float(last.root), last)
            elif len(internal_roots) == 1 and internal_roots[0].tangent:
                root = internal_roots[0]
                contacts["C2"] = BesselianContact("C2", float(root.root), root)
                contacts["C3"] = BesselianContact("C3", float(root.root), root)
                warnings.append("Central grazing contact: C2 and C3 are represented by one tangent root.")
            else:
                eclipse_type = "partial"
                warnings.append("Central classification had no two internal roots; result downgraded to partial.")

        partial_duration = None
        if "C1" in contacts and "C4" in contacts:
            partial_duration = (contacts["C4"].jd_tt - contacts["C1"].jd_tt) * 86400.0
        central_duration = None
        if "C2" in contacts and "C3" in contacts:
            central_duration = (contacts["C3"].jd_tt - contacts["C2"].jd_tt) * 86400.0
        return BesselianLocalResult(
            observer=observer, eclipse_type=eclipse_type,
            maximum_jd_tt=maximum_jd, maximum_state=max_state,
            contacts=contacts, partial_phase_duration_seconds=partial_duration,
            central_phase_duration_seconds=central_duration,
            delta_t_seconds_at_maximum=max_state.delta_t_seconds,
            elements_source=elements.source, elements_ephemeris=elements.ephemeris,
            warnings=tuple(warnings),
        )

    def find_global_maximum(
        self,
        elements: BesselianElements,
        *,
        start_jd_tt: float | None = None,
        end_jd_tt: float | None = None,
    ) -> float:
        """Return the TT JD of minimum geocentric shadow-axis distance gamma.

        This is the conventional geocentric closest-approach time. It is not
        necessarily identical to maximum magnitude at a particular location.
        """
        start = (
            elements.epoch_tt_jd + elements.validity_start_hours / 24.0
            if start_jd_tt is None else float(start_jd_tt)
        )
        end = (
            elements.epoch_tt_jd + elements.validity_end_hours / 24.0
            if end_jd_tt is None else float(end_jd_tt)
        )
        if not start < end:
            raise ValueError("start_jd_tt must be earlier than end_jd_tt")
        elements.evaluate(start)
        elements.evaluate(end)

        def gamma_squared(jd: float) -> float:
            snapshot = elements.evaluate(jd)
            return snapshot.x * snapshot.x + snapshot.y * snapshot.y

        result, _ = golden_section_minimize(
            gamma_squared, start, end,
            tolerance_days=self.config.maximum_tolerance_seconds / 86400.0,
            max_iterations=self.solver_config.minimum_max_iterations,
        )
        return result

    def central_line_point(
        self,
        elements: BesselianElements,
        jd_tt: float,
        *,
        delta_t_seconds: DeltaTProvider = 0.0,
    ) -> BesselianGlobalPoint | None:
        """Intersect the shadow axis with the oblate Earth at one TT instant."""
        snapshot = elements.evaluate(jd_tt)
        delta_t = self._delta_t(delta_t_seconds, jd_tt)
        mu_ut1 = snapshot.mu_deg
        if elements.mu_convention == "ephemeris":
            mu_ut1 -= delta_t * (1.002738 * 15.0 / 3600.0)

        flattening = self.config.earth_flattening
        eccentricity_sq = flattening * (2.0 - flattening)
        declination = math.radians(snapshot.d_deg)
        sin_d, cos_d = math.sin(declination), math.cos(declination)
        rho1 = math.sqrt(1.0 - eccentricity_sq * cos_d * cos_d)
        rho2 = math.sqrt(1.0 - eccentricity_sq * sin_d * sin_d)
        eta1 = snapshot.y / rho1
        sd1 = sin_d / rho1
        cd1 = math.sqrt(1.0 - eccentricity_sq) * cos_d / rho1
        sdd = eccentricity_sq * sin_d * cos_d / (rho1 * rho2)
        cdd_sq = 1.0 - sdd * sdd
        p = 1.0 - snapshot.x * snapshot.x - eta1 * eta1
        if p < 0.0 or cdd_sq <= 0.0:
            return None
        zeta1 = math.sqrt(max(0.0, p))
        zeta = rho2 * (zeta1 * math.sqrt(cdd_sq) - eta1 * sdd)
        b = -snapshot.y * sin_d + zeta * cos_d
        theta = math.degrees(math.atan2(snapshot.x, b))
        longitude = (theta - mu_ut1 + 180.0) % 360.0 - 180.0
        sin_geocentric_lat = eta1 * cd1 + zeta1 * sd1
        cos_geocentric_lat_sq = 1.0 - sin_geocentric_lat * sin_geocentric_lat
        if cos_geocentric_lat_sq < -1.0e-12:
            return None
        cos_geocentric_lat = math.sqrt(max(0.0, cos_geocentric_lat_sq))
        latitude = math.degrees(
            math.atan2(sin_geocentric_lat, (1.0 - flattening) * cos_geocentric_lat)
        )
        l2_at_axis = snapshot.l2 - zeta * snapshot.tan_f2
        kind = "umbral" if l2_at_axis <= 0.0 else "antumbral"
        return BesselianGlobalPoint(
            jd_tt=float(jd_tt), latitude=latitude, longitude=longitude,
            umbral_radius_fundamental_km=abs(l2_at_axis) * self.config.earth_equatorial_radius_km,
            shadow_kind=kind, gamma=snapshot.gamma,
        )

    def global_central_line(
        self,
        elements: BesselianElements,
        start_jd_tt: float,
        end_jd_tt: float,
        *,
        samples: int = 101,
        delta_t_seconds: DeltaTProvider = 0.0,
    ) -> list[BesselianGlobalPoint]:
        """Sample the central-axis ground track; omit instants where it misses Earth."""
        start, end = float(start_jd_tt), float(end_jd_tt)
        if not start < end:
            raise ValueError("start_jd_tt must be earlier than end_jd_tt")
        if isinstance(samples, bool) or int(samples) != samples or samples < 2:
            raise ValueError("samples must be an integer >= 2")
        elements.evaluate(start)
        elements.evaluate(end)
        points: list[BesselianGlobalPoint] = []
        for index in range(int(samples)):
            jd = start + (end - start) * index / (int(samples) - 1)
            point = self.central_line_point(
                elements, jd, delta_t_seconds=delta_t_seconds
            )
            if point is not None:
                points.append(point)
        return points
