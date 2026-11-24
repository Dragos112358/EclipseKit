"""Sample a 2017 total-eclipse shadow corridor and compare it with NASA limits.

Run from the project root after installing EclipseKit and making DE440s available:
    python examples/shadow_corridor_2017.py
"""
from pathlib import Path

from eclipsekit import (
    EclipseEngine,
    shadow_corridor_to_geojson,
    validate_shadow_corridor_reference,
    write_geojson,
    write_shadow_corridor_csv,
    write_shadow_corridor_kml,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports" / "phase7_3"
REFERENCE = ROOT / "data" / "validation" / "global_corridor_2017_nasa.csv"


def main() -> int:
    engine = EclipseEngine.from_jpl("de440s")
    corridor = engine.global_shadow_corridor(
        "2017-08-21T17:00:00Z",
        "2017-08-21T17:40:00Z",
        samples=3,
        boundary_samples=144,
    )
    print("2017-08-21 NASA central corridor sample")
    print(f"Valid time slices: {len(corridor.samples)}")
    for sample in corridor.samples:
        print(
            f"{sample.center.time.utc_iso()} center=({sample.center.latitude:.5f}, "
            f"{sample.center.longitude:.5f}) kind={sample.center.shadow_kind} "
            f"core_width={sample.central_width_km!s} km "
            f"penumbra_width={sample.penumbral_width_km!s} km "
            f"central_track_chord={sample.central_track_chord_km!s} km "
            f"central_duration_estimate={sample.central_phase_duration_estimate_seconds!s} s"
        )

    report = validate_shadow_corridor_reference(
        corridor,
        REFERENCE,
        source_id="NASA/GSFC 2017-08-21 path table, selected rows 17:00/17:20/17:40 UT",
        coordinate_tolerance_km=8.0,
        width_tolerance_km=8.0,
        duration_tolerance_seconds=10.0,
        max_time_offset_seconds=65.0,
    )
    print(report.to_markdown())

    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_geojson(shadow_corridor_to_geojson(corridor), OUTPUT / "global-corridor.geojson")
    write_shadow_corridor_csv(corridor, OUTPUT / "global-corridor.csv")
    write_shadow_corridor_kml(corridor, OUTPUT / "global-corridor.kml")
    (OUTPUT / "validation.md").write_text(report.to_markdown(), encoding="utf-8")
    print(f"Exports written to: {OUTPUT}")
    return 0 if report.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
