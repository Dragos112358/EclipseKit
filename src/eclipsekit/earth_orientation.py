"""Explicit Earth-orientation and time-scale configuration.

Operational modes:
- ``builtin``: Skyfield's bundled Delta-T and leap-second tables; offline-friendly.
- ``iers``: load ``finals2000A.all`` through Skyfield/IERS (network on first use).

The ``fixed_delta_t`` mode is for reproducing a published historical prediction
that explicitly specifies a Delta-T assumption. It is NOT a replacement for
observed UT1-UTC and can produce a synthetic DUT1 outside UTC's normal range.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import math
from pathlib import Path
from typing import Any, Literal

EarthOrientationMode = Literal["builtin", "iers", "fixed_delta_t"]


@dataclass(frozen=True, slots=True)
class EarthOrientationConfig:
    """Configuration for constructing the Skyfield time scale.

    Examples
    --------
    ``EarthOrientationConfig(mode="builtin")``
        Use Skyfield's bundled Earth-rotation data (default).

    ``EarthOrientationConfig(mode="iers")``
        Use IERS ``finals2000A.all`` data via ``Loader.timescale(builtin=False)``.

    ``EarthOrientationConfig(mode="fixed_delta_t", fixed_delta_t_seconds=71.4)``
        Reproduce a historical prediction that specifies this exact Delta-T.
        Use reference timestamps explicitly interpreted as UT1. Do not use this
        mode for current UTC/operational predictions.
    """

    mode: EarthOrientationMode = "builtin"
    fixed_delta_t_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"builtin", "iers", "fixed_delta_t"}:
            raise ValueError(
                "mode must be 'builtin', 'iers', or 'fixed_delta_t'"
            )
        if self.mode == "fixed_delta_t":
            if self.fixed_delta_t_seconds is None:
                raise ValueError(
                    "fixed_delta_t_seconds is required when mode='fixed_delta_t'"
                )
            if not math.isfinite(float(self.fixed_delta_t_seconds)):
                raise ValueError("fixed_delta_t_seconds must be finite")
        elif self.fixed_delta_t_seconds is not None:
            raise ValueError(
                "fixed_delta_t_seconds is only valid when mode='fixed_delta_t'"
            )

    @classmethod
    def builtin(cls) -> "EarthOrientationConfig":
        return cls(mode="builtin")

    @classmethod
    def iers(cls) -> "EarthOrientationConfig":
        return cls(mode="iers")

    @classmethod
    def fixed(cls, delta_t_seconds: float) -> "EarthOrientationConfig":
        """Create a historical-reproduction configuration with fixed Delta-T."""
        return cls(mode="fixed_delta_t", fixed_delta_t_seconds=float(delta_t_seconds))

    def create_timescale(self, loader: Any) -> Any:
        """Build a Skyfield Timescale using the selected source."""
        if self.mode == "builtin":
            return loader.timescale()
        if self.mode == "iers":
            return loader.timescale(builtin=False)
        return loader.timescale(delta_t=float(self.fixed_delta_t_seconds))


def describe_earth_orientation_source(
    config: EarthOrientationConfig | None,
    *,
    cache_dir: str | Path | None = None,
    explicit_timescale: bool = False,
    skyfield_version: str | None = None,
) -> dict[str, Any]:
    """Describe and fingerprint the source of the active Earth-orientation data.

    Built-in Skyfield tables are version-scoped. IERS mode is content-hashed
    when Skyfield's downloaded ``finals2000A.all`` file is found in the active
    loader cache. A missing file is reported as UNVERIFIED rather than being
    mistaken for a pinned data source.
    """
    if skyfield_version is None:
        try:
            skyfield_version = importlib.metadata.version("skyfield")
        except importlib.metadata.PackageNotFoundError:
            skyfield_version = None

    if explicit_timescale:
        return {
            "schema": "eclipsekit.phase8_3.earth_orientation_provenance.v1",
            "mode": "explicit_timescale",
            "status": "UNVERIFIED",
            "reproducibility_level": "CALLER_MANAGED",
            "source": "Caller-supplied Skyfield timescale object",
            "skyfield_version": skyfield_version,
            "cache_dir": str(Path(cache_dir).expanduser()) if cache_dir is not None else None,
            "data_file": None,
            "size_bytes": None,
            "sha256": None,
            "fixed_delta_t_seconds": None,
            "notes": ["The caller must record the construction and source data of the supplied timescale."],
        }

    active = config or EarthOrientationConfig.builtin()
    base = {
        "schema": "eclipsekit.phase8_3.earth_orientation_provenance.v1",
        "mode": active.mode,
        "skyfield_version": skyfield_version,
        "cache_dir": str(Path(cache_dir).expanduser()) if cache_dir is not None else None,
        "data_file": None,
        "size_bytes": None,
        "sha256": None,
        "fixed_delta_t_seconds": active.fixed_delta_t_seconds,
    }
    if active.mode == "builtin":
        base.update({
            "status": "PASS",
            "reproducibility_level": "SKYFIELD_VERSION_SCOPED",
            "source": "Skyfield bundled Delta-T and leap-second tables",
            "notes": [
                "The data are bundled with Skyfield; reproducibility is scoped to the recorded Skyfield version.",
                "Built-in tables are not separately content-hashed by this audit.",
            ],
        })
        return base
    if active.mode == "fixed_delta_t":
        base.update({
            "status": "PASS_WITH_EXPLICIT_ASSUMPTION",
            "reproducibility_level": "EXPLICIT_NUMERIC_ASSUMPTION",
            "source": "User-specified fixed Delta-T value",
            "notes": [
                "This is a historical-reproduction assumption, not observed operational UT1-UTC data.",
                "The exact Delta-T value is recorded; derived DUT1 may not be UTC-consistent.",
            ],
        })
        return base

    cache = Path(cache_dir).expanduser() if cache_dir is not None else None
    legacy_names = ("deltat.data", "deltat.preds", "Leap_Second.dat")
    legacy_files = [cache / name for name in legacy_names] if cache is not None else []
    legacy_complete = bool(legacy_files) and all(path.is_file() for path in legacy_files)
    finals_file = cache / "finals2000A.all" if cache is not None else None

    # Skyfield retains a backwards-compatibility branch: when all three older
    # files exist, builtin=False uses them instead of finals2000A.all.
    # Fingerprint that exact active set rather than reporting the unused file.
    if legacy_complete:
        selected_files = legacy_files
        source = "Skyfield legacy external Delta-T/leap-second tables"
        level = "CONTENT_HASHED_LEGACY_SKYFIELD_TABLES"
    elif finals_file is not None and finals_file.is_file():
        selected_files = [finals_file]
        source = "IERS finals2000A table loaded from the Skyfield cache"
        level = "CONTENT_HASHED_IERS_FILE"
    else:
        base.update({
            "status": "UNVERIFIED",
            "reproducibility_level": "EXTERNAL_SOURCE_NOT_FINGERPRINTED",
            "source": "IERS finals2000A.all or complete legacy Skyfield time-scale table set",
            "data_files": [],
            "notes": [
                "No complete external IERS/legacy time-scale file set was found in the supplied cache directory.",
                "The active Skyfield timescale may have used another cache location; supply that directory to fingerprint it.",
            ],
        })
        return base

    file_records = []
    aggregate = hashlib.sha256()
    total_size = 0
    for source_file in selected_files:
        digest = hashlib.sha256()
        with source_file.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        stat = source_file.stat()
        file_hash = digest.hexdigest()
        file_records.append({
            "name": source_file.name,
            "path": str(source_file.resolve()),
            "size_bytes": stat.st_size,
            "sha256": file_hash,
            "modified_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
        })
        aggregate.update(source_file.name.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(bytes.fromhex(file_hash))
        total_size += stat.st_size
    base.update({
        "status": "PASS",
        "reproducibility_level": level,
        "source": source,
        "data_file": file_records[0]["path"] if len(file_records) == 1 else None,
        "data_files": file_records,
        "size_bytes": total_size,
        "sha256": file_records[0]["sha256"] if len(file_records) == 1 else aggregate.hexdigest(),
        "fingerprint_scheme": (
            "sha256(file_bytes)" if len(file_records) == 1
            else "sha256(concatenated filename, NUL, component SHA-256 records in Skyfield load order)"
        ),
        "notes": ["Each data_files entry identifies the exact file bytes used by the selected Skyfield compatibility branch."],
    })
    return base


def describe_time_scale(
    time: Any,
    mode: str,
    *,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return auditable Delta-T/DUT1 diagnostics for a Skyfield Time instance.

    A DUT1 magnitude above 0.9 seconds is flagged because UTC is maintained
    within 0.9 seconds of UT1. This flag is expected for some fixed-Delta-T
    historical-reproduction configurations and is not a calculation failure.
    """
    delta_t = float(time.delta_t)
    dut1 = float(time.dut1)
    utc_consistent = abs(dut1) <= 0.9
    result: dict[str, Any] = {
        "mode": str(mode),
        "utc": str(time.utc_iso()),
        "delta_t_seconds": delta_t,
        "dut1_seconds": dut1,
        "dut1_within_utc_limit": utc_consistent,
    }
    if mode == "fixed_delta_t":
        result["warning"] = (
            "Fixed Delta-T is a historical-prediction reproduction mode; "
            "its derived DUT1 may not be physically compatible with UTC."
        )
    elif not utc_consistent:
        result["warning"] = (
            "The selected time-scale data imply |UT1-UTC| > 0.9 s; "
            "check leap-second/Earth-orientation data freshness."
        )
    if provenance is not None:
        result["provenance"] = dict(provenance)
        provenance_status = provenance.get("status")
        if provenance_status == "UNVERIFIED":
            result["provenance_warning"] = "Earth-orientation source provenance could not be fully verified."
    return result


def main(argv: list[str] | None = None) -> int:
    """Audit the active Skyfield time-scale source and write a provenance report."""
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Audit and fingerprint EclipseKit Earth-orientation/time-scale inputs"
    )
    parser.add_argument("--mode", choices=("builtin", "iers", "fixed_delta_t"), default="builtin")
    parser.add_argument("--delta-t-seconds", type=float, default=None)
    from .ephemeris import default_ephemeris_cache_dir
    parser.add_argument("--cache-dir", default=str(default_ephemeris_cache_dir()))
    parser.add_argument("--at", default="2017-08-21T17:20:00Z", help="UTC instant used for Delta-T/DUT1 diagnostics")
    parser.add_argument("--json-out", default="reports/phase8_3/eop-provenance.json")
    parser.add_argument("--markdown-out", default="reports/phase8_3/eop-provenance.md")
    args = parser.parse_args(argv)
    if args.mode == "fixed_delta_t" and args.delta_t_seconds is None:
        parser.error("--delta-t-seconds is required with --mode fixed_delta_t")
    if args.mode != "fixed_delta_t" and args.delta_t_seconds is not None:
        parser.error("--delta-t-seconds is only valid with --mode fixed_delta_t")
    if args.delta_t_seconds is not None and (not math.isfinite(args.delta_t_seconds)):
        parser.error("--delta-t-seconds must be finite")
    try:
        from datetime import datetime
        from skyfield.api import Loader
        cache = Path(args.cache_dir).expanduser()
        cache.mkdir(parents=True, exist_ok=True)
        config = (
            EarthOrientationConfig.fixed(args.delta_t_seconds)
            if args.mode == "fixed_delta_t"
            else EarthOrientationConfig(mode=args.mode)
        )
        loader = Loader(str(cache), verbose=False)
        timescale = config.create_timescale(loader)
        stamp = args.at.strip().replace("Z", "+00:00")
        moment = datetime.fromisoformat(stamp)
        if moment.tzinfo is None or moment.utcoffset() is None:
            parser.error("--at must include Z or an explicit UTC offset")
        moment = moment.astimezone(timezone.utc)
        seconds = moment.second + moment.microsecond / 1_000_000.0
        skyfield_time = timescale.utc(moment.year, moment.month, moment.day, moment.hour, moment.minute, seconds)
        provenance = describe_earth_orientation_source(config, cache_dir=cache)
        diagnostics = describe_time_scale(skyfield_time, config.mode, provenance=provenance)
    except SystemExit:
        raise
    except Exception as exc:
        parser.exit(2, f"Could not audit Earth-orientation source: {type(exc).__name__}: {exc}\n")

    report = {
        "schema": "eclipsekit.phase8_3.eop_audit_report.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "status": provenance["status"],
        "diagnostic_epoch_utc": args.at,
        "time_scale_diagnostics": diagnostics,
        "provenance": provenance,
        "interpretation": (
            "A content hash identifies the exact external IERS file. Built-in mode is scoped to the recorded Skyfield version. "
            "Fixed Delta-T is an explicit historical assumption, not observed EOP data."
        ),
    }
    json_path = Path(args.json_out).expanduser()
    markdown_path = Path(args.markdown_out).expanduser()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    p = provenance
    lines = [
        "# EclipseKit Phase 8.3 — Earth-orientation provenance", "",
        f"**Status:** {report['status']}",
        f"**Mode:** {p['mode']}",
        f"**Source:** {p['source']}",
        f"**Skyfield version:** {p.get('skyfield_version') or 'not detected'}",
        f"**Reproducibility level:** {p['reproducibility_level']}",
        f"**Diagnostic epoch:** {args.at}",
        f"**Delta-T:** {diagnostics['delta_t_seconds']:.6f} s",
        f"**DUT1:** {diagnostics['dut1_seconds']:+.6f} s",
        f"**IERS data files:** {', '.join(item['name'] for item in p.get('data_files', [])) or 'not applicable / not found'}",
        f"**SHA-256 fingerprint:** {p.get('sha256') or 'not available'}", "",
        report['interpretation'], "", "## Notes", "",
    ]
    lines.extend(f"- {note}" for note in p.get("notes", []))
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Earth-orientation audit: {report['status']}")
    print(f"Mode: {p['mode']} | reproducibility: {p['reproducibility_level']}")
    print(f"Skyfield: {p.get('skyfield_version') or 'not detected'}")
    if p.get("sha256"):
        print(f"IERS SHA-256: {p['sha256']}")
    if diagnostics.get("warning"):
        print(f"WARNING: {diagnostics['warning']}")
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")
    return 1 if report["status"] == "UNVERIFIED" else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
