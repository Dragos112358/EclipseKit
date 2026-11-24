"""Validate the real city catalogue and optional user lunar-limb checkpoint."""
from pathlib import Path

from eclipsekit import CityCatalog

ROOT = Path(__file__).resolve().parents[1]
CITY_FILE = ROOT / "data" / "CountryPoints.csv"
CHECKPOINT = ROOT / "models" / "lunar_altitude_contact_bands_fp16_finetuned.pt"


def main() -> None:
    catalog = CityCatalog.from_csv(CITY_FILE)
    print(f"Cities loaded: {len(catalog.cities):,}")
    print(f"Country/territory labels: {len(catalog.countries):,}")
    for country in ("Romania", "Spain", "United States"):
        try:
            indices = catalog.indices_for_country(country)
            print(f"{country}: {len(indices):,} catalogued locations")
        except ValueError as exc:
            print(exc)

    if not CHECKPOINT.is_file():
        print("Lunar checkpoint not found; copy it into models/ to test it.")
        return

    from eclipsekit import LunarLimbCorrector
    corrector = LunarLimbCorrector.from_checkpoint(CHECKPOINT)
    print(f"Lunar model validation RMSE metadata: {corrector.metadata.best_val_rmse_m} m")
    for lat, lon in ((0.0, 0.0), (45.0, 0.0), (-45.0, -90.0)):
        altitude = corrector.predict_altitude_m(lat, lon)
        print(f"Predicted limb terrain at ({lat:+.1f}, {lon:+.1f}): {altitude:+.2f} m")


if __name__ == "__main__":
    main()
