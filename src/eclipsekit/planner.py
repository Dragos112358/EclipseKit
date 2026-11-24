"""Weather-agnostic, multi-observer solar-eclipse observation planning."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from .models import Observer
from .timeutils import time_to_utc_iso


@dataclass(frozen=True, slots=True)
class ObservationScoreWeights:
    """Relative weights for the transparent 0–100 observation score."""

    obscuration: float = 0.50
    solar_altitude: float = 0.30
    partial_duration: float = 0.20

    def __post_init__(self) -> None:
        values: list[float] = []
        for name in ("obscuration", "solar_altitude", "partial_duration"):
            value = getattr(self, name)
            if isinstance(value, bool):
                raise ValueError(f"{name} weight must be finite and non-negative")
            try:
                number = float(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"{name} weight must be finite and non-negative") from exc
            if not math.isfinite(number) or number < 0.0:
                raise ValueError(f"{name} weight must be finite and non-negative")
            object.__setattr__(self, name, number)
            values.append(number)
        if not any(value > 0.0 for value in values):
            raise ValueError("at least one observation score weight must be positive")

    def normalized(self) -> dict[str, float]:
        # Scale first so valid finite weights near 1e308 cannot overflow on sum.
        raw = self.to_dict()
        scale = max(raw.values())
        scaled = {name: value / scale for name, value in raw.items()}
        total = sum(scaled.values())
        return {name: value / total for name, value in scaled.items()}

    def to_dict(self) -> dict[str, float]:
        return {
            "obscuration": self.obscuration,
            "solar_altitude": self.solar_altitude,
            "partial_duration": self.partial_duration,
        }


@dataclass(frozen=True, slots=True)
class ObservationSitePlan:
    """Planner output for one observer, including its local eclipse calculation."""

    observer: Observer
    status: str
    local_result: Any | None = None
    score: float | None = None
    obscuration_score: float | None = None
    solar_altitude_score: float | None = None
    partial_duration_score: float | None = None
    visibility_class: str = "unknown"
    rank: int | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.observer, Observer):
            raise TypeError("observer must be an Observer")
        allowed = {
            "recommended", "below_minimum_sun_altitude", "no_eclipse", "calculation_error"
        }
        if not isinstance(self.status, str) or self.status not in allowed:
            raise ValueError(f"status must be one of {sorted(allowed)}")
        evaluated = self.status in {"recommended", "below_minimum_sun_altitude"}
        if evaluated and self.local_result is None:
            raise ValueError("an evaluated observation site must include local_result")
        if not evaluated and self.local_result is not None:
            raise ValueError("a site without a local result cannot include local_result")
        if evaluated and self.score is None:
            raise ValueError("an evaluated observation site requires a score")
        if not evaluated and any(
            getattr(self, name) is not None
            for name in ("score", "obscuration_score", "solar_altitude_score", "partial_duration_score")
        ):
            raise ValueError("sites without a local result cannot include scores")
        if self.status == "calculation_error" and not self.message:
            raise ValueError("calculation_error sites require a non-empty message")
        if self.message is not None and not isinstance(self.message, str):
            raise TypeError("message must be a string or None")
        if self.rank is not None:
            if self.status != "recommended":
                raise ValueError("only recommended sites may have a rank")
            if isinstance(self.rank, bool) or not isinstance(self.rank, int) or self.rank < 1:
                raise ValueError("rank must be a positive integer")
        allowed_visibility = {"unknown", "below_horizon", "very_low", "low", "good", "high"}
        if self.visibility_class not in allowed_visibility:
            raise ValueError(f"visibility_class must be one of {sorted(allowed_visibility)}")
        for name in (
            "score", "obscuration_score", "solar_altitude_score", "partial_duration_score"
        ):
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool):
                raise ValueError(f"{name} must be a finite number in [0, 100]")
            try:
                number = float(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"{name} must be a finite number in [0, 100]") from exc
            if not math.isfinite(number) or not 0.0 <= number <= 100.0:
                raise ValueError(f"{name} must be a finite number in [0, 100]")
            object.__setattr__(self, name, number)

    @property
    def site_label(self) -> str:
        if self.observer.name:
            return self.observer.name
        if self.observer.country:
            return (
                f"{self.observer.country} "
                f"({self.observer.latitude:.4f}, {self.observer.longitude:.4f})"
            )
        return f"({self.observer.latitude:.4f}, {self.observer.longitude:.4f})"

    def to_dict(self) -> dict[str, Any]:
        result = self.local_result.to_dict() if self.local_result is not None else None
        return {
            "site": {
                "name": self.observer.name,
                "country": self.observer.country,
                "latitude": float(self.observer.latitude),
                "longitude": float(self.observer.longitude),
                "elevation_m": float(self.observer.elevation_m),
            },
            "status": self.status,
            "rank": self.rank,
            "score": self.score,
            "score_components": {
                "obscuration": self.obscuration_score,
                "solar_altitude": self.solar_altitude_score,
                "partial_duration": self.partial_duration_score,
            },
            "visibility_class": self.visibility_class,
            "message": self.message,
            "local_result": result,
        }


@dataclass(frozen=True, slots=True)
class ObservationPlan:
    """Ranked multi-site plan for one target eclipse epoch."""

    target_time: Any
    sites: tuple[ObservationSitePlan, ...]
    weights: ObservationScoreWeights
    minimum_sun_altitude_deg: float
    full_sun_altitude_score_deg: float
    maximum_partial_duration_seconds: float
    notes: tuple[str, ...] = (
        "Ranking is a weather-agnostic heuristic, not a probability of clear skies or observing success.",
        "Clouds, local horizon obstructions, light pollution, access, safety and transport are not modelled.",
        "Solar altitude is evaluated at the local eclipse maximum; contact times remain in UTC.",
    )

    def __post_init__(self) -> None:
        sites = tuple(self.sites)
        notes = tuple(self.notes)
        if not sites:
            raise ValueError("an observation plan must contain at least one site")
        if not isinstance(self.weights, ObservationScoreWeights):
            raise TypeError("weights must be ObservationScoreWeights")
        for name in (
            "minimum_sun_altitude_deg", "full_sun_altitude_score_deg",
            "maximum_partial_duration_seconds",
        ):
            value = getattr(self, name)
            if isinstance(value, bool):
                raise ValueError(f"{name} must be finite")
            try:
                number = float(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"{name} must be finite") from exc
            if not math.isfinite(number):
                raise ValueError(f"{name} must be finite")
            object.__setattr__(self, name, number)
        if not -90.0 <= self.minimum_sun_altitude_deg <= 90.0:
            raise ValueError("minimum_sun_altitude_deg must be in [-90, 90]")
        if not 0.0 < self.full_sun_altitude_score_deg <= 90.0:
            raise ValueError("full_sun_altitude_score_deg must be in (0, 90]")
        if self.maximum_partial_duration_seconds <= 0.0:
            raise ValueError("maximum_partial_duration_seconds must be positive")
        if any(not isinstance(site, ObservationSitePlan) for site in sites):
            raise TypeError("sites must contain ObservationSitePlan objects")
        if any(not isinstance(note, str) or not note.strip() for note in notes):
            raise ValueError("notes must contain non-empty strings")
        recommended = [site for site in sites if site.status == "recommended"]
        ranks = [site.rank for site in recommended]
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError("recommended sites must be ordered with contiguous ranks starting at 1")
        object.__setattr__(self, "sites", sites)
        object.__setattr__(self, "notes", notes)

    @property
    def recommended_sites(self) -> tuple[ObservationSitePlan, ...]:
        return tuple(site for site in self.sites if site.status == "recommended")

    @property
    def below_minimum_sites(self) -> tuple[ObservationSitePlan, ...]:
        return tuple(site for site in self.sites if site.status == "below_minimum_sun_altitude")

    @property
    def no_eclipse_sites(self) -> tuple[ObservationSitePlan, ...]:
        return tuple(site for site in self.sites if site.status == "no_eclipse")

    @property
    def error_sites(self) -> tuple[ObservationSitePlan, ...]:
        return tuple(site for site in self.sites if site.status == "calculation_error")

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_time_utc": time_to_utc_iso(self.target_time),
            "score_model": "weather_agnostic_weighted_heuristic_v1",
            "weights": self.weights.to_dict(),
            "normalized_weights": self.weights.normalized(),
            "minimum_sun_altitude_deg": self.minimum_sun_altitude_deg,
            "full_sun_altitude_score_deg": self.full_sun_altitude_score_deg,
            "maximum_partial_duration_seconds": self.maximum_partial_duration_seconds,
            "counts": {
                "total_sites": len(self.sites),
                "recommended": len(self.recommended_sites),
                "below_minimum_sun_altitude": len(self.below_minimum_sites),
                "no_eclipse": len(self.no_eclipse_sites),
                "calculation_errors": len(self.error_sites),
            },
            "notes": list(self.notes),
            "sites": [site.to_dict() for site in self.sites],
        }

    def to_markdown(self) -> str:
        lines = [
            "# EclipseKit observation plan",
            "",
            f"- Target epoch: `{time_to_utc_iso(self.target_time)}`",
            f"- Evaluated sites: {len(self.sites)}",
            f"- Recommended: {len(self.recommended_sites)}",
            f"- Below minimum Sun altitude: {len(self.below_minimum_sites)}",
            f"- No local eclipse: {len(self.no_eclipse_sites)}",
            f"- Calculation errors: {len(self.error_sites)}",
            "",
            "| Rank | Site | Status | Score | Eclipse | Obscuration | Sun altitude | C1–C4 span |",
            "|---:|---|---|---:|---|---:|---:|---:|",
        ]
        for site in self.sites:
            result = site.local_result
            eclipse_type = result.eclipse_type if result is not None else "—"
            obscuration = f"{result.obscuration_percent:.2f}%" if result is not None else "—"
            altitude = f"{result.sun_altitude_deg:.2f}°" if result is not None else "—"
            duration = (
                f"{result.partial_phase_duration_seconds:.1f} s"
                if result is not None and result.partial_phase_duration_seconds is not None else "—"
            )
            score = f"{site.score:.1f}" if site.score is not None else "—"
            rank = str(site.rank) if site.rank is not None else "—"
            label = site.site_label.replace("|", "\\|").replace("\n", " ")
            lines.append(
                f"| {rank} | {label} | {site.status} | {score} | {eclipse_type} | "
                f"{obscuration} | {altitude} | {duration} |"
            )
            if site.message:
                lines.append(f"\n> {label}: {site.message.replace(chr(10), ' ')}")
        lines.extend(["", "## Score model", ""])
        lines.extend([
            "The score is a weighted heuristic from 0 to 100, not a weather or success probability.",
            "- Obscuration component: modelled obscuration percentage (0–100).",
            "- Sun-altitude component: `clip(max(altitude, 0) / full_sun_altitude_score_deg × 100, 0, 100)`. ",
            "- Duration component: `clip(C1–C4 span / maximum_partial_duration_seconds × 100, 0, 100)`. ",
            "- Weights are normalized to sum to 1 before combining the components.",
            "",
            "## Interpretation",
            "",
        ])
        lines.extend(f"- {note}" for note in self.notes)
        lines.append("")
        return "\n".join(lines)


def _clamp_score(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def _finite_result_value(result: Any, attribute: str, *, minimum: float, maximum: float | None = None) -> float:
    value = getattr(result, attribute)
    if isinstance(value, bool):
        raise ValueError(f"local result {attribute} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"local result {attribute} must be numeric") from exc
    if not math.isfinite(number) or number < minimum or (maximum is not None and number > maximum):
        bounds = f"[{minimum}, {maximum}]" if maximum is not None else f">= {minimum}"
        raise ValueError(f"local result {attribute} must be finite and within {bounds}")
    return number


def _visibility_class(sun_altitude_deg: float) -> str:
    if sun_altitude_deg < 0.0:
        return "below_horizon"
    if sun_altitude_deg < 10.0:
        return "very_low"
    if sun_altitude_deg < 25.0:
        return "low"
    if sun_altitude_deg < 45.0:
        return "good"
    return "high"


def build_observation_plan(
    engine: Any,
    observers: Any,
    when: Any,
    *,
    search_window_hours: float = 12.0,
    weights: ObservationScoreWeights | None = None,
    minimum_sun_altitude_deg: float = 0.0,
    full_sun_altitude_score_deg: float = 45.0,
    maximum_partial_duration_seconds: float = 3600.0,
    limb_model: Any | None = None,
    continue_on_error: bool = True,
) -> ObservationPlan:
    """Evaluate candidate observers and rank sites using local circumstances.

    The planner deliberately disables next-eclipse searching: a site without an
    eclipse in the requested window is reported as ``no_eclipse`` rather than
    silently being evaluated against a later event.
    """
    if isinstance(search_window_hours, bool):
        raise ValueError("search_window_hours must be finite and positive")
    try:
        search_window = float(search_window_hours)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("search_window_hours must be finite and positive") from exc
    if not math.isfinite(search_window) or not 0.0 < search_window <= 36.0:
        raise ValueError("search_window_hours must be in (0, 36]")

    numeric_options = (
        ("minimum_sun_altitude_deg", minimum_sun_altitude_deg, -90.0, 90.0),
        ("full_sun_altitude_score_deg", full_sun_altitude_score_deg, 0.0, 90.0),
        ("maximum_partial_duration_seconds", maximum_partial_duration_seconds, 0.0, None),
    )
    normalized_options: dict[str, float] = {}
    for name, value, lower, upper in numeric_options:
        if isinstance(value, bool):
            raise ValueError(f"{name} must be numeric and in its allowed range")
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{name} must be numeric and in its allowed range") from exc
        if (
            not math.isfinite(number)
            or number < lower
            or (upper is not None and number > upper)
            or (name == "full_sun_altitude_score_deg" and number == 0.0)
        ):
            raise ValueError(f"{name} must be in its allowed range")
        normalized_options[name] = number
    if normalized_options["maximum_partial_duration_seconds"] <= 0.0:
        raise ValueError("maximum_partial_duration_seconds must be positive")
    if not isinstance(continue_on_error, bool):
        raise ValueError("continue_on_error must be bool")

    try:
        candidates = tuple(observers)
    except TypeError as exc:
        raise TypeError("observers must be an iterable of Observer objects") from exc
    if not candidates:
        raise ValueError("at least one observer is required")
    if any(not isinstance(observer, Observer) for observer in candidates):
        raise TypeError("observers must contain only Observer objects")
    active_weights = ObservationScoreWeights() if weights is None else weights
    if not isinstance(active_weights, ObservationScoreWeights):
        raise TypeError("weights must be ObservationScoreWeights or None")

    target_time = engine.time(when)
    normalized_weights = active_weights.normalized()
    evaluated: list[ObservationSitePlan] = []
    for observer in candidates:
        try:
            result = engine.calculate_local(
                observer,
                target_time,
                search_window_hours=search_window,
                find_next_if_none=False,
                limb_model=limb_model,
                include_sunrise_sunset=False,
                include_shadow_metrics=False,
                include_planets=False,
            )
            if result is None:
                evaluated.append(ObservationSitePlan(observer=observer, status="no_eclipse"))
                continue

            obscuration = _finite_result_value(
                result, "obscuration_percent", minimum=0.0, maximum=100.0
            )
            sun_altitude = _finite_result_value(
                result, "sun_altitude_deg", minimum=-90.0, maximum=90.0
            )
            partial_duration_value = getattr(result, "partial_phase_duration_seconds")
            if partial_duration_value is None:
                partial_duration = None
            else:
                partial_duration = _finite_result_value(
                    result, "partial_phase_duration_seconds", minimum=0.0
                )
        except Exception as exc:
            if not continue_on_error:
                raise
            evaluated.append(ObservationSitePlan(
                observer=observer,
                status="calculation_error",
                message=f"{type(exc).__name__}: {exc}",
            ))
            continue

        obscuration_score = _clamp_score(obscuration)
        altitude_score = _clamp_score(max(0.0, sun_altitude) / normalized_options[
            "full_sun_altitude_score_deg"
        ] * 100.0)
        duration_score = _clamp_score(
            (partial_duration or 0.0) / normalized_options["maximum_partial_duration_seconds"] * 100.0
        )
        score = (
            normalized_weights["obscuration"] * obscuration_score
            + normalized_weights["solar_altitude"] * altitude_score
            + normalized_weights["partial_duration"] * duration_score
        )
        visible_class = _visibility_class(sun_altitude)
        status = (
            "recommended" if sun_altitude >= normalized_options["minimum_sun_altitude_deg"]
            else "below_minimum_sun_altitude"
        )
        evaluated.append(ObservationSitePlan(
            observer=observer,
            status=status,
            local_result=result,
            score=score,
            obscuration_score=obscuration_score,
            solar_altitude_score=altitude_score,
            partial_duration_score=duration_score,
            visibility_class=visible_class,
        ))

    recommended = sorted(
        (site for site in evaluated if site.status == "recommended"),
        key=lambda site: (
            -(site.score if site.score is not None else -1.0),
            -(site.local_result.obscuration_percent if site.local_result else -1.0),
            -(site.local_result.sun_altitude_deg if site.local_result else -91.0),
            site.site_label.casefold(),
        ),
    )
    others = [site for site in evaluated if site.status != "recommended"]
    others.sort(key=lambda site: (site.status, site.site_label.casefold()))
    ranked_sites = tuple(
        ObservationSitePlan(
            observer=site.observer,
            status=site.status,
            local_result=site.local_result,
            score=site.score,
            obscuration_score=site.obscuration_score,
            solar_altitude_score=site.solar_altitude_score,
            partial_duration_score=site.partial_duration_score,
            visibility_class=site.visibility_class,
            rank=index,
            message=site.message,
        )
        for index, site in enumerate(recommended, start=1)
    ) + tuple(others)

    return ObservationPlan(
        target_time=target_time,
        sites=ranked_sites,
        weights=active_weights,
        minimum_sun_altitude_deg=normalized_options["minimum_sun_altitude_deg"],
        full_sun_altitude_score_deg=normalized_options["full_sun_altitude_score_deg"],
        maximum_partial_duration_seconds=normalized_options["maximum_partial_duration_seconds"],
    )
