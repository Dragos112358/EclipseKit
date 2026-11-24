"""Country scan with per-city contacts corrected by the supplied lunar model."""
from pathlib import Path

from eclipsekit import CityCatalog, EclipseEngine, LunarLimbCorrector

ROOT = Path(__file__).resolve().parents[1]

engine = EclipseEngine("de440s")
catalog = CityCatalog.from_csv(ROOT / "data" / "CountryPoints.csv")
limb = LunarLimbCorrector.from_checkpoint(
    ROOT / "models" / "lunar_altitude_contact_bands_fp16_finetuned.pt"
)

events = engine.find_solar_eclipses_by_country(
    "2026-01-01",
    "2027-01-01",
    catalog,
    country="Romania",
    include_contacts=True,
    limb_corrector=limb,
)

for event in events:
    print(event.country, event.geocentric_maximum)
    for hit in event.city_hits:
        print(hit.city.name, hit.eclipse_type, hit.magnitude)
        print("Geometric contacts:", hit.contacts.as_dict() if hit.contacts else None)
        print("Limb corrections:", {
            name: value.delta_seconds
            for name, value in hit.limb_corrected_contacts.items()
        })
