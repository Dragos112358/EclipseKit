"""Route queries across two compatible local PDS3 lunar DEM products.

Example:
    python examples/lunar_dem_mosaic.py \
        --west-image data/west.img --west-label data/west.lbl \
        --east-image data/east.img --east-label data/east.lbl \
        --latitude 12 --longitude -45

Both products must declare the same lunar frame, vertical datum and reference
radius. This script performs no raster merge or scientific accuracy validation.
"""

from __future__ import annotations

import argparse
import json
from contextlib import ExitStack

from eclipsekit import LunarDEMMosaicModel, open_pds3_lunar_dem


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--west-image", required=True)
    parser.add_argument("--west-label", required=True)
    parser.add_argument("--east-image", required=True)
    parser.add_argument("--east-label", required=True)
    parser.add_argument("--latitude", type=float, required=True)
    parser.add_argument("--longitude", type=float, required=True)
    parser.add_argument(
        "--strategy", choices=("priority", "finest", "mean"), default="priority"
    )
    parser.add_argument(
        "--expected-coordinate-system",
        default=None,
        help="Optional exact product-label frame assertion passed to both PDS3 readers",
    )
    args = parser.parse_args()

    with ExitStack() as stack:
        west = stack.enter_context(
            open_pds3_lunar_dem(
                args.west_image,
                args.west_label,
                expected_coordinate_system=args.expected_coordinate_system,
            )
        )
        east = stack.enter_context(
            open_pds3_lunar_dem(
                args.east_image,
                args.east_label,
                expected_coordinate_system=args.expected_coordinate_system,
            )
        )
        mosaic = LunarDEMMosaicModel(
            [west, east],
            strategy=args.strategy,
            name="Two-product lunar DEM mosaic",
        )
        prediction = mosaic.predict_altitude_m(args.latitude, args.longitude)
        result = {
            "altitude_m": prediction,
            "latitude_deg": args.latitude,
            "longitude_deg": args.longitude,
            "strategy": args.strategy,
            "mosaic_product_info": mosaic.product_info.to_dict(),
            "limitations": [
                "virtual query routing only; no raster merge or reprojection",
                "metadata compatibility does not prove horizontal co-registration",
                "no independent accuracy claim is made",
            ],
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
