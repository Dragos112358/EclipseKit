# Data and model provenance checklist

Do not publish these local assets until you have confirmed redistribution rights
and documented their provenance.

| Asset | Local use | Required before public redistribution |
|---|---|---|
| `data/CountryPoints.csv` | City/country visibility scan | Source, dataset version, licence, attribution, coordinate accuracy |
| `models/lunar_altitude_contact_bands_fp16_finetuned.pt` | Optional lunar-limb correction | Training data provenance/licence, architecture provenance, model licence, evaluation split, independent test results |
| `reference/legacy_server_source.txt` | Migration traceability | Explicit ownership and permission to publish the original server source |
| JPL BSP kernels | Ephemeris calculations | Do not upload kernels; download/cache them locally from the authoritative provider |

## Lunar topography candidate

NASA GSFC's Planetary Geology, Geophysics and Geochemistry Laboratory lists
SLDEM2015, a lunar digital elevation model combining LOLA and SELENE Terrain
Camera information. The product page describes global maps at several pixel-per-
degree resolutions and gives the required research citation. Review the data
product's own terms and technical documentation before using it to train a new
model or redistributing derived files.

Reference: https://pgda.gsfc.nasa.gov/products/54

### Phase 7.6 PDS3 reader

`PDS3LunarDEMModel` reads one uncompressed PDS3 `IMG` object at a time. The
NASA SLDEM2015 global product label describes a simple-cylindrical,
pixel-registered image, 128 pixels/degree, 60°S–60°N, east-positive longitude,
32-bit `PC_REAL` samples in kilometres, and a 1737.4 km spherical reference
radius in the mean-Earth/polar-axis-of-DE421 body-fixed frame. The implementation
uses the label's scaling and offset to return height above that reference
sphere in metres. It does not distribute or download the product.

The SLDEM2015 product page reports a typical vertical accuracy of approximately
3–4 m, but EclipseKit does not treat this product-wide statistic as a pointwise
uncertainty and does not populate `LunarLimbPrediction.uncertainty_m` from it.
A separate data-quality/uncertainty layer and independent benchmark are still
needed for an uncertainty claim.

Technical references:

- https://ode.rsl.wustl.edu/moon/pagehelp/Content/Missions_Instruments/LRO/LOLA/SLDEM.htm
- https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/sldem2015/global/float_img/sldem2015_128_60s_60n_000_360_float.lbl
- https://doi.org/10.1016/j.icarus.2015.07.039

## Minimum model card for Lunar Limb V2

Before releasing a new checkpoint, document:

- exact DEM source(s), release/version, download date, licence and citations;
- coordinate system, datum, height convention, resolution and missing-data mask;
- sample construction, target transformation, normalization and units;
- architecture, parameter count, optimizer, learning rate, training schedule and seed;
- spatially disjoint training/validation/test partitions;
- metrics in metres on an untouched test partition, including regional breakdowns;
- comparisons against direct DEM interpolation;
- contact-time differences on independent eclipse/location cases;
- known coverage limits, extrapolation behaviour, and checkpoint hash.
