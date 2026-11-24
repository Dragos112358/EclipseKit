# Contact Event Model (Phase 3)

Phase 3 adds a structured event record to local solar-eclipse results while
retaining the original `ContactTimes` API.

## Public API

`LocalEclipseResult.contact_events` is an insertion-ordered dictionary keyed
by event name. It can contain `C1`, `C2`, `MAXIMUM`, `C3`, and `C4` in
chronological order. A partial eclipse normally has `C1`, `MAXIMUM`, and `C4`;
internal contacts are present only when the calculation finds them.

Each value is a public `ContactEvent` with:

- `time`: the underlying Skyfield `Time` object;
- `time_utc`, `time_tt_jd`, and `time_ut1_jd`: separate display/reference
  representations of the same instant;
- `event_type`: `external`, `internal`, or `maximum`;
- `separation_deg`, the apparent topocentric Sun-Moon angular separation;
- apparent angular radii for the adopted contact geometry;
- `position_angle_deg`, measured from celestial north toward east;
- `vertex_angle_deg`, the signed position angle relative to the local vertical,
  wrapped to [-180, 180) degrees;
- apparent topocentric solar altitude/azimuth and a simple horizon status;
- `solver_result` for C1-C4, retaining RootResult status, method, residual,
  iterations, calls, and final bracket;
- optional `limb_correction` metadata when a lunar-limb correction was used;
- `uncertainty_seconds` and `uncertainty_note`.

The `MAXIMUM` event is the refined minimum-separation time. The current
minimum-refinement helper does not emit iteration diagnostics, so the maximum
record intentionally has no root-solver result. This avoids presenting a
minimum search as a contact root solve.

## Time-scale convention

UTC is provided as an ISO-8601 string for civil display. TT and UT1 are
provided as Julian Dates from the same Skyfield `Time` object. They are not
interchangeable: reference data labelled UT/UT1 should be compared against
`time_ut1_jd`, not against the UTC display string or TT Julian Date.

## Geometry and visibility convention

Contact position angle uses the existing topocentric position-angle utility.
Vertex angle is defined here as position angle minus the parallactic angle of
the local zenith, normalized to [-180, 180). Solar altitude and azimuth use
the configured atmospheric refraction settings. `visibility_status` only
classifies the apparent solar altitude (`above_horizon`, `at_horizon`, or
`below_horizon`). It does not account for mountains, buildings, trees, or a
custom local horizon profile.

## Uncertainty and interpretation

`uncertainty_seconds` is `None` by default. A small root residual or narrow
numerical bracket is not a physical prediction-uncertainty estimate. A
quantitative uncertainty value will be added only when there is an explicit,
validated uncertainty model for the ephemeris, Earth orientation, adopted
radii, and (where applicable) lunar limb profile.

## Backwards compatibility

- `LocalEclipseResult.contacts` and its `C1`/`C2`/`C3`/`C4` times are unchanged.
- `duration_seconds` keeps its historical behavior, including `0.0` for a
  partial-only event.
- `central_phase_duration_seconds` is the new unambiguous field and is `None`
  when there is no C2-C3 central phase.
- `to_dict()` retains the old keys and adds `contact_events` and
  `central_phase_duration_seconds`.

See `examples/contact_event_model.py` for a complete example.
