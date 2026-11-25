"""EclipseKit: local and global solar-eclipse calculations."""

from ._version import __version__

from .cities import CityCatalog
from .engine import EclipseEngine
from .lunar_eclipse import LunarEclipseContacts, LunarEclipseResult, LunarShadowGeometry, lunar_shadow_geometry
from .contacts import RootResult, bisect_root, brent_root, solve_root
from .earth_orientation import EarthOrientationConfig, describe_earth_orientation_source
from .ephemeris import default_ephemeris_cache_dir
from .config import (AtmosphereConfig, BesselianConfig, ContactModelConfig, EclipseConfig, EphemerisConfig, SolverConfig)
from .limb import (
    AngularLunarLimbProfile,
    GriddedLunarLimbModel,
    LunarLimbCorrector,
    LunarLimbModel,
    LunarLimbModelMetadata,
    LunarLimbPrediction,
    LunarLimbQuery,
    NeuralLunarLimbModel,
    SphericalLunarLimbModel,
    TabulatedAngularLunarLimbProfile,
    predict_lunar_limb,
)
from .besselian import (
    BesselianContact, BesselianElements, BesselianGlobalPoint, BesselianLocalResult,
    BesselianObserverState, BesselianPolynomial, BesselianSnapshot, BesselianSolver,
)
from .models import (
    City, CityEclipseHit, ContactEvent, ContactTimes, CountryEclipseEvent, LimbContact,
    LocalEclipseResult, Observer, HorizonProfile, ObservationGeometry, ShadowPathPoint,
    ShadowFootprint, ShadowCorridorEdge, ShadowCorridorSample, ShadowCorridorResult,
    SolarEclipseLocationHit,
    SolarEclipseSearchEvent, SolarEclipseSearchResult,
)
from .timeutils import delta_t_seconds, time_to_utc_iso, time_to_ut1_iso
from .exports import (
    city_hits_to_geojson, shadow_path_to_geojson, shadow_corridor_to_geojson,
    shadow_corridor_to_kml, write_city_hits_csv, write_geojson,
    write_shadow_corridor_csv, write_shadow_corridor_kml,
    write_observation_plan_csv, write_observation_plan_json,
    shadow_footprint_to_geojson, write_shadow_footprint_geojson,
)
from .planner import ObservationPlan, ObservationScoreWeights, ObservationSitePlan
from .topography import (
    LunarDEMCacheInfo, LunarDEMWindow, PDS3LunarDEMModel, PDS3LunarDEMProductInfo,
    open_pds3_lunar_dem, parse_pds3_label,
)
from .topography_formats import (
    LunarDEMFormatProductInfo, PDS4LunarDEMModel, RasterioLunarDEMModel,
    GeoTiffLunarDEMModel, JP2LunarDEMModel,
    open_pds4_lunar_dem, open_geotiff_lunar_dem, open_jp2_lunar_dem,
)
from .lunar_coordinates import (
    LunarFrameTransform, LunarReferenceSphereTransform, LunarCoordinateResult,
    LunarCoordinateTransform, de440_pa_to_de421_me_transform,
    de421_me_to_de440_pa_transform,
)
from .lunar_control_points import (
    LunarControlPoint, LunarControlPointSet, LunarControlPointRow,
    LunarDEMControlPointReport, load_lunar_control_points,
    validate_lunar_dem_control_points, write_lunar_dem_control_point_report,
)
from .lunar_dem_transform import TransformedLunarDEMModel, TransformedLunarDEMProductInfo
from .lunar_dem_mosaic import (
    LunarDEMCoverage, LunarDEMMosaicSource, LunarDEMMosaicProductInfo,
    LunarDEMOutOfCoverageError, LunarDEMMosaicModel,
)
from .lunar_dem_mosaic_validation import (
    LunarDEMOverlapSample, LunarDEMOverlapPairResult, LunarDEMMosaicOverlapReport,
    audit_lunar_dem_mosaic_overlaps, write_lunar_dem_mosaic_overlap_report,
)
from .lunar_coordinates_validation import (
    LunarFrameAuditRow, LunarFrameAuditReport, validate_de440_pa_to_de421_me,
    write_lunar_frame_audit_report,
)
from .topography_formats_validation import (
    LunarDEMFormatSample, LunarDEMFormatValidationReport,
    validate_lunar_dem_format, write_lunar_dem_format_report,
)
from .topography_validation import (
    PDS3LunarDEMValidationReport, validate_pds3_lunar_dem,
    write_pds3_topography_validation_report,
)
from .uncertainty import (
    ContactTimeUncertainty, PropagationResult, UncertaintyBudget,
    altitude_uncertainty_to_time_seconds, apply_contact_uncertainties,
    combine_independent_uncertainties, estimate_contact_time_uncertainty,
    estimate_lunar_limb_contact_time_uncertainty, finite_difference_jacobian,
    propagate_covariance, propagate_shadow_path_position_uncertainty,
    propagate_uncertainty, uncertainty_result_to_markdown, write_uncertainty_report,
)
from .shadow_corridor_validation import (
    CorridorReferenceRow, CorridorValidationReport, CorridorValidationRow,
    load_corridor_reference_csv, validate_shadow_corridor_reference,
    compare_shadow_corridor_resolutions,
)


__all__ = [
    "EclipseEngine", "EclipseConfig", "EphemerisConfig", "ContactModelConfig",
    "LunarEclipseContacts", "LunarEclipseResult", "LunarShadowGeometry",
    "lunar_shadow_geometry",
    "HorizonProfile", "ObservationGeometry", "ShadowFootprint",
    "SolarEclipseLocationHit", "SolarEclipseSearchEvent", "SolarEclipseSearchResult",
    "SolverConfig", "AtmosphereConfig", "BesselianConfig", "EarthOrientationConfig", "describe_earth_orientation_source", "default_ephemeris_cache_dir", "Observer", "CityCatalog", "City", "ContactTimes", "ContactEvent", "LunarLimbCorrector",
    "LunarLimbModel", "LunarLimbModelMetadata", "LunarLimbQuery", "LunarLimbPrediction",
    "SphericalLunarLimbModel", "GriddedLunarLimbModel", "AngularLunarLimbProfile",
    "TabulatedAngularLunarLimbProfile", "NeuralLunarLimbModel", "predict_lunar_limb",
    "LocalEclipseResult", "LimbContact", "CityEclipseHit", "CountryEclipseEvent",
    "ShadowPathPoint", "ShadowCorridorEdge", "ShadowCorridorSample", "ShadowCorridorResult",
    "RootResult", "bisect_root", "brent_root", "solve_root",
    "BesselianPolynomial", "BesselianElements", "BesselianSnapshot",
    "BesselianObserverState", "BesselianContact", "BesselianLocalResult",
    "BesselianGlobalPoint", "BesselianSolver",
    "delta_t_seconds", "time_to_utc_iso", "time_to_ut1_iso",
    "city_hits_to_geojson", "shadow_path_to_geojson", "shadow_corridor_to_geojson",
    "shadow_corridor_to_kml", "write_shadow_corridor_csv", "write_shadow_corridor_kml",
    "ObservationPlan", "ObservationSitePlan", "ObservationScoreWeights",
    "write_observation_plan_csv", "write_observation_plan_json",
    "CorridorReferenceRow", "CorridorValidationRow", "CorridorValidationReport",
    "load_corridor_reference_csv", "validate_shadow_corridor_reference",
    "compare_shadow_corridor_resolutions",
    "write_city_hits_csv", "write_geojson",
    "shadow_footprint_to_geojson", "write_shadow_footprint_geojson",
    "UncertaintyBudget", "PropagationResult", "ContactTimeUncertainty",
    "finite_difference_jacobian", "propagate_covariance", "propagate_uncertainty",
    "propagate_shadow_path_position_uncertainty",
    "estimate_contact_time_uncertainty", "estimate_lunar_limb_contact_time_uncertainty",
    "altitude_uncertainty_to_time_seconds", "apply_contact_uncertainties",
    "combine_independent_uncertainties", "uncertainty_result_to_markdown",
    "write_uncertainty_report",
    "PDS3LunarDEMModel", "PDS3LunarDEMProductInfo", "LunarDEMWindow", "LunarDEMCacheInfo",
    "open_pds3_lunar_dem",
    "parse_pds3_label", "PDS3LunarDEMValidationReport", "validate_pds3_lunar_dem",
    "write_pds3_topography_validation_report",
    "LunarDEMFormatProductInfo", "PDS4LunarDEMModel", "RasterioLunarDEMModel",
    "GeoTiffLunarDEMModel", "JP2LunarDEMModel", "open_pds4_lunar_dem",
    "open_geotiff_lunar_dem", "open_jp2_lunar_dem", "LunarDEMFormatSample",
    "LunarDEMFormatValidationReport", "validate_lunar_dem_format",
    "write_lunar_dem_format_report",
    "LunarFrameTransform", "LunarReferenceSphereTransform", "LunarCoordinateResult",
    "LunarCoordinateTransform", "de440_pa_to_de421_me_transform",
    "de421_me_to_de440_pa_transform", "LunarFrameAuditRow", "LunarFrameAuditReport",
    "validate_de440_pa_to_de421_me", "write_lunar_frame_audit_report",
    "TransformedLunarDEMModel", "TransformedLunarDEMProductInfo",
    "LunarDEMCoverage", "LunarDEMMosaicSource", "LunarDEMMosaicProductInfo",
    "LunarDEMOutOfCoverageError", "LunarDEMMosaicModel",
    "LunarDEMOverlapSample", "LunarDEMOverlapPairResult", "LunarDEMMosaicOverlapReport",
    "audit_lunar_dem_mosaic_overlaps", "write_lunar_dem_mosaic_overlap_report",
    "LunarControlPoint", "LunarControlPointSet", "LunarControlPointRow",
    "LunarDEMControlPointReport", "load_lunar_control_points",
    "validate_lunar_dem_control_points", "write_lunar_dem_control_point_report",
    "__version__",
]

# Public integration surface added in Phase 14. Existing root imports remain
# available; new integrations should prefer the curated ``eclipsekit.api``.
from .api import API_CONTRACT_VERSION, API_STATUS, RuntimeInfo, get_runtime_info
from .extensions import (
    EXTENSION_GROUPS, AmbiguousExtensionError, ExtensionError, ExtensionInfo,
    ExtensionLoadError, UnknownExtensionError, LunarDEMReader, LunarDEMReaderFactory,
    LunarLimbModelFactory, discover_extensions, load_extension,
)
from .serialization import dumps_json, to_jsonable, write_json
from .performance import (
    BenchmarkCaseResult, BenchmarkSuiteResult, benchmark_callable,
    compare_benchmark_suites, run_benchmark_suite,
)

__all__ += [
    "API_CONTRACT_VERSION", "API_STATUS", "RuntimeInfo", "get_runtime_info",
    "EXTENSION_GROUPS", "ExtensionInfo", "ExtensionError", "ExtensionLoadError",
    "UnknownExtensionError", "AmbiguousExtensionError", "LunarLimbModelFactory",
    "LunarDEMReader", "LunarDEMReaderFactory", "discover_extensions", "load_extension",
    "to_jsonable", "dumps_json", "write_json", "BenchmarkCaseResult",
    "BenchmarkSuiteResult", "benchmark_callable", "compare_benchmark_suites",
    "run_benchmark_suite",
]
