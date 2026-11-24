"""Explicit lunar body-fixed frame and spherical vertical-datum transforms.

The built-in DE440 PA -> DE421 ME rotation is the constant transformation
published as Equation (19) by Park et al. (2021). It is not a time-dependent
lunar orientation model and is not a raster reprojection routine.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np

ARCSECONDS_TO_RADIANS = math.pi / (180.0 * 3600.0)
DEFAULT_LUNAR_REFERENCE_RADIUS_M = 1_737_400.0
DE440_FRAME_REFERENCE_URL = "https://doi.org/10.3847/1538-3881/abd414"


def _as_finite_array(value: Any, name: str) -> np.ndarray:
    """Convert numeric input to float64, rejecting booleans and non-finite values."""
    raw = np.asarray(value, dtype=object)
    if any(isinstance(item, (bool, np.bool_)) for item in raw.flat):
        raise TypeError(f"{name} must contain numeric values, not booleans")
    try:
        result = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{name} must contain numeric values") from exc
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must contain only finite values")
    return result


def _scalar_or_array(value: np.ndarray) -> float | np.ndarray:
    if value.ndim == 0:
        return float(value)
    return value


def _rotation_x_passive(angle_rad: float) -> np.ndarray:
    cosine, sine = math.cos(angle_rad), math.sin(angle_rad)
    return np.array(
        [[1.0, 0.0, 0.0], [0.0, cosine, sine], [0.0, -sine, cosine]],
        dtype=np.float64,
    )


def _rotation_y_passive(angle_rad: float) -> np.ndarray:
    cosine, sine = math.cos(angle_rad), math.sin(angle_rad)
    return np.array(
        [[cosine, 0.0, -sine], [0.0, 1.0, 0.0], [sine, 0.0, cosine]],
        dtype=np.float64,
    )


def _rotation_z_passive(angle_rad: float) -> np.ndarray:
    cosine, sine = math.cos(angle_rad), math.sin(angle_rad)
    return np.array(
        [[cosine, sine, 0.0], [-sine, cosine, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )


@dataclass(frozen=True, slots=True)
class LunarFrameTransform:
    """A fixed, source-to-target rotation between lunar body-fixed frames.

    ``rotation_matrix`` acts on column vectors: ``xyz_target = R @ xyz_source``.
    For arrays whose final axis is XYZ, the implementation performs the
    equivalent row-array operation ``xyz_source @ R.T``.
    """

    source_frame: str
    target_frame: str
    rotation_matrix: tuple[tuple[float, float, float], ...]
    provenance: str
    reference_url: str
    description: str = ""

    def __post_init__(self) -> None:
        for field_name in ("source_frame", "target_frame", "provenance", "reference_url"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if not isinstance(self.description, str):
            raise TypeError("description must be a string")

        matrix = _as_finite_array(self.rotation_matrix, "rotation_matrix")
        if matrix.shape != (3, 3):
            raise ValueError("rotation_matrix must have shape (3, 3)")
        identity = np.eye(3, dtype=np.float64)
        if not np.allclose(matrix @ matrix.T, identity, rtol=0.0, atol=2e-12):
            raise ValueError("rotation_matrix must be orthonormal")
        determinant = float(np.linalg.det(matrix))
        if not math.isclose(determinant, 1.0, rel_tol=0.0, abs_tol=2e-12):
            raise ValueError("rotation_matrix must be a proper right-handed rotation (determinant +1)")
        canonical = tuple(tuple(float(item) for item in row) for row in matrix)
        object.__setattr__(self, "rotation_matrix", canonical)

    @classmethod
    def from_euler_xyz_arcsec(
        cls,
        *,
        source_frame: str,
        target_frame: str,
        x_arcsec: float,
        y_arcsec: float,
        z_arcsec: float,
        provenance: str,
        reference_url: str,
        description: str = "",
    ) -> "LunarFrameTransform":
        """Build the published passive ``Rx(x) @ Ry(y) @ Rz(z)`` convention.

        The passive right-handed matrices follow the convention explicitly
        printed in Park et al. (2021), Equations (9)--(11). The rightmost
        rotation acts first on a column vector.
        """
        angles = _as_finite_array((x_arcsec, y_arcsec, z_arcsec), "Euler angles")
        x_rad, y_rad, z_rad = (float(value) * ARCSECONDS_TO_RADIANS for value in angles)
        matrix = (
            _rotation_x_passive(x_rad)
            @ _rotation_y_passive(y_rad)
            @ _rotation_z_passive(z_rad)
        )
        return cls(
            source_frame=source_frame,
            target_frame=target_frame,
            rotation_matrix=tuple(tuple(float(item) for item in row) for row in matrix),
            provenance=provenance,
            reference_url=reference_url,
            description=description,
        )

    @classmethod
    def de440_pa_to_de421_me(cls) -> "LunarFrameTransform":
        """Return the published fixed DE440 PA -> DE421 ME/MER transform.

        Angles and rotation order are taken from Park et al. (2021),
        Equation (19): Rx(-0.2785 arcsec) Ry(-78.6944 arcsec)
        Rz(-67.8526 arcsec). The paper's passive rotation-matrix convention
        from Equations (9)--(11) is used.
        """
        return cls.from_euler_xyz_arcsec(
            source_frame="MOON_PA_DE440",
            target_frame="MOON_ME_DE421",
            x_arcsec=-0.2785,
            y_arcsec=-78.6944,
            z_arcsec=-67.8526,
            provenance=(
                "Park et al. (2021), The JPL Planetary and Lunar Ephemerides DE440 and DE441, "
                "Equation (19); fixed rotation estimated from lunar laser retroreflector coordinates"
            ),
            reference_url=DE440_FRAME_REFERENCE_URL,
            description=(
                "Fixed DE440 principal-axes to DE421 mean-Earth/mean-rotation (also called "
                "mean-Earth/polar-axis) frame rotation."
            ),
        )

    def inverse(self) -> "LunarFrameTransform":
        """Return the exact inverse frame rotation."""
        matrix = np.asarray(self.rotation_matrix, dtype=np.float64).T
        return LunarFrameTransform(
            source_frame=self.target_frame,
            target_frame=self.source_frame,
            rotation_matrix=tuple(tuple(float(item) for item in row) for row in matrix),
            provenance=f"Inverse of: {self.provenance}",
            reference_url=self.reference_url,
            description=f"Inverse of the fixed transform {self.source_frame} -> {self.target_frame}.",
        )

    def transform_cartesian(self, xyz: Any) -> np.ndarray:
        """Transform one XYZ vector or an array with final dimension 3."""
        values = _as_finite_array(xyz, "xyz")
        if values.ndim == 0 or values.shape[-1] != 3:
            raise ValueError("xyz must have final dimension length 3")
        matrix = np.asarray(self.rotation_matrix, dtype=np.float64)
        return np.matmul(values, matrix.T)

    def transform_latlon(
        self, latitude_deg: Any, longitude_deg: Any
    ) -> tuple[float | np.ndarray, float | np.ndarray]:
        """Transform spherical geocentric latitude/longitude coordinates.

        Longitude output is normalized to ``[-180, 180)`` degrees. Input
        longitudes may use any finite degree branch; latitude must be in
        ``[-90, 90]`` degrees.
        """
        latitude = _as_finite_array(latitude_deg, "latitude_deg")
        longitude = _as_finite_array(longitude_deg, "longitude_deg")
        latitude, longitude = np.broadcast_arrays(latitude, longitude)
        if np.any((latitude < -90.0) | (latitude > 90.0)):
            raise ValueError("latitude_deg must be within [-90, 90]")
        lat_rad = np.deg2rad(latitude)
        lon_rad = np.deg2rad(longitude)
        cosine_lat = np.cos(lat_rad)
        xyz = np.stack(
            (cosine_lat * np.cos(lon_rad), cosine_lat * np.sin(lon_rad), np.sin(lat_rad)),
            axis=-1,
        )
        rotated = self.transform_cartesian(xyz)
        horizontal = np.hypot(rotated[..., 0], rotated[..., 1])
        output_latitude = np.rad2deg(np.arctan2(rotated[..., 2], horizontal))
        output_longitude = (np.rad2deg(np.arctan2(rotated[..., 1], rotated[..., 0])) + 180.0) % 360.0 - 180.0
        return _scalar_or_array(output_latitude), _scalar_or_array(output_longitude)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_frame": self.source_frame,
            "target_frame": self.target_frame,
            "rotation_matrix": [list(row) for row in self.rotation_matrix],
            "rotation_convention": "passive right-handed; column vectors; Rx @ Ry @ Rz",
            "provenance": self.provenance,
            "reference_url": self.reference_url,
            "description": self.description,
            "time_dependent": False,
        }


@dataclass(frozen=True, slots=True)
class LunarReferenceSphereTransform:
    """Convert heights between explicitly declared spherical reference radii."""

    source_reference_radius_m: float
    target_reference_radius_m: float
    source_vertical_datum: str
    target_vertical_datum: str

    def __post_init__(self) -> None:
        for field_name in ("source_reference_radius_m", "target_reference_radius_m"):
            value = getattr(self, field_name)
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number)):
                raise TypeError(f"{field_name} must be a finite positive number")
            if not math.isfinite(float(value)) or float(value) <= 0.0:
                raise ValueError(f"{field_name} must be a finite positive number")
            object.__setattr__(self, field_name, float(value))
        for field_name in ("source_vertical_datum", "target_vertical_datum"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")

    def transform_height_m(self, height_m: Any) -> float | np.ndarray:
        """Convert height while preserving the same centre-of-Moon radius."""
        height = _as_finite_array(height_m, "height_m")
        radius = height + self.source_reference_radius_m
        if np.any(radius <= 0.0):
            raise ValueError("source radius (reference radius + height) must be positive")
        converted = radius - self.target_reference_radius_m
        return _scalar_or_array(converted)

    def inverse(self) -> "LunarReferenceSphereTransform":
        return LunarReferenceSphereTransform(
            source_reference_radius_m=self.target_reference_radius_m,
            target_reference_radius_m=self.source_reference_radius_m,
            source_vertical_datum=self.target_vertical_datum,
            target_vertical_datum=self.source_vertical_datum,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_reference_radius_m": self.source_reference_radius_m,
            "target_reference_radius_m": self.target_reference_radius_m,
            "source_vertical_datum": self.source_vertical_datum,
            "target_vertical_datum": self.target_vertical_datum,
            "height_conversion": "h_target = h_source + R_source - R_target",
        }


@dataclass(frozen=True, slots=True)
class LunarCoordinateResult:
    """Spherical lunar coordinates returned by a combined transformation."""

    latitude_deg: float | np.ndarray
    longitude_deg: float | np.ndarray
    height_above_reference_m: float | np.ndarray

    def to_dict(self) -> dict[str, Any]:
        def serialise(value: float | np.ndarray) -> float | list[Any]:
            return value.tolist() if isinstance(value, np.ndarray) else float(value)

        return {
            "latitude_deg": serialise(self.latitude_deg),
            "longitude_deg": serialise(self.longitude_deg),
            "height_above_reference_m": serialise(self.height_above_reference_m),
        }


@dataclass(frozen=True, slots=True)
class LunarCoordinateTransform:
    """Transform lunar DEM sample coordinates and heights between two frames.

    This transforms points, not raster grids. It treats each declared vertical
    datum as a spherical reference radius and therefore does not model a lunar
    geoid, ellipsoid, local terrain datum, or spatially varying vertical offset.
    """

    frame_transform: LunarFrameTransform
    vertical_transform: LunarReferenceSphereTransform

    def __post_init__(self) -> None:
        if not isinstance(self.frame_transform, LunarFrameTransform):
            raise TypeError("frame_transform must be a LunarFrameTransform")
        if not isinstance(self.vertical_transform, LunarReferenceSphereTransform):
            raise TypeError("vertical_transform must be a LunarReferenceSphereTransform")

    def transform_points(
        self, latitude_deg: Any, longitude_deg: Any, height_m: Any
    ) -> LunarCoordinateResult:
        """Transform broadcast-compatible arrays of geocentric lat/lon/heights."""
        latitude = _as_finite_array(latitude_deg, "latitude_deg")
        longitude = _as_finite_array(longitude_deg, "longitude_deg")
        height = _as_finite_array(height_m, "height_m")
        latitude, longitude, height = np.broadcast_arrays(latitude, longitude, height)
        if np.any((latitude < -90.0) | (latitude > 90.0)):
            raise ValueError("latitude_deg must be within [-90, 90]")
        source_radius = height + self.vertical_transform.source_reference_radius_m
        if np.any(source_radius <= 0.0):
            raise ValueError("source radius (reference radius + height) must be positive")

        lat_rad = np.deg2rad(latitude)
        lon_rad = np.deg2rad(longitude)
        cos_lat = np.cos(lat_rad)
        xyz_source = np.stack(
            (
                source_radius * cos_lat * np.cos(lon_rad),
                source_radius * cos_lat * np.sin(lon_rad),
                source_radius * np.sin(lat_rad),
            ),
            axis=-1,
        )
        xyz_target = self.frame_transform.transform_cartesian(xyz_source)
        target_radius = np.linalg.norm(xyz_target, axis=-1)
        horizontal = np.hypot(xyz_target[..., 0], xyz_target[..., 1])
        target_latitude = np.rad2deg(np.arctan2(xyz_target[..., 2], horizontal))
        target_longitude = (
            np.rad2deg(np.arctan2(xyz_target[..., 1], xyz_target[..., 0])) + 180.0
        ) % 360.0 - 180.0
        target_height = target_radius - self.vertical_transform.target_reference_radius_m
        return LunarCoordinateResult(
            latitude_deg=_scalar_or_array(target_latitude),
            longitude_deg=_scalar_or_array(target_longitude),
            height_above_reference_m=_scalar_or_array(target_height),
        )

    def transform_point(
        self, latitude_deg: float, longitude_deg: float, height_m: float
    ) -> LunarCoordinateResult:
        """Scalar convenience wrapper around :meth:`transform_points`."""
        result = self.transform_points(latitude_deg, longitude_deg, height_m)
        if isinstance(result.latitude_deg, np.ndarray):
            raise RuntimeError("scalar transform unexpectedly returned an array")
        return result

    def inverse(self) -> "LunarCoordinateTransform":
        return LunarCoordinateTransform(
            frame_transform=self.frame_transform.inverse(),
            vertical_transform=self.vertical_transform.inverse(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_transform": self.frame_transform.to_dict(),
            "vertical_transform": self.vertical_transform.to_dict(),
            "scope": "point transformation only; no raster reprojection or resampling",
        }


def de440_pa_to_de421_me_transform() -> LunarFrameTransform:
    """Convenience factory for the published DE440 PA -> DE421 ME rotation."""
    return LunarFrameTransform.de440_pa_to_de421_me()


def de421_me_to_de440_pa_transform() -> LunarFrameTransform:
    """Convenience factory for the inverse DE421 ME -> DE440 PA rotation."""
    return LunarFrameTransform.de440_pa_to_de421_me().inverse()
