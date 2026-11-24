"""Engine-level Phase 5 smoke test using an explicitly synthetic global DEM.

This example verifies the new ``limb_model=`` plumbing and metadata path. The
height grid is synthetic and must never be used as scientific lunar terrain.
It uses the same local DE440s kernel/cache as the other engine examples.
"""

from __future__ import annotations

import numpy as np

from eclipsekit import EclipseEngine, GriddedLunarLimbModel, Observer


def main() -> None:
    latitudes = np.linspace(-90.0, 90.0, 19)
    longitudes = np.arange(-180.0, 180.0, 30.0)
    lat_grid = np.radians(latitudes[:, None])
    lon_grid = np.radians(longitudes[None, :])
    synthetic_heights = 120.0 * np.cos(lat_grid) * np.sin(lon_grid)
    synthetic_uncertainty = np.full_like(synthetic_heights, 25.0)

    model = GriddedLunarLimbModel(
        latitudes,
        longitudes,
        synthetic_heights,
        uncertainties_m=synthetic_uncertainty,
        periodic_longitude=True,
        name="Synthetic global DEM smoke fixture",
        source="synthetic example values; not lunar terrain",
        vertical_datum="synthetic radial reference",
    )

    engine = EclipseEngine.from_jpl("de440s")
    observer = Observer(
        42.6, -5.5703, elevation_m=800.0, name="León", country="Spain"
    )
    result = engine.calculate_local(
        observer,
        "2026-08-12T18:00:00Z",
        search_window_hours=4.0,
        limb_model=model,
        include_sunrise_sunset=False,
        include_shadow_metrics=False,
        include_planets=False,
    )
    if result is None:
        raise RuntimeError("No local eclipse found for the engine integration smoke case")

    print("Eclipse type:", result.eclipse_type)
    for name in ("C1", "C2", "C3", "C4"):
        contact = result.limb_corrected_contacts.get(name)
        if contact is None:
            print(f"{name}: no corrected result")
            continue
        delta_text = (
            f"{contact.delta_seconds:+.4f} s"
            if contact.delta_seconds is not None else "not solved"
        )
        print(
            f"{name}: delta={delta_text}, "
            f"terrain={contact.predicted_terrain_altitude_m:+.2f} m, "
            f"sigma={contact.altitude_uncertainty_m}, "
            f"model={contact.model_name}, source={contact.model_source}"
        )

    serialized = result.to_dict()
    c1_event = serialized.get("contact_events", {}).get("C1", {})
    c1_limb = c1_event.get("limb_correction")
    print("Serialized C1 limb metadata fields:", sorted(c1_limb) if c1_limb else None)
    print("NOTE: synthetic model only; results are not astronomical predictions.")


if __name__ == "__main__":
    main()
