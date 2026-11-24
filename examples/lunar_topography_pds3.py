"""Inspect and sample a user-downloaded PDS3 lunar DEM.

Example:
    python examples/lunar_topography_pds3.py --image data/lunar.img --label data/lunar.lbl \
        --latitude 12.0 --longitude 35.0

The sample coordinates are demonstration inputs, not a recommended eclipse
contact location. No DEM data are bundled with EclipseKit.
"""

from __future__ import annotations

import argparse
import json

from eclipsekit import LunarLimbQuery, PDS3LunarDEMModel


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="Uncompressed PDS3 IMG data file")
    parser.add_argument("--label", help="Detached PDS3 LBL file")
    parser.add_argument("--latitude", type=float, help="Optional selenographic latitude in degrees")
    parser.add_argument("--longitude", type=float, help="Optional east-positive longitude in degrees")
    parser.add_argument(
        "--expected-coordinate-system",
        help="Optional exact coordinate-system name required in the PDS3 label",
    )
    args = parser.parse_args()
    if (args.latitude is None) != (args.longitude is None):
        parser.error("--latitude and --longitude must be supplied together")

    with PDS3LunarDEMModel.from_pds3_img(
        args.image,
        args.label,
        expected_coordinate_system=args.expected_coordinate_system,
    ) as model:
        print(json.dumps(model.product_info.to_dict(), ensure_ascii=False, indent=2))
        if args.latitude is not None:
            prediction = model.predict(LunarLimbQuery(
                selenographic_latitude_deg=args.latitude,
                selenographic_longitude_deg=args.longitude,
                limb_angle_deg=0.0,
            ))
            print("Sample prediction:")
            print(json.dumps(prediction.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
