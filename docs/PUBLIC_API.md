# EclipseKit public API — Phase 14

## Scope and status

New application code should import supported symbols from `eclipsekit.api`.
The existing `eclipsekit` package-root imports remain available as a
backwards-compatibility surface. Phase 14 introduces the curated API contract
version `1`; the distribution version remains `0.1.0` and the API status is
reported as `stabilization-candidate` until Phase 15 release acceptance.

```python
from eclipsekit.api import (
    API_CONTRACT_VERSION,
    EclipseConfig,
    EclipseEngine,
    EphemerisConfig,
    Observer,
    get_runtime_info,
)

config = EclipseConfig(ephemeris=EphemerisConfig.jpl("de440s"))
engine = EclipseEngine(config=config)
result = engine.calculate_local(Observer(44.4268, 26.1025), "2026-08-12T17:00:00Z")
print(API_CONTRACT_VERSION, get_runtime_info().to_dict())
```

## Contract boundaries

The exact exported-name set for API contract 1 is pinned in
[`API_MANIFEST_V1.json`](API_MANIFEST_V1.json) and checked in the test suite.
The curated `eclipsekit.api` module is the recommended integration surface. It
contains the documented engine/configuration models, observer/result types,
solver entry points, lunar-limb interfaces and models, observation planning,
DEM reader/adaptor types, validation/report helpers, benchmark records, strict
JSON helpers, runtime information, and extension discovery.

The package root continues to expose the legacy symbols from earlier EclipseKit
phases. New names are added there only when they are intended to be broadly
supported; low-level implementation helpers remain in their defining modules.

### Compatibility policy

- Additive public symbols and optional keyword-only arguments may be introduced
  within API contract version 1.
- Existing positional parameters, defaults, units, coordinate conventions,
  return shapes, sorting rules, file schemas and documented exceptions are
  treated as compatibility commitments unless explicitly marked experimental.
- A planned breaking change requires a documented migration path and a
  deprecation warning before removal. Removal or incompatible semantic changes
  require a new API contract major version.
- Numerical algorithm or default changes are called out separately from Python
  signature changes; passing API compatibility tests does not establish
  scientific accuracy.
- JSON report schemas remain individually versioned by their existing
  `schema_version` fields. The API contract version does not replace those
  report schema versions.
- Optional extras remain optional. Importing `eclipsekit.api`, querying runtime
  information, or discovering extension metadata does not import PyTorch or
  Rasterio.

## Runtime diagnostics

`get_runtime_info()` returns an immutable `RuntimeInfo` record with the package
version, API contract version/status, Python implementation/version, platform,
required dependency versions, and optional Torch/Rasterio installation status
(as version strings or `None`). It uses distribution metadata rather than
importing optional packages and can be serialized with `write_json()`.

```python
from eclipsekit.api import get_runtime_info, write_json

write_json(get_runtime_info(), "reports/runtime-info.json")
```

## JSON interchange

`to_jsonable(value)` converts supported dataclasses, objects with `to_dict()`,
mappings, sequences, enums, dates/times, paths, and NumPy values into JSON
primitives. `dumps_json()` returns strict JSON text; `write_json()` writes to a
temporary sibling file and atomically replaces the destination after successful
conversion and serialization.

Unsupported values, circular references, non-string mapping keys, and
non-finite floating-point values are rejected. NumPy arrays are converted to
nested JSON lists; this is suitable for small numerical payloads, not for large
DEMs, raster cubes or memory-mapped science products. The functions do not
serialize Skyfield internals, arbitrary user objects or open file handles.
Prefer the result model's `to_dict()` when available and keep large scientific
arrays in their native file formats.

## Typed package

The package includes `eclipsekit/py.typed` (PEP 561 marker). This advertises the
presence of inline typing information; it does not promise that every legacy
internal module is fully annotated or that a particular static type checker
will produce zero diagnostics.

## Examples and migration

- [`examples/public_api_integration.py`](../examples/public_api_integration.py)
  shows a complete integration through `eclipsekit.api`.
- [`EXTENSIONS.md`](EXTENSIONS.md) documents third-party entry-point plugins.
- [`API_MIGRATION.md`](API_MIGRATION.md) explains moving from the package root
  to the curated API without changing existing calls.
