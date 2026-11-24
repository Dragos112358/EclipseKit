"""Optional neural lunar-limb model, preserving the architecture in the supplied code.

PyTorch is imported only when this module's model classes are instantiated/used.
The checkpoint file remains user-supplied and is not packaged with EclipseKit.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable
import csv
import math

import numpy as np


@dataclass(slots=True)
class LunarLimbMetadata:
    alt_mean: float
    alt_std: float
    limb_centers_deg: Any = None
    band_half_width_deg: Any = None
    lat_min: float = -90.0
    lat_max: float = 90.0
    best_val_rmse_m: float | None = None


class LunarLimbCorrector:
    """Loads the user's LunarAltitudeNet checkpoint and predicts limb altitude."""

    def __init__(self, model: Any, metadata: LunarLimbMetadata, *, device: str = "cpu") -> None:
        self.model = model
        self.metadata = metadata
        self.device = device

    @classmethod
    def from_checkpoint(cls, path: str | Path, *, device: str = "cpu") -> "LunarLimbCorrector":
        try:
            import torch
            import torch.nn as nn
        except ImportError as exc:  # pragma: no cover
            raise ImportError("Lunar limb correction requires PyTorch: pip install 'eclipsekit[limb]'") from exc

        checkpoint_path = Path(path).expanduser()
        if not checkpoint_path.is_file():
            raise FileNotFoundError(f"Lunar-limb checkpoint not found: {checkpoint_path}")

        # The source checkpoint is a state-dict + primitive metadata. The safe
        # weights-only loader avoids unpickling arbitrary Python objects.
        try:
            checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=True)
        except Exception as exc:
            raise RuntimeError(
                "Checkpoint could not be loaded safely with weights_only=True. "
                "Re-save it as a plain state_dict plus primitive metadata, or inspect it locally "
                "before using any trusted-checkpoint loading workflow."
            ) from exc

        levels, features, log2_size = 20, 2, 21
        base_res, finest_res = 16, 46080
        prime_lon, prime_lat = 1, 2654435761

        class Encoding(nn.Module):
            def __init__(self, recommended_lon_cells: int) -> None:
                super().__init__()
                b = math.exp((math.log(finest_res) - math.log(base_res)) / (levels - 1))
                self.res_lat = [max(1, int(round(base_res * (b**level)))) for level in range(levels)]
                aspect = recommended_lon_cells / finest_res
                self.res_lon = [max(1, int(round(r * aspect))) for r in self.res_lat]
                max_size = 2**log2_size
                self.table_sizes: list[int] = []
                self.use_hash: list[bool] = []
                for rlon, rlat in zip(self.res_lon, self.res_lat):
                    count = (rlon + 1) * (rlat + 1)
                    self.table_sizes.append(min(count, max_size))
                    self.use_hash.append(count > max_size)
                self.embeddings = nn.ModuleList([nn.Embedding(size, features) for size in self.table_sizes])

            def _index(self, ix: Any, iy: Any, level: int) -> Any:
                if not self.use_hash[level]:
                    return ix * (self.res_lat[level] + 1) + iy
                h = (ix.to(torch.int64) * prime_lon) ^ (iy.to(torch.int64) * prime_lat)
                return h % self.table_sizes[level]

            def forward(self, u: Any, v: Any) -> Any:
                encoded = []
                for level in range(levels):
                    rlon, rlat = self.res_lon[level], self.res_lat[level]
                    x, y = u * rlon, v * rlat
                    x0f, y0f = torch.floor(x), torch.floor(y)
                    fx, fy = (x - x0f).unsqueeze(-1), (y - y0f).unsqueeze(-1)
                    x0 = x0f.long().clamp(0, rlon)
                    x1 = (x0f.long() + 1).clamp(0, rlon)
                    y0 = y0f.long().clamp(0, rlat)
                    y1 = (y0f.long() + 1).clamp(0, rlat)
                    e00 = self.embeddings[level](self._index(x0, y0, level))
                    e01 = self.embeddings[level](self._index(x0, y1, level))
                    e10 = self.embeddings[level](self._index(x1, y0, level))
                    e11 = self.embeddings[level](self._index(x1, y1, level))
                    top = e00 * (1 - fx) + e10 * fx
                    bottom = e01 * (1 - fx) + e11 * fx
                    encoded.append(top * (1 - fy) + bottom * fy)
                return torch.cat(encoded, dim=-1)

        class LunarAltitudeNet(nn.Module):
            def __init__(self, recommended_lon_cells: int, hidden: int = 256) -> None:
                super().__init__()
                self.encoding = Encoding(recommended_lon_cells)
                self.mlp = nn.Sequential(
                    nn.Linear(levels * features, hidden), nn.GELU(),
                    nn.Linear(hidden, hidden), nn.GELU(),
                    nn.Linear(hidden, hidden), nn.GELU(),
                    nn.Linear(hidden, 1),
                )

            def forward(self, u: Any, v: Any) -> Any:
                return self.mlp(self.encoding(u, v)).squeeze(-1)

        model = LunarAltitudeNet(int(checkpoint["recommended_lon_cells"])).to(device)
        model.load_state_dict(checkpoint["model_state"])
        model.eval().float()
        metadata = LunarLimbMetadata(
            alt_mean=float(checkpoint["alt_mean"]),
            alt_std=float(checkpoint["alt_std"]),
            limb_centers_deg=checkpoint.get("limb_centers_deg"),
            band_half_width_deg=checkpoint.get("band_half_width_deg"),
            lat_min=float(checkpoint.get("lat_min", -90.0)),
            lat_max=float(checkpoint.get("lat_max", 90.0)),
            best_val_rmse_m=(
                float(checkpoint["best_val_rmse_m"])
                if checkpoint.get("best_val_rmse_m") is not None else None
            ),
        )
        instance = cls(model, metadata, device=device)
        instance._torch = torch
        instance.checkpoint_path = str(checkpoint_path)
        return instance

    def predict_altitude_m(self, latitude_deg: float, longitude_deg: float) -> float:
        torch = getattr(self, "_torch", None)
        if torch is None:
            try:
                import torch
            except ImportError as exc:  # pragma: no cover
                raise ImportError("PyTorch is required for lunar-limb correction") from exc
        u = ((longitude_deg + 180.0) / 360.0) % 1.0
        v = min(1.0, max(0.0, (latitude_deg - self.metadata.lat_min) /
                         (self.metadata.lat_max - self.metadata.lat_min)))
        with torch.no_grad():
            u_tensor = torch.tensor([u], dtype=torch.float32, device=self.device)
            v_tensor = torch.tensor([v], dtype=torch.float32, device=self.device)
            prediction = self.model(u_tensor, v_tensor).item()
        return float(prediction * self.metadata.alt_std + self.metadata.alt_mean)


def compute_moon_libration_and_axis(observer: Any, t: Any, moon: Any) -> tuple[float, float, float]:
    """Optical lunar libration and lunar-axis position-angle approximation (Meeus-style)."""
    T = (t.tt - 2451545.0) / 36525.0
    omega_node = math.radians(125.04452 - 1934.136261 * T)
    sun_mean = math.radians(280.4665 + 36000.7698 * T)
    moon_mean = math.radians(218.3165 + 481267.8813 * T)
    dpsi_arcsec = (-17.20*math.sin(omega_node) - 1.32*math.sin(2*sun_mean)
                   - 0.23*math.sin(2*moon_mean) + 0.21*math.sin(2*omega_node))
    deps_arcsec = (9.20*math.cos(omega_node) + 0.57*math.cos(2*sun_mean)
                   + 0.10*math.cos(2*moon_mean) - 0.09*math.cos(2*omega_node))
    dpsi = dpsi_arcsec / 3600.0
    deps = deps_arcsec / 3600.0
    eps0 = (84381.448 - 46.8150*T - 0.00059*T*T + 0.001813*T**3) / 3600.0
    eps = math.radians(eps0 + deps)
    moon_app = observer.at(t).observe(moon).apparent()
    beta_angle, lambda_angle, _ = moon_app.ecliptic_latlon()
    lam, beta = lambda_angle.radians, beta_angle.radians
    F = math.radians((93.2720950 + 483202.0175233*T - 0.0036539*T*T
                      - T**3/3526000.0 + T**4/863310000.0) % 360.0)
    Omega = math.radians((125.0445479 - 1934.1362891*T + 0.0020754*T*T
                          + T**3/467441.0 - T**4/60616000.0) % 360.0)
    inclination = math.radians(1.54242)
    W = lam - Omega
    A = math.atan2(math.sin(W)*math.cos(beta)*math.cos(inclination) - math.sin(beta)*math.sin(inclination),
                   math.cos(W)*math.cos(beta))
    l_opt = (math.degrees(A) - math.degrees(F) + 180.0) % 360.0 - 180.0
    b_opt = math.asin(max(-1.0, min(1.0, -math.sin(W)*math.cos(beta)*math.sin(inclination)
                                      - math.sin(beta)*math.cos(inclination))))
    V = Omega + math.radians(dpsi)
    X = math.sin(inclination) * math.sin(V)
    Y = math.sin(inclination) * math.cos(V) * math.cos(eps) - math.cos(inclination) * math.sin(eps)
    omega_axis = math.atan2(X, Y)
    denominator = math.cos(b_opt)
    if abs(denominator) < 1e-9:
        p_axis = 0.0
    else:
        sin_p = math.sqrt(X*X + Y*Y) * math.cos(lam - omega_axis) / denominator
        p_axis = math.degrees(math.asin(max(-1.0, min(1.0, sin_p))))
    return l_opt, math.degrees(b_opt), p_axis % 360.0


def contact_selenographic_point(libration_lon_deg: float, libration_lat_deg: float,
                                 limb_angle_deg: float) -> tuple[float, float]:
    """Map a point on the apparent lunar limb to selenographic latitude/longitude."""
    c_ang = math.radians(limb_angle_deg)
    l0, b0 = math.radians(libration_lon_deg), math.radians(libration_lat_deg)
    x, y = math.sin(c_ang), math.cos(c_ang)
    rho = min(1.0, math.hypot(x, y))
    c = math.asin(rho)
    if rho < 1e-9:
        return libration_lat_deg, libration_lon_deg
    sin_lat = math.sin(b0)*math.cos(c) + (y*math.sin(c)*math.cos(b0))/rho
    lat = math.asin(max(-1.0, min(1.0, sin_lat)))
    delta_lon = math.atan2(x*math.sin(c), rho*math.cos(b0)*math.cos(c) - y*math.sin(b0)*math.sin(c))
    lon = (math.degrees(l0 + delta_lon) + 180.0) % 360.0 - 180.0
    return math.degrees(lat), lon


# ---------------------------------------------------------------------------
# Phase 5: provider-neutral lunar-limb model framework
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class LunarLimbModelMetadata:
    """Provenance and declared characteristics of a lunar-limb data source.

    ``validation_rmse_m`` is a dataset/model validation metric, not a per-point
    uncertainty. ``vertical_datum`` and ``resolution_m`` are left unspecified
    unless the source actually supplies them.
    """

    name: str
    model_type: Literal[
        "spherical", "gridded_dem", "pds3_dem", "pds4_dem", "geotiff_dem", "jp2_dem", "angular_profile", "neural", "custom"
    ]
    source: str
    reference_frame: Literal["selenographic", "apparent_limb"] = "selenographic"
    vertical_datum: str | None = None
    resolution_m: float | None = None
    validation_rmse_m: float | None = None
    description: str = ""
    product_id: str | None = None
    coordinate_system: str | None = None
    reference_radius_m: float | None = None
    pixel_registration: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Lunar-limb model name must be non-empty")
        if not self.source.strip():
            raise ValueError("Lunar-limb model source must be non-empty")
        if self.model_type not in {
            "spherical", "gridded_dem", "pds3_dem", "pds4_dem", "geotiff_dem", "jp2_dem", "angular_profile", "neural", "custom"
        }:
            raise ValueError("Unsupported lunar-limb model_type")
        if self.reference_frame not in {"selenographic", "apparent_limb"}:
            raise ValueError("reference_frame must be 'selenographic' or 'apparent_limb'")
        if self.resolution_m is not None and (
            not math.isfinite(float(self.resolution_m)) or float(self.resolution_m) <= 0.0
        ):
            raise ValueError("resolution_m must be finite and positive when supplied")
        if self.validation_rmse_m is not None and (
            not math.isfinite(float(self.validation_rmse_m))
            or float(self.validation_rmse_m) < 0.0
        ):
            raise ValueError("validation_rmse_m must be finite and non-negative")
        if self.reference_radius_m is not None and (
            not math.isfinite(float(self.reference_radius_m)) or float(self.reference_radius_m) <= 0.0
        ):
            raise ValueError("reference_radius_m must be finite and positive")
        for field_name in ("product_id", "coordinate_system", "pixel_registration"):
            field_value = getattr(self, field_name)
            if field_value is not None and not field_value.strip():
                raise ValueError(f"{field_name} must be non-empty when supplied")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "model_type": self.model_type,
            "source": self.source,
            "reference_frame": self.reference_frame,
            "vertical_datum": self.vertical_datum,
            "resolution_m": self.resolution_m,
            "validation_rmse_m": self.validation_rmse_m,
            "description": self.description,
            "product_id": self.product_id,
            "coordinate_system": self.coordinate_system,
            "reference_radius_m": self.reference_radius_m,
            "pixel_registration": self.pixel_registration,
        }


@dataclass(frozen=True, slots=True)
class LunarLimbQuery:
    """One contact-point request shared by selenographic and angular profiles."""

    selenographic_latitude_deg: float
    selenographic_longitude_deg: float
    limb_angle_deg: float
    contact_name: str | None = None
    time_tt_jd: float | None = None
    libration_longitude_deg: float | None = None
    libration_latitude_deg: float | None = None

    def __post_init__(self) -> None:
        values = (
            self.selenographic_latitude_deg,
            self.selenographic_longitude_deg,
            self.limb_angle_deg,
        )
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("LunarLimbQuery coordinates and limb angle must be finite")
        if not -90.0 <= float(self.selenographic_latitude_deg) <= 90.0:
            raise ValueError("selenographic latitude must be between -90 and +90 degrees")
        if self.time_tt_jd is not None and not math.isfinite(float(self.time_tt_jd)):
            raise ValueError("time_tt_jd must be finite when supplied")
        optional_angles = (self.libration_longitude_deg, self.libration_latitude_deg)
        if any(value is not None and not math.isfinite(float(value)) for value in optional_angles):
            raise ValueError("Optional libration coordinates must be finite when supplied")


@dataclass(frozen=True, slots=True)
class LunarLimbPrediction:
    """A terrain-height prediction with auditable source metadata."""

    altitude_m: float
    model_name: str
    model_type: str
    source: str
    uncertainty_m: float | None = None
    status: str = "ok"

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.altitude_m)):
            raise ValueError("Lunar-limb altitude prediction must be finite")
        if self.uncertainty_m is not None and (
            not math.isfinite(float(self.uncertainty_m)) or float(self.uncertainty_m) < 0.0
        ):
            raise ValueError("uncertainty_m must be finite and non-negative")
        if not self.model_name.strip() or not self.source.strip():
            raise ValueError("Prediction model_name and source must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "altitude_m": float(self.altitude_m),
            "model_name": self.model_name,
            "model_type": self.model_type,
            "source": self.source,
            "uncertainty_m": self.uncertainty_m,
            "status": self.status,
        }


@runtime_checkable
class LunarLimbModel(Protocol):
    """Protocol implemented by all Phase 5 lunar-limb providers."""

    metadata: LunarLimbModelMetadata

    def predict(self, query: LunarLimbQuery) -> LunarLimbPrediction:
        """Predict radial terrain altitude for the supplied limb contact point."""
        ...


class SphericalLunarLimbModel:
    """Zero-relief baseline. It applies no topographic correction."""

    def __init__(self, *, name: str = "Spherical mean limb") -> None:
        self.metadata = LunarLimbModelMetadata(
            name=name,
            model_type="spherical",
            source="analytic zero-relief reference",
            reference_frame="selenographic",
            description="Zero terrain altitude; useful as a controlled baseline only.",
        )

    def predict(self, query: LunarLimbQuery) -> LunarLimbPrediction:
        del query
        return LunarLimbPrediction(
            altitude_m=0.0,
            model_name=self.metadata.name,
            model_type=self.metadata.model_type,
            source=self.metadata.source,
        )

    def predict_altitude_m(self, latitude_deg: float, longitude_deg: float) -> float:
        del latitude_deg, longitude_deg
        return 0.0


class GriddedLunarLimbModel:
    """Bilinear interpolation over a user-supplied selenographic DEM grid.

    The grid is ``altitudes_m[latitude_index, longitude_index]``. Longitude is
    east-positive. Missing cells are allowed in the input but any prediction
    whose four interpolation corners include a missing value raises ValueError.
    Set ``periodic_longitude=True`` only for a genuinely global 360-degree grid.
    """

    def __init__(
        self,
        latitudes_deg: Any,
        longitudes_deg: Any,
        altitudes_m: Any,
        *,
        uncertainties_m: Any | None = None,
        periodic_longitude: bool = False,
        name: str = "Gridded lunar DEM",
        source: str = "user-supplied gridded DEM",
        vertical_datum: str | None = None,
        resolution_m: float | None = None,
        validation_rmse_m: float | None = None,
    ) -> None:
        self.latitudes_deg = np.asarray(latitudes_deg, dtype=float)
        self.longitudes_deg = np.asarray(longitudes_deg, dtype=float)
        self.altitudes_m = np.asarray(altitudes_m, dtype=float)
        self.uncertainties_m = (
            np.asarray(uncertainties_m, dtype=float) if uncertainties_m is not None else None
        )
        if self.latitudes_deg.ndim != 1 or len(self.latitudes_deg) < 2:
            raise ValueError("latitudes_deg must be a 1D array with at least two values")
        if self.longitudes_deg.ndim != 1 or len(self.longitudes_deg) < 2:
            raise ValueError("longitudes_deg must be a 1D array with at least two values")
        if not np.all(np.isfinite(self.latitudes_deg)) or not np.all(np.isfinite(self.longitudes_deg)):
            raise ValueError("Grid coordinates must be finite")
        if np.any(np.diff(self.latitudes_deg) <= 0.0):
            raise ValueError("latitudes_deg must be strictly increasing")
        if np.any(np.diff(self.longitudes_deg) <= 0.0):
            raise ValueError("longitudes_deg must be strictly increasing")
        if self.latitudes_deg[0] < -90.0 or self.latitudes_deg[-1] > 90.0:
            raise ValueError("Grid latitudes must lie within [-90, 90]")
        expected_shape = (len(self.latitudes_deg), len(self.longitudes_deg))
        if self.altitudes_m.shape != expected_shape:
            raise ValueError(f"altitudes_m must have shape {expected_shape}")
        if np.any(np.isinf(self.altitudes_m)):
            raise ValueError("altitudes_m may contain NaN for missing cells, but not infinity")
        if not np.any(np.isfinite(self.altitudes_m)):
            raise ValueError("altitudes_m must contain at least one finite height")
        if self.uncertainties_m is not None:
            if self.uncertainties_m.shape != expected_shape:
                raise ValueError(f"uncertainties_m must have shape {expected_shape}")
            if not np.all(np.isfinite(self.uncertainties_m)) or np.any(self.uncertainties_m < 0.0):
                raise ValueError("uncertainties_m must be finite and non-negative")
        if not isinstance(periodic_longitude, bool):
            raise ValueError("periodic_longitude must be a bool")
        if periodic_longitude and self.longitudes_deg[-1] - self.longitudes_deg[0] >= 360.0:
            raise ValueError("Periodic longitude grid must not duplicate the 360-degree seam")
        self.periodic_longitude = periodic_longitude
        self.metadata = LunarLimbModelMetadata(
            name=name,
            model_type="gridded_dem",
            source=source,
            reference_frame="selenographic",
            vertical_datum=vertical_datum,
            resolution_m=resolution_m,
            validation_rmse_m=validation_rmse_m,
            description="Bilinear interpolation of a caller-supplied lunar elevation grid.",
        )

    @classmethod
    def from_csv(cls, path: str | Path, **kwargs: Any) -> "GriddedLunarLimbModel":
        """Load CSV columns ``latitude_deg,longitude_deg,altitude_m``.

        An optional ``uncertainty_m`` column is loaded when present. The file
        must describe a rectilinear grid; missing height cells remain NaN and
        will be rejected only when queried.
        """
        csv_path = Path(path).expanduser()
        if not csv_path.is_file():
            raise FileNotFoundError(csv_path)
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"latitude_deg", "longitude_deg", "altitude_m"}
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise ValueError(
                    "DEM CSV requires latitude_deg, longitude_deg, altitude_m columns"
                )
            rows = list(reader)
        if not rows:
            raise ValueError("DEM CSV contains no data rows")
        samples: list[tuple[float, float, float, float | None]] = []
        seen: set[tuple[float, float]] = set()
        for row in rows:
            try:
                lat = float(row["latitude_deg"])
                lon = float(row["longitude_deg"])
                altitude = float(row["altitude_m"])
                uncertainty_text = row.get("uncertainty_m")
                uncertainty = (
                    float(uncertainty_text)
                    if uncertainty_text not in (None, "") else None
                )
            except (TypeError, ValueError) as exc:
                raise ValueError("DEM CSV contains a non-numeric sample") from exc
            if (lat, lon) in seen:
                raise ValueError(f"Duplicate DEM sample at latitude={lat}, longitude={lon}")
            seen.add((lat, lon))
            samples.append((lat, lon, altitude, uncertainty))
        lats = np.array(sorted({item[0] for item in samples}), dtype=float)
        lons = np.array(sorted({item[1] for item in samples}), dtype=float)
        heights = np.full((len(lats), len(lons)), np.nan, dtype=float)
        has_uncertainty = any(item[3] is not None for item in samples)
        uncertainties = np.full_like(heights, np.nan) if has_uncertainty else None
        lat_index = {float(value): index for index, value in enumerate(lats)}
        lon_index = {float(value): index for index, value in enumerate(lons)}
        for lat, lon, altitude, uncertainty in samples:
            i, j = lat_index[lat], lon_index[lon]
            if np.isfinite(heights[i, j]):
                raise ValueError(f"Duplicate DEM sample at latitude={lat}, longitude={lon}")
            heights[i, j] = altitude
            if uncertainties is not None:
                if uncertainty is None or not math.isfinite(uncertainty) or uncertainty < 0.0:
                    raise ValueError("Every uncertainty_m value must be finite and non-negative")
                uncertainties[i, j] = uncertainty
        kwargs.setdefault("source", str(csv_path))
        return cls(
            lats, lons, heights, uncertainties_m=uncertainties, **kwargs
        )

    @classmethod
    def from_npz(cls, path: str | Path, **kwargs: Any) -> "GriddedLunarLimbModel":
        """Load a NumPy archive with latitudes_deg, longitudes_deg, altitudes_m."""
        npz_path = Path(path).expanduser()
        if not npz_path.is_file():
            raise FileNotFoundError(npz_path)
        with np.load(npz_path, allow_pickle=False) as data:
            required = {"latitudes_deg", "longitudes_deg", "altitudes_m"}
            if not required.issubset(data.files):
                raise ValueError(f"DEM NPZ must contain {sorted(required)}")
            uncertainty = data["uncertainties_m"] if "uncertainties_m" in data.files else None
            lats = np.array(data["latitudes_deg"], dtype=float)
            lons = np.array(data["longitudes_deg"], dtype=float)
            heights = np.array(data["altitudes_m"], dtype=float)
            uncertainties = np.array(uncertainty, dtype=float) if uncertainty is not None else None
        kwargs.setdefault("source", str(npz_path))
        return cls(lats, lons, heights, uncertainties_m=uncertainties, **kwargs)

    @staticmethod
    def _latitude_interval(axis: np.ndarray, value: float) -> tuple[int, int, float]:
        if value < axis[0] or value > axis[-1]:
            raise ValueError(
                f"Latitude {value:.6f}° is outside DEM coverage "
                f"[{axis[0]:.6f}°, {axis[-1]:.6f}°]"
            )
        index = int(np.searchsorted(axis, value, side="right") - 1)
        index = min(max(index, 0), len(axis) - 2)
        fraction = (value - axis[index]) / (axis[index + 1] - axis[index])
        return index, index + 1, float(fraction)

    def _longitude_interval(self, value: float) -> tuple[int, int, float]:
        axis = self.longitudes_deg
        if self.periodic_longitude:
            wrapped = ((value - axis[0]) % 360.0) + axis[0]
            index = int(np.searchsorted(axis, wrapped, side="right") - 1)
            if index < 0:
                index = len(axis) - 1
                left_lon = float(axis[index]) - 360.0
                right_lon = float(axis[0])
                fraction = (wrapped - left_lon) / (right_lon - left_lon)
                return index, 0, float(fraction)
            if index >= len(axis) - 1:
                left_lon = float(axis[-1])
                right_lon = float(axis[0]) + 360.0
                fraction = (wrapped - left_lon) / (right_lon - left_lon)
                return len(axis) - 1, 0, float(fraction)
            fraction = (wrapped - axis[index]) / (axis[index + 1] - axis[index])
            return index, index + 1, float(fraction)
        if value < axis[0] or value > axis[-1]:
            raise ValueError(
                f"Longitude {value:.6f}° is outside DEM coverage "
                f"[{axis[0]:.6f}°, {axis[-1]:.6f}°]"
            )
        index = int(np.searchsorted(axis, value, side="right") - 1)
        index = min(max(index, 0), len(axis) - 2)
        fraction = (value - axis[index]) / (axis[index + 1] - axis[index])
        return index, index + 1, float(fraction)

    def predict(self, query: LunarLimbQuery) -> LunarLimbPrediction:
        i0, i1, fy = self._latitude_interval(
            self.latitudes_deg, float(query.selenographic_latitude_deg)
        )
        j0, j1, fx = self._longitude_interval(
            float(query.selenographic_longitude_deg)
        )
        weights = np.array(
            [(1.0-fy)*(1.0-fx), (1.0-fy)*fx, fy*(1.0-fx), fy*fx],
            dtype=float,
        )
        values = np.array(
            [
                self.altitudes_m[i0, j0], self.altitudes_m[i0, j1],
                self.altitudes_m[i1, j0], self.altitudes_m[i1, j1],
            ],
            dtype=float,
        )
        if not np.all(np.isfinite(values)):
            raise ValueError("DEM interpolation touches one or more missing elevation cells")
        altitude = float(np.dot(weights, values))
        uncertainty = None
        if self.uncertainties_m is not None:
            sigma = np.array(
                [
                    self.uncertainties_m[i0, j0], self.uncertainties_m[i0, j1],
                    self.uncertainties_m[i1, j0], self.uncertainties_m[i1, j1],
                ],
                dtype=float,
            )
            # Independent-node uncertainty propagation through bilinear weights.
            uncertainty = float(math.sqrt(float(np.dot(weights * weights, sigma * sigma))))
        return LunarLimbPrediction(
            altitude_m=altitude,
            model_name=self.metadata.name,
            model_type=self.metadata.model_type,
            source=self.metadata.source,
            uncertainty_m=uncertainty,
        )

    def predict_altitude_m(self, latitude_deg: float, longitude_deg: float) -> float:
        query = LunarLimbQuery(latitude_deg, longitude_deg, 0.0)
        return self.predict(query).altitude_m


class TabulatedAngularLunarLimbProfile:
    """Periodic one-dimensional apparent-limb profile (e.g. an adopted Watts-like table).

    The caller supplies the profile and its provenance. This class does not
    bundle or claim to reproduce the original Watts, LOLA, or another published
    profile unless that exact source data is provided.
    """

    def __init__(
        self,
        limb_angles_deg: Any,
        altitudes_m: Any,
        *,
        uncertainties_m: Any | None = None,
        periodic: bool = True,
        name: str = "Tabulated apparent lunar limb",
        source: str = "user-supplied angular limb profile",
        validation_rmse_m: float | None = None,
    ) -> None:
        angles = np.asarray(limb_angles_deg, dtype=float)
        heights = np.asarray(altitudes_m, dtype=float)
        if angles.ndim != 1 or len(angles) < 2 or heights.shape != angles.shape:
            raise ValueError("limb_angles_deg and altitudes_m must be matching 1D arrays of length >= 2")
        if not np.all(np.isfinite(angles)) or not np.all(np.isfinite(heights)):
            raise ValueError("Angular profile samples must be finite")
        uncertainty = None
        if uncertainties_m is not None:
            uncertainty = np.asarray(uncertainties_m, dtype=float)
            if uncertainty.shape != angles.shape or not np.all(np.isfinite(uncertainty)):
                raise ValueError("uncertainties_m must be finite and match limb_angles_deg")
            if np.any(uncertainty < 0.0):
                raise ValueError("uncertainties_m must be non-negative")
        normalized = np.mod(angles, 360.0) if periodic else angles.copy()
        order = np.argsort(normalized)
        normalized, heights = normalized[order], heights[order]
        if uncertainty is not None:
            uncertainty = uncertainty[order]
        if np.any(np.diff(normalized) <= 1e-10):
            raise ValueError("Limb angles must be unique after 360-degree normalization")
        self.limb_angles_deg = normalized
        self.altitudes_m = heights
        self.uncertainties_m = uncertainty
        self.periodic = periodic
        self.metadata = LunarLimbModelMetadata(
            name=name,
            model_type="angular_profile",
            source=source,
            reference_frame="apparent_limb",
            validation_rmse_m=validation_rmse_m,
            description="Linearly interpolated tabulated apparent-limb radial profile.",
        )

    @classmethod
    def from_csv(cls, path: str | Path, **kwargs: Any) -> "TabulatedAngularLunarLimbProfile":
        profile_path = Path(path).expanduser()
        if not profile_path.is_file():
            raise FileNotFoundError(profile_path)
        with profile_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"limb_angle_deg", "altitude_m"}
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise ValueError("Profile CSV requires limb_angle_deg and altitude_m columns")
            rows = list(reader)
        if not rows:
            raise ValueError("Profile CSV contains no samples")
        try:
            angles = [float(row["limb_angle_deg"]) for row in rows]
            heights = [float(row["altitude_m"]) for row in rows]
            uncertainty_values = [
                float(row["uncertainty_m"]) for row in rows
            ] if "uncertainty_m" in (reader.fieldnames or []) else None
        except (TypeError, ValueError) as exc:
            raise ValueError("Profile CSV contains a non-numeric sample") from exc
        kwargs.setdefault("source", str(profile_path))
        return cls(
            angles, heights, uncertainties_m=uncertainty_values, **kwargs
        )

    def predict_by_limb_angle(self, limb_angle_deg: float) -> LunarLimbPrediction:
        angle = float(limb_angle_deg)
        if not math.isfinite(angle):
            raise ValueError("limb_angle_deg must be finite")
        axis = self.limb_angles_deg
        if self.periodic:
            angle = ((angle - axis[0]) % 360.0) + axis[0]
            x = np.concatenate((axis, [axis[0] + 360.0]))
            y = np.concatenate((self.altitudes_m, [self.altitudes_m[0]]))
            uncertainty_values = (
                np.concatenate((self.uncertainties_m, [self.uncertainties_m[0]]))
                if self.uncertainties_m is not None else None
            )
            if angle < axis[0]:
                angle += 360.0
        else:
            if angle < axis[0] or angle > axis[-1]:
                raise ValueError("Requested limb angle is outside profile coverage")
            x, y = axis, self.altitudes_m
            uncertainty_values = self.uncertainties_m
        altitude = float(np.interp(angle, x, y))
        uncertainty = (
            float(np.interp(angle, x, uncertainty_values))
            if uncertainty_values is not None else None
        )
        return LunarLimbPrediction(
            altitude_m=altitude,
            model_name=self.metadata.name,
            model_type=self.metadata.model_type,
            source=self.metadata.source,
            uncertainty_m=uncertainty,
        )

    def predict(self, query: LunarLimbQuery) -> LunarLimbPrediction:
        return self.predict_by_limb_angle(query.limb_angle_deg)


# Short descriptive alias retained alongside the explicit class name.
AngularLunarLimbProfile = TabulatedAngularLunarLimbProfile


class NeuralLunarLimbModel:
    """Adapter exposing the existing PyTorch checkpoint as a Phase 5 provider."""

    def __init__(self, corrector: LunarLimbCorrector, *, source: str = "user-supplied PyTorch checkpoint") -> None:
        self.corrector = corrector
        validation_rmse = corrector.metadata.best_val_rmse_m
        self.metadata = LunarLimbModelMetadata(
            name="LunarAltitudeNet checkpoint",
            model_type="neural",
            source=source,
            reference_frame="selenographic",
            validation_rmse_m=validation_rmse,
            description=(
                "Neural terrain-height predictor. The checkpoint validation RMSE is "
                "reported as provenance metadata, not as a per-contact uncertainty."
            ),
        )

    @classmethod
    def from_checkpoint(
        cls, path: str | Path, *, device: str = "cpu"
    ) -> "NeuralLunarLimbModel":
        corrector = LunarLimbCorrector.from_checkpoint(path, device=device)
        return cls(corrector, source=str(Path(path).expanduser()))

    def predict(self, query: LunarLimbQuery) -> LunarLimbPrediction:
        altitude = self.corrector.predict_altitude_m(
            query.selenographic_latitude_deg,
            query.selenographic_longitude_deg,
        )
        return LunarLimbPrediction(
            altitude_m=float(altitude),
            model_name=self.metadata.name,
            model_type=self.metadata.model_type,
            source=self.metadata.source,
        )

    def predict_altitude_m(self, latitude_deg: float, longitude_deg: float) -> float:
        return self.corrector.predict_altitude_m(latitude_deg, longitude_deg)


def predict_lunar_limb(model: Any, query: LunarLimbQuery) -> LunarLimbPrediction:
    """Evaluate a Phase 5 provider or adapt a legacy ``predict_altitude_m`` object."""
    if hasattr(model, "predict"):
        result = model.predict(query)
        if isinstance(result, LunarLimbPrediction):
            return result
        if isinstance(result, (int, float, np.integer, np.floating)):
            result = float(result)
        else:
            raise TypeError("Lunar-limb model predict(query) must return LunarLimbPrediction or a number")
        metadata = getattr(model, "metadata", None)
        return LunarLimbPrediction(
            altitude_m=result,
            model_name=getattr(metadata, "name", type(model).__name__),
            model_type=getattr(metadata, "model_type", "custom"),
            source=getattr(metadata, "source", "custom predictor"),
        )
    if hasattr(model, "predict_altitude_m"):
        altitude = float(model.predict_altitude_m(
            query.selenographic_latitude_deg,
            query.selenographic_longitude_deg,
        ))
        is_neural = isinstance(model, LunarLimbCorrector)
        return LunarLimbPrediction(
            altitude_m=altitude,
            model_name="LunarAltitudeNet checkpoint" if is_neural else type(model).__name__,
            model_type="neural" if is_neural else "custom",
            source=(
                getattr(model, "checkpoint_path", "user-supplied PyTorch checkpoint")
                if is_neural else "legacy predict_altitude_m interface"
            ),
        )
    raise TypeError(
        "limb_corrector must implement predict(LunarLimbQuery) or predict_altitude_m(latitude, longitude)"
    )
