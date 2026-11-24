# Contributing to PyEclipse

## Development setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,limb]"
```

PyTorch is optional. To work only on the core engine and tests, install
`.[dev]` instead of `.[dev,limb]`.

## Before opening a pull request

```powershell
python -m pytest -v --basetemp=".pytest_tmp\pytest-run"
python -m ruff check src tests examples
python -m compileall -q src tests examples
```

For the real astronomical integration check, use a locally cached DE440s kernel:

```powershell
python .\examples\full_api_check.py
```

For comparison with published event data, run the independent-reference suite
as described in [Scientific validation](docs/SCIENTIFIC_VALIDATION.md).

## Scientific changes

Any change to contact solving, time scales, radii, shadow geometry, or lunar-limb
correction should include:

- a focused regression test;
- the reference source and its published precision;
- explicit tolerances and assumptions;
- before/after results for at least one affected event;
- a note about whether the change affects historical/future epochs.

Do not mark an experimental approximation as validated merely because it returns
a finite value or passes a smoke test.
