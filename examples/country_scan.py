from pathlib import Path

from eclipsekit import CityCatalog, EclipseEngine

ROOT = Path(__file__).resolve().parents[1]

engine = EclipseEngine("de440s")
catalog = CityCatalog.from_csv(ROOT / "data" / "CountryPoints.csv")

hits = engine.search_cities("2026-08-12", catalog, country="Romania")
for hit in hits:
    print(
        hit.city.name,
        hit.eclipse_type,
        f"magnitude={hit.magnitude:.4f}",
        f"obscuration={hit.obscuration_percent:.2f}%",
        hit.maximum,
    )
