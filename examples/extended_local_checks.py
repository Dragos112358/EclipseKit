"""Extended EclipseKit local and catalogue regression checks.

Run from the project root:
    python .\\examples\\extended_local_checks.py
    python .\\examples\\extended_local_checks.py --with-limb

This is a robustness/sanity suite, not an independent high-precision
astronomical reference test. The latter is provided by eclipsekit.validation.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from eclipsekit import CityCatalog, EclipseEngine, LunarLimbCorrector, Observer


LOCAL_CASES = [
    # The reference classification is based on published visibility tables.
    ("León / 2026 total", "2026-08-12", Observer(42.6000, -5.5703, 844, "León", "Spain"), "total"),
    ("Reykjavík / 2026 total", "2026-08-12", Observer(64.1466, -21.9426, 0, "Reykjavík", "Iceland"), "total"),
    ("Bucharest / 2026 partial", "2026-08-12", Observer(44.4268, 26.1025, 80, "Bucharest", "Romania"), "partial"),
    ("Dallas / 2024 total", "2024-04-08", Observer(32.7831, -96.8067, 128, "Dallas", "USA"), "total"),
    ("Albuquerque / 2023 annular", "2023-10-14", Observer(35.0845, -106.6511, 1511, "Albuquerque", "USA"), "annular"),
    # Negative control: the 2026 August eclipse is confined to the Northern Hemisphere.
    ("Sydney / 2026 no eclipse", "2026-08-12", Observer(-33.8688, 151.2093, 58, "Sydney", "Australia"), None),
]


def check_local_cases(engine: EclipseEngine) -> tuple[int, int]:
    passed = failed = 0
    print("\n=== Local eclipse classification and contact sanity ===")
    for name, when, observer, expected_type in LOCAL_CASES:
        try:
            result = engine.calculate_local(
                observer,
                when,
                find_next_if_none=False,
                include_sunrise_sunset=False,
                include_shadow_metrics=False,
                include_planets=False,
            )
            if expected_type is None:
                if result is None:
                    print(f"[PASS] {name}: no local eclipse returned")
                    passed += 1
                else:
                    print(f"[FAIL] {name}: unexpected {result.eclipse_type} eclipse")
                    failed += 1
                continue

            if result is None:
                print(f"[FAIL] {name}: expected {expected_type}, got no event")
                failed += 1
                continue

            reasons: list[str] = []
            if result.eclipse_type != expected_type:
                reasons.append(f"type={result.eclipse_type}, expected={expected_type}")
            if not math.isfinite(result.magnitude) or result.magnitude <= 0:
                reasons.append(f"invalid magnitude={result.magnitude}")
            if not math.isfinite(result.obscuration_percent) or not 0 <= result.obscuration_percent <= 100:
                reasons.append(f"invalid obscuration={result.obscuration_percent}")

            contacts = result.contacts.as_dict()
            if contacts["C1"] is None or contacts["C4"] is None:
                reasons.append("missing external contact C1/C4")
            else:
                c1, c4 = float(contacts["C1"].tt), float(contacts["C4"].tt)
                maximum = float(result.maximum.tt)
                if not c1 <= maximum <= c4:
                    reasons.append("C1 <= maximum <= C4 chronology failed")

            is_central = expected_type in {"total", "annular"}
            if is_central:
                if contacts["C2"] is None or contacts["C3"] is None:
                    reasons.append("central event missing C2/C3")
                elif not (float(contacts["C1"].tt) <= float(contacts["C2"].tt)
                          <= float(contacts["C3"].tt) <= float(contacts["C4"].tt)):
                    reasons.append("C1 <= C2 <= C3 <= C4 chronology failed")
                if result.duration_seconds is None or result.duration_seconds <= 0:
                    reasons.append("central duration is not positive")
            else:
                if contacts["C2"] is not None or contacts["C3"] is not None:
                    reasons.append("partial eclipse unexpectedly has C2/C3")

            if reasons:
                print(f"[FAIL] {name}: " + "; ".join(reasons))
                failed += 1
            else:
                print(
                    f"[PASS] {name}: type={result.eclipse_type}, "
                    f"magnitude={result.magnitude:.5f}, "
                    f"obscuration={result.obscuration_percent:.2f}%, "
                    f"duration={result.duration_seconds} s"
                )
                passed += 1
        except Exception as exc:  # report a failed case but continue the suite
            print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
            failed += 1
    return passed, failed


def check_catalogue_batch_stability(engine: EclipseEngine, catalog_path: Path) -> tuple[int, int]:
    print("\n=== Catalogue batch-size reproducibility (Spain, 2026-08-12) ===")
    if not catalog_path.is_file():
        print(f"[SKIP] Catalogue not found: {catalog_path}")
        return 0, 0
    try:
        catalog = CityCatalog.from_csv(catalog_path)
        small = engine.search_cities(
            "2026-08-12", catalog, country="Spain", min_magnitude=0.001,
            batch_size=16, include_contacts=False,
        )
        large = engine.search_cities(
            "2026-08-12", catalog, country="Spain", min_magnitude=0.001,
            batch_size=512, include_contacts=False,
        )
        a = {(hit.city.country, hit.city.name): hit for hit in small}
        b = {(hit.city.country, hit.city.name): hit for hit in large}
        if a.keys() != b.keys():
            print(f"[FAIL] Result sets differ: batch16={len(a)}, batch512={len(b)}")
            return 0, 1
        max_delta = max((abs(a[key].magnitude - b[key].magnitude) for key in a), default=0.0)
        if max_delta > 1e-7:
            print(f"[FAIL] Magnitudes differ by up to {max_delta:.3e}")
            return 0, 1
        print(f"[PASS] {len(a)} matching city hits; max magnitude delta={max_delta:.3e}")
        return 1, 0
    except Exception as exc:
        print(f"[FAIL] Catalogue batch comparison: {type(exc).__name__}: {exc}")
        return 0, 1


def check_limb_subset(engine: EclipseEngine, catalog_path: Path, checkpoint: Path) -> tuple[int, int]:
    print("\n=== Optional lunar-limb correction on three Spanish localities ===")
    if not catalog_path.is_file():
        print(f"[SKIP] Catalogue not found: {catalog_path}")
        return 0, 0
    if not checkpoint.is_file():
        print(f"[SKIP] Lunar checkpoint not found: {checkpoint}")
        return 0, 0
    try:
        all_cities = CityCatalog.from_csv(catalog_path)
        wanted = {"León", "Burgos", "Valladolid"}
        selected = [c for c in all_cities.cities if c.country == "Spain" and c.name in wanted]
        found = {c.name for c in selected}
        if found != wanted:
            print(f"[FAIL] Required sample cities missing from catalogue: {sorted(wanted - found)}")
            return 0, 1
        subset = CityCatalog(selected)
        limb = LunarLimbCorrector.from_checkpoint(checkpoint, device="cpu")
        hits = engine.search_cities(
            "2026-08-12", subset, min_magnitude=0.001, batch_size=8,
            include_contacts=True, limb_corrector=limb,
        )
        by_name = {hit.city.name: hit for hit in hits}
        failed = 0
        for city_name in sorted(wanted):
            hit = by_name.get(city_name)
            if hit is None:
                print(f"[FAIL] {city_name}: no eclipse hit")
                failed += 1
                continue
            expected = {"C1", "C2", "C3", "C4"}
            actual = {
                key for key, value in hit.limb_corrected_contacts.items()
                if value.time is not None
            }
            if actual != expected:
                print(f"[FAIL] {city_name}: corrected contacts={sorted(actual)}")
                failed += 1
            else:
                print(f"[PASS] {city_name}: all four lunar-limb contacts found")
        return len(wanted) - failed, failed
    except Exception as exc:
        print(f"[FAIL] Lunar-limb subset: {type(exc).__name__}: {exc}")
        return 0, 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Extended EclipseKit robustness checks")
    parser.add_argument("--kernel", default="de440s")
    parser.add_argument("--catalog", default="data/CountryPoints.csv")
    parser.add_argument("--checkpoint", default="models/lunar_altitude_contact_bands_fp16_finetuned.pt")
    parser.add_argument("--with-limb", action="store_true", help="also test corrected contacts in León, Burgos and Valladolid")
    args = parser.parse_args()

    engine = EclipseEngine.from_jpl(args.kernel)
    total_passed = total_failed = 0
    p, f = check_local_cases(engine)
    total_passed += p
    total_failed += f
    p, f = check_catalogue_batch_stability(engine, Path(args.catalog))
    total_passed += p
    total_failed += f
    if args.with_limb:
        p, f = check_limb_subset(engine, Path(args.catalog), Path(args.checkpoint))
        total_passed += p
        total_failed += f

    print("\n=== Summary ===")
    print(f"Passed: {total_passed}")
    print(f"Failed: {total_failed}")
    if total_failed:
        print("Investigate every [FAIL] before relying on the affected feature.")
        return 1
    print("All executed extended checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
