"""EclipseKit 0.1.0-alpha: end-to-end public API smoke test.

Run from the project root:
    python examples/full_api_check.py

Optional slow country-wide limb scan:
    python examples/full_api_check.py --slow-country-limb

This is an integration/smoke test, not an independent scientific validation.
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import traceback

from eclipsekit import (
    CityCatalog,
    EclipseEngine,
    LunarLimbCorrector,
    Observer,
    delta_t_seconds,
    time_to_utc_iso,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "CountryPoints.csv"
CHECKPOINT = ROOT / "models" / "lunar_altitude_contact_bands_fp16_finetuned.pt"
SOLAR_DATE = "2026-08-12"
LUNAR_MAXIMUM_UTC = "2026-03-03T11:34:00Z"  # NASA GSFC catalogue maximum, rounded to minute


def section(title: str) -> None:
    print("\n" + "=" * 76)
    print(title)
    print("=" * 76)


def report(name: str, fn):
    try:
        value = fn()
        print(f"[OK] {name}")
        return value
    except Exception as exc:
        print(f"[ERROR] {name}: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--slow-country-limb", action="store_true",
        help="Also calculate local contacts + lunar-limb corrections for Spain city hits.",
    )
    args = parser.parse_args()

    section("1. Files and catalogue")
    if not DATA.is_file():
        print(f"[FATAL] CSV not found: {DATA}")
        return 2
    if not CHECKPOINT.is_file():
        print(f"[WARN] Lunar checkpoint not found: {CHECKPOINT}; limb tests will be skipped.")

    catalog = report("CityCatalog.from_csv", lambda: CityCatalog.from_csv(DATA))
    if catalog is None:
        return 2
    print(f"Catalogue rows: {len(catalog.cities):,}")
    print(f"Countries/territories: {len(catalog.countries):,}")
    print(f"Romania rows: {len(catalog.indices_for_country('Romania'))}")
    print(f"Spain rows: {len(catalog.indices_for_country('Spain'))}")

    section("2. Ephemeris and time API")
    engine = report("EclipseEngine.from_jpl('de440s')", lambda: EclipseEngine.from_jpl("de440s"))
    if engine is None:
        print("[FATAL] Engine could not be initialized. Check internet/kernel cache and the traceback.")
        return 2

    t1 = report("engine.time(ISO-8601)", lambda: engine.time("2026-08-12T16:00:00Z"))
    t2 = report("engine.time_from_calendar", lambda: engine.time_from_calendar(2026, 8, 12, 16, 0, 0))
    if t1 is not None:
        print("ISO time:", time_to_utc_iso(t1))
    if t2 is not None:
        print("Calendar time:", time_to_utc_iso(t2))
    print("Delta-T 2026 (s):", delta_t_seconds(2026, 8))

    local_kernel = Path.home() / ".eclipsekit" / "ephemerides" / "de440s.bsp"
    if local_kernel.is_file():
        report("EclipseEngine from local BSP path", lambda: EclipseEngine(local_kernel))
    else:
        print(f"[SKIP] Local BSP-path test: not found at {local_kernel}")

    # Re-use a city in the catalog that the previous global scan classified as total.
    city = next(
        (c for c in catalog.cities if c.country == "Spain" and c.name in {"León", "Leon"}),
        None,
    )
    if city is None:
        city = next((c for c in catalog.cities if c.country == "Spain"), None)
    if city is None:
        print("[FATAL] No Spanish city exists in the supplied catalogue.")
        return 2

    observer = Observer(
        city.latitude, city.longitude, city.elevation_m,
        name=city.name, country=city.country,
    )
    print(f"Observer: {observer.name}, {observer.country} "
          f"({observer.latitude:.5f}, {observer.longitude:.5f})")

    section("3. Local eclipse calculation, report and result serialization")
    local = report(
        "engine.calculate_local",
        lambda: engine.calculate_local(
            observer, SOLAR_DATE,
            find_next_if_none=False,
            include_sunrise_sunset=True,
            include_shadow_metrics=True,
            include_planets=True,
        ),
    )
    if local is not None:
        print(engine.format_report(local, language="en"))
        print("Romanian report:\n", engine.format_report(local, language="ro"))
        print("Result dictionary keys:", sorted(local.to_dict().keys()))
        print("Contacts UTC:", {
            name: time_to_utc_iso(value) if value is not None else None
            for name, value in local.contacts.as_dict().items()
        })
        print("Warnings:", local.warnings)
    else:
        print("[WARN] No local eclipse result for this observer/date.")

    section("4. Contact solver and next-local-eclipse search")
    if local is not None and local.contacts.c1 is not None:
        left = engine.ts.tt_jd(local.contacts.c1.tt - 60.0 / 86400.0)
        solved_c1 = report(
            "engine.solve_contact external (C1 bracket)",
            lambda: engine.solve_contact(observer, "external", left, local.maximum),
        )
        if solved_c1 is not None:
            print("Solved C1:", time_to_utc_iso(solved_c1))
    else:
        print("[SKIP] C1 unavailable; cannot bracket an external contact.")

    if local is not None and local.eclipse_type in {"total", "annular"} and local.contacts.c1 is not None:
        solved_c2 = report(
            "engine.solve_contact internal (C2 bracket)",
            lambda: engine.solve_contact(observer, "internal", local.contacts.c1, local.maximum),
        )
        if solved_c2 is not None:
            print("Solved C2:", time_to_utc_iso(solved_c2))
    else:
        print("[SKIP] No central phase/C1 for an internal-contact test.")

    next_eclipse = report(
        "engine.find_next_local_eclipse",
        lambda: engine.find_next_local_eclipse(observer, "2026-01-01", search_days=550),
    )
    if next_eclipse is not None:
        print("Next local maximum:", time_to_utc_iso(next_eclipse))
    else:
        print("[WARN] No next local eclipse returned in 550 days.")

    section("5. Global maximum and shadow path diagnostics")
    global_max = report(
        "engine.find_global_maximum",
        lambda: engine.find_global_maximum(SOLAR_DATE, half_window_hours=12.0),
    )
    if global_max is not None:
        print("Geocentric maximum:", time_to_utc_iso(global_max))
        # Private methods are used here only to diagnose the path function returning zero points.
        is_global = report(
            "diagnostic: _is_global_solar_eclipse",
            lambda: engine._is_global_solar_eclipse(global_max),
        )
        state = report(
            "diagnostic: _shadow_state at maximum",
            lambda: engine._shadow_state(global_max),
        )
        print("Global-eclipse candidate (shadow hit or geocentric overlap):", is_global)
        if state is None:
            print("[WARN] Shadow axis did not intersect WGS84 at the computed maximum.")
        else:
            print("Shadow-axis impact:",
                  f"lat={state['latitude']:.5f}",
                  f"lon={state['longitude']:.5f}",
                  f"cone_radius_km={state['cone_radius_km']:.3f}",
                  f"kind={state['shadow_kind']}")

        start = engine.ts.tt_jd(global_max.tt - 4.0 / 24.0)
        end = engine.ts.tt_jd(global_max.tt + 4.0 / 24.0)
        path_direct = report(
            "engine.global_shadow_path",
            lambda: engine.global_shadow_path(start, end, samples=301),
        )
        path_wrapped = report(
            "engine.global_path_for_eclipse",
            lambda: engine.global_path_for_eclipse(SOLAR_DATE, search_radius_hours=4.0, samples=301),
        )
        print("Direct global path points:", len(path_direct) if path_direct is not None else "ERROR")
        print("Convenience global path points:", len(path_wrapped) if path_wrapped is not None else "ERROR")
        if not path_direct and is_global:
            print("[FOLLOW-UP REQUIRED] A global solar eclipse is detected, but the WGS84 shadow path is empty.")

    section("6. Global city scan and country event search")
    hits = report(
        "engine.search_cities (all supplied localities)",
        lambda: engine.search_cities(
            SOLAR_DATE, catalog, country=None, min_magnitude=0.001,
            search_radius_hours=4.0, coarse_steps=49, batch_size=512,
            include_contacts=False,
        ),
    )
    if hits is not None:
        print("Affected catalogue locations:", len(hits))
        print("Eclipse types:", dict(Counter(hit.eclipse_type for hit in hits)))
        print("Top 10:")
        for hit in hits[:10]:
            print(f"  {hit.city.country} / {hit.city.name}: {hit.eclipse_type}, "
                  f"mag={hit.magnitude:.5f}, obsc={hit.obscuration_percent:.2f}%")

    country_events = report(
        "engine.find_solar_eclipses_by_country (Spain, August 2026)",
        lambda: engine.find_solar_eclipses_by_country(
            "2026-08-01", "2026-09-01", catalog,
            country="Spain", min_magnitude=0.001,
            include_contacts=False,
        ),
    )
    if country_events is not None:
        print("Events returned:", len(country_events))
        for event in country_events:
            print(event.country, time_to_utc_iso(event.geocentric_maximum),
                  "city hits:", len(event.city_hits))
            print("First event dict keys:", sorted(event.to_dict().keys()))

    section("7. Lunar-eclipse city visibility (experimental approximation)")
    lunar_hits = report(
        "engine.lunar_eclipse_city_visibility (2026-03-03 total lunar eclipse)",
        lambda: engine.lunar_eclipse_city_visibility(
            LUNAR_MAXIMUM_UTC, catalog, country=None,
        ),
    )
    if lunar_hits is not None:
        print("Locations with Moon above the horizon threshold:", len(lunar_hits))
        print("Sample:", lunar_hits[:3])
        print("NOTE: this API is explicitly experimental; do not treat as a validated lunar-eclipse model.")

    section("8. Neural lunar-limb model and corrected contacts")
    limb = None
    if CHECKPOINT.is_file():
        limb = report(
            "LunarLimbCorrector.from_checkpoint",
            lambda: LunarLimbCorrector.from_checkpoint(CHECKPOINT),
        )
    else:
        print("[SKIP] Checkpoint missing.")

    if limb is not None:
        prediction = report(
            "limb.predict_altitude_m",
            lambda: limb.predict_altitude_m(0.0, 0.0),
        )
        print("Sample limb prediction at (0, 0):", prediction, "m")
        limb_local = report(
            "engine.calculate_local with limb_corrector",
            lambda: engine.calculate_local(
                observer, SOLAR_DATE, find_next_if_none=False,
                limb_corrector=limb,
                include_sunrise_sunset=False,
                include_shadow_metrics=False,
                include_planets=False,
            ),
        )
        if limb_local is not None:
            print("Limb-corrected contacts:")
            corrected_times = {}
            for name in ("C1", "C2", "C3", "C4"):
                correction = limb_local.limb_corrected_contacts.get(name)
                corrected_time = correction.time if correction is not None else None
                corrected_times[name] = corrected_time
                if correction is None:
                    print(f"  {name}: [MISSING] no correction object returned")
                    continue
                print(f"  {name}: delta={correction.delta_seconds} s; "
                      f"terrain={correction.predicted_terrain_altitude_m:.2f} m; "
                      f"corrected time={time_to_utc_iso(corrected_time) if corrected_time is not None else None}")

            print("Limb-corrected central-phase duration (s):",
                  limb_local.limb_corrected_duration_seconds)
            print("Limb-corrected maximum UTC:",
                  time_to_utc_iso(limb_local.limb_corrected_maximum)
                  if limb_local.limb_corrected_maximum is not None else None)

            if all(corrected_times[name] is not None for name in ("C1", "C2", "C3", "C4")):
                ordered = [corrected_times[name].tt for name in ("C1", "C2", "C3", "C4")]
                if ordered == sorted(ordered):
                    print("[OK] Limb-corrected contacts are chronologically ordered.")
                else:
                    print("[FOLLOW-UP REQUIRED] Limb-corrected contacts are not chronological.")

                calculated_duration = (ordered[2] - ordered[1]) * 86400.0
                reported_duration = limb_local.limb_corrected_duration_seconds
                if reported_duration is not None and abs(calculated_duration - reported_duration) < 0.01:
                    print("[OK] Corrected central duration matches C3-C2:",
                          f"{calculated_duration:.3f} s")
                else:
                    print("[FOLLOW-UP REQUIRED] Corrected duration does not match C3-C2:",
                          f"computed={calculated_duration:.3f} s; reported={reported_duration}")
            else:
                missing = [name for name, value in corrected_times.items() if value is None]
                print("[FOLLOW-UP REQUIRED] Missing limb-corrected contact times:",
                      ", ".join(missing))

            print("Limb warnings:", limb_local.warnings)

        if args.slow_country_limb:
            country_limb_events = report(
                "engine.find_solar_eclipses_by_country with contacts + limb model",
                lambda: engine.find_solar_eclipses_by_country(
                    "2026-08-01", "2026-09-01", catalog,
                    country="Spain", min_magnitude=0.001,
                    include_contacts=True, limb_corrector=limb,
                ),
            )
            if country_limb_events is not None:
                print("Country+limb events:", len(country_limb_events))
                for event in country_limb_events:
                    print(event.country, "city hits:", len(event.city_hits))
                    for hit in event.city_hits[:5]:
                        print(" ", hit.city.name, "contacts:",
                              hit.contacts.as_dict() if hit.contacts else None,
                              "limb shifts:", {
                                  k: v.delta_seconds
                                  for k, v in hit.limb_corrected_contacts.items()
                              })

    section("9. End of smoke test")
    print("The script has exercised the public API paths listed above.")
    print("A green smoke test is not the same as independent astronomical validation.")
    print("Investigate any [ERROR] or [FOLLOW-UP REQUIRED] lines before relying on the result.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
