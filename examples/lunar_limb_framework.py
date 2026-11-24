"""Offline smoke example for Phase 5 lunar-limb providers.

The numerical grids below are synthetic fixtures, not lunar terrain data.
For real work, load a sourced DEM/profile with its actual metadata.
"""

from __future__ import annotations

import numpy as np

from eclipsekit import (
    GriddedLunarLimbModel,
    LunarLimbQuery,
    SphericalLunarLimbModel,
    TabulatedAngularLunarLimbProfile,
    predict_lunar_limb,
)


def main() -> None:
    query = LunarLimbQuery(
        selenographic_latitude_deg=0.0,
        selenographic_longitude_deg=0.0,
        limb_angle_deg=45.0,
        contact_name="C1",
    )

    # Synthetic 2x2 DEM used only to demonstrate bilinear interpolation.
    dem = GriddedLunarLimbModel(
        latitudes_deg=[-1.0, 1.0],
        longitudes_deg=[-1.0, 1.0],
        altitudes_m=np.array([[0.0, 100.0], [200.0, 300.0]]),
        uncertainties_m=np.full((2, 2), 10.0),
        name="Synthetic DEM fixture",
        source="example-only synthetic values",
        vertical_datum="synthetic radial reference",
    )

    angular = TabulatedAngularLunarLimbProfile(
        limb_angles_deg=[0.0, 90.0, 180.0, 270.0],
        altitudes_m=[0.0, 40.0, -10.0, 20.0],
        name="Synthetic angular profile",
        source="example-only synthetic values",
    )

    for model in (SphericalLunarLimbModel(), dem, angular):
        prediction = predict_lunar_limb(model, query)
        print(
            f"{prediction.model_type:>14}: "
            f"{prediction.altitude_m:+8.2f} m, "
            f"uncertainty={prediction.uncertainty_m}, source={prediction.source}"
        )

    print("\nFor a real calculation, pass the selected provider as limb_model=... ")
    print("to EclipseEngine.calculate_local() or the city/country contact search.")


if __name__ == "__main__":
    main()
