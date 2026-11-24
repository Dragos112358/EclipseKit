"""Readers for documented PDS3 lunar topography products.

The implementation is deliberately lazy: PDS image data are memory-mapped and
only the four samples needed for a bilinear interpolation are read.  This is
important for global SLDEM2015 products, whose uncompressed images are several
gigabytes in size.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, replace
from pathlib import Path
import math
import re
from threading import RLock
from typing import Any, Iterator

import numpy as np

from .limb import LunarLimbModelMetadata, LunarLimbPrediction, LunarLimbQuery


_PDS_KEY_RE = re.compile(
    r"(?ims)^\s*(\^?[A-Z][A-Z0-9_]*)\s*=\s*(.*?)"
    r"(?=^\s*\^?[A-Z][A-Z0-9_]*\s*=|^\s*END\s*$|\Z)"
)
_NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?")
_UNIT_TO_METRES = {
    "M": 1.0,
    "METER": 1.0,
    "METERS": 1.0,
    "METRE": 1.0,
    "METRES": 1.0,
    "KM": 1000.0,
    "KILOMETER": 1000.0,
    "KILOMETERS": 1000.0,
    "KILOMETRE": 1000.0,
    "KILOMETRES": 1000.0,
    "CM": 0.01,
    "CENTIMETER": 0.01,
    "CENTIMETERS": 0.01,
}


def _strip_comments(label_text: str) -> str:
    """Remove PDS3 block comments before extracting keyword values."""
    return re.sub(r"/\*.*?\*/", "", label_text, flags=re.DOTALL)


def parse_pds3_label(label_path: str | Path) -> dict[str, str]:
    """Parse the scalar keywords used by PDS3 image labels.

    The parser intentionally preserves values as strings and is not intended
    to replace a full PDS3 parser.  Unsupported/ambiguous labels are rejected
    by :class:`PDS3LunarDEMModel` rather than guessed.
    """
    path = Path(label_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = path.read_text(encoding="latin-1")
    text = _strip_comments(text)
    values: dict[str, str] = {}
    for match in _PDS_KEY_RE.finditer(text):
        key = match.group(1).upper()
        value = match.group(2).strip().rstrip(",").strip()
        if value:
            values[key] = value
    if not values:
        raise ValueError(f"No PDS3 keywords could be read from {path}")
    version = _unquote(values.get("PDS_VERSION_ID", ""))
    if version.upper() != "PDS3":
        raise ValueError(f"Expected a PDS3 label; found {version or 'unknown format'}")
    return values


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1].strip()
    return value


def _number(value: str, key: str) -> tuple[float, str | None]:
    raw = value.strip()
    match = _NUMBER_RE.match(raw)
    if match is None:
        raise ValueError(f"PDS3 keyword {key} must contain a numeric value; found {raw!r}")
    number = float(match.group(0))
    suffix = raw[match.end():].strip()
    unit = None
    if suffix.startswith("<") and ">" in suffix:
        unit = suffix[1:suffix.index(">")].strip()
    if not math.isfinite(number):
        raise ValueError(f"PDS3 keyword {key} must be finite")
    return number, unit


def _required_text(values: dict[str, str], key: str) -> str:
    if key not in values:
        raise ValueError(f"PDS3 label is missing required keyword {key}")
    result = _unquote(values[key])
    if not result:
        raise ValueError(f"PDS3 keyword {key} must be non-empty")
    return result


def _required_number(values: dict[str, str], key: str) -> tuple[float, str | None]:
    if key not in values:
        raise ValueError(f"PDS3 label is missing required keyword {key}")
    return _number(values[key], key)


def _unit_to_metres(unit: str, key: str) -> float:
    factor = _UNIT_TO_METRES.get(unit.strip().upper())
    if factor is None:
        raise ValueError(f"Unsupported or missing length unit for {key}: {unit!r}")
    return factor


def _image_pointer_offset(values: dict[str, str], record_bytes: int) -> int:
    """Return the zero-based byte offset named by the PDS ^IMAGE pointer."""
    raw = values.get("^IMAGE")
    if raw is None:
        # Detached labels sometimes omit the pointer; the supplied image is
        # then treated as a stream beginning at byte zero.
        return 0
    text = raw.strip()
    if text.startswith("(") and text.endswith(")"):
        inside = text[1:-1].strip()
        parts = [part.strip() for part in inside.split(",", maxsplit=1)]
        if len(parts) != 2:
            raise ValueError("Unsupported PDS3 ^IMAGE tuple pointer")
        pointer_text = parts[1]
        pointer_match = _NUMBER_RE.match(pointer_text)
        if pointer_match is None:
            raise ValueError("PDS3 ^IMAGE tuple pointer has an invalid position")
        position_value = float(pointer_match.group(0))
        if not position_value.is_integer():
            raise ValueError("PDS3 ^IMAGE pointer position must be an integer")
        position = int(position_value)
        if position < 1:
            raise ValueError("PDS3 ^IMAGE pointer positions are one-based and positive")
        if "BYTE" in pointer_text.upper():
            return position - 1
        return (position - 1) * record_bytes
    unquoted = _unquote(text)
    pointer_match = _NUMBER_RE.match(unquoted)
    if pointer_match is not None:
        position_value = float(pointer_match.group(0))
        if not position_value.is_integer() or position_value < 1:
            raise ValueError("PDS3 ^IMAGE pointer position must be a positive integer")
        position = int(position_value)
        if "BYTE" in unquoted.upper():
            return position - 1
        return (position - 1) * record_bytes
    return 0


def _pds_dtype(sample_type: str, sample_bits: int) -> np.dtype[Any]:
    sample_type = sample_type.strip().upper()
    formats = {
        ("PC_REAL", 32): "<f4",
        ("IEEE_REAL", 32): ">f4",
        ("LSB_INTEGER", 8): "i1",
        ("LSB_INTEGER", 16): "<i2",
        ("LSB_INTEGER", 32): "<i4",
        ("MSB_INTEGER", 8): "i1",
        ("MSB_INTEGER", 16): ">i2",
        ("MSB_INTEGER", 32): ">i4",
        ("LSB_UNSIGNED_INTEGER", 8): "u1",
        ("LSB_UNSIGNED_INTEGER", 16): "<u2",
        ("LSB_UNSIGNED_INTEGER", 32): "<u4",
        ("MSB_UNSIGNED_INTEGER", 8): "u1",
        ("MSB_UNSIGNED_INTEGER", 16): ">u2",
        ("MSB_UNSIGNED_INTEGER", 32): ">u4",
    }
    dtype = formats.get((sample_type, sample_bits))
    if dtype is None:
        raise ValueError(
            f"Unsupported PDS3 SAMPLE_TYPE/SAMPLE_BITS: {sample_type}/{sample_bits}"
        )
    return np.dtype(dtype)


@dataclass(frozen=True, slots=True)
class PDS3LunarDEMProductInfo:
    """Auditable PDS3 geometry, datum, storage and provenance metadata."""

    product_id: str
    data_set_id: str
    product_version_id: str
    image_file_name: str
    label_file_name: str
    lines: int
    line_samples: int
    sample_type: str
    sample_bits: int
    unit: str
    scaling_factor: float
    offset_m: float
    reference_radius_m: float
    coordinate_system_type: str
    coordinate_system_name: str
    map_projection_type: str
    pixels_per_degree: float
    min_latitude_deg: float
    max_latitude_deg: float
    west_longitude_deg: float
    east_longitude_deg: float
    center_latitude_deg: float
    center_longitude_deg: float
    line_projection_offset: float
    sample_projection_offset: float
    pixel_registration: str
    resolution_m: float
    data_offset_bytes: int
    record_bytes: int
    file_size_bytes: int

    @property
    def shape(self) -> tuple[int, int]:
        return self.lines, self.line_samples

    @property
    def global_longitude(self) -> bool:
        return math.isclose(
            self.east_longitude_deg - self.west_longitude_deg,
            360.0,
            rel_tol=0.0,
            abs_tol=1e-6,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "data_set_id": self.data_set_id,
            "product_version_id": self.product_version_id,
            "image_file_name": self.image_file_name,
            "label_file_name": self.label_file_name,
            "shape": list(self.shape),
            "sample_type": self.sample_type,
            "sample_bits": self.sample_bits,
            "unit": self.unit,
            "scaling_factor": self.scaling_factor,
            "offset_m": self.offset_m,
            "reference_radius_m": self.reference_radius_m,
            "coordinate_system_type": self.coordinate_system_type,
            "coordinate_system_name": self.coordinate_system_name,
            "map_projection_type": self.map_projection_type,
            "pixels_per_degree": self.pixels_per_degree,
            "coverage": {
                "min_latitude_deg": self.min_latitude_deg,
                "max_latitude_deg": self.max_latitude_deg,
                "west_longitude_deg": self.west_longitude_deg,
                "east_longitude_deg": self.east_longitude_deg,
            },
            "center_latitude_deg": self.center_latitude_deg,
            "center_longitude_deg": self.center_longitude_deg,
            "line_projection_offset": self.line_projection_offset,
            "sample_projection_offset": self.sample_projection_offset,
            "pixel_registration": self.pixel_registration,
            "resolution_m": self.resolution_m,
            "data_offset_bytes": self.data_offset_bytes,
            "record_bytes": self.record_bytes,
            "file_size_bytes": self.file_size_bytes,
            "storage": "read-only memory-mapped PDS3 image",
        }


@dataclass(frozen=True, slots=True)
class LunarDEMWindow:
    """A bounded rectangular DEM window in metres above its declared sphere.

    Row and column bounds are zero-based, half-open image indices. Elevations
    are copied into an independent, read-only float64 array; NaN cells remain
    NaN so callers can distinguish missing source samples from zero relief.
    """

    row_start: int
    row_stop: int
    column_start: int
    column_stop: int
    height_above_reference_m: np.ndarray

    def __post_init__(self) -> None:
        for name in ("row_start", "row_stop", "column_start", "column_stop"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
                raise TypeError(f"{name} must be an integer")
        if self.row_start < 0 or self.column_start < 0:
            raise ValueError("DEM window starts must be non-negative")
        if self.row_stop <= self.row_start or self.column_stop <= self.column_start:
            raise ValueError("DEM window stop indices must be greater than start indices")
        values = np.asarray(self.height_above_reference_m, dtype=np.float64)
        expected = (self.row_stop - self.row_start, self.column_stop - self.column_start)
        if values.shape != expected:
            raise ValueError(f"DEM window array shape must be {expected}; found {values.shape}")
        frozen = np.array(values, dtype=np.float64, copy=True)
        frozen.setflags(write=False)
        object.__setattr__(self, "height_above_reference_m", frozen)

    @property
    def shape(self) -> tuple[int, int]:
        return self.height_above_reference_m.shape


@dataclass(frozen=True, slots=True)
class LunarDEMCacheInfo:
    """Observable counters for the bounded in-memory DEM tile cache."""

    tile_shape: tuple[int, int]
    max_tiles: int
    current_tiles: int
    hits: int
    misses: int
    evictions: int
    cached_bytes: int
    max_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "tile_shape": list(self.tile_shape),
            "max_tiles": self.max_tiles,
            "current_tiles": self.current_tiles,
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "cached_bytes": self.cached_bytes,
            "max_bytes": self.max_bytes,
        }


class PDS3LunarDEMModel:
    """Lazy, read-only lunar-limb provider for PDS3 simple-cylindrical IMG DEMs.

    The model supports documented PDS3 IMG image objects with a regular
    pixel-registered simple-cylindrical grid and a spherical reference radius.
    It does not reproject coordinates or convert between lunar body-fixed
    frames.  The label's frame and datum are retained and can be checked by
    the caller before passing the model to an eclipse calculation.
    """

    def __init__(
        self,
        image_path: str | Path,
        label_path: str | Path | None = None,
        *,
        name: str | None = None,
        expected_reference_radius_m: float | None = 1_737_400.0,
        radius_tolerance_m: float = 1.0,
        expected_coordinate_system: str | None = None,
        tile_shape: int | tuple[int, int] = 512,
        cache_tiles: int = 8,
    ) -> None:
        """Open a PDS3 DEM with a bounded cache of converted elevation tiles.

        ``tile_shape`` is a square pixel count or a ``(rows, columns)`` pair.
        ``cache_tiles`` limits retained tiles; set it to zero to disable caching.
        With the defaults, the worst-case cache allocation is 16 MiB of float64
        heights, independent of the size of the source IMG file.
        """
        self.tile_shape = self._validate_tile_shape(tile_shape)
        if isinstance(cache_tiles, bool) or not isinstance(cache_tiles, (int, np.integer)):
            raise TypeError("cache_tiles must be an integer")
        if int(cache_tiles) < 0:
            raise ValueError("cache_tiles must be non-negative")
        self.cache_tiles = int(cache_tiles)
        self._tile_cache: OrderedDict[tuple[int, int], np.ndarray] = OrderedDict()
        self._cache_lock = RLock()
        self._cache_hits = 0
        self._cache_misses = 0
        self._cache_evictions = 0
        self.image_path = Path(image_path).expanduser().resolve()
        if not self.image_path.is_file():
            raise FileNotFoundError(self.image_path)
        if label_path is None:
            candidates = [self.image_path.with_suffix(".LBL"), self.image_path.with_suffix(".lbl")]
            label = next((candidate for candidate in candidates if candidate.is_file()), None)
            if label is None:
                raise FileNotFoundError(
                    f"No adjacent PDS3 label found for {self.image_path}; pass label_path explicitly"
                )
            self.label_path = label.resolve()
        else:
            self.label_path = Path(label_path).expanduser().resolve()
        values = parse_pds3_label(self.label_path)
        self.product_info = self._read_product_info(
            values,
            expected_reference_radius_m=expected_reference_radius_m,
            radius_tolerance_m=radius_tolerance_m,
            expected_coordinate_system=expected_coordinate_system,
        )
        self.product_info = replace(
            self.product_info,
            image_file_name=self.image_path.name,
            label_file_name=self.label_path.name,
            file_size_bytes=self.image_path.stat().st_size,
        )
        dtype = _pds_dtype(self.product_info.sample_type, self.product_info.sample_bits)
        bytes_per_sample = dtype.itemsize
        row_bytes = self.product_info.line_samples * bytes_per_sample
        if self.product_info.record_bytes < row_bytes:
            raise ValueError(
                f"PDS3 RECORD_BYTES ({self.product_info.record_bytes}) is smaller than image row ({row_bytes})"
            )
        required_bytes = (
            self.product_info.data_offset_bytes
            + self.product_info.lines * self.product_info.record_bytes
        )
        if self.product_info.file_size_bytes < required_bytes:
            raise ValueError(
                f"PDS3 image is truncated: need at least {required_bytes} bytes, "
                f"found {self.product_info.file_size_bytes}"
            )
        self._raw_map = np.memmap(
            self.image_path,
            dtype=np.uint8,
            mode="r",
            offset=self.product_info.data_offset_bytes,
            shape=(self.product_info.lines, self.product_info.record_bytes),
        )
        self._data = np.ndarray(
            shape=self.product_info.shape,
            dtype=dtype,
            buffer=self._raw_map,
            strides=(self.product_info.record_bytes, bytes_per_sample),
        )
        product_label = self.product_info.product_id or self.image_path.name
        vertical_datum = (
            f"radial height relative to the {self.product_info.reference_radius_m:.3f} m "
            "spherical reference radius declared by the PDS3 label"
        )
        self.metadata = LunarLimbModelMetadata(
            name=name or product_label,
            model_type="pds3_dem",
            source=f"{self.image_path} [{self.product_info.product_id}]",
            reference_frame="selenographic",
            vertical_datum=vertical_datum,
            resolution_m=self.product_info.resolution_m,
            description=(
                "PDS3 pixel-registered simple-cylindrical lunar DEM; source image is "
                "read-only memory-mapped and accessed through a bounded LRU tile cache. "
                "No coordinate-frame or datum transformation is applied."
            ),
            product_id=self.product_info.product_id,
            coordinate_system=(
                f"{self.product_info.coordinate_system_type}: "
                f"{self.product_info.coordinate_system_name}"
            ),
            reference_radius_m=self.product_info.reference_radius_m,
            pixel_registration=self.product_info.pixel_registration,
        )
        self._closed = False

    @classmethod
    def from_pds3_img(
        cls, image_path: str | Path, label_path: str | Path | None = None, **kwargs: Any
    ) -> "PDS3LunarDEMModel":
        """Open an uncompressed PDS3 ``.IMG`` lunar DEM and detached label."""
        return cls(image_path, label_path, **kwargs)

    @classmethod
    def from_img(
        cls, image_path: str | Path, label_path: str | Path | None = None, **kwargs: Any
    ) -> "PDS3LunarDEMModel":
        """Alias for :meth:`from_pds3_img`."""
        return cls.from_pds3_img(image_path, label_path, **kwargs)

    @staticmethod
    def _read_product_info(
        values: dict[str, str],
        *,
        expected_reference_radius_m: float | None,
        radius_tolerance_m: float,
        expected_coordinate_system: str | None,
    ) -> PDS3LunarDEMProductInfo:
        target = values.get("TARGET_NAME", "").strip().strip('"').upper()
        if target and target != "MOON":
            raise ValueError(f"PDS3 target must be MOON, not {target!r}")
        projection = _required_text(values, "MAP_PROJECTION_TYPE").upper()
        if projection != "SIMPLE CYLINDRICAL":
            raise ValueError(f"Unsupported PDS3 map projection: {projection}")
        longitude_direction = _required_text(values, "POSITIVE_LONGITUDE_DIRECTION").upper()
        if longitude_direction != "EAST":
            raise ValueError("PDS3 lunar DEM must use east-positive longitude")
        coordinate_type = _required_text(values, "COORDINATE_SYSTEM_TYPE")
        coordinate_name = _required_text(values, "COORDINATE_SYSTEM_NAME")
        if "BODY-FIXED" not in coordinate_type.upper():
            raise ValueError(
                "PDS3 lunar DEM must declare a body-fixed coordinate system; "
                f"found {coordinate_type!r}"
            )
        if expected_coordinate_system is not None and (
            coordinate_name.casefold() != expected_coordinate_system.strip().casefold()
        ):
            raise ValueError(
                "PDS3 coordinate-system mismatch: "
                f"expected {expected_coordinate_system!r}, found {coordinate_name!r}"
            )
        registration = _required_text(values, "PIXEL_REGISTRATION") if "PIXEL_REGISTRATION" in values else "PIXEL"
        if registration.casefold() not in {"pixel", "pixel registration", "center"}:
            raise ValueError(f"Unsupported PDS3 grid registration: {registration!r}")

        lines_value, _ = _required_number(values, "LINES")
        samples_value, _ = _required_number(values, "LINE_SAMPLES")
        bits_value, _ = _required_number(values, "SAMPLE_BITS")
        lines, samples, bits = int(lines_value), int(samples_value), int(bits_value)
        if lines < 2 or samples < 2 or lines != lines_value or samples != samples_value:
            raise ValueError("PDS3 image LINES and LINE_SAMPLES must be integers >= 2")
        if bits not in {8, 16, 32} or bits != bits_value:
            raise ValueError("PDS3 SAMPLE_BITS must be 8, 16 or 32")
        sample_type = _required_text(values, "SAMPLE_TYPE").upper()
        dtype = _pds_dtype(sample_type, bits)
        record_bytes_value = values.get("RECORD_BYTES")
        if record_bytes_value is None:
            record_bytes = samples * dtype.itemsize
        else:
            record_bytes_num, _ = _number(record_bytes_value, "RECORD_BYTES")
            record_bytes = int(record_bytes_num)
            if record_bytes != record_bytes_num or record_bytes <= 0:
                raise ValueError("PDS3 RECORD_BYTES must be a positive integer")

        unit = _required_text(values, "UNIT")
        unit_factor = _unit_to_metres(unit, "UNIT")
        scale_factor, _ = _required_number(values, "SCALING_FACTOR")
        offset, offset_unit = _required_number(values, "OFFSET")
        if offset_unit is None:
            offset_factor = unit_factor
        else:
            offset_factor = _unit_to_metres(offset_unit, "OFFSET")
        offset_m = offset * offset_factor

        radii: list[float] = []
        for key in ("A_AXIS_RADIUS", "B_AXIS_RADIUS", "C_AXIS_RADIUS"):
            radius, radius_unit = _required_number(values, key)
            radius_factor = _unit_to_metres(radius_unit or unit, key)
            radii.append(radius * radius_factor)
        if max(radii) - min(radii) > 0.01:
            raise ValueError(
                "This PDS3 reader currently requires a spherical lunar reference surface "
                "(A/B/C axis radii must agree within 1 cm)"
            )
        reference_radius_m = float(sum(radii) / len(radii))
        if not math.isfinite(radius_tolerance_m) or radius_tolerance_m < 0.0:
            raise ValueError("radius_tolerance_m must be finite and non-negative")
        if expected_reference_radius_m is not None:
            expected = float(expected_reference_radius_m)
            if not math.isfinite(expected) or expected <= 0.0:
                raise ValueError("expected_reference_radius_m must be finite and positive")
            if abs(reference_radius_m - expected) > radius_tolerance_m:
                raise ValueError(
                    "PDS3 reference radius does not match the requested datum: "
                    f"expected {expected:.3f} m, found {reference_radius_m:.3f} m. "
                    "Pass expected_reference_radius_m=None only after reviewing the source datum."
                )

        ppd, _ = _required_number(values, "MAP_RESOLUTION")
        if ppd <= 0.0:
            raise ValueError("PDS3 MAP_RESOLUTION must be positive")
        center_lat, _ = _required_number(values, "CENTER_LATITUDE")
        center_lon, _ = _required_number(values, "CENTER_LONGITUDE")
        line_offset, _ = _required_number(values, "LINE_PROJECTION_OFFSET")
        sample_offset, _ = _required_number(values, "SAMPLE_PROJECTION_OFFSET")
        min_lat, _ = _required_number(values, "MINIMUM_LATITUDE")
        max_lat, _ = _required_number(values, "MAXIMUM_LATITUDE")
        west_lon, _ = _required_number(values, "WESTERNMOST_LONGITUDE")
        east_lon, _ = _required_number(values, "EASTERNMOST_LONGITUDE")
        if not (-90.0 <= min_lat < max_lat <= 90.0):
            raise ValueError("PDS3 latitude coverage must satisfy -90 <= minimum < maximum <= 90")
        if not (0.0 < east_lon - west_lon <= 360.0 + 1e-6):
            raise ValueError("PDS3 longitude coverage must span more than 0 and at most 360 degrees")
        line_first = values.get("LINE_FIRST_PIXEL", "1")
        sample_first = values.get("SAMPLE_FIRST_PIXEL", "1")
        if int(_number(line_first, "LINE_FIRST_PIXEL")[0]) != 1 or int(
            _number(sample_first, "SAMPLE_FIRST_PIXEL")[0]
        ) != 1:
            raise ValueError("Only PDS3 image objects whose first line/sample is 1 are supported")

        # PDS map projection offsets refer to pixel coordinates.  Convert them
        # to outer pixel edges and verify that the label's geographic bounds
        # describe the actual array geometry.
        top_edge = center_lat + (line_offset + 0.5) / ppd
        bottom_edge = top_edge - lines / ppd
        left_edge = center_lon - (sample_offset + 0.5) / ppd
        right_edge = left_edge + samples / ppd
        edge_tolerance = max(1e-4, 0.51 / ppd)
        if abs(top_edge - max_lat) > edge_tolerance or abs(bottom_edge - min_lat) > edge_tolerance:
            raise ValueError(
                "PDS3 latitude bounds disagree with image dimensions/projection offsets"
            )
        # Longitude is cyclic; compare in the label's declared west/east range.
        def _cyclic_error(left: float, right: float) -> float:
            return abs((left - right + 180.0) % 360.0 - 180.0)
        if _cyclic_error(left_edge, west_lon) > edge_tolerance or abs(
            (right_edge - left_edge) - (east_lon - west_lon)
        ) > edge_tolerance:
            raise ValueError(
                "PDS3 longitude bounds disagree with image dimensions/projection offsets"
            )

        map_scale_m = None
        if "MAP_SCALE" in values:
            scale, scale_unit = _required_number(values, "MAP_SCALE")
            scale_factor_m = 1000.0 if scale_unit and "KM" in scale_unit.upper() else 1.0
            map_scale_m = scale * scale_factor_m
        else:
            map_scale_m = reference_radius_m * math.pi / (180.0 * ppd)
        if not math.isfinite(map_scale_m) or map_scale_m <= 0.0:
            raise ValueError("PDS3 map scale must be finite and positive")

        data_offset = _image_pointer_offset(values, record_bytes)
        product_id = _unquote(values.get("PRODUCT_ID", "unknown"))
        dataset_id = _unquote(values.get("DATA_SET_ID", "unknown"))
        product_version = _unquote(values.get("PRODUCT_VERSION_ID", "unknown"))
        return PDS3LunarDEMProductInfo(
            product_id=product_id,
            data_set_id=dataset_id,
            product_version_id=product_version,
            image_file_name="",
            label_file_name="",
            lines=lines,
            line_samples=samples,
            sample_type=sample_type,
            sample_bits=bits,
            unit=unit,
            scaling_factor=scale_factor,
            offset_m=offset_m,
            reference_radius_m=reference_radius_m,
            coordinate_system_type=coordinate_type,
            coordinate_system_name=coordinate_name,
            map_projection_type=projection,
            pixels_per_degree=ppd,
            min_latitude_deg=min_lat,
            max_latitude_deg=max_lat,
            west_longitude_deg=west_lon,
            east_longitude_deg=east_lon,
            center_latitude_deg=center_lat,
            center_longitude_deg=center_lon,
            line_projection_offset=line_offset,
            sample_projection_offset=sample_offset,
            pixel_registration=registration,
            resolution_m=map_scale_m,
            data_offset_bytes=data_offset,
            record_bytes=record_bytes,
            file_size_bytes=0,  # replaced with the actual path size by __init__
        )

    @property
    def is_closed(self) -> bool:
        return self._closed

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("PDS3 lunar DEM model is closed")

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
        normalized: list[int] = []
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
                raise TypeError("tile_shape entries must be integers")
            if int(value) < 1:
                raise ValueError("tile_shape entries must be positive")
            normalized.append(int(value))
        return normalized[0], normalized[1]

    def _raw_to_height_m(self, raw: np.ndarray) -> np.ndarray:
        """Convert PDS digital numbers to height above the declared sphere."""
        unit_factor = _unit_to_metres(self.product_info.unit, "UNIT")
        return (
            np.asarray(raw, dtype=np.float64) * self.product_info.scaling_factor * unit_factor
            + self.product_info.offset_m - self.product_info.reference_radius_m
        )

    def _load_tile(self, tile_row: int, tile_column: int) -> np.ndarray:
        tile_height, tile_width = self.tile_shape
        row_start = tile_row * tile_height
        column_start = tile_column * tile_width
        row_stop = min(row_start + tile_height, self.product_info.lines)
        column_stop = min(column_start + tile_width, self.product_info.line_samples)
        raw = np.array(self._data[row_start:row_stop, column_start:column_stop], copy=True)
        heights = self._raw_to_height_m(raw)
        heights.setflags(write=False)
        return heights

    def _get_tile(self, row: int, column: int) -> np.ndarray:
        tile_height, tile_width = self.tile_shape
        key = (row // tile_height, column // tile_width)
        with self._cache_lock:
            self._ensure_open()
            cached = self._tile_cache.get(key)
            if cached is not None:
                self._cache_hits += 1
                self._tile_cache.move_to_end(key)
                return cached
            self._cache_misses += 1
            tile = self._load_tile(*key)
            if self.cache_tiles > 0:
                self._tile_cache[key] = tile
                self._tile_cache.move_to_end(key)
                while len(self._tile_cache) > self.cache_tiles:
                    self._tile_cache.popitem(last=False)
                    self._cache_evictions += 1
            return tile

    def cache_info(self) -> LunarDEMCacheInfo:
        """Return tile-cache counters without exposing internal cache arrays."""
        with self._cache_lock:
            self._ensure_open()
            return LunarDEMCacheInfo(
                tile_shape=self.tile_shape,
                max_tiles=self.cache_tiles,
                current_tiles=len(self._tile_cache),
                hits=self._cache_hits,
                misses=self._cache_misses,
                evictions=self._cache_evictions,
                cached_bytes=sum(tile.nbytes for tile in self._tile_cache.values()),
                max_bytes=(
                    self.cache_tiles * self.tile_shape[0] * self.tile_shape[1] * np.dtype(np.float64).itemsize
                ),
            )

    def clear_tile_cache(self, *, reset_statistics: bool = True) -> None:
        """Drop cached tiles and optionally reset cache counters."""
        if not isinstance(reset_statistics, bool):
            raise TypeError("reset_statistics must be a bool")
        with self._cache_lock:
            self._ensure_open()
            self._tile_cache.clear()
            if reset_statistics:
                self._cache_hits = 0
                self._cache_misses = 0
                self._cache_evictions = 0

    def read_window(
        self, row_start: int, row_stop: int, column_start: int, column_stop: int
    ) -> LunarDEMWindow:
        """Read a zero-based, half-open image window as height above reference sphere.

        The returned array is an independent read-only copy. Bounds do not wrap
        around the global longitude seam; use normalised image columns for a
        window that crosses that seam.
        """
        self._ensure_open()
        bounds = (row_start, row_stop, column_start, column_stop)
        names = ("row_start", "row_stop", "column_start", "column_stop")
        for name, value in zip(names, bounds):
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
                raise TypeError(f"{name} must be an integer")
        row_start, row_stop, column_start, column_stop = map(int, bounds)
        if row_start < 0 or column_start < 0:
            raise ValueError("DEM window starts must be non-negative")
        if row_stop <= row_start or column_stop <= column_start:
            raise ValueError("DEM window stop indices must be greater than start indices")
        if row_stop > self.product_info.lines or column_stop > self.product_info.line_samples:
            raise IndexError("DEM window extends beyond image bounds")
        raw = np.array(self._data[row_start:row_stop, column_start:column_stop], copy=True)
        return LunarDEMWindow(
            row_start, row_stop, column_start, column_stop, self._raw_to_height_m(raw)
        )

    def iter_tiles(
        self, tile_shape: int | tuple[int, int] | None = None
    ) -> Iterator[LunarDEMWindow]:
        """Yield the image as bounded, non-overlapping, read-only DEM windows.

        Only one yielded tile is materialised at a time. The last tile along an
        image edge may be smaller than the requested tile shape.
        """
        self._ensure_open()
        height, width = self.tile_shape if tile_shape is None else self._validate_tile_shape(tile_shape)
        for row_start in range(0, self.product_info.lines, height):
            row_stop = min(row_start + height, self.product_info.lines)
            for column_start in range(0, self.product_info.line_samples, width):
                column_stop = min(column_start + width, self.product_info.line_samples)
                yield self.read_window(row_start, row_stop, column_start, column_stop)

    @property
    def coverage(self) -> tuple[float, float, float, float]:
        info = self.product_info
        return (
            info.min_latitude_deg,
            info.max_latitude_deg,
            info.west_longitude_deg,
            info.east_longitude_deg,
        )

    def _row_coordinate(self, latitude_deg: float) -> float:
        info = self.product_info
        if not info.min_latitude_deg - 1e-10 <= latitude_deg <= info.max_latitude_deg + 1e-10:
            raise ValueError(
                f"Latitude {latitude_deg:.6f}° is outside PDS3 DEM coverage "
                f"[{info.min_latitude_deg:.6f}°, {info.max_latitude_deg:.6f}°]"
            )
        return min(
            max(info.line_projection_offset - (latitude_deg - info.center_latitude_deg) * info.pixels_per_degree,
                0.0),
            float(info.lines - 1),
        )

    def _column_coordinate(self, longitude_deg: float) -> float:
        info = self.product_info
        if not math.isfinite(longitude_deg):
            raise ValueError("Longitude must be finite")
        if info.global_longitude:
            delta = (longitude_deg - info.center_longitude_deg + 180.0) % 360.0 - 180.0
            return info.sample_projection_offset + delta * info.pixels_per_degree
        region_center = 0.5 * (info.west_longitude_deg + info.east_longitude_deg)
        wrapped = longitude_deg + 360.0 * round((region_center - longitude_deg) / 360.0)
        if wrapped < info.west_longitude_deg - 1e-10 or wrapped > info.east_longitude_deg + 1e-10:
            raise ValueError(
                f"Longitude {longitude_deg:.6f}° is outside PDS3 DEM coverage "
                f"[{info.west_longitude_deg:.6f}°, {info.east_longitude_deg:.6f}°]"
            )
        left_edge = info.center_longitude_deg - (info.sample_projection_offset + 0.5) / info.pixels_per_degree
        coordinate = (wrapped - left_edge) * info.pixels_per_degree - 0.5
        return min(max(coordinate, 0.0), float(info.line_samples - 1))

    def pixel_center(self, row: int, column: int) -> tuple[float, float]:
        """Return the selenographic latitude/east longitude at a zero-based pixel center."""
        self._ensure_open()
        if not (0 <= row < self.product_info.lines and 0 <= column < self.product_info.line_samples):
            raise IndexError("PDS3 pixel index is outside the image")
        info = self.product_info
        latitude = info.center_latitude_deg + (info.line_projection_offset - row) / info.pixels_per_degree
        longitude = info.center_longitude_deg + (column - info.sample_projection_offset) / info.pixels_per_degree
        longitude = (longitude + 180.0) % 360.0 - 180.0
        return float(latitude), float(longitude)

    def predict(self, query: LunarLimbQuery) -> LunarLimbPrediction:
        """Bilinearly sample height above the PDS reference sphere via the LRU tile cache."""
        self._ensure_open()
        if not isinstance(query, LunarLimbQuery):
            raise TypeError("query must be a LunarLimbQuery")
        lat = float(query.selenographic_latitude_deg)
        lon = float(query.selenographic_longitude_deg)
        row_coordinate = self._row_coordinate(lat)
        column_coordinate = self._column_coordinate(lon)
        row0 = int(math.floor(row_coordinate))
        column0 = int(math.floor(column_coordinate))
        fy = row_coordinate - row0
        fx = column_coordinate - column0
        row1 = min(row0 + 1, self.product_info.lines - 1)
        if self.product_info.global_longitude:
            column0 %= self.product_info.line_samples
            column1 = (column0 + 1) % self.product_info.line_samples
        else:
            column0 = min(max(column0, 0), self.product_info.line_samples - 1)
            column1 = min(column0 + 1, self.product_info.line_samples - 1)
        rows = (row0, row0, row1, row1)
        columns = (column0, column1, column0, column1)
        weights = np.asarray(
            ((1.0 - fy) * (1.0 - fx), (1.0 - fy) * fx,
             fy * (1.0 - fx), fy * fx), dtype=float,
        )
        height_values = np.asarray(
            [
                self._get_tile(r, c)[r % self.tile_shape[0], c % self.tile_shape[1]]
                for r, c in zip(rows, columns)
            ],
            dtype=float,
        )
        needed = weights > 1e-14
        if not np.all(np.isfinite(height_values[needed])):
            raise ValueError("PDS3 DEM interpolation touches one or more missing elevation cells")
        height_values = np.where(np.isfinite(height_values), height_values, 0.0)
        altitude_m = float(np.dot(weights, height_values))
        return LunarLimbPrediction(
            altitude_m=altitude_m,
            model_name=self.metadata.name,
            model_type=self.metadata.model_type,
            source=self.metadata.source,
            uncertainty_m=None,
            status="ok",
        )

    def predict_altitude_m(self, latitude_deg: float, longitude_deg: float) -> float:
        return self.predict(LunarLimbQuery(latitude_deg, longitude_deg, 0.0)).altitude_m

    def close(self) -> None:
        """Close the read-only memory map and release all cached tiles."""
        with self._cache_lock:
            if not self._closed:
                self._closed = True
                self._tile_cache.clear()
                mmap_obj = getattr(self._raw_map, "_mmap", None)
                if mmap_obj is not None:
                    mmap_obj.close()
                self._data = None
                self._raw_map = None

    def __enter__(self) -> "PDS3LunarDEMModel":
        self._ensure_open()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        del exc_type, exc, traceback
        self.close()


def open_pds3_lunar_dem(
    image_path: str | Path, label_path: str | Path | None = None, **kwargs: Any
) -> PDS3LunarDEMModel:
    """Convenience function matching the class factory."""
    return PDS3LunarDEMModel.from_pds3_img(image_path, label_path, **kwargs)
