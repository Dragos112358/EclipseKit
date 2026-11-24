"""Rank several Spanish observing sites for the 2026-08-12 solar eclipse.

This is a retrospective, reproducible example. It uses the same DE440s engine
as the rest of EclipseKit and writes JSON, CSV, and Markdown reports.
"""

from __future__ import annotations

from pathlib import Path

from eclipsekit import (
    EclipseEngine,
    Observer,
    ObservationScoreWeights,
    write_observation_plan_csv,
    write_observation_plan_json,
)


def main() -> int:
    engine = EclipseEngine.from_jpl("de440s")
    observers = [
        Observer(42.60000, -5.57030, 837.0, name="León", country="Spain"),
        Observer(42.34390, -3.69690, 859.0, name="Burgos", country="Spain"),
        Observer(43.53220, -5.66110, 3.0, name="Gijón", country="Spain"),
        Observer(39.56960, 2.65020, 13.0, name="Palma", country="Spain"),
        Observer(40.41680, -3.70380, 667.0, name="Madrid", country="Spain"),
    ]

    plan = engine.plan_observations(
        observers,
        "2026-08-12T17:45:59Z",
        search_window_hours=8.0,
        weights=ObservationScoreWeights(
            obscuration=0.50,
            solar_altitude=0.30,
            partial_duration=0.20,
        ),
        minimum_sun_altitude_deg=5.0,
        full_sun_altitude_score_deg=45.0,
        maximum_partial_duration_seconds=3600.0,
        continue_on_error=True,
    )

    report_dir = Path("reports/phase7_4")
    csv_path = write_observation_plan_csv(plan, report_dir / "observation-plan.csv")
    json_path = write_observation_plan_json(plan, report_dir / "observation-plan.json")
    report_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = report_dir / "observation-plan.md"
    markdown_path.write_text(plan.to_markdown(), encoding="utf-8")

    print(plan.to_markdown())
    print(f"CSV: {csv_path.resolve()}")
    print(f"JSON: {json_path.resolve()}")
    print(f"Markdown: {markdown_path.resolve()}")
    if plan.error_sites:
        print("One or more sites had calculation errors; inspect the report before use.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
