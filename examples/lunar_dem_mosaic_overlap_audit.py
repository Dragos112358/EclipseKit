"""Run a PDS3 lunar DEM overlap audit from an external JSON manifest."""

from __future__ import annotations

import argparse

from eclipsekit.lunar_dem_mosaic_validation import main


def run() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--samples-per-axis", type=int, default=11)
    parser.add_argument("--tolerance-m", type=float, default=100.0)
    parser.add_argument("--output-dir", default="reports/phase9_7")
    args = parser.parse_args()
    return main(
        [
            "--manifest", args.manifest,
            "--samples-per-axis", str(args.samples_per_axis),
            "--tolerance-m", str(args.tolerance_m),
            "--output-dir", args.output_dir,
        ]
    )


if __name__ == "__main__":
    raise SystemExit(run())
