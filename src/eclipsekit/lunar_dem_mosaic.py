"""Coverage-aware composition of multiple compatible lunar DEM readers.

The mosaic is a virtual query router. It does not resample or rewrite source
rasters. Each query is routed using declared rectangular coverage in one common
lunar coordinate frame and spherical vertical datum.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable, Literal, Sequence

import numpy as np

from .limb import LunarLimbModelMetadata, LunarLimbPrediction, LunarLimbQuery

MosaicStrategy = Literal["priority", "finest", "mean"]


def _normalise_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def _finite_number(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number)):
        raise TypeError(f"{name} must be a numeric value")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if positive and result <= 0.0:
        raise ValueError(f"{name} must be positive")
    return result


def _info_dict(info: Any) -> dict[str, Any]:
    to_dict = getattr(info, "to_dict", None)
    if callable(to_dict):
        value = to_dict()
        if isinstance(value, dict):
            return value
    try:
        return {key: value for key, value in vars(info).items() if not key.startswith("_")}
    except TypeError:
        return {"type": type(info).__name__}


@dataclass(frozen=True, slots=True)
class LunarDEMCoverage:
    """A rectangular planetocentric latitude/east-longitude coverage region.

    Longitudes may use any continuous 360-degree branch. For example, a region
    crossing the antimeridian can be represented as west=170, east=190.
    """

    south_latitude_deg: float
    north_latitude_deg: float
    west_longitude_deg: float
    east_longitude_deg: float

    def __post_init__(self) -> None:
        south = _finite_number(self.south_latitude_deg, "south_latitude_deg")
        north = _finite_number(self.north_latitude_deg, "north_latitude_deg")
        west = _finite_number(self.west_longitude_deg, "west_longitude_deg")
        east = _finite_number(self.east_longitude_deg, "east_longitude_deg")
        if not -90.0 <= south < north <= 90.0:
            raise ValueError("coverage latitude bounds must satisfy -90 <= south < north <= 90")
        if not 0.0 < east - west <= 360.0 + 1e-8:
            raise ValueError("coverage longitude span must be in (0, 360] degrees")
        object.__setattr__(self, "south_latitude_deg", south)
        object.__setattr__(self, "north_latitude_deg", north)
        object.__setattr__(self, "west_longitude_deg", west)
        object.__setattr__(self, "east_longitude_deg", east)

    @property
    def global_longitude(self) -> bool:
        return math.isclose(
            self.east_longitude_deg - self.west_longitude_deg,
            360.0,
            rel_tol=0.0,
            abs_tol=1e-6,
        )

    def contains(self, latitude_deg: float, longitude_deg: float, *, tolerance_deg: float = 1e-10) -> bool:
        if not self.south_latitude_deg - tolerance_deg <= latitude_deg <= self.north_latitude_deg + tolerance_deg:
            return False
        if self.global_longitude:
            return True
        center = 0.5 * (self.west_longitude_deg + self.east_longitude_deg)
        wrapped = longitude_deg + 360.0 * round((center - longitude_deg) / 360.0)
        return self.west_longitude_deg - tolerance_deg <= wrapped <= self.east_longitude_deg + tolerance_deg

    def to_dict(self) -> dict[str, Any]:
        return {
            "south_latitude_deg": self.south_latitude_deg,
            "north_latitude_deg": self.north_latitude_deg,
            "west_longitude_deg": self.west_longitude_deg,
            "east_longitude_deg": self.east_longitude_deg,
            "global_longitude": self.global_longitude,
        }


@dataclass(frozen=True, slots=True)
class LunarDEMMosaicSource:
    """One source reader and its explicitly resolved metadata."""

    name: str
    model: Any
    coverage: LunarDEMCoverage
    resolution_m: float | None
    product_info: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "coverage": self.coverage.to_dict(),
            "resolution_m": self.resolution_m,
            "product_info": self.product_info,
        }


@dataclass(frozen=True, slots=True)
class LunarDEMMosaicProductInfo:
    """Common metadata and coverage components for a virtual DEM mosaic."""

    format: str
    product_id: str
    coordinate_system_name: str
    vertical_datum: str
    reference_radius_m: float
    strategy: str
    sources: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "product_id": self.product_id,
            "coordinate_system_name": self.coordinate_system_name,
            "vertical_datum": self.vertical_datum,
            "reference_radius_m": self.reference_radius_m,
            "strategy": self.strategy,
            "sources": list(self.sources),
            "storage": "virtual coverage-aware query mosaic; source rasters remain unchanged",
        }


class LunarDEMOutOfCoverageError(LookupError):
    """Raised when no source declares coverage for a requested lunar location."""


class LunarDEMMosaicModel:
    """Route lunar DEM queries to compatible sources without materialising a mosaic.

    ``sources`` are ordered from highest to lowest priority. ``priority`` selects
    the first covering source; ``finest`` selects the covering source with the
    smallest declared ground resolution; and ``mean`` averages all covering
    sources. Mean mode is an unweighted arithmetic mean, not an uncertainty-
    weighted fusion.

    All sources must describe the same coordinate-system label, vertical datum
    and spherical reference radius. Coverage must be declared by the product
    metadata or supplied explicitly in ``coverage_overrides`` (one entry per
    source). A query inside declared coverage that encounters NoData or another
    reader error is reported; the mosaic never silently hides it by switching
    to a lower-priority product.

    Source readers are not closed by default. Set ``close_sources=True`` to
    transfer lifecycle ownership to this virtual mosaic.
    """

    def __init__(
        self,
        sources: Iterable[Any],
        *,
        strategy: MosaicStrategy = "priority",
        source_names: Sequence[str] | None = None,
        coverage_overrides: Sequence[LunarDEMCoverage | tuple[float, float, float, float] | None] | None = None,
        name: str = "Lunar DEM mosaic",
        product_id: str = "eclipsekit-lunar-dem-mosaic",
        close_sources: bool = False,
    ) -> None:
        models = tuple(sources)
        if not models:
            raise ValueError("sources must contain at least one DEM model")
        if len({id(model) for model in models}) != len(models):
            raise ValueError("sources must not contain the same model more than once")
        if strategy not in {"priority", "finest", "mean"}:
            raise ValueError("strategy must be 'priority', 'finest', or 'mean'")
        if not isinstance(close_sources, bool):
            raise TypeError("close_sources must be a bool")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("name must be a non-empty string")
        if not isinstance(product_id, str) or not product_id.strip():
            raise ValueError("product_id must be a non-empty string")
        if source_names is not None:
            names = tuple(source_names)
            if len(names) != len(models):
                raise ValueError("source_names must contain exactly one name per source")
            if any(not isinstance(item, str) or not item.strip() for item in names):
                raise ValueError("source_names entries must be non-empty strings")
        else:
            names = tuple(
                str(
                    getattr(getattr(model, "metadata", None), "name", None)
                    or getattr(getattr(model, "product_info", None), "product_id", None)
                    or f"source-{index + 1}"
                )
                for index, model in enumerate(models)
            )
        if len({_normalise_text(item) for item in names}) != len(names):
            raise ValueError("source names must be unique")
        if coverage_overrides is not None:
            overrides = tuple(coverage_overrides)
            if len(overrides) != len(models):
                raise ValueError("coverage_overrides must contain exactly one entry per source")
        else:
            overrides = (None,) * len(models)

        resolved: list[LunarDEMMosaicSource] = []
        common_frame: str | None = None
        common_datum: str | None = None
        common_radius: float | None = None
        for index, (model, source_name, override) in enumerate(zip(models, names, overrides)):
            sampler = getattr(model, "predict_altitude_m", None)
            if not callable(sampler):
                raise TypeError(f"source {source_name!r} must provide predict_altitude_m(latitude, longitude)")
            info = getattr(model, "product_info", None)
            if info is None:
                raise TypeError(f"source {source_name!r} must expose product_info metadata")
            metadata = getattr(model, "metadata", None)
            frame = getattr(info, "coordinate_system_name", None)
            datum = getattr(info, "vertical_datum", None) or getattr(metadata, "vertical_datum", None)
            radius = _finite_number(
                getattr(info, "reference_radius_m", None),
                f"source {source_name!r} reference_radius_m",
                positive=True,
            )
            if not isinstance(frame, str) or not frame.strip():
                raise ValueError(f"source {source_name!r} must declare coordinate_system_name")
            if not isinstance(datum, str) or not datum.strip():
                raise ValueError(f"source {source_name!r} must declare vertical_datum")
            if common_frame is None:
                common_frame = frame.strip()
                common_datum = datum.strip()
                common_radius = radius
            else:
                if _normalise_text(frame) != _normalise_text(common_frame):
                    raise ValueError(
                        f"source {source_name!r} coordinate system does not match the mosaic frame"
                    )
                if _normalise_text(datum) != _normalise_text(common_datum or ""):
                    raise ValueError(
                        f"source {source_name!r} vertical datum does not match the mosaic datum"
                    )
                if not math.isclose(radius, common_radius or 0.0, rel_tol=0.0, abs_tol=1e-6):
                    raise ValueError(
                        f"source {source_name!r} reference radius does not match the mosaic radius"
                    )

            coverage = self._resolve_coverage(info, override, source_name)
            resolution_value = getattr(info, "resolution_m", None)
            if resolution_value is None:
                resolution_value = getattr(metadata, "resolution_m", None)
            resolution = None if resolution_value is None else _finite_number(
                resolution_value, f"source {source_name!r} resolution_m", positive=True
            )
            resolved.append(
                LunarDEMMosaicSource(
                    name=source_name.strip(), model=model, coverage=coverage,
                    resolution_m=resolution, product_info=_info_dict(info),
                )
            )

        if strategy == "finest" and any(source.resolution_m is None for source in resolved):
            raise ValueError("strategy='finest' requires a positive resolution_m for every source")
        assert common_frame is not None and common_datum is not None and common_radius is not None

        self.sources = tuple(resolved)
        self.strategy = strategy
        self._closed = False
        self._close_sources = close_sources
        self.product_info = LunarDEMMosaicProductInfo(
            format="virtual-mosaic",
            product_id=product_id.strip(),
            coordinate_system_name=common_frame,
            vertical_datum=common_datum,
            reference_radius_m=common_radius,
            strategy=strategy,
            sources=tuple(source.to_dict() for source in resolved),
        )
        self.metadata = LunarLimbModelMetadata(
            name=name.strip(),
            model_type="custom",
            source="; ".join(source.name for source in resolved),
            reference_frame="selenographic",
            vertical_datum=common_datum,
            resolution_m=min(
                (source.resolution_m for source in resolved if source.resolution_m is not None),
                default=None,
            ),
            description=(
                "Virtual lunar DEM mosaic with explicit common frame/datum/radius and declared "
                f"coverage routing (strategy={strategy}). Source rasters are read-only and "
                "remain separate; no interpolation across product seams is performed."
            ),
            product_id=product_id.strip(),
            coordinate_system=common_frame,
            reference_radius_m=common_radius,
        )

    @staticmethod
    def _resolve_coverage(
        info: Any,
        override: LunarDEMCoverage | tuple[float, float, float, float] | None,
        source_name: str,
    ) -> LunarDEMCoverage:
        if override is not None:
            if isinstance(override, LunarDEMCoverage):
                return override
            if isinstance(override, tuple) and len(override) == 4:
                return LunarDEMCoverage(*override)
            raise TypeError(
                f"coverage override for {source_name!r} must be LunarDEMCoverage, a 4-tuple, or None"
            )
        south = getattr(info, "south_latitude_deg", getattr(info, "min_latitude_deg", None))
        north = getattr(info, "north_latitude_deg", getattr(info, "max_latitude_deg", None))
        west = getattr(info, "west_longitude_deg", None)
        east = getattr(info, "east_longitude_deg", None)
        if all(value is not None for value in (south, north, west, east)):
            return LunarDEMCoverage(south, north, west, east)
        raise ValueError(
            f"source {source_name!r} has no rectangular coverage metadata; supply an explicit coverage override"
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("LunarDEMMosaicModel is closed")

    @staticmethod
    def _validate_query(latitude_deg: Any, longitude_deg: Any) -> tuple[float, float]:
        latitude = _finite_number(latitude_deg, "latitude_deg")
        longitude = _finite_number(longitude_deg, "longitude_deg")
        if not -90.0 <= latitude <= 90.0:
            raise ValueError("latitude_deg must be within [-90, 90]")
        return latitude, longitude

    def _covering_sources(self, latitude: float, longitude: float) -> tuple[LunarDEMMosaicSource, ...]:
        covering = tuple(
            source for source in self.sources
            if source.coverage.contains(latitude, longitude)
        )
        if not covering:
            raise LunarDEMOutOfCoverageError(
                f"No lunar DEM source declares coverage at latitude={latitude:.8f}, "
                f"longitude={longitude:.8f}"
            )
        return covering

    def _select_sources(self, covering: tuple[LunarDEMMosaicSource, ...]) -> tuple[LunarDEMMosaicSource, ...]:
        if self.strategy == "mean":
            return covering
        if self.strategy == "finest":
            return (min(covering, key=lambda source: source.resolution_m or math.inf),)
        return (covering[0],)

    def _sample(self, latitude_deg: Any, longitude_deg: Any) -> tuple[float, tuple[str, ...]]:
        self._ensure_open()
        latitude, longitude = self._validate_query(latitude_deg, longitude_deg)
        selected = self._select_sources(self._covering_sources(latitude, longitude))
        values: list[float] = []
        names: list[str] = []
        for source in selected:
            try:
                raw_value = source.model.predict_altitude_m(latitude, longitude)
                value = _finite_number(raw_value, f"source {source.name!r} altitude_m")
            except Exception as exc:
                raise RuntimeError(
                    f"DEM source {source.name!r} failed inside its declared coverage; "
                    "the mosaic did not silently fall back to another source"
                ) from exc
            values.append(value)
            names.append(source.name)
        altitude = float(np.mean(np.asarray(values, dtype=np.float64)))
        return altitude, tuple(names)

    def predict_altitude_m(self, latitude_deg: float, longitude_deg: float) -> float:
        """Return a height using the configured deterministic source strategy."""
        altitude, _ = self._sample(latitude_deg, longitude_deg)
        return altitude

    def predict(self, query: LunarLimbQuery) -> LunarLimbPrediction:
        """Return a provider-neutral prediction with the selected source names."""
        if not isinstance(query, LunarLimbQuery):
            raise TypeError("query must be a LunarLimbQuery")
        altitude, source_names = self._sample(
            query.selenographic_latitude_deg, query.selenographic_longitude_deg
        )
        return LunarLimbPrediction(
            altitude_m=altitude,
            model_name=self.metadata.name,
            model_type=self.metadata.model_type,
            source="; ".join(source_names),
            uncertainty_m=None,
            status="ok",
        )

    def predict_many(self, latitude_deg: Any, longitude_deg: Any) -> np.ndarray:
        """Sample broadcast-compatible coordinate arrays in deterministic order."""
        self._ensure_open()
        raw_latitudes = np.asarray(latitude_deg, dtype=object)
        raw_longitudes = np.asarray(longitude_deg, dtype=object)
        if any(isinstance(value, (bool, np.bool_)) for value in raw_latitudes.flat) or any(
            isinstance(value, (bool, np.bool_)) for value in raw_longitudes.flat
        ):
            raise TypeError("latitude_deg and longitude_deg must contain numeric values, not booleans")
        try:
            latitudes, longitudes = np.broadcast_arrays(
                np.asarray(latitude_deg, dtype=np.float64),
                np.asarray(longitude_deg, dtype=np.float64),
            )
        except (TypeError, ValueError) as exc:
            raise TypeError("latitude_deg and longitude_deg must be numeric and broadcast-compatible") from exc
        if not np.all(np.isfinite(latitudes)) or not np.all(np.isfinite(longitudes)):
            raise ValueError("latitude_deg and longitude_deg must be finite")
        if np.any((latitudes < -90.0) | (latitudes > 90.0)):
            raise ValueError("latitude_deg must be within [-90, 90]")
        result = np.empty(latitudes.shape, dtype=np.float64)
        for index in np.ndindex(latitudes.shape):
            result[index] = self.predict_altitude_m(
                float(latitudes[index]), float(longitudes[index])
            )
        return result

    def close(self) -> None:
        """Close the virtual mosaic and optionally close every owned source."""
        if self._closed:
            return
        self._closed = True
        if self._close_sources:
            for source in self.sources:
                close = getattr(source.model, "close", None)
                if callable(close):
                    close()

    def __enter__(self) -> "LunarDEMMosaicModel":
        self._ensure_open()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        del exc_type, exc, traceback
        self.close()
