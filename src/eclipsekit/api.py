"""Curated public API for application and third-party integrations.

New integrations should import from ``eclipsekit.api``. The package-root
imports remain supported as a backwards-compatibility surface. The API
contract version is independent of the pre-1.0 distribution version.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib import metadata
import platform
import sys

from ._version import __version__ as PACKAGE_VERSION
from .besselian import (
    BesselianContact, BesselianElements, BesselianGlobalPoint, BesselianLocalResult,
    BesselianObserverState, BesselianPolynomial, BesselianSnapshot, BesselianSolver,
)
from .cities import CityCatalog
from .config import (
    AtmosphereConfig, BesselianConfig, ContactModelConfig, EclipseConfig,
    EphemerisConfig, SolverConfig,
)
from .contacts import RootResult, bisect_root, brent_root, solve_root
from .earth_orientation import EarthOrientationConfig, describe_earth_orientation_source
from .engine import EclipseEngine
from .ephemeris import default_ephemeris_cache_dir
from .exports import (
    city_hits_to_geojson, shadow_corridor_to_geojson, shadow_corridor_to_kml,
    shadow_footprint_to_geojson, shadow_path_to_geojson, write_city_hits_csv,
    write_geojson, write_observation_plan_csv, write_observation_plan_json,
    write_shadow_corridor_csv, write_shadow_corridor_kml, write_shadow_footprint_geojson,
)
from .extensions import (
    EXTENSION_GROUPS, AmbiguousExtensionError, ExtensionInfo, ExtensionLoadError,
    UnknownExtensionError, ExtensionError, LunarDEMReader, LunarDEMReaderFactory,
    LunarLimbModelFactory, discover_extensions, load_extension,
)
from .lunar_eclipse import (
    LunarEclipseContacts, LunarEclipseResult, LunarShadowGeometry, lunar_shadow_geometry,
)
from .limb import (
    AngularLunarLimbProfile, GriddedLunarLimbModel, LunarLimbCorrector,
    LunarLimbModel, LunarLimbModelMetadata, LunarLimbPrediction, LunarLimbQuery,
    NeuralLunarLimbModel, SphericalLunarLimbModel, TabulatedAngularLunarLimbProfile,
    predict_lunar_limb,
)
from .lunar_control_points import (
    LunarControlPoint, LunarControlPointSet, LunarDEMControlPointReport,
    load_lunar_control_points, validate_lunar_dem_control_points,
    write_lunar_dem_control_point_report,
)
from .lunar_coordinates import (
    LunarCoordinateResult, LunarCoordinateTransform, LunarFrameTransform,
    LunarReferenceSphereTransform, de421_me_to_de440_pa_transform,
    de440_pa_to_de421_me_transform,
)
from .lunar_dem_mosaic import (
    LunarDEMCoverage, LunarDEMMosaicModel, LunarDEMMosaicProductInfo,
    LunarDEMMosaicSource, LunarDEMOutOfCoverageError,
)
from .lunar_dem_mosaic_validation import (
    LunarDEMMosaicOverlapReport, audit_lunar_dem_mosaic_overlaps,
    write_lunar_dem_mosaic_overlap_report,
)
from .lunar_dem_transform import TransformedLunarDEMModel
from .models import (
    City, CityEclipseHit, ContactEvent, ContactTimes, CountryEclipseEvent,
    HorizonProfile, LimbContact, LocalEclipseResult, ObservationGeometry, Observer,
    ShadowCorridorEdge, ShadowCorridorResult, ShadowCorridorSample, ShadowFootprint,
    ShadowPathPoint, SolarEclipseLocationHit, SolarEclipseSearchEvent,
    SolarEclipseSearchResult,
)
from .performance import (
    BenchmarkCaseResult, BenchmarkSuiteResult, benchmark_callable,
    compare_benchmark_suites, run_benchmark_suite,
)
from .planner import ObservationPlan, ObservationScoreWeights, ObservationSitePlan
from .serialization import dumps_json, to_jsonable, write_json
from .shadow_corridor_validation import (
    CorridorReferenceRow, CorridorValidationReport, CorridorValidationRow,
    compare_shadow_corridor_resolutions, load_corridor_reference_csv,
    validate_shadow_corridor_reference,
)
from .timeutils import delta_t_seconds, time_to_utc_iso, time_to_ut1_iso
from .topography import (
    LunarDEMCacheInfo, LunarDEMWindow, PDS3LunarDEMModel,
    PDS3LunarDEMProductInfo, open_pds3_lunar_dem, parse_pds3_label,
)
from .topography_formats import (
    GeoTiffLunarDEMModel, JP2LunarDEMModel, LunarDEMFormatProductInfo,
    PDS4LunarDEMModel, RasterioLunarDEMModel, open_geotiff_lunar_dem,
    open_jp2_lunar_dem, open_pds4_lunar_dem,
)
from .uncertainty import (
    ContactTimeUncertainty, PropagationResult, UncertaintyBudget,
    altitude_uncertainty_to_time_seconds, apply_contact_uncertainties,
    combine_independent_uncertainties, estimate_contact_time_uncertainty,
    estimate_lunar_limb_contact_time_uncertainty, finite_difference_jacobian,
    propagate_covariance, propagate_shadow_path_position_uncertainty,
    propagate_uncertainty, uncertainty_result_to_markdown, write_uncertainty_report,
)

API_CONTRACT_VERSION = "1"
API_STATUS = "stabilization-candidate"


@dataclass(frozen=True, slots=True)
class RuntimeInfo:
    """JSON-friendly runtime and optional-integration inventory."""

    package_version: str
    api_contract_version: str
    api_status: str
    python_version: str
    python_implementation: str
    platform_system: str
    platform_machine: str
    required_dependencies: tuple[tuple[str, str | None], ...]
    optional_dependencies: tuple[tuple[str, str | None], ...]

    def to_dict(self) -> dict[str, object]:
        """Return a plain dictionary suitable for logs or JSON export."""
        return asdict(self)


def _distribution_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def get_runtime_info() -> RuntimeInfo:
    """Report package/API/runtime versions without importing optional packages."""
    return RuntimeInfo(
        package_version=_distribution_version("eclipsekit") or PACKAGE_VERSION,
        api_contract_version=API_CONTRACT_VERSION,
        api_status=API_STATUS,
        python_version=platform.python_version(),
        python_implementation=sys.implementation.name,
        platform_system=platform.system(),
        platform_machine=platform.machine(),
        required_dependencies=tuple(
            (name, _distribution_version(distribution))
            for name, distribution in (("numpy", "numpy"), ("skyfield", "skyfield"))
        ),
        optional_dependencies=tuple(
            (name, _distribution_version(distribution))
            for name, distribution in (("limb/torch", "torch"), ("raster/rasterio", "rasterio"))
        ),
    )


__all__ = [
    "API_CONTRACT_VERSION", "API_STATUS", "PACKAGE_VERSION", "RuntimeInfo", "get_runtime_info",
    "EclipseEngine", "EclipseConfig", "EphemerisConfig", "ContactModelConfig",
    "LunarEclipseContacts", "LunarEclipseResult", "LunarShadowGeometry",
    "lunar_shadow_geometry",
    "SolverConfig", "AtmosphereConfig", "BesselianConfig", "EarthOrientationConfig",
    "describe_earth_orientation_source", "default_ephemeris_cache_dir", "Observer", "City",
    "CityCatalog", "ContactTimes", "ContactEvent", "LimbContact", "LocalEclipseResult",
    "CityEclipseHit", "CountryEclipseEvent", "SolarEclipseLocationHit",
    "SolarEclipseSearchEvent", "SolarEclipseSearchResult", "HorizonProfile",
    "ObservationGeometry", "ShadowFootprint", "ShadowPathPoint", "ShadowCorridorEdge",
    "ShadowCorridorSample", "ShadowCorridorResult", "RootResult", "bisect_root",
    "brent_root", "solve_root", "BesselianPolynomial", "BesselianElements",
    "BesselianSnapshot", "BesselianObserverState", "BesselianContact", "BesselianLocalResult",
    "BesselianGlobalPoint", "BesselianSolver", "delta_t_seconds", "time_to_utc_iso", "time_to_ut1_iso",
    "city_hits_to_geojson", "shadow_path_to_geojson", "shadow_corridor_to_geojson",
    "shadow_corridor_to_kml", "write_shadow_corridor_csv", "write_shadow_corridor_kml",
    "shadow_footprint_to_geojson", "write_shadow_footprint_geojson", "write_city_hits_csv",
    "write_geojson", "ObservationPlan", "ObservationSitePlan", "ObservationScoreWeights",
    "write_observation_plan_csv", "write_observation_plan_json", "LunarLimbCorrector",
    "LunarLimbModel", "LunarLimbModelMetadata", "LunarLimbQuery", "LunarLimbPrediction",
    "SphericalLunarLimbModel", "GriddedLunarLimbModel", "AngularLunarLimbProfile",
    "TabulatedAngularLunarLimbProfile", "NeuralLunarLimbModel", "predict_lunar_limb",
    "UncertaintyBudget", "PropagationResult", "ContactTimeUncertainty",
    "finite_difference_jacobian", "propagate_covariance", "propagate_uncertainty",
    "propagate_shadow_path_position_uncertainty", "estimate_contact_time_uncertainty",
    "estimate_lunar_limb_contact_time_uncertainty", "altitude_uncertainty_to_time_seconds",
    "apply_contact_uncertainties", "combine_independent_uncertainties",
    "uncertainty_result_to_markdown", "write_uncertainty_report", "PDS3LunarDEMModel",
    "PDS3LunarDEMProductInfo", "LunarDEMWindow", "LunarDEMCacheInfo", "open_pds3_lunar_dem",
    "parse_pds3_label", "LunarDEMFormatProductInfo", "PDS4LunarDEMModel",
    "RasterioLunarDEMModel", "GeoTiffLunarDEMModel", "JP2LunarDEMModel",
    "open_pds4_lunar_dem", "open_geotiff_lunar_dem", "open_jp2_lunar_dem",
    "LunarFrameTransform", "LunarReferenceSphereTransform", "LunarCoordinateResult",
    "LunarCoordinateTransform", "de440_pa_to_de421_me_transform",
    "de421_me_to_de440_pa_transform", "LunarControlPoint", "LunarControlPointSet",
    "LunarDEMControlPointReport", "load_lunar_control_points", "validate_lunar_dem_control_points",
    "write_lunar_dem_control_point_report", "TransformedLunarDEMModel", "LunarDEMCoverage",
    "LunarDEMMosaicSource", "LunarDEMMosaicProductInfo", "LunarDEMOutOfCoverageError",
    "LunarDEMMosaicModel", "LunarDEMMosaicOverlapReport", "audit_lunar_dem_mosaic_overlaps",
    "write_lunar_dem_mosaic_overlap_report", "CorridorReferenceRow", "CorridorValidationRow",
    "CorridorValidationReport", "load_corridor_reference_csv", "validate_shadow_corridor_reference",
    "compare_shadow_corridor_resolutions", "BenchmarkCaseResult", "BenchmarkSuiteResult", "benchmark_callable",
    "compare_benchmark_suites", "run_benchmark_suite", "EXTENSION_GROUPS", "ExtensionInfo", "ExtensionError", "LunarLimbModelFactory",
    "LunarDEMReader", "LunarDEMReaderFactory", "AmbiguousExtensionError",
    "ExtensionLoadError", "UnknownExtensionError",
    "discover_extensions", "load_extension", "to_jsonable", "dumps_json", "write_json",
]
