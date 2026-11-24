# Migrating to the curated EclipseKit API

Phase 14 adds `eclipsekit.api` as the recommended import path. Existing
`from eclipsekit import ...` statements continue to work; an immediate mass
rename is not required.

## Before

```python
from eclipsekit import EclipseEngine, Observer, EclipseConfig, EphemerisConfig
```

## Recommended for new integrations

```python
from eclipsekit.api import EclipseEngine, Observer, EclipseConfig, EphemerisConfig
```

The imported objects are the same classes/functions. Constructor signatures,
units and result contracts are not changed by the import-path migration.

## Continue using established APIs

- Prefer `EclipseConfig` for new engine construction; the legacy constructor
  overrides remain supported as a compatibility bridge.
- Use `search_cities()` when a fully collected magnitude-sorted list is needed;
  use `iter_search_cities()` for catalogue-order streaming.
- Use result-specific `to_dict()` methods for scientific reports when present.
  `dumps_json()` and `write_json()` are general strict interchange helpers, not
  replacements for report-specific versioned schemas.
- Keep optional Torch/Rasterio dependencies optional and install the matching
  extras only when those features are needed.

## Version interpretation

`eclipsekit.__version__` is the distribution version. `API_CONTRACT_VERSION`
identifies the curated Python interface contract; the exact contract-1 exports
are pinned in `docs/API_MANIFEST_V1.json`. Individual report
`schema_version` values identify serialized report formats. These identifiers
are intentionally separate and should not be conflated by integrations.
