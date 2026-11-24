"""Independent benchmark evaluation for provider-neutral lunar-limb models.

A benchmark CSV must contain independently measured/reference radial heights;
synthetic examples are useful for API tests but are not scientific validation.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, replace
import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping


@dataclass(frozen=True, slots=True)
class LunarLimbBenchmarkSample:
    sample_id: str
    selenographic_latitude_deg: float
    selenographic_longitude_deg: float
    limb_angle_deg: float
    reference_altitude_m: float
    reference_uncertainty_m: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.sample_id, str) or not self.sample_id.strip():
            raise ValueError("sample_id must be a non-empty string")
        object.__setattr__(self, "sample_id", self.sample_id.strip())
        numeric_fields = (
            "selenographic_latitude_deg", "selenographic_longitude_deg",
            "limb_angle_deg", "reference_altitude_m",
        )
        for field in numeric_fields:
            value = getattr(self, field)
            if isinstance(value, bool):
                raise ValueError(f"{field} must be finite, not bool")
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field} must be finite") from exc
            if not math.isfinite(number):
                raise ValueError(f"{field} must be finite")
            object.__setattr__(self, field, number)
        if not -90.0 <= self.selenographic_latitude_deg <= 90.0:
            raise ValueError("selenographic latitude must lie in [-90, 90]")
        if not -180.0 <= self.selenographic_longitude_deg <= 180.0:
            raise ValueError("selenographic longitude must lie in [-180, 180]")
        if self.reference_uncertainty_m is not None:
            if isinstance(self.reference_uncertainty_m, bool):
                raise ValueError("reference_uncertainty_m must be finite and non-negative")
            try:
                uncertainty = float(self.reference_uncertainty_m)
            except (TypeError, ValueError) as exc:
                raise ValueError("reference_uncertainty_m must be finite and non-negative") from exc
            if not math.isfinite(uncertainty) or uncertainty < 0.0:
                raise ValueError("reference_uncertainty_m must be finite and non-negative")
            object.__setattr__(self, "reference_uncertainty_m", uncertainty)


def _finite(value: Any, field: str, row_number: int) -> float:
    if isinstance(value, bool):
        raise ValueError(f"Row {row_number}: {field} must be numeric, not bool")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Row {row_number}: {field} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"Row {row_number}: {field} must be finite")
    return result


def load_lunar_limb_benchmark(filename: str | Path) -> list[LunarLimbBenchmarkSample]:
    """Load reference samples from a CSV with explicit coordinate conventions."""
    path = Path(filename).expanduser()
    if not path.is_file():
        raise FileNotFoundError(path)
    required = {
        "selenographic_latitude_deg", "selenographic_longitude_deg",
        "limb_angle_deg", "reference_altitude_m",
    }
    samples: list[LunarLimbBenchmarkSample] = []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(
                "Lunar-limb benchmark CSV requires columns: " + ", ".join(sorted(required))
            )
        for row_number, row in enumerate(reader, start=2):
            if not any(value not in (None, "") for value in row.values()):
                continue
            latitude = _finite(row["selenographic_latitude_deg"], "selenographic_latitude_deg", row_number)
            longitude = _finite(row["selenographic_longitude_deg"], "selenographic_longitude_deg", row_number)
            limb_angle = _finite(row["limb_angle_deg"], "limb_angle_deg", row_number)
            altitude = _finite(row["reference_altitude_m"], "reference_altitude_m", row_number)
            if not -90.0 <= latitude <= 90.0:
                raise ValueError(f"Row {row_number}: selenographic latitude must lie in [-90, 90]")
            if not -180.0 <= longitude <= 180.0:
                raise ValueError(f"Row {row_number}: selenographic longitude must lie in [-180, 180]")
            uncertainty = None
            if "reference_uncertainty_m" in (reader.fieldnames or []) and row.get("reference_uncertainty_m") not in (None, ""):
                uncertainty = _finite(row["reference_uncertainty_m"], "reference_uncertainty_m", row_number)
                if uncertainty < 0.0:
                    raise ValueError(f"Row {row_number}: reference_uncertainty_m must be non-negative")
            sample_id = str(row.get("sample_id") or f"row-{row_number}").strip()
            if not sample_id:
                raise ValueError(f"Row {row_number}: sample_id must be non-empty")
            samples.append(LunarLimbBenchmarkSample(
                sample_id, latitude, longitude, limb_angle, altitude, uncertainty
            ))
    if not samples:
        raise ValueError("Lunar-limb benchmark contains no samples")
    if len({sample.sample_id for sample in samples}) != len(samples):
        raise ValueError("Lunar-limb benchmark sample_id values must be unique")
    return samples


def _evaluate_model(
    model: Any,
    samples: list[LunarLimbBenchmarkSample],
) -> dict[str, Any]:
    from .limb import LunarLimbQuery, predict_lunar_limb

    predictions: list[dict[str, Any]] = []
    residuals: list[float] = []
    normalized_residuals: list[float] = []
    errors: list[dict[str, str]] = []
    for sample in samples:
        try:
            query = LunarLimbQuery(
                sample.selenographic_latitude_deg,
                sample.selenographic_longitude_deg,
                sample.limb_angle_deg,
                contact_name=sample.sample_id,
            )
            prediction = predict_lunar_limb(model, query)
            residual = float(prediction.altitude_m) - sample.reference_altitude_m
            residuals.append(residual)
            combined_sigma = None
            if sample.reference_uncertainty_m is not None and prediction.uncertainty_m is not None:
                combined_sigma = math.hypot(
                    sample.reference_uncertainty_m, prediction.uncertainty_m
                )
                if combined_sigma > 0.0:
                    normalized_residuals.append(residual / combined_sigma)
            predictions.append({
                "sample_id": sample.sample_id,
                "reference_altitude_m": sample.reference_altitude_m,
                "predicted_altitude_m": prediction.altitude_m,
                "residual_m": residual,
                "absolute_error_m": abs(residual),
                "reference_uncertainty_m": sample.reference_uncertainty_m,
                "model_uncertainty_m": prediction.uncertainty_m,
                "combined_sigma_m": combined_sigma,
                "model_name": prediction.model_name,
                "model_type": prediction.model_type,
                "model_source": prediction.source,
                "prediction_status": prediction.status,
            })
        except Exception as exc:
            errors.append({
                "sample_id": sample.sample_id,
                "error": f"{type(exc).__name__}: {exc}",
            })
    if residuals:
        count = len(residuals)
        bias = sum(residuals) / count
        mae = sum(abs(value) for value in residuals) / count
        rmse = math.sqrt(sum(value * value for value in residuals) / count)
        max_abs = max(abs(value) for value in residuals)
        median_abs = median(abs(value) for value in residuals)
    else:
        count = 0
        bias = mae = rmse = max_abs = median_abs = None
    uncertainty_metrics = None
    if normalized_residuals:
        count_sigma = len(normalized_residuals)
        uncertainty_metrics = {
            "samples_with_combined_uncertainty": count_sigma,
            "mean_normalized_residual": sum(normalized_residuals) / count_sigma,
            "fraction_within_1_sigma": sum(abs(value) <= 1.0 for value in normalized_residuals) / count_sigma,
            "fraction_within_2_sigma": sum(abs(value) <= 2.0 for value in normalized_residuals) / count_sigma,
            "note": "Coverage is descriptive for this benchmark; it is not a calibrated confidence claim unless uncertainties are calibrated and samples are independent.",
        }
    metadata = getattr(model, "metadata", None)
    metadata_dict = metadata.to_dict() if metadata is not None and hasattr(metadata, "to_dict") else {
        "name": type(model).__name__,
        "source": "custom model without LunarLimbModelMetadata",
    }
    status = "PASS" if not errors and count == len(samples) else ("ERROR" if count == 0 else "FAIL")
    return {
        "status": status,
        "model": metadata_dict,
        "requested_samples": len(samples),
        "successful_samples": count,
        "error_count": len(errors),
        "metrics": {
            "bias_m": bias,
            "mae_m": mae,
            "rmse_m": rmse,
            "median_absolute_error_m": median_abs,
            "maximum_absolute_error_m": max_abs,
        },
        "uncertainty_metrics": uncertainty_metrics,
        "predictions": predictions,
        "errors": errors,
    }


def run_lunar_limb_model_validation(
    model: Any,
    samples: Iterable[LunarLimbBenchmarkSample],
    *,
    benchmark_source: str,
    benchmark_vertical_datum: str | None = None,
    include_spherical_baseline: bool = True,
    acceptance_rmse_m: float | None = None,
    acceptance_max_absolute_error_m: float | None = None,
) -> dict[str, Any]:
    """Evaluate a lunar-limb model against independent measured radial heights.

    ``bias_m`` is predicted minus reference. The provider's model-wide
    ``validation_rmse_m`` metadata is preserved but never substituted for the
    sample-wise benchmark metrics or pointwise uncertainty.
    """
    from .limb import SphericalLunarLimbModel

    if not isinstance(benchmark_source, str) or not benchmark_source.strip():
        raise ValueError("benchmark_source must describe the independent reference data")
    if benchmark_vertical_datum is not None and not str(benchmark_vertical_datum).strip():
        raise ValueError("benchmark_vertical_datum must be non-empty or None")
    sample_list = list(samples)
    if not sample_list:
        raise ValueError("At least one lunar-limb benchmark sample is required")
    if acceptance_rmse_m is not None:
        acceptance_rmse_m = float(acceptance_rmse_m)
        if not math.isfinite(acceptance_rmse_m) or acceptance_rmse_m < 0.0:
            raise ValueError("acceptance_rmse_m must be finite and non-negative")
    if acceptance_max_absolute_error_m is not None:
        acceptance_max_absolute_error_m = float(acceptance_max_absolute_error_m)
        if not math.isfinite(acceptance_max_absolute_error_m) or acceptance_max_absolute_error_m < 0.0:
            raise ValueError("acceptance_max_absolute_error_m must be finite and non-negative")
    model_metadata = getattr(model, "metadata", None)
    model_vertical_datum = getattr(model_metadata, "vertical_datum", None)
    if model_vertical_datum and benchmark_vertical_datum:
        def normalize_datum(value: Any) -> str:
            return " ".join(str(value).casefold().split())

        if normalize_datum(model_vertical_datum) != normalize_datum(benchmark_vertical_datum):
            raise ValueError(
                "Model and benchmark vertical datums do not match: "
                f"{model_vertical_datum!r} versus {benchmark_vertical_datum!r}"
            )
    result = _evaluate_model(model, sample_list)
    metrics = result["metrics"]
    criteria_configured = (
        acceptance_rmse_m is not None or acceptance_max_absolute_error_m is not None
    )
    if result["successful_samples"] != len(sample_list):
        result["status"] = "ERROR" if result["successful_samples"] == 0 else "FAIL"
    elif not criteria_configured:
        result["status"] = "UNASSESSED"
    else:
        criterion_results = []
        if acceptance_rmse_m is not None:
            criterion_results.append(metrics["rmse_m"] is not None and metrics["rmse_m"] <= acceptance_rmse_m)
        if acceptance_max_absolute_error_m is not None:
            criterion_results.append(
                metrics["maximum_absolute_error_m"] is not None
                and metrics["maximum_absolute_error_m"] <= acceptance_max_absolute_error_m
            )
        result["status"] = "PASS" if all(criterion_results) else "FAIL"
    report: dict[str, Any] = {
        "schema_version": 1,
        "benchmark": {
            "source": str(benchmark_source),
            "vertical_datum": benchmark_vertical_datum,
            "sample_count": len(sample_list),
            "coordinate_frame": "selenographic latitude/longitude plus apparent limb angle",
            "reference_quantity": "radial altitude in metres, relative to the declared source surface",
        },
        "acceptance_criteria": {
            "rmse_max_m": acceptance_rmse_m,
            "maximum_absolute_error_max_m": acceptance_max_absolute_error_m,
            "note": (
                "No quality PASS/FAIL is assigned unless at least one explicit acceptance limit is supplied."
            ),
        },
        **result,
    }
    if include_spherical_baseline and getattr(getattr(model, "metadata", None), "model_type", None) != "spherical":
        baseline = _evaluate_model(SphericalLunarLimbModel(), sample_list)
        report["spherical_zero_relief_baseline"] = {
            "metrics": baseline["metrics"],
            "status": "COMPUTED" if baseline["successful_samples"] == len(sample_list) else "ERROR",
            "note": "Analytic zero-relief comparator; not a topographic reference dataset.",
        }
    return report


def render_lunar_limb_validation_markdown(report: Mapping[str, Any]) -> str:
    metrics = report.get("metrics", {})
    model = report.get("model", {})
    lines = [
        "# EclipseKit lunar-limb model benchmark",
        "",
        f"**Status:** {report.get('status', 'UNKNOWN')}",
        f"**Model:** {model.get('name', 'unknown')} ({model.get('model_type', 'unknown')})",
        f"**Model source:** {model.get('source', 'not recorded')}",
        f"**Independent benchmark:** {report.get('benchmark', {}).get('source', 'not recorded')}",
        f"**Reference vertical datum:** {report.get('benchmark', {}).get('vertical_datum') or 'not specified'}",
        f"**Successful samples:** {report.get('successful_samples', 0)}/{report.get('requested_samples', 0)}",
        "",
        "## Residual metrics (prediction − reference)",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for label, key in (
        ("Bias (m)", "bias_m"), ("MAE (m)", "mae_m"), ("RMSE (m)", "rmse_m"),
        ("Median absolute error (m)", "median_absolute_error_m"),
        ("Maximum absolute error (m)", "maximum_absolute_error_m"),
    ):
        value = metrics.get(key)
        lines.append(f"| {label} | {'—' if value is None else f'{value:.4f}'} |")
    uncertainty = report.get("uncertainty_metrics")
    if uncertainty:
        lines.extend([
            "",
            "## Descriptive uncertainty coverage",
            "",
            f"- Samples with combined uncertainty: {uncertainty['samples_with_combined_uncertainty']}",
            f"- Within 1σ: {uncertainty['fraction_within_1_sigma']:.1%}",
            f"- Within 2σ: {uncertainty['fraction_within_2_sigma']:.1%}",
            f"- {uncertainty['note']}",
        ])
    baseline = report.get("spherical_zero_relief_baseline")
    if baseline:
        lines.extend([
            "",
            "## Spherical zero-relief baseline",
            "",
            f"- MAE: {_fmt(baseline.get('metrics', {}).get('mae_m'))} m",
            f"- RMSE: {_fmt(baseline.get('metrics', {}).get('rmse_m'))} m",
            f"- {baseline.get('note', '')}",
        ])
    if report.get("errors"):
        lines.extend(["", "## Prediction errors", ""])
        for error in report["errors"]:
            lines.append(f"- {error['sample_id']}: {error['error']}")
    lines.extend([
        "",
        "> This report evaluates only the supplied samples and the reference "
        "surface/datum they document. It does not certify lunar-limb timing "
        "corrections or imply a contact-time uncertainty without a separate "
        "propagation model.",
        "",
    ])
    return "\n".join(lines)


def _fmt(value: Any) -> str:
    return "—" if value is None else f"{float(value):.4f}"



class NeuralLimbModelFactory:
    """Small helper to attach CLI provenance without mutating frozen metadata."""

    @staticmethod
    def from_checkpoint(path: str | Path, *, device: str, name: str, source: str) -> Any:
        from .limb import LunarLimbCorrector, NeuralLunarLimbModel

        corrector = LunarLimbCorrector.from_checkpoint(path, device=device)
        model = NeuralLunarLimbModel(corrector, source=source)
        model.metadata = replace(model.metadata, name=name, source=source)
        return model


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark a EclipseKit lunar-limb model against independent reference samples"
    )
    parser.add_argument("--benchmark-csv", required=True)
    parser.add_argument(
        "--benchmark-source", required=True,
        help="Independent product/publication ID, release/version and provenance",
    )
    parser.add_argument("--benchmark-vertical-datum", default=None)
    parser.add_argument("--model", choices=("dem", "angular-profile", "neural", "spherical"), required=True)
    parser.add_argument("--model-file", default=None)
    parser.add_argument("--model-name", default="User-supplied lunar-limb model")
    parser.add_argument("--model-source", default=None)
    parser.add_argument("--vertical-datum", default=None)
    parser.add_argument("--resolution-m", type=float, default=None)
    parser.add_argument("--non-periodic", action="store_true", help="Do not wrap angular-profile interpolation at 360°")
    parser.add_argument("--periodic-longitude", action="store_true", help="Use periodic 360° longitude on a global DEM grid")
    parser.add_argument("--device", default="cpu", help="PyTorch device for --model neural")
    parser.add_argument("--max-rmse-m", type=float, default=None, help="Optional RMSE acceptance threshold in metres")
    parser.add_argument("--max-absolute-error-m", type=float, default=None, help="Optional maximum absolute-error acceptance threshold in metres")
    parser.add_argument("--json-out", default="reports/lunar-limb-validation.json")
    parser.add_argument("--markdown-out", default="reports/lunar-limb-validation.md")
    args = parser.parse_args(argv)

    if args.model != "spherical" and not args.model_file:
        parser.error("--model-file is required for dem, angular-profile, and neural models")
    if args.model == "spherical" and any((
        args.model_file, args.model_source, args.vertical_datum, args.resolution_m,
        args.periodic_longitude, args.non_periodic,
    )):
        parser.error("model file/source, datum, resolution and periodic options do not apply to the spherical baseline")
    if args.model != "dem" and (args.periodic_longitude or args.vertical_datum or args.resolution_m is not None):
        parser.error("--periodic-longitude, --vertical-datum and --resolution-m apply only to a gridded DEM")
    if args.model != "angular-profile" and args.non_periodic:
        parser.error("--non-periodic applies only to an angular profile")
    if args.max_rmse_m is not None and (
        not math.isfinite(args.max_rmse_m) or args.max_rmse_m < 0.0
    ):
        parser.error("--max-rmse-m must be finite and non-negative")
    if args.max_absolute_error_m is not None and (
        not math.isfinite(args.max_absolute_error_m) or args.max_absolute_error_m < 0.0
    ):
        parser.error("--max-absolute-error-m must be finite and non-negative")

    try:
        from .limb import (
            GriddedLunarLimbModel,
            SphericalLunarLimbModel,
            TabulatedAngularLunarLimbProfile,
        )

        source = args.model_source or (
            str(Path(args.model_file).expanduser())
            if args.model_file else "analytic zero-relief reference"
        )
        if args.model == "dem":
            model = GriddedLunarLimbModel.from_csv(
                args.model_file,
                name=args.model_name,
                source=source,
                vertical_datum=args.vertical_datum,
                resolution_m=args.resolution_m,
                periodic_longitude=args.periodic_longitude,
            )
        elif args.model == "angular-profile":
            model = TabulatedAngularLunarLimbProfile.from_csv(
                args.model_file,
                name=args.model_name,
                source=source,
                periodic=not args.non_periodic,
            )
        elif args.model == "neural":
            model = NeuralLimbModelFactory.from_checkpoint(
                args.model_file, device=args.device, name=args.model_name, source=source
            )
        else:
            model = SphericalLunarLimbModel(name=args.model_name)

        samples = load_lunar_limb_benchmark(args.benchmark_csv)
        report = run_lunar_limb_model_validation(
            model,
            samples,
            benchmark_source=args.benchmark_source,
            benchmark_vertical_datum=args.benchmark_vertical_datum,
            acceptance_rmse_m=args.max_rmse_m,
            acceptance_max_absolute_error_m=args.max_absolute_error_m,
        )
    except Exception as exc:
        parser.exit(2, f"Could not run lunar-limb benchmark: {type(exc).__name__}: {exc}\n")

    json_path = Path(args.json_out).expanduser()
    markdown_path = Path(args.markdown_out).expanduser()
    try:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        markdown = render_lunar_limb_validation_markdown(report)
        markdown_path.write_text(markdown, encoding="utf-8")
    except OSError as exc:
        parser.exit(2, f"Could not write lunar-limb benchmark report: {exc}\n")
    print(markdown)
    print(f"\nJSON report: {json_path.resolve()}")
    print(f"Markdown report: {markdown_path.resolve()}")
    return 1 if report["status"] in {"FAIL", "ERROR"} else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
