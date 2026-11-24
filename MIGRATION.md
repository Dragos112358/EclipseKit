# Extraction map from the supplied simulator source

| Original function/class | New location | New public entry point / note |
|---|---|---|
| `LunarAltitudeNet`, `_Encoding`, `load` | `src/pyeclipse/limb.py` | `LunarLimbCorrector.from_checkpoint()`; checkpoint stays external |
| `uses_custom_deltat`, `delta_t_seconds`, `build_tt_time`, `jd_ut_to_hms`, `format_event_time`, `get_skyfield_time` | `src/pyeclipse/timeutils.py` | `time_from_calendar()`, `coerce_time()`, `time_to_utc_iso()` |
| Skyfield global initialization / `Loader` | `src/pyeclipse/ephemeris.py` | `EphemerisContext`; selected kernel and timescale are instance-scoped |
| `get_radius_degrees`, `get_separation_geometric`, `calculate_p_angle` | `geometry.py`, `engine.py` | reusable angular helpers and engine-internal observer geometry |
| `contact_check_custom`, `solve_bisection_custom` | `contacts.py`, `engine.py` | `bisect_root()`, `EclipseEngine.solve_contact()` |
| `find_next_eclipse` | `engine.py` | `find_next_local_eclipse()` |
| `find_shadow_center`, `get_live_shadow_center_wgs84`, `update_global_eclipse_path`, `calculate_path_for_udp` | `geometry.py`, `engine.py` | `_shadow_state()`, `global_shadow_path()`, `global_path_for_eclipse()`; no UDP payload |
| `calculate_path_width`, `calculate_accurate_umbral_velocity`, `calculate_umbral_depth`, `calculate_xavier_angular` | `engine.py` | `_shadow_kinematics()`, `_shadow_metrics()` |
| `get_visible_planets_during_totality`, `get_sun_constellation` | `engine.py` | `_visible_planets()`, `_approximate_zodiac_sector()` |
| `generate_report_table` | `engine.py`, `models.py` | `calculate_local()` returns `LocalEclipseResult`; `format_report()` renders text on request |
| `init_cities_cache` | `cities.py` | `CityCatalog.from_csv()`; no global mutable arrays; local catalogue path is user-supplied and excluded from the public starter archive until its licence is documented |
| `solve_cities_for_eclipse` | `engine.py` | vectorized/batched `search_cities()`; optional exact contacts and limb-corrected contacts |
| (country/event iteration around new moons) | `engine.py` | `find_solar_eclipses_by_country()` |
| `solve_cities_for_lunar_eclipse` | `engine.py` | `lunar_eclipse_city_visibility()`; explicitly approximate |
| `compute_moon_libration_and_axis`, `contact_selenographic_point` | `limb.py` | preserved reusable lunar orientation/coordinate methods |
| `calculate_limb_corrected_contact`, `print_contact_coordinates_with_limb_correction` | `engine.py`, `limb.py` | optional `limb_corrector=` argument and structured `limb_corrected_contacts` |

## Intentionally removed from the scientific package

- `background_calculate()` and all cached HUD/report state.
- UDP socket setup, request listeners, binary packet layout, and main `while True` loop.
- Unreal Engine-specific output packing and simulation-rate throttling.
- Reverse geocoding with Nominatim/geopy. A city/country catalogue is supplied explicitly instead.
- Automatic downloads of the Jupiter/Saturn/Neptune satellite SPKs used only to animate the simulator.
- Import-time checkpoint loading, ephemeris downloads, CSV loading, socket binds, and thread creation.

These are application/integration concerns, not reusable eclipse calculations.


## Supplied assets checked during this integration

- The developer's local `data/CountryPoints.csv` was checked during integration:
  8,133 valid records across 245 country/territory labels; the parser handles
  the real header and UTF-8 names. The data file is not redistributed in this
  public starter bundle until its licence and provenance are documented.
- `models/lunar_altitude_contact_bands_fp16_finetuned.pt`: checkpoint loads with
  `weights_only=True` against the ported model architecture. It is deliberately
  kept outside the source wheel and must be copied locally by the developer.
- `reference/legacy_server_source.txt`: preserved copy of the full 3,167-line
  server source for traceability; do not execute it as a library module.

The installed PyEclipse package does not include either data asset.
