"""Additional, provenance-aware lunar DEM readers (PDS4, GeoTIFF and JP2).

PDS4 binary arrays are opened read-only through ``numpy.memmap``. GeoTIFF and
JPEG 2000 use the optional Rasterio/GDAL backend and read bounded windows.
Only regular, north-up, east-positive simple-cylindrical longitude/latitude
grids are supported here. No reprojection or lunar-frame transformation is
performed; the declared lunar frame and vertical datum are retained verbatim.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import importlib
import math
from pathlib import Path
import re
from threading import RLock
from typing import Any, Literal
import xml.etree.ElementTree as ET

import numpy as np

from .limb import LunarLimbModelMetadata, LunarLimbPrediction, LunarLimbQuery
from .topography import LunarDEMCacheInfo, LunarDEMWindow

ValueInterpretation = Literal["height", "radius"]

_UNIT_TO_METRES = {
    "M": 1.0, "METER": 1.0, "METERS": 1.0, "METRE": 1.0, "METRES": 1.0,
    "KM": 1000.0, "KILOMETER": 1000.0, "KILOMETERS": 1000.0,
    "KILOMETRE": 1000.0, "KILOMETRES": 1000.0,
    "CM": 0.01, "CENTIMETER": 0.01, "CENTIMETERS": 0.01,
    "MM": 0.001, "MILLIMETER": 0.001, "MILLIMETERS": 0.001,
}

_PDS4_DTYPES: dict[str, str] = {
    "IEEE754MSBSINGLE": ">f4", "IEEE754LSBSINGLE": "<f4",
    "IEEE754MSBDOUBLE": ">f8", "IEEE754LSBDOUBLE": "<f8",
    "SIGNEDMSB2": ">i2", "SIGNEDLSB2": "<i2",
    "SIGNEDMSB4": ">i4", "SIGNEDLSB4": "<i4",
    "UNSIGNEDBYTE": "u1", "SIGNEDBYTE": "i1",
    "UNSIGNEDMSB2": ">u2", "UNSIGNEDLSB2": "<u2",
    "UNSIGNEDMSB4": ">u4", "UNSIGNEDLSB4": "<u4",
}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":")[-1]


def _elements(root: ET.Element, name: str) -> list[ET.Element]:
    wanted = name.casefold()
    return [item for item in root.iter() if _local_name(item.tag).casefold() == wanted]


def _first_text(root: ET.Element, name: str, *, required: bool = False) -> str | None:
    for item in _elements(root, name):
        if item.text and item.text.strip():
            return item.text.strip()
    if required:
        raise ValueError(f"PDS4 label is missing required element {name}")
    return None


def _float_text(root: ET.Element, name: str, *, required: bool = False) -> float | None:
    raw = _first_text(root, name, required=required)
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"PDS4 element {name} must be numeric, found {raw!r}") from exc
    if not math.isfinite(value):
        raise ValueError(f"PDS4 element {name} must be finite")
    return value


def _unit_factor(unit: str | None, field: str) -> float:
    if unit is None:
        raise ValueError(f"A length unit is required for {field}")
    factor = _UNIT_TO_METRES.get(unit.strip().strip("<>").upper())
    if factor is None:
        raise ValueError(f"Unsupported length unit for {field}: {unit!r}")
    return factor


def _parse_quantity(element: ET.Element, field: str) -> tuple[float, str | None]:
    if element.text is None or not element.text.strip():
        raise ValueError(f"PDS4 element {field} has no value")
    try:
        value = float(element.text.strip())
    except ValueError as exc:
        raise ValueError(f"PDS4 element {field} must be numeric") from exc
    if not math.isfinite(value):
        raise ValueError(f"PDS4 element {field} must be finite")
    unit = element.attrib.get("unit")
    return value, unit


def _pds4_type(name: str) -> np.dtype[Any]:
    key = re.sub(r"[^A-Z0-9]", "", name.upper())
    spec = _PDS4_DTYPES.get(key)
    if spec is None:
        raise ValueError(f"Unsupported PDS4 Element_Array data_type: {name!r}")
    return np.dtype(spec)


def _normalise_registration(value: str | None) -> Literal["area", "point"]:
    if value is None:
        raise ValueError("Pixel registration must be declared; refusing to infer cell geometry")
    key = re.sub(r"[^a-z]", "", value.casefold())
    if key in {"area", "pixelarea", "pixelisarea", "cell"}:
        return "area"
    if key in {"point", "pixel", "pixelcenter", "pixelispoint"}:
        return "point"
    raise ValueError(f"Pixel registration is unsupported: {value!r}")


def _validate_value_interpretation(value: str | None) -> ValueInterpretation:
    if value is None:
        raise ValueError(
            "DEM sample interpretation is ambiguous; specify 'height' (already relative "
            "to the reference sphere) or 'radius' (radial distance from the lunar centre)"
        )
    key = value.strip().casefold().replace("_", "-")
    if key in {"height", "elevation", "height-above-reference", "height-above-datum"}:
        return "height"
    if key in {"radius", "radial", "radius-from-centre", "planetocentric-radius"}:
        return "radius"
    raise ValueError("value_interpretation must be 'height' or 'radius'")


@dataclass(frozen=True, slots=True)
class LunarDEMFormatProductInfo:
    """Common geometry, scaling and provenance for supported raster products."""

    format: str
    product_id: str
    source_file: str
    data_file: str
    lines: int
    samples: int
    sample_type: str
    unit: str
    scaling_factor: float
    value_offset_m: float
    value_interpretation: ValueInterpretation
    reference_radius_m: float
    coordinate_system_name: str
    vertical_datum: str
    pixel_registration: str
    north_latitude_deg: float
    south_latitude_deg: float
    west_longitude_deg: float
    east_longitude_deg: float
    resolution_m: float
    data_offset_bytes: int
    file_size_bytes: int

    @property
    def shape(self) -> tuple[int, int]:
        return self.lines, self.samples

    @property
    def global_longitude(self) -> bool:
        return math.isclose(self.east_longitude_deg - self.west_longitude_deg, 360.0,
                            rel_tol=0.0, abs_tol=1e-6)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format, "product_id": self.product_id,
            "source_file": self.source_file, "data_file": self.data_file,
            "shape": list(self.shape), "sample_type": self.sample_type,
            "unit": self.unit, "scaling_factor": self.scaling_factor,
            "value_offset_m": self.value_offset_m,
            "value_interpretation": self.value_interpretation,
            "reference_radius_m": self.reference_radius_m,
            "coordinate_system_name": self.coordinate_system_name,
            "vertical_datum": self.vertical_datum,
            "pixel_registration": self.pixel_registration,
            "coverage": {
                "north_latitude_deg": self.north_latitude_deg,
                "south_latitude_deg": self.south_latitude_deg,
                "west_longitude_deg": self.west_longitude_deg,
                "east_longitude_deg": self.east_longitude_deg,
            },
            "resolution_m": self.resolution_m,
            "data_offset_bytes": self.data_offset_bytes,
            "file_size_bytes": self.file_size_bytes,
            "coordinate_transform": "none; regular simple-cylindrical grid is sampled as declared",
        }


class _CachedLunarGridDEM:
    """Shared bounded tile cache and bilinear sampling for regular lunar grids."""

    def __init__(
        self,
        *,
        info: LunarDEMFormatProductInfo,
        name: str | None,
        tile_shape: int | tuple[int, int],
        cache_tiles: int,
    ) -> None:
        self.product_info = info
        self.tile_shape = self._validate_tile_shape(tile_shape)
        if isinstance(cache_tiles, bool) or not isinstance(cache_tiles, (int, np.integer)):
            raise TypeError("cache_tiles must be an integer")
        if int(cache_tiles) < 0:
            raise ValueError("cache_tiles must be non-negative")
        self.cache_tiles = int(cache_tiles)
        self._tile_cache: OrderedDict[tuple[int, int], np.ndarray] = OrderedDict()
        self._cache_lock = RLock()
        self._cache_hits = self._cache_misses = self._cache_evictions = 0
        self._closed = False
        model_type = {"PDS4": "pds4_dem", "GeoTIFF": "geotiff_dem", "JP2": "jp2_dem"}[info.format]
        self.metadata = LunarLimbModelMetadata(
            name=name or info.product_id or Path(info.data_file).name,
            model_type=model_type,
            source=f"{info.data_file} [{info.product_id}]",
            reference_frame="selenographic",
            vertical_datum=info.vertical_datum,
            resolution_m=info.resolution_m,
            description=(
                f"{info.format} lunar DEM on a regular east-positive simple-cylindrical grid; "
                "window reads and a bounded LRU tile cache are used. No reprojection or "
                "lunar body-fixed frame transformation is applied."
            ),
            product_id=info.product_id,
            coordinate_system=info.coordinate_system_name,
            reference_radius_m=info.reference_radius_m,
            pixel_registration=info.pixel_registration,
        )

    @staticmethod
    def _validate_tile_shape(tile_shape: int | tuple[int, int]) -> tuple[int, int]:
        if isinstance(tile_shape, bool):
            raise TypeError("tile_shape must be a positive integer or a pair of positive integers")
        if isinstance(tile_shape, (int, np.integer)):
            values = (int(tile_shape), int(tile_shape))
        elif isinstance(tile_shape, tuple) and len(tile_shape) == 2:
            values = tile_shape
        else:
            raise TypeError("tile_shape must be a positive integer or a pair of positive integers")
        result: list[int] = []
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
                raise TypeError("tile_shape entries must be integers")
            if int(value) < 1:
                raise ValueError("tile_shape entries must be positive")
            result.append(int(value))
        return result[0], result[1]

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError(f"{self.product_info.format} lunar DEM model is closed")

    def _read_raw_window(self, row_start: int, row_stop: int,
                         column_start: int, column_stop: int) -> np.ndarray:
        raise NotImplementedError

    def _raw_to_height(self, raw: Any) -> np.ndarray:
        masked = np.ma.asarray(raw)
        values = np.asarray(masked.data, dtype=np.float64).copy()
        mask = np.ma.getmaskarray(masked)
        if np.any(mask):
            values[mask] = np.nan
        unit_factor = _unit_factor(self.product_info.unit, "DEM sample values")
        values = values * self.product_info.scaling_factor * unit_factor + self.product_info.value_offset_m
        if self.product_info.value_interpretation == "radius":
            values = values - self.product_info.reference_radius_m
        values.setflags(write=False)
        return values

    @property
    def coverage(self) -> tuple[float, float, float, float]:
        info = self.product_info
        return (info.south_latitude_deg, info.north_latitude_deg,
                info.west_longitude_deg, info.east_longitude_deg)

    @property
    def is_closed(self) -> bool:
        return self._closed

    def _load_tile(self, tile_row: int, tile_column: int) -> np.ndarray:
        th, tw = self.tile_shape
        r0, c0 = tile_row * th, tile_column * tw
        r1, c1 = min(r0 + th, self.product_info.lines), min(c0 + tw, self.product_info.samples)
        tile = self._raw_to_height(self._read_raw_window(r0, r1, c0, c1))
        tile.setflags(write=False)
        return tile

    def _get_tile(self, row: int, column: int) -> np.ndarray:
        key = (row // self.tile_shape[0], column // self.tile_shape[1])
        with self._cache_lock:
            self._ensure_open()
            tile = self._tile_cache.get(key)
            if tile is not None:
                self._cache_hits += 1
                self._tile_cache.move_to_end(key)
                return tile
            self._cache_misses += 1
            tile = self._load_tile(*key)
            if self.cache_tiles:
                self._tile_cache[key] = tile
                while len(self._tile_cache) > self.cache_tiles:
                    self._tile_cache.popitem(last=False)
                    self._cache_evictions += 1
            return tile

    def cache_info(self) -> LunarDEMCacheInfo:
        with self._cache_lock:
            self._ensure_open()
            return LunarDEMCacheInfo(
                tile_shape=self.tile_shape, max_tiles=self.cache_tiles,
                current_tiles=len(self._tile_cache), hits=self._cache_hits,
                misses=self._cache_misses, evictions=self._cache_evictions,
                cached_bytes=sum(item.nbytes for item in self._tile_cache.values()),
                max_bytes=(self.cache_tiles * self.tile_shape[0] * self.tile_shape[1] * 8),
            )

    def clear_tile_cache(self, *, reset_statistics: bool = True) -> None:
        if not isinstance(reset_statistics, bool):
            raise TypeError("reset_statistics must be a bool")
        with self._cache_lock:
            self._ensure_open()
            self._tile_cache.clear()
            if reset_statistics:
                self._cache_hits = self._cache_misses = self._cache_evictions = 0

    def read_window(self, row_start: int, row_stop: int,
                    column_start: int, column_stop: int) -> LunarDEMWindow:
        self._ensure_open()
        bounds = (row_start, row_stop, column_start, column_stop)
        for name, value in zip(("row_start", "row_stop", "column_start", "column_stop"), bounds):
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
                raise TypeError(f"{name} must be an integer")
        r0, r1, c0, c1 = map(int, bounds)
        if r0 < 0 or c0 < 0 or r1 <= r0 or c1 <= c0:
            raise ValueError("DEM window bounds must be non-negative and have positive extent")
        if r1 > self.product_info.lines or c1 > self.product_info.samples:
            raise IndexError("DEM window extends beyond image bounds")
        return LunarDEMWindow(r0, r1, c0, c1, self._raw_to_height(
            self._read_raw_window(r0, r1, c0, c1)))

    def iter_tiles(self, tile_shape: int | tuple[int, int] | None = None):
        self._ensure_open()
        height, width = self.tile_shape if tile_shape is None else self._validate_tile_shape(tile_shape)
        for r0 in range(0, self.product_info.lines, height):
            r1 = min(r0 + height, self.product_info.lines)
            for c0 in range(0, self.product_info.samples, width):
                c1 = min(c0 + width, self.product_info.samples)
                yield self.read_window(r0, r1, c0, c1)

    def _coordinates_to_pixel(self, latitude_deg: float, longitude_deg: float) -> tuple[float, float]:
        info = self.product_info
        lat = float(latitude_deg)
        lon = float(longitude_deg)
        if not math.isfinite(lat) or not math.isfinite(lon):
            raise ValueError("Lunar DEM query coordinates must be finite")
        if not info.south_latitude_deg - 1e-10 <= lat <= info.north_latitude_deg + 1e-10:
            raise ValueError("Latitude is outside lunar DEM coverage")
        if info.global_longitude:
            lon = info.west_longitude_deg + ((lon - info.west_longitude_deg) % 360.0)
        else:
            lon += 360.0 * round((0.5 * (info.west_longitude_deg + info.east_longitude_deg) - lon) / 360.0)
            if lon < info.west_longitude_deg - 1e-10 or lon > info.east_longitude_deg + 1e-10:
                raise ValueError("Longitude is outside lunar DEM coverage")
        dlat = (info.north_latitude_deg - info.south_latitude_deg) / (
            info.lines if info.pixel_registration == "area" else info.lines - 1)
        dlon = (info.east_longitude_deg - info.west_longitude_deg) / (
            info.samples if info.pixel_registration == "area" else info.samples - 1)
        if dlat <= 0.0 or dlon <= 0.0:
            raise ValueError("Lunar DEM grid spacing must be positive")
        half = 0.5 if info.pixel_registration == "area" else 0.0
        row = (info.north_latitude_deg - lat) / dlat - half
        col = (lon - info.west_longitude_deg) / dlon - half
        # Area-registered bounds are outer cell edges. Clamp points in the
        # half-cell fringe to the nearest sample centre, never extrapolate.
        row = min(max(row, 0.0), float(info.lines - 1))
        col = min(max(col, 0.0), float(info.samples - 1))
        return row, col

    def pixel_center(self, row: int, column: int) -> tuple[float, float]:
        self._ensure_open()
        if not (0 <= row < self.product_info.lines and 0 <= column < self.product_info.samples):
            raise IndexError("Lunar DEM pixel index is outside the image")
        info = self.product_info
        dlat = (info.north_latitude_deg - info.south_latitude_deg) / (
            info.lines if info.pixel_registration == "area" else info.lines - 1)
        dlon = (info.east_longitude_deg - info.west_longitude_deg) / (
            info.samples if info.pixel_registration == "area" else info.samples - 1)
        half = 0.5 if info.pixel_registration == "area" else 0.0
        lat = info.north_latitude_deg - (row + half) * dlat
        lon = info.west_longitude_deg + (column + half) * dlon
        return float(lat), float((lon + 180.0) % 360.0 - 180.0)

    def predict(self, query: LunarLimbQuery) -> LunarLimbPrediction:
        self._ensure_open()
        if not isinstance(query, LunarLimbQuery):
            raise TypeError("query must be a LunarLimbQuery")
        y, x = self._coordinates_to_pixel(query.selenographic_latitude_deg,
                                          query.selenographic_longitude_deg)
        r0, c0 = int(math.floor(y)), int(math.floor(x))
        r1, c1 = min(r0 + 1, self.product_info.lines - 1), min(c0 + 1, self.product_info.samples - 1)
        fy, fx = y - r0, x - c0
        if self.product_info.global_longitude:
            c1 = (c0 + 1) % self.product_info.samples
        coords = ((r0, c0), (r0, c1), (r1, c0), (r1, c1))
        weights = ((1-fy)*(1-fx), (1-fy)*fx, fy*(1-fx), fy*fx)
        vals = []
        for row, col in coords:
            tile = self._get_tile(row, col)
            vals.append(float(tile[row % self.tile_shape[0], col % self.tile_shape[1]]))
        needed = [weight > 1e-14 for weight in weights]
        if not all(math.isfinite(value) for value, use in zip(vals, needed) if use):
            raise ValueError("Lunar DEM interpolation touches missing or invalid elevation cells")
        altitude = sum(value * weight for value, weight in zip(vals, weights) if weight > 0.0)
        return LunarLimbPrediction(
            altitude_m=float(altitude), model_name=self.metadata.name,
            model_type=self.metadata.model_type, source=self.metadata.source,
        )

    def predict_altitude_m(self, latitude_deg: float, longitude_deg: float) -> float:
        return self.predict(LunarLimbQuery(latitude_deg, longitude_deg, 0.0)).altitude_m

    def close(self) -> None:
        with self._cache_lock:
            if not self._closed:
                self._closed = True
                self._tile_cache.clear()
                self._close_source()

    def _close_source(self) -> None:
        pass

    def __enter__(self):
        self._ensure_open()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        del exc_type, exc, traceback
        self.close()


class PDS4LunarDEMModel(_CachedLunarGridDEM):
    """Reader for a conservative PDS4 ``Array_2D_Image`` lunar DEM subset.

    The label must provide a regular simple-cylindrical grid, bounds, pixel
    registration, a lunar coordinate-system name and a spherical reference
    radius. Sample values must be identified as radial ``radius`` or already
    datum-relative ``height`` either in the label or via the explicit argument.
    Unsupported or ambiguous geometry is rejected rather than inferred.
    """

    def __init__(self, label_path: str | Path, image_path: str | Path | None = None, *,
                 name: str | None = None, value_interpretation: str | None = None,
                 expected_reference_radius_m: float | None = 1_737_400.0,
                 radius_tolerance_m: float = 1.0,
                 expected_coordinate_system: str | None = None,
                 tile_shape: int | tuple[int, int] = 512, cache_tiles: int = 8) -> None:
        self._validate_tile_shape(tile_shape)
        if isinstance(cache_tiles, bool) or not isinstance(cache_tiles, (int, np.integer)) or int(cache_tiles) < 0:
            raise ValueError("cache_tiles must be a non-negative integer")
        self.label_path = Path(label_path).expanduser().resolve()
        if not self.label_path.is_file():
            raise FileNotFoundError(self.label_path)
        try:
            root = ET.parse(self.label_path).getroot()
        except ET.ParseError as exc:
            raise ValueError(f"Invalid PDS4 XML label: {exc}") from exc
        product_root = _local_name(root.tag).casefold()
        if not product_root.startswith("product_"):
            raise ValueError("Expected a PDS4 Product_* XML label")
        array_area: ET.Element | None = None
        array: ET.Element | None = None
        file_name: str | None = None
        for area_name in ("File_Area_Observational", "File_Area_Ancillary", "File_Area"):
            for area in _elements(root, area_name):
                candidates = [x for x in area.iter() if _local_name(x.tag).casefold() == "array_2d_image"]
                if not candidates:
                    candidates = [x for x in area.iter() if _local_name(x.tag).casefold() == "array_2d"]
                if candidates:
                    array_area, array = area, candidates[0]
                    file_node = next((x for x in area.iter() if _local_name(x.tag).casefold() == "file"), None)
                    if file_node is not None:
                        file_name = _first_text(file_node, "file_name")
                    break
            if array is not None:
                break
        if array is None or array_area is None:
            raise ValueError("PDS4 label has no supported File_Area with Array_2D_Image")
        if image_path is None:
            if not file_name:
                raise ValueError("PDS4 File_Area is missing file_name; pass image_path explicitly")
            self.image_path = (self.label_path.parent / file_name).resolve()
        else:
            self.image_path = Path(image_path).expanduser().resolve()
        if not self.image_path.is_file():
            raise FileNotFoundError(self.image_path)

        axes_value = _first_text(array, "axes", required=True)
        if axes_value != "2":
            raise ValueError(f"Only two-dimensional PDS4 arrays are supported; found axes={axes_value}")
        axis_order = (_first_text(array, "axis_index_order") or "Last Index Fastest").casefold()
        if axis_order != "last index fastest":
            raise ValueError("PDS4 array must declare axis_index_order='Last Index Fastest'")
        axis_entries = [x for x in array.iter() if _local_name(x.tag).casefold() == "axis_array"]
        axis_map: dict[str, tuple[int, int]] = {}
        for entry in axis_entries:
            axis_name = (_first_text(entry, "axis_name", required=True) or "").casefold()
            elements = int(_first_text(entry, "elements", required=True) or "0")
            sequence = int(_first_text(entry, "sequence_number", required=True) or "0")
            axis_map[axis_name] = (sequence, elements)
        if "line" not in axis_map or "sample" not in axis_map:
            raise ValueError("PDS4 DEM axes must be named Line and Sample")
        if axis_map["line"][0] != 1 or axis_map["sample"][0] != 2:
            raise ValueError("PDS4 image axis order must be Line=1 and Sample=2")
        lines, samples = axis_map["line"][1], axis_map["sample"][1]
        if lines < 2 or samples < 2:
            raise ValueError("PDS4 DEM must have at least two rows and columns")
        element_array = next((x for x in array.iter()
                              if _local_name(x.tag).casefold() == "element_array"), None)
        if element_array is None:
            raise ValueError("PDS4 Array_2D_Image is missing Element_Array")
        data_type = _first_text(element_array, "data_type", required=True) or ""
        dtype = _pds4_type(data_type)
        scaling = _float_text(element_array, "scaling_factor")
        scaling = 1.0 if scaling is None else scaling
        value_offset = _float_text(element_array, "value_offset")
        value_offset = 0.0 if value_offset is None else value_offset
        unit = element_array.attrib.get("unit") or _first_text(element_array, "unit")
        if unit is None:
            unit = _first_text(array, "unit")
        unit_factor = _unit_factor(unit, "PDS4 Element_Array")
        offset_node = next((x for x in array if _local_name(x.tag).casefold() == "offset"), None)
        if offset_node is None:
            raise ValueError("PDS4 Array_2D_Image is missing its required byte offset")
        offset_value, offset_unit = _parse_quantity(offset_node, "Array_2D_Image/offset")
        if offset_unit and offset_unit.casefold() not in {"byte", "bytes"}:
            raise ValueError("PDS4 array offset must be expressed in bytes")
        if not offset_value.is_integer() or offset_value < 0:
            raise ValueError("PDS4 array byte offset must be a non-negative integer")
        data_offset = int(offset_value)
        expected_bytes = data_offset + lines * samples * dtype.itemsize
        file_size = self.image_path.stat().st_size
        if file_size < expected_bytes:
            raise ValueError(f"PDS4 image is truncated: need {expected_bytes} bytes, found {file_size}")

        projection = (_first_text(root, "map_projection_name") or "").casefold().replace("_", " ")
        projection_nodes = _elements(root, "Simple_Cylindrical")
        if not ("simple cylindrical" in projection or "equirectangular" in projection or projection_nodes):
            raise ValueError("PDS4 DEM must declare a supported simple-cylindrical/equirectangular projection")
        longitude_direction = (_first_text(root, "positive_longitude_direction")
                               or _first_text(root, "longitude_direction"))
        if longitude_direction is None:
            raise ValueError("PDS4 label must explicitly declare positive_longitude_direction=East")
        longitude_direction = longitude_direction.casefold()
        if longitude_direction not in {"east", "positive east"}:
            raise ValueError("PDS4 lunar DEM must use east-positive longitude")
        coordinate_name = (_first_text(root, "coordinate_system_name")
                           or _first_text(root, "local_identifier"))
        if not coordinate_name:
            raise ValueError("PDS4 label must declare coordinate_system_name")
        if expected_coordinate_system and coordinate_name.casefold() != expected_coordinate_system.strip().casefold():
            raise ValueError(f"PDS4 coordinate-system mismatch: expected {expected_coordinate_system!r}, found {coordinate_name!r}")
        registration_text = (_first_text(root, "pixel_registration")
                             or _first_text(root, "pixel_location"))
        registration = _normalise_registration(registration_text)

        bounds_parent = next((x for x in root.iter()
                              if _local_name(x.tag).casefold() == "bounding_coordinates"), root)
        west = _float_text(bounds_parent, "west_bounding_coordinate", required=True)
        east = _float_text(bounds_parent, "east_bounding_coordinate", required=True)
        south = _float_text(bounds_parent, "south_bounding_coordinate", required=True)
        north = _float_text(bounds_parent, "north_bounding_coordinate", required=True)
        assert west is not None and east is not None and south is not None and north is not None
        if east <= west and east + 360.0 > west:
            east += 360.0
        if not (-90.0 <= south < north <= 90.0) or not (0.0 < east - west <= 360.0 + 1e-6):
            raise ValueError("PDS4 lunar DEM bounds must describe a valid east-positive lon/lat grid")

        target_nodes = next(iter(_elements(root, "Target_Identification")), root)
        target_name = _first_text(target_nodes, "name") or _first_text(root, "target_name")
        if target_name is None or target_name.strip().casefold() != "moon":
            raise ValueError("PDS4 DEM target must be explicitly identified as Moon")
        radius_values: list[float] = []
        for scope in (target_nodes, root):
            for key in ("a_axis_radius", "b_axis_radius", "c_axis_radius"):
                nodes = _elements(scope, key)
                if nodes:
                    value, radius_unit = _parse_quantity(nodes[0], key)
                    radius_values.append(value * _unit_factor(radius_unit, key))
            if radius_values:
                break
        if not radius_values:
            for scope in (target_nodes, root):
                for key in ("reference_radius", "mean_radius", "equatorial_radius",
                            "semi_major_radius", "radius"):
                    nodes = _elements(scope, key)
                    if nodes:
                        value, radius_unit = _parse_quantity(nodes[0], key)
                        radius_values.append(value * _unit_factor(radius_unit, key))
                        break
                if radius_values:
                    break
        if not radius_values:
            raise ValueError("PDS4 label must declare a lunar reference radius with a length unit")
        radius = float(sum(radius_values) / len(radius_values))
        if not math.isfinite(radius_tolerance_m) or radius_tolerance_m < 0.0:
            raise ValueError("radius_tolerance_m must be finite and non-negative")
        if len(radius_values) > 1 and max(radius_values) - min(radius_values) > 0.01:
            raise ValueError("Only a spherical lunar reference surface is supported in Phase 9.2")
        if expected_reference_radius_m is not None:
            if not math.isfinite(expected_reference_radius_m) or expected_reference_radius_m <= 0:
                raise ValueError("expected_reference_radius_m must be finite and positive")
            if abs(radius - expected_reference_radius_m) > radius_tolerance_m:
                raise ValueError(f"PDS4 reference radius mismatch: expected {expected_reference_radius_m:.3f} m, found {radius:.3f} m")
        interpretation_text = (value_interpretation or _first_text(root, "value_interpretation")
                               or _first_text(root, "height_reference"))
        interpretation = _validate_value_interpretation(interpretation_text)
        vertical_datum = (_first_text(root, "vertical_datum")
                          or f"{interpretation} relative to declared lunar reference sphere")
        product_id = _first_text(root, "logical_identifier") or _first_text(root, "product_id") or self.image_path.stem
        lon_step = (east - west) / (samples if registration == "area" else samples - 1)
        lat_step = (north - south) / (lines if registration == "area" else lines - 1)
        resolution_m = radius * math.radians(max(lon_step, lat_step))
        self._map = np.memmap(self.image_path, dtype=np.uint8, mode="r", offset=data_offset,
                              shape=(lines, samples, dtype.itemsize))
        self._data = np.ndarray((lines, samples), dtype=dtype, buffer=self._map,
                                strides=(samples * dtype.itemsize, dtype.itemsize))
        self._missing_values: set[float] = set()
        special = next((x for x in array_area.iter()
                        if _local_name(x.tag).casefold() == "special_constants"), None)
        if special is not None:
            for key in ("missing_constant", "invalid_constant", "unknown_constant"):
                raw_missing = _float_text(special, key)
                if raw_missing is not None:
                    self._missing_values.add(raw_missing)
        self._sample_scale = float(scaling)
        self._sample_offset_m = float(value_offset * unit_factor)
        self._unit = str(unit)
        info = LunarDEMFormatProductInfo(
            format="PDS4", product_id=product_id, source_file=str(self.label_path),
            data_file=str(self.image_path), lines=lines, samples=samples,
            sample_type=data_type, unit=self._unit, scaling_factor=self._sample_scale,
            value_offset_m=self._sample_offset_m, value_interpretation=interpretation,
            reference_radius_m=radius, coordinate_system_name=coordinate_name,
            vertical_datum=vertical_datum, pixel_registration=registration,
            north_latitude_deg=north, south_latitude_deg=south,
            west_longitude_deg=west, east_longitude_deg=east,
            resolution_m=resolution_m, data_offset_bytes=data_offset, file_size_bytes=file_size,
        )
        super().__init__(info=info, name=name, tile_shape=tile_shape, cache_tiles=cache_tiles)

    def _read_raw_window(self, row_start: int, row_stop: int,
                         column_start: int, column_stop: int) -> np.ndarray:
        raw = np.array(self._data[row_start:row_stop, column_start:column_stop], copy=True)
        if self._missing_values:
            raw = raw.astype(np.float64, copy=False)
            for missing in self._missing_values:
                raw[raw == missing] = np.nan
        return raw

    def _close_source(self) -> None:
        mmap_obj = getattr(self._map, "_mmap", None)
        if mmap_obj is not None:
            mmap_obj.close()
        self._data = None
        self._map = None


class RasterioLunarDEMModel(_CachedLunarGridDEM):
    """Read-only windowed GeoTIFF/JP2 reader through optional Rasterio.

    Lunar frame, reference radius, vertical datum and whether sample values are
    radial radii or datum-relative heights must be present in dataset tags or
    passed explicitly. For non-georeferenced JP2, provide ``bounds`` and set
    ``coordinates_in_degrees=True``. No Earth-to-Moon CRS transformation is
    attempted; projected/rotated grids are rejected.
    """

    def __init__(self, image_path: str | Path, *, format: Literal["GeoTIFF", "JP2"],
                 name: str | None = None, coordinate_system_name: str | None = None,
                 reference_radius_m: float | None = None, vertical_datum: str | None = None,
                 value_interpretation: str | None = None, value_unit: str | None = None,
                 bounds: tuple[float, float, float, float] | None = None,
                 coordinates_in_degrees: bool = False,
                 expected_coordinate_system: str | None = None,
                 tile_shape: int | tuple[int, int] = 512, cache_tiles: int = 8) -> None:
        self.image_path = Path(image_path).expanduser().resolve()
        if not self.image_path.is_file():
            raise FileNotFoundError(self.image_path)
        try:
            rasterio = importlib.import_module("rasterio")
        except ImportError as exc:
            raise ImportError(
                "GeoTIFF/JP2 support requires the optional dependency. Install with: pip install 'eclipsekit[raster]'"
            ) from exc
        self._dataset = rasterio.open(self.image_path, "r")
        try:
            if self._dataset.count != 1:
                raise ValueError("Only single-band lunar DEM rasters are supported")
            driver = str(self._dataset.driver or "").upper()
            if format == "GeoTIFF" and driver not in {"GTIFF", "COG"}:
                raise ValueError(f"Expected a GeoTIFF raster; GDAL opened driver {driver!r}")
            if format == "JP2" and not ("JP2" in driver or self.image_path.suffix.casefold() in {".jp2", ".j2k", ".j2c"}):
                raise ValueError(f"Expected a JPEG 2000 raster; GDAL opened driver {driver!r}")
            if self._dataset.width < 2 or self._dataset.height < 2:
                raise ValueError("Lunar raster must have at least two rows and columns")
            tags = dict(self._dataset.tags())
            tags.update(self._dataset.tags(1))
            def tag(*keys: str) -> str | None:
                for key in keys:
                    if key in tags and str(tags[key]).strip():
                        return str(tags[key]).strip()
                return None
            coord_name = coordinate_system_name or tag("LUNAR_COORDINATE_SYSTEM", "COORDINATE_SYSTEM_NAME")
            radius_raw = reference_radius_m if reference_radius_m is not None else tag("LUNAR_REFERENCE_RADIUS_M", "REFERENCE_RADIUS_M")
            datum = vertical_datum or tag("LUNAR_VERTICAL_DATUM", "VERTICAL_DATUM")
            interp_raw = value_interpretation or tag("LUNAR_VALUE_INTERPRETATION", "VALUE_INTERPRETATION")
            unit = value_unit or (self._dataset.units[0] if self._dataset.units else None) or tag("UNIT", "ELEVATION_UNITS")
            if not coord_name:
                raise ValueError("Supply coordinate_system_name or LUNAR_COORDINATE_SYSTEM raster tag")
            if expected_coordinate_system and coord_name.casefold() != expected_coordinate_system.strip().casefold():
                raise ValueError(f"Raster lunar coordinate-system mismatch: expected {expected_coordinate_system!r}, found {coord_name!r}")
            if radius_raw is None:
                raise ValueError("Supply reference_radius_m or LUNAR_REFERENCE_RADIUS_M raster tag")
            radius = float(radius_raw)
            if not math.isfinite(radius) or radius <= 0:
                raise ValueError("reference_radius_m must be finite and positive")
            if not datum:
                raise ValueError("Supply vertical_datum or LUNAR_VERTICAL_DATUM raster tag")
            interpretation = _validate_value_interpretation(interp_raw)
            factor = _unit_factor(unit, "raster band values")
            transform = self._dataset.transform
            if self._dataset.crs is not None:
                if not self._dataset.crs.is_geographic:
                    raise ValueError("Only geographic longitude/latitude GeoTIFF/JP2 grids are supported; reproject explicitly")
                if bounds is None:
                    raster_bounds = self._dataset.bounds
                    bounds = (float(raster_bounds.left), float(raster_bounds.bottom),
                              float(raster_bounds.right), float(raster_bounds.top))
            else:
                if bounds is None or not coordinates_in_degrees:
                    raise ValueError("Unreferenced raster requires bounds=(west,south,east,north) and coordinates_in_degrees=True")
            if bounds is None or len(bounds) != 4:
                raise ValueError("bounds must contain west, south, east, north")
            west, south, east, north = (float(x) for x in bounds)
            if east <= west and east + 360.0 > west:
                east += 360.0
            if not (-90 <= south < north <= 90 and 0 < east - west <= 360.0 + 1e-6):
                raise ValueError("Raster bounds must be valid east-positive lunar longitude/latitude degrees")
            registration_text = tag("AREA_OR_POINT") or "Area"
            registration = _normalise_registration(registration_text)
            # If the raster has an affine geographic transform, ensure it is
            # north-up and agrees with the supplied/derived bounds.
            if self._dataset.crs is not None:
                if abs(float(transform.b)) > 1e-12 or abs(float(transform.d)) > 1e-12:
                    raise ValueError("Rotated/sheared raster grids are not supported; warp to north-up first")
                if float(transform.a) <= 0 or float(transform.e) >= 0:
                    raise ValueError("Raster must use east-increasing columns and north-to-south rows")
                tb = self._dataset.bounds
                tol = max(abs(float(transform.a)), abs(float(transform.e))) * 1e-6 + 1e-9
                if any(abs(a-b) > tol for a, b in zip(
                    (west, south, east, north), (tb.left, tb.bottom, tb.right, tb.top))):
                    raise ValueError("Explicit raster bounds disagree with the GeoTIFF/JP2 geotransform")
            scale = float(self._dataset.scales[0]) if self._dataset.scales else 1.0
            offset = float(self._dataset.offsets[0]) if self._dataset.offsets else 0.0
            if not math.isfinite(scale) or not math.isfinite(offset):
                raise ValueError("Raster band scale/offset must be finite")
            offset_m = offset * factor
            lines, samples = int(self._dataset.height), int(self._dataset.width)
            lon_step = (east-west)/(samples if registration == "area" else samples-1)
            lat_step = (north-south)/(lines if registration == "area" else lines-1)
            info = LunarDEMFormatProductInfo(
                format=format, product_id=tag("PRODUCT_ID", "PRODUCT_NAME") or self.image_path.stem,
                source_file=str(self.image_path), data_file=str(self.image_path),
                lines=lines, samples=samples, sample_type=str(self._dataset.dtypes[0]),
                unit=str(unit), scaling_factor=scale, value_offset_m=offset_m,
                value_interpretation=interpretation, reference_radius_m=radius,
                coordinate_system_name=coord_name, vertical_datum=datum,
                pixel_registration=registration, north_latitude_deg=north,
                south_latitude_deg=south, west_longitude_deg=west,
                east_longitude_deg=east,
                resolution_m=radius*math.radians(max(lon_step, lat_step)),
                data_offset_bytes=0, file_size_bytes=self.image_path.stat().st_size,
            )
            super().__init__(info=info, name=name, tile_shape=tile_shape, cache_tiles=cache_tiles)
        except Exception:
            self._dataset.close()
            raise

    def _read_raw_window(self, row_start: int, row_stop: int,
                         column_start: int, column_stop: int) -> np.ndarray:
        from rasterio.windows import Window
        window = Window(column_start, row_start, column_stop-column_start, row_stop-row_start)
        return self._dataset.read(1, window=window, masked=True)

    def _close_source(self) -> None:
        self._dataset.close()


class GeoTiffLunarDEMModel(RasterioLunarDEMModel):
    """GeoTIFF lunar DEM adapter; requires ``pip install eclipsekit[raster]``."""
    def __init__(self, image_path: str | Path, **kwargs: Any) -> None:
        super().__init__(image_path, format="GeoTIFF", **kwargs)


class JP2LunarDEMModel(RasterioLunarDEMModel):
    """JPEG 2000 lunar DEM adapter; requires GDAL JP2OpenJPEG support via Rasterio."""
    def __init__(self, image_path: str | Path, **kwargs: Any) -> None:
        super().__init__(image_path, format="JP2", **kwargs)


def open_pds4_lunar_dem(label_path: str | Path, image_path: str | Path | None = None,
                        **kwargs: Any) -> PDS4LunarDEMModel:
    return PDS4LunarDEMModel(label_path, image_path, **kwargs)


def open_geotiff_lunar_dem(image_path: str | Path, **kwargs: Any) -> GeoTiffLunarDEMModel:
    return GeoTiffLunarDEMModel(image_path, **kwargs)


def open_jp2_lunar_dem(image_path: str | Path, **kwargs: Any) -> JP2LunarDEMModel:
    return JP2LunarDEMModel(image_path, **kwargs)
