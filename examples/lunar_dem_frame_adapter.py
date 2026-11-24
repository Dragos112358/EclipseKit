"""Demonstrate lazy DE421 ME -> DE440 PA DEM querying.

Run only with a PDS3 DEM whose authoritative product documentation confirms
that it is registered in the DE421 mean-Earth/polar-axis frame.
"""

from eclipsekit import (
    LunarCoordinateTransform,
    LunarReferenceSphereTransform,
    TransformedLunarDEMModel,
    de421_me_to_de440_pa_transform,
    open_pds3_lunar_dem,
)


with open_pds3_lunar_dem(
    "data/SLDEM2015_128_60S_60N_000_360_FLOAT.IMG",
    "data/SLDEM2015_128_60S_60N_000_360_FLOAT.LBL",
    expected_coordinate_system="MEAN EARTH/POLAR AXIS OF DE421",
) as source_dem:
    transform = LunarCoordinateTransform(
        frame_transform=de421_me_to_de440_pa_transform(),
        vertical_transform=LunarReferenceSphereTransform(
            source_reference_radius_m=source_dem.product_info.reference_radius_m,
            target_reference_radius_m=1_737_400.0,
            source_vertical_datum=source_dem.metadata.vertical_datum,
            target_vertical_datum="radial height above the MOON_PA_DE440 1,737,400 m sphere",
        ),
    )
    with TransformedLunarDEMModel(
        source_dem,
        transform,
        source_coordinate_system_name=source_dem.product_info.coordinate_system_name,
    ) as target_dem:
        print("Target frame:", target_dem.product_info.coordinate_system_name)
        print("Target vertical datum:", target_dem.product_info.vertical_datum)
        print("Sample height (m):", target_dem.predict_altitude_m(12.0, -45.0))
        batch = target_dem.predict_many([10.0, 12.0, 14.0], [-42.0, -45.0, -48.0])
        print("Batch heights (m):", batch)
