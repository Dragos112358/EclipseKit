"""Export a country/city scan and global shadow path as GeoJSON and CSV."""

from pathlib import Path

from eclipsekit import CityCatalog, EclipseEngine
from eclipsekit.exports import (
    city_hits_to_geojson,
    shadow_path_to_geojson,
    write_city_hits_csv,
    write_geojson,
)


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data" / "CountryPoints.csv"
OUTPUT_DIR = ROOT / "results"
EVENT_DATE = "2026-08-12"
COUNTRY = "Spain"


def main() -> None:
    if not CATALOG_PATH.is_file():
        raise FileNotFoundError(
            f"City catalogue not found at {CATALOG_PATH}. Add CountryPoints.csv "
            "or edit CATALOG_PATH to point to your own catalogue."
        )

    catalog = CityCatalog.from_csv(CATALOG_PATH)
    engine = EclipseEngine("de440s")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    hits = engine.search_cities(
        EVENT_DATE,
        catalog,
        country=COUNTRY,
        min_magnitude=0.001,
        include_contacts=True,
    )
    write_geojson(city_hits_to_geojson(hits), OUTPUT_DIR / "spain-city-hits.geojson")
    write_city_hits_csv(hits, OUTPUT_DIR / "spain-city-hits.csv")

    path = engine.global_path_for_eclipse(EVENT_DATE, search_radius_hours=4.0, samples=301)
    if len(path) >= 2:
        write_geojson(shadow_path_to_geojson(path), OUTPUT_DIR / "global-shadow-path.geojson")
    else:
        print(f"Not enough shadow-path points to export a line: {len(path)}")

    print(f"Exported {len(hits)} city hits to {OUTPUT_DIR}")
    print(f"Exported {len(path)} global shadow-path points")


if __name__ == "__main__":
    main()
