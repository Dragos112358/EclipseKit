"""Exercise the Besselian backend through EclipseEngine and its time scales."""

from pathlib import Path

from eclipsekit import BesselianElements, EclipseEngine, Observer


ROOT = Path(__file__).resolve().parents[1]
ELEMENTS_PATH = ROOT / "data" / "validation" / "besselian_1999_aug11_nasa.json"


def main() -> None:
    elements = BesselianElements.from_json(ELEMENTS_PATH)
    engine = EclipseEngine.from_jpl("de440s")
    observer = Observer(
        45.075, 24.30, name="Greatest-eclipse region", country="Romania"
    )

    local = engine.calculate_local_besselian(elements, observer)
    print(f"Local classification: {local.eclipse_type}")
    if local.maximum_jd_tt is not None:
        maximum = engine.ts.tt_jd(local.maximum_jd_tt)
        print(f"Local maximum (engine time scale): {maximum.utc_iso()}")
    for name in ("C1", "C2", "C3", "C4"):
        contact = local.contacts.get(name)
        if contact is not None:
            moment = engine.ts.tt_jd(contact.jd_tt)
            print(f"{name}: {moment.utc_iso()} ({contact.root_result.status})")

    global_maximum = engine.find_global_maximum_besselian(elements)
    print(f"Geocentric maximum: {global_maximum.utc_iso()}")

    start = elements.epoch_tt_jd - 1.0 / 24.0
    end = elements.epoch_tt_jd + 1.0 / 24.0
    path = engine.besselian_global_shadow_path(elements, start, end, samples=31)
    print(f"Central-line ground-track points: {len(path)}")
    if path:
        first, last = path[0], path[-1]
        print(
            f"Track extent: {first.latitude:.3f}°, {first.longitude:.3f}° -> "
            f"{last.latitude:.3f}°, {last.longitude:.3f}°"
        )
    print("ΔT source: engine-configured TT/UT1 time scales")


if __name__ == "__main__":
    main()
