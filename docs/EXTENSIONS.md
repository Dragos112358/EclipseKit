# Third-party extensions

EclipseKit supports explicit Python package entry-point discovery for optional
third-party providers. Discovery is metadata-only: it does not import or execute
plugin modules. A plugin is imported only after the host calls
`load_extension(group, name)`.

## Supported entry-point groups

The `LunarLimbModelFactory`, `LunarDEMReaderFactory` and `LunarDEMReader`
protocols are exported from `eclipsekit.api` for static type checking. The
loader enforces that entry points are callable; it does not instantiate or
runtime-certify the provider returned by a factory.

| Entry-point group | Factory contract | Intended use |
|---|---|---|
| `eclipsekit.lunar_limb_models` | Callable factory returning an object satisfying `LunarLimbModel` (`metadata` plus `predict(query)`) | Custom lunar-limb/terrain providers |
| `eclipsekit.dem_readers` | Callable factory accepting a source/path and returning a DEM provider with declared metadata and `predict_altitude_m(latitude_deg, longitude_deg)` | Custom PDS/GeoTIFF/other DEM readers or adapters |

These are Python packaging contracts, not an automatic registration into the
engine. The host application decides how to instantiate, validate, own and pass
the returned provider to EclipseKit. No plugin is loaded at import time and no
network access is performed during discovery.

## Registering a plugin

In the third-party provider's `pyproject.toml`:

```toml
[project.entry-points."eclipsekit.lunar_limb_models"]
my_lola_provider = "my_lola_package.plugin:create_model"
```

The `create_model` function is imported when explicitly requested and should
return an object conforming to the `LunarLimbModel` protocol:

```python
from eclipsekit.api import LunarLimbModel, LunarLimbQuery, LunarLimbPrediction

class MyLunarLimbProvider:
    metadata = ...  # LunarLimbModelMetadata instance

    def predict(self, query: LunarLimbQuery) -> LunarLimbPrediction:
        ...


def create_model(**configuration):
    return MyLunarLimbProvider(...)
```

## Discover and load

```python
from eclipsekit.api import discover_extensions, load_extension

for item in discover_extensions():
    print(item.group, item.name, item.distribution, item.version)

factory = load_extension("my_lola_provider", "eclipsekit.lunar_limb_models")
model = factory(data_path="/path/to/user/LOLA/product")
```

`discover_extensions()` returns sorted `ExtensionInfo` records. It preserves
duplicate registrations so an application can report collisions. Loading
requires an exact group and name. Duplicate registrations raise
`AmbiguousExtensionError`; missing registrations raise `UnknownExtensionError`;
import failures and non-callable entry points raise `ExtensionLoadError`.

## Security and reproducibility

Entry-point loading imports and executes third-party Python code. Only load
plugins from distributions that the application/user trusts. EclipseKit does
not sandbox plugins, inspect their dependencies, fetch them, install them, or
silently select a winner when two distributions publish the same name.

The application should record the plugin distribution/version and the
configuration/source identifiers in its own scientific provenance report.
The extension loader reports entry-point metadata only; it does not claim that a
plugin's numerical outputs are scientifically validated.
