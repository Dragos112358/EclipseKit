# Lunar Limb Framework — Phase 5

Phase 5 introduces a provider-neutral interface for lunar-limb radial-height
models. The existing `LunarLimbCorrector` remains supported; new callers should
prefer the `limb_model=` argument and one of the Phase 5 model classes.

## Model types

### Spherical baseline

`SphericalLunarLimbModel` returns zero terrain height. It is useful for
controlled comparisons and API tests. It is not a topographic model and does
not change the adopted mean lunar radius.

### Selenographic gridded DEM

`GriddedLunarLimbModel` bilinearly interpolates a caller-supplied regular
latitude/longitude grid. It accepts a NumPy array at construction, CSV, or NPZ.
The grid uses selenographic latitude (north positive), east-positive longitude,
and radial altitude in metres relative to the data source's stated reference
surface. EclipseKit does not assume a vertical datum or relabel the input as
LOLA/Watts data.

CSV format:

```csv
latitude_deg,longitude_deg,altitude_m,uncertainty_m
-1.0,-1.0,12.0,5.0
-1.0, 1.0,18.0,5.0
 1.0,-1.0,27.0,5.0
 1.0, 1.0,31.0,5.0
```

`uncertainty_m` is optional, but when present it must be present and valid for
every sample. The output uncertainty is propagated through bilinear weights
assuming independent grid-node uncertainties. This is a stated interpolation
assumption, not a complete DEM error budget.

NPZ files must contain `latitudes_deg`, `longitudes_deg`, and `altitudes_m`;
`uncertainties_m` is optional. Loads use `allow_pickle=False`.

Longitude is non-periodic by default. Set `periodic_longitude=True` only for a
global grid whose longitude samples cover a full 360-degree cycle without a
duplicated seam column. Missing elevation cells are permitted in a source file,
but a query touching one of them raises `ValueError`. Queries outside latitude
or non-periodic longitude coverage also raise; the model does not silently
extrapolate.

### Tabulated apparent-limb profile

`TabulatedAngularLunarLimbProfile` (short alias
`AngularLunarLimbProfile`) interpolates radial heights against apparent-limb
angle. It can represent an externally supplied Watts-style or other angular
profile once the user supplies the actual samples and their provenance. It does
not contain an embedded Watts table. CSV columns are `limb_angle_deg` and
`altitude_m`, with optional `uncertainty_m`.

This is distinct from a 2D selenographic DEM: an angular profile is referenced
to the apparent limb and is sampled using the contact's `limb_angle_deg`.

### Existing neural checkpoint

`NeuralLunarLimbModel.from_checkpoint(path)` wraps the existing PyTorch
`LunarLimbCorrector` checkpoint in the common provider interface. The older
`LunarLimbCorrector.from_checkpoint(path)` remains usable directly. Its
`best_val_rmse_m`, if present in the checkpoint, is retained as a validation
metric in model metadata; it is not reported as a per-contact uncertainty.

No checkpoint, Watts table, or LOLA DEM is redistributed by EclipseKit. Use
`PDS3LunarDEMModel.from_pds3_img()` for supported uncompressed PDS3 lunar DEMs
(Phase 7.6); supply your own data and preserve its source, reference frame,
vertical datum, and resolution metadata. JP2/PDS4 and automatic reprojection
are not included in the current reader.

## Public API

```python
from eclipsekit import (
    EclipseEngine,
    GriddedLunarLimbModel,
    NeuralLunarLimbModel,
    Observer,
    TabulatedAngularLunarLimbProfile,
)

# A gridded DEM from a user-supplied file.
dem = GriddedLunarLimbModel.from_csv(
    "lunar_dem.csv",
    name="LOLA-derived regional DEM",
    source="NASA PDS product identifier / processing version",
    vertical_datum="document the DEM reference surface",
    resolution_m=100.0,
)

# Or an angular apparent-limb profile from a supplied table.
profile = TabulatedAngularLunarLimbProfile.from_csv(
    "apparent_limb_profile.csv",
    name="Adopted angular profile",
    source="bibliographic reference, edition, and table identifier",
)

engine = EclipseEngine.from_jpl("de440s")
observer = Observer(42.6, -5.5703, elevation_m=800.0, name="León")
result = engine.calculate_local(
    observer,
    "2026-08-12T18:00:00Z",
    limb_model=dem,
)
```

The legacy argument is retained:

```python
legacy_result = engine.calculate_local(
    observer, "2026-08-12T18:00:00Z", limb_corrector=old_corrector
)
```

Passing both `limb_model` and `limb_corrector` is an error. The same alias is
available on `search_cities()` and `find_solar_eclipses_by_country()`.

## Contact geometry and provenance

For each C1-C4 correction the engine provides a `LunarLimbQuery` containing:

- the selenographic latitude and longitude of the contact point;
- apparent-limb angle used by angular profiles;
- contact name and TT Julian Date;
- the optical libration longitude and latitude used in the mapping.

Every provider returns a `LunarLimbPrediction` with terrain height, model name,
model type, source, optional point uncertainty, and status. `LimbContact` and
its JSON representation retain this provenance for each solved contact.

`validation_rmse_m` on model metadata is deliberately not copied into
`altitude_uncertainty_m`: a global validation score is not automatically a
pointwise uncertainty distribution. If no point uncertainty is supplied, the
field remains `null`.

## Scope and limitations

1. The lunar libration and position-angle transformation is the existing
   Meeus-style approximation; Phase 5 does not claim a new high-precision
   physical-libration solution.
2. The generic DEM adapter performs bilinear interpolation over caller-supplied
   arrays. Phase 7.6 adds a lazy PDS3 IMG reader for simple-cylindrical lunar
   products; it does not download data, decode JP2/PDS4, reproject, or transform
   between body-fixed coordinate frames.
3. The angular-profile adapter interpolates supplied samples; it does not
   synthesize a Watts profile or apply a published Watts libration correction
   table not provided by the caller.
4. A gridded terrain surface and an apparent-limb angular profile have
   different reference frames and must not be treated as interchangeable.
5. Terrain-height corrections still use the existing spherical visual Moon
   radius as their baseline. Full Besselian limb-profile geometry and northern/
   southern path-boundary corrections remain future work.
6. Model provenance and available data uncertainties are recorded, but no
   timing-uncertainty budget is inferred from numerical root residuals or a
   model-wide validation RMSE.


For a DE440s-backed engine integration smoke test (using deliberately synthetic
global heights, not real lunar terrain), run
`examples/lunar_limb_engine_integration.py`.
