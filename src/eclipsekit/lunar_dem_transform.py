"""Lazy lunar DEM query adapter for explicit body-fixed frame/datum conversion.

The wrapper exposes a DEM whose public query coordinates and heights use the
transform's target frame and spherical reference radius. Sampling is delegated
to the original DEM after inverse-transforming each query; the raster itself is
never warped, resampled, copied, or rewritten.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np

from .limb import LunarLimbModelMetadata, LunarLimbPrediction, LunarLimbQuery
from .lunar_coordinates import LunarCoordinateTransform


def _normalise_label(value: str) -> str:
    return " ".join(value.split()).casefold()


def _finite_scalar(value: Any, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number)):
        raise TypeError(f"{name} must be a numeric scalar")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _product_info_dict(info: Any) -> dict[str, Any]:
    if callable(getattr(info, "to_dict", None)):
        result = info.to_dict()
        if isinstance(result, dict):
            return result
    return {
        key: value
        for key, value in vars(info).items()
        if not key.startswith("_")
    }


@dataclass(frozen=True, slots=True)
class TransformedLunarDEMProductInfo:
    """Metadata describing the target-coordinate view of a source DEM."""

    format: str
    product_id: str
    coordinate_system_name: str
    vertical_datum: str
    reference_radius_m: float
    source_coordinate_system_name: str
    source_vertical_datum: str
    source_reference_radius_m: float
    source_product_info: dict[str, Any]
    coordinate_transform: dict[str, Any]
    shape: tuple[int, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "product_id": self.product_id,
            "coordinate_system_name": self.coordinate_system_name,
            "vertical_datum": self.vertical_datum,
            "reference_radius_m": self.reference_radius_m,
            "source_coordinate_system_name": self.source_coordinate_system_name,
            "source_vertical_datum": self.source_vertical_datum,
            "source_reference_radius_m": self.source_reference_radius_m,
            "source_product_info": self.source_product_info,
            "coordinate_transform": self.coordinate_transform,
            "shape": list(self.shape) if self.shape is not None else None,
            "storage": "virtual target-frame view; source DEM is sampled lazily without raster reprojection",
        }


class TransformedLunarDEMModel:
    """Expose a source lunar DEM in a different explicitly declared frame/datum.

    ``coordinate_transform`` must map source DEM coordinates/heights to the
    target coordinates/heights accepted by this wrapper. Every target query is
    inverse-rotated before sampling the source DEM. The returned source height
    is then converted to the target spherical reference radius.

    ``source_coordinate_system_name`` is an explicit mapping assertion: it
    must match the exact coordinate-system label in the source product's
    metadata. The caller is responsible for establishing that the labelled
    product really uses ``coordinate_transform.frame_transform.source_frame``.
    No frame is inferred from an ephemeris name or from a vague label.

    By default the wrapper does not own the source reader. Set
    ``close_source=True`` to make :meth:`close` close it as well.
    """

    def __init__(
        self,
        source_model: Any,
        coordinate_transform: LunarCoordinateTransform,
        *,
        source_coordinate_system_name: str,
        name: str | None = None,
        close_source: bool = False,
    ) -> None:
        if not isinstance(coordinate_transform, LunarCoordinateTransform):
            raise TypeError("coordinate_transform must be a LunarCoordinateTransform")
        if not callable(getattr(source_model, "predict_altitude_m", None)):
            raise TypeError("source_model must provide predict_altitude_m(latitude_deg, longitude_deg)")
        if not isinstance(close_source, bool):
            raise TypeError("close_source must be a bool")
        if not isinstance(source_coordinate_system_name, str) or not source_coordinate_system_name.strip():
            raise ValueError("source_coordinate_system_name must be a non-empty string")

        info = getattr(source_model, "product_info", None)
        if info is None:
            raise TypeError("source_model must expose product_info metadata")
        source_label = getattr(info, "coordinate_system_name", None)
        if not isinstance(source_label, str) or not source_label.strip():
            raise ValueError("source DEM product_info must declare coordinate_system_name")
        if _normalise_label(source_label) != _normalise_label(source_coordinate_system_name):
            raise ValueError(
                "source_coordinate_system_name does not match the source DEM product metadata"
            )

        source_metadata = getattr(source_model, "metadata", None)
        source_datum = getattr(info, "vertical_datum", None)
        if source_datum is None:
            source_datum = getattr(source_metadata, "vertical_datum", None)
        if not isinstance(source_datum, str) or not source_datum.strip():
            raise ValueError("source DEM metadata must declare a vertical datum")
        transform_datum = coordinate_transform.vertical_transform.source_vertical_datum
        if _normalise_label(source_datum) != _normalise_label(transform_datum):
            raise ValueError("source DEM vertical datum does not match transform source_vertical_datum")

        source_radius = getattr(info, "reference_radius_m", None)
        if isinstance(source_radius, (bool, np.bool_)) or not isinstance(
            source_radius, (int, float, np.number)
        ):
            raise ValueError("source DEM metadata must declare a numeric reference_radius_m")
        source_radius = float(source_radius)
        if not math.isfinite(source_radius) or source_radius <= 0.0:
            raise ValueError("source DEM reference_radius_m must be finite and positive")
        expected_radius = coordinate_transform.vertical_transform.source_reference_radius_m
        if not math.isclose(source_radius, expected_radius, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("source DEM reference radius does not match transform source radius")

        target_frame = coordinate_transform.frame_transform.target_frame
        target_datum = coordinate_transform.vertical_transform.target_vertical_datum
        target_radius = coordinate_transform.vertical_transform.target_reference_radius_m
        source_info_dict = _product_info_dict(info)
        shape_value = getattr(info, "shape", None)
        shape = tuple(int(value) for value in shape_value) if shape_value is not None else None
        product_id = str(getattr(info, "product_id", None) or getattr(source_metadata, "product_id", None) or "")
        source_format = str(getattr(info, "format", None) or getattr(source_metadata, "model_type", None) or "lunar_dem")

        self.source_model = source_model
        self.coordinate_transform = coordinate_transform
        self._inverse_frame = coordinate_transform.frame_transform.inverse()
        self._closed = False
        self._close_source = close_source
        self.product_info = TransformedLunarDEMProductInfo(
            format=f"virtual:{source_format}",
            product_id=product_id,
            coordinate_system_name=target_frame,
            vertical_datum=target_datum,
            reference_radius_m=target_radius,
            source_coordinate_system_name=source_label,
            source_vertical_datum=source_datum,
            source_reference_radius_m=source_radius,
            source_product_info=source_info_dict,
            coordinate_transform={
                "frame": coordinate_transform.frame_transform.to_dict(),
                "vertical": coordinate_transform.vertical_transform.to_dict(),
                "sampling_strategy": "inverse-transform target query, sample source DEM, convert returned height",
            },
            shape=shape,
        )
        source_name = getattr(source_metadata, "name", type(source_model).__name__)
        source_path = getattr(source_metadata, "source", str(source_name))
        self.metadata = LunarLimbModelMetadata(
            name=name or f"{source_name} [{target_frame}]",
            model_type="custom",
            source=f"virtual transform of {source_path}",
            reference_frame="selenographic",
            vertical_datum=target_datum,
            resolution_m=getattr(source_metadata, "resolution_m", None),
            validation_rmse_m=getattr(source_metadata, "validation_rmse_m", None),
            description=(
                "Lazy target-frame/datum view of an existing lunar DEM. The source raster is "
                "sampled in its native frame after inverse coordinate rotation; no raster "
                "reprojection, resampling, copy, or rewrite occurs. "
                f"{coordinate_transform.frame_transform.source_frame} -> {target_frame}."
            ),
            product_id=product_id or None,
            coordinate_system=target_frame,
            reference_radius_m=target_radius,
            pixel_registration=getattr(source_metadata, "pixel_registration", None),
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("TransformedLunarDEMModel is closed")

    def predict_altitude_m(self, latitude_deg: float, longitude_deg: float) -> float:
        """Return a target-datum height for one target-frame planetocentric query."""
        self._ensure_open()
        latitude = _finite_scalar(latitude_deg, "latitude_deg")
        longitude = _finite_scalar(longitude_deg, "longitude_deg")
        if not -90.0 <= latitude <= 90.0:
            raise ValueError("latitude_deg must be within [-90, 90]")
        source_latitude, source_longitude = self._inverse_frame.transform_latlon(
            latitude, longitude
        )
        source_height = _finite_scalar(
            self.source_model.predict_altitude_m(float(source_latitude), float(source_longitude)),
            "source DEM altitude_m",
        )
        target_height = self.coordinate_transform.vertical_transform.transform_height_m(source_height)
        return _finite_scalar(target_height, "target DEM altitude_m")

    def predict(self, query: LunarLimbQuery) -> LunarLimbPrediction:
        """Provider-neutral prediction interface retaining transform provenance."""
        if not isinstance(query, LunarLimbQuery):
            raise TypeError("query must be a LunarLimbQuery")
        altitude = self.predict_altitude_m(
            query.selenographic_latitude_deg, query.selenographic_longitude_deg
        )
        return LunarLimbPrediction(
            altitude_m=altitude,
            model_name=self.metadata.name,
            model_type=self.metadata.model_type,
            source=self.metadata.source,
        )

    def predict_many(self, latitude_deg: Any, longitude_deg: Any) -> np.ndarray:
        """Sample broadcast-compatible target coordinates; return their common shape."""
        self._ensure_open()
        raw_lat = np.asarray(latitude_deg, dtype=object)
        raw_lon = np.asarray(longitude_deg, dtype=object)
        if any(isinstance(value, (bool, np.bool_)) for value in raw_lat.flat) or any(
            isinstance(value, (bool, np.bool_)) for value in raw_lon.flat
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
        source_latitudes, source_longitudes = self._inverse_frame.transform_latlon(
            latitudes, longitudes
        )
        source_heights = np.empty(latitudes.shape, dtype=np.float64)
        for index in np.ndindex(latitudes.shape):
            source_heights[index] = _finite_scalar(
                self.source_model.predict_altitude_m(
                    float(source_latitudes[index]), float(source_longitudes[index])
                ),
                "source DEM altitude_m",
            )
        target_heights = self.coordinate_transform.vertical_transform.transform_height_m(
            source_heights
        )
        return np.asarray(target_heights, dtype=np.float64)

    def close(self) -> None:
        """Close this view and, only when requested, its underlying source reader."""
        if not self._closed:
            self._closed = True
            if self._close_source:
                close = getattr(self.source_model, "close", None)
                if callable(close):
                    close()

    def __enter__(self) -> "TransformedLunarDEMModel":
        self._ensure_open()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        del exc_type, exc, traceback
        self.close()
