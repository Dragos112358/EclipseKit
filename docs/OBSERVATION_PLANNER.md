# Eclipse Observation Planner (Phase 7.4)

## Purpose

`EclipseEngine.plan_observations()` compares a caller-supplied set of ground
observers for one target solar-eclipse epoch. It calculates local circumstances
for each site, separates sites with no eclipse from calculation failures, and
ranks only sites that satisfy the configured minimum apparent solar altitude.

The planner is deliberately weather-agnostic. Its score is a transparent
comparison heuristic, **not** a probability of clear skies, image quality, or
successful observation.

## Quick start

```python
from eclipsekit import (
    EclipseEngine,
    Observer,
    ObservationScoreWeights,
    write_observation_plan_csv,
    write_observation_plan_json,
)

engine = EclipseEngine.from_jpl("de440s")
sites = [
    Observer(42.6000, -5.5703, 837, name="León", country="Spain"),
    Observer(42.3439, -3.6969, 859, name="Burgos", country="Spain"),
    Observer(43.5322, -5.6611, 3, name="Gijón", country="Spain"),
]

plan = engine.plan_observations(
    sites,
    "2026-08-12T17:45:59Z",
    search_window_hours=8,
    weights=ObservationScoreWeights(0.50, 0.30, 0.20),
    minimum_sun_altitude_deg=5,
)

print(plan.to_markdown())
write_observation_plan_csv(plan, "reports/observation-plan.csv")
write_observation_plan_json(plan, "reports/observation-plan.json")
```

`search_window_hours` is the half-width of the local search around `when`;
`calculate_local()` evaluates a window extending that many hours before and
after the supplied epoch. The planner passes `find_next_if_none=False`, so a
site without an eclipse in this window is reported as `no_eclipse` rather than
being silently matched to a later eclipse.

Run the reproducible multi-site example from the project root:

```powershell
python .\examples\observation_planner.py
```

It writes `reports/phase7_4/observation-plan.csv`,
`reports/phase7_4/observation-plan.json`, and
`reports/phase7_4/observation-plan.md`. The sample date is historical and used
for reproducibility; replace it and the candidate observers for a future event.

## Public API

### `EclipseEngine.plan_observations(observers, when, ...)`

`observers` must be a non-empty iterable of `Observer` instances. `when` accepts
the normal `EclipseEngine.time()` input types. Options:

| Option | Default | Meaning |
|---|---:|---|
| `search_window_hours` | `12.0` | Half-width around the requested epoch, constrained to `(0, 36]` hours |
| `weights` | `ObservationScoreWeights()` | Relative score weights |
| `minimum_sun_altitude_deg` | `0.0` | Minimum apparent Sun altitude for inclusion in the ranked recommendations |
| `full_sun_altitude_score_deg` | `45.0` | Sun altitude at which the altitude score reaches 100 |
| `maximum_partial_duration_seconds` | `3600.0` | C1–C4 event span at which the duration score reaches 100 |
| `limb_model` | `None` | Optional Phase 5 lunar-limb provider passed to local calculations |
| `continue_on_error` | `True` | Record per-site exceptions as `calculation_error`; set `False` to re-raise |

The planner disables sunrise/sunset and planet calculations for each site to
avoid unrelated work during site ranking. Local C1–C4 circumstances and local
maximum remain part of the result.

### Score model

The defaults are:

- obscuration: 0.50;
- solar altitude: 0.30;
- C1–C4 partial-event span: 0.20.

Weights are normalized to sum to 1. Each component is scaled to 0–100:

- **Obscuration:** modelled obscuration percentage, already in 0–100.
- **Solar altitude:** `clip(max(apparent_altitude, 0) / full_sun_altitude_score_deg × 100, 0, 100)`.
- **Duration:** `clip((C4 − C1) / maximum_partial_duration_seconds × 100, 0, 100)`.

The final score is the sum of each component multiplied by its normalized
weight. It is not a physical quantity. Defaults are policy choices, not
universal observing priorities; callers may set weights appropriate to their
use case. A long partial phase is not necessarily preferable when totality,
weather, or other operational requirements dominate.

### Site statuses

| Status | Meaning |
|---|---|
| `recommended` | Local eclipse found and Sun altitude meets the minimum; receives a rank |
| `below_minimum_sun_altitude` | Local eclipse found but maximum occurs below the configured altitude threshold; retained for diagnostics but not ranked |
| `no_eclipse` | No local eclipse found in the requested search window |
| `calculation_error` | Local calculation or result validation failed; exception type/message is retained |

Recommended sites sort by descending total score, then obscuration, then Sun
altitude, and finally site label for deterministic tie-breaking. Site visibility
classes (`below_horizon`, `very_low`, `low`, `good`, `high`) are descriptive
altitude bands and are not a horizon/terrain model.

## Output formats

- `ObservationPlan.to_dict()` provides JSON-friendly plan, weight, count,
  component-score, and local-result data.
- `ObservationPlan.to_markdown()` provides a readable ranked table and the
  score-model limitations.
- `write_observation_plan_csv()` writes one row per candidate, including status,
  rank, coordinates, component scores, eclipse type, maximum, obscuration,
  altitude, C1–C4 times, and event-duration fields.
- `write_observation_plan_json()` writes the complete `to_dict()` structure as
  UTF-8 JSON and rejects non-finite JSON values.

## Important limitations

The planner does **not** currently model or ingest:

- cloud cover, precipitation, wind, transparency, seeing, or forecast confidence;
- observer-specific terrain, buildings, skyline, or horizon profile;
- light pollution, access permissions, safety, travel time, fuel, lodging, or cost;
- telescope/camera setup, field of view, exposure constraints, or operator skill;
- uncertainty in the underlying eclipse prediction.

Solar altitude is evaluated at local eclipse maximum, not continuously over the
entire partial phase. The score therefore does not establish that the Sun is
above a site's real horizon at every contact. Use the returned local contact
times and altitude fields to perform further site-specific planning.

When `limb_model` is supplied, its corrections are passed through the existing
local calculation API; the planner does not independently certify that model.
The result is only as scientifically defensible as the ephemeris, time-scale,
contact model, and any optional lunar-limb model supplied to `EclipseEngine`.
