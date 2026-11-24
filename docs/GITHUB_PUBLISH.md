# Publish EclipseKit to GitHub and PyPI (Alpha 0.1.0)

This procedure publishes the Python source, documentation, tests and the small
curated NASA/GSFC regression fixtures. It deliberately excludes the developer's
local DEM collection, city catalogue, kernels, neural checkpoint, caches,
reports and results.

## What is published

- `src/eclipsekit/`: the installable Python library.
- `tests/`, `docs/`, `examples/`, `scripts/` and `.github/workflows/`.
- Exactly nine small files under `data/validation/`, allow-listed in `.gitignore`
  and the source-distribution configuration. These are the compact reference
  inputs used by tests and validation workflows.
- Project metadata, Apache-2.0 licence and notices.

Not published: `data/` except those nine named reference fixtures; `models/`;
`CountryPoints.csv`; PDS3/PDS4 DEM rasters; `.bsp` kernels; `.pt`, `.pth`, and
`.ckpt` weights; `.venv/`; reports/results; caches; `dist/`; or local archives.

The PyPI wheel contains only `src/eclipsekit` plus its `py.typed` marker. The
source distribution additionally contains tests/docs/examples/scripts and the
nine small public validation fixtures. It does not contain the large local
scientific assets.

## 1. Check the project name on PyPI

Open `https://pypi.org/project/eclipsekit/` while signed into your PyPI account.
The distribution name `eclipsekit` must be available to register. If the name is
already registered or reserved, choose a new distribution name before building
(e.g. a unique name containing your publisher identity); the import name can
remain `eclipsekit`.

## 2. Install build and release tools

From the project root in PowerShell:

```powershell
python -m pip install --upgrade build twine hatchling
```

## 3. Build and inspect both distributions

```powershell
Remove-Item .\dist -Recurse -Force -ErrorAction SilentlyContinue
python -m build
python -m twine check .\dist\*
Get-ChildItem .\dist | Select-Object Name,Length
```

Both the wheel and source archive must be comfortably below PyPI's default
100 MB per-file limit. The project is expected to be much smaller because the
wheel is code-only and the sdist has an explicit allow-list. PyPI's current
storage limits are documented at
https://docs.pypi.org/project-management/storage-limits/.

Check the wheel contains no development or local data:

```powershell
python -c "import glob,zipfile; p=glob.glob('dist/*.whl')[0]; z=zipfile.ZipFile(p); n=z.namelist(); assert 'eclipsekit/py.typed' in n; assert all(not x.startswith(('tests/','data/','models/','reports/','results/')) for x in n); print('\n'.join(n))"
```

Check the sdist allow-list and size:

```powershell
python -c "import glob,tarfile; p=glob.glob('dist/*.tar.gz')[0]; t=tarfile.open(p); n=t.getnames(); bad=[x for x in n if any('/'+d+'/' in '/'+x+'/' for d in ('models','reports','results','.venv','dist','build')) or x.endswith(('.bsp','.pt','.pth','.ckpt','.IMG','.LBL','.img','.lbl','.cub','.jp2','.tif','.tiff','.npz','.npy'))]; assert not bad, bad; print('sdist files:',len(n)); print('sdist bytes:',__import__('os').path.getsize(p))"
```

## 4. Create the GitHub repository

Create an empty public repository named `EclipseKit` on GitHub. Do not ask
GitHub to generate another README, licence or `.gitignore`; the local project
already contains them.

After the repository exists, add its real URL to `pyproject.toml` under the
`[project.urls]` table before the first package build (replace `OWNER`):

```toml
[project.urls]
Homepage = "https://github.com/OWNER/EclipseKit"
Repository = "https://github.com/OWNER/EclipseKit"
Issues = "https://github.com/OWNER/EclipseKit/issues"
```

If this local folder has not yet been initialized as Git:

```powershell
git init
git branch -M main
```

If it is already a Git repository, do not run `git init` again. Inspect first:

```powershell
git status --short --branch
git remote -v
git branch --show-current
```

## 5. Stage only the public allow-list

Do not use `git add .` for this project. First clear any previously staged
local-only directories from the Git index (this does not delete local files),
then stage the known source directories and metadata explicitly:

```powershell
git rm -r --cached --ignore-unmatch data models reports results reference
git rm --cached --ignore-unmatch INTEGRATION_STATUS.md

git add .gitignore pyproject.toml README.md CHANGELOG.md LICENSE.md NOTICE SECURITY.md CITATION.cff CONTRIBUTING.md MIGRATION.md
git add .github docs examples scripts src tests

git add data/validation/reference_cases.json `
  data/validation/path_reference_manifest.json `
  data/validation/global_path_2017-08-21.csv `
  data/validation/global_path_2019-07-02.csv `
  data/validation/global_path_2020-06-21.csv `
  data/validation/global_path_2026-08-12.csv `
  data/validation/global_corridor_2017_nasa.csv `
  data/validation/besselian_1999_reference.json `
  data/validation/besselian_1999_aug11_nasa.json
```

Review the exact staged file list:

```powershell
git status --short
git diff --cached --stat
git diff --cached --name-only
```

Verify that `data/` contains only the nine whitelisted reference fixtures and
that no local assets are staged:

```powershell
git ls-files data models reports results reference
```

The `data` output must show only the nine files listed above. `models`,
`reports`, `results` and `reference` should produce no paths.

Check staged file sizes. GitHub warns at 50 MiB and blocks individual Git
objects above 100 MiB; this release should not stage any file above 50 MiB:

```powershell
$staged = git diff --cached --name-only
$large = foreach ($f in $staged) {
    if (Test-Path -LiteralPath $f -PathType Leaf) {
        $item = Get-Item -LiteralPath $f
        if ($item.Length -ge 50MB) {
            [pscustomobject]@{ Path = $f; MiB = [math]::Round($item.Length / 1MB, 2) }
        }
    }
}
$large | Format-Table -AutoSize
if ($large) { throw 'Large staged files found. Do not commit.' }
```

If `git ls-files` already lists a checkpoint, DEM or report because it was
committed in an earlier commit, `.gitignore` and `git rm --cached` cannot remove
it from Git history. Stop before pushing; use a new clean public repository or
carefully clean the history after making a backup. Do not run history-rewriting
commands without a backup. The ignored `INTEGRATION_STATUS.md` contains local
Windows test-environment details and must not be published.

When the staged list is clean:

```powershell
git diff --cached --check
git commit -m "Prepare EclipseKit 0.1.0 Alpha release"
```

Add the remote URL shown by GitHub (replace the owner with your account):

```powershell
git remote add origin https://github.com/YOUR-GITHUB-OWNER/EclipseKit.git
git push -u origin main
```

If `origin` already exists, inspect `git remote -v` and use `git remote set-url`
only if it points to the wrong repository.

## 6. Configure PyPI Trusted Publishing

Trusted Publishing is preferred over storing a long-lived PyPI API token in
GitHub. Official documentation:
https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/.

After the repository exists:

1. Sign in to PyPI and open `https://pypi.org/manage/account/publishing/`.
2. Create a **pending publisher** for project name `eclipsekit`.
3. Choose GitHub Actions and enter the exact GitHub owner, repository name,
   workflow filename `publish-pypi.yml`, and environment `pypi`.
4. In the GitHub repository, open Settings → Environments and create an
   environment named `pypi`. Protect it with required reviewer approval when
   available.

A pending publisher does not reserve the project name until the first
successful publication. If the name is unavailable, resolve the name before
creating the GitHub Release.

## 7. Publish the Alpha release

Create a GitHub Release from the `main` commit:

- Tag: `v0.1.0`
- Title: `EclipseKit 0.1.0 (Alpha)`
- Description: summarize features and list known scientific limitations
- Mark it as a **pre-release** on GitHub

Versioning note: `0.1.0` is a final-release identifier under Python's version
specification, even though the package classifier says Alpha and the GitHub
Release is marked pre-release. If you specifically want PyPI/pip to recognise
the version itself as an alpha pre-release, use `0.1.0a1` before the first
upload and update `pyproject.toml`, `src/eclipsekit/_version.py`,
`CITATION.cff`, release notes and version-sensitive tests together. The tested
project currently declares `0.1.0`, so this guide keeps that version unchanged.

Publishing the GitHub Release triggers `.github/workflows/publish-pypi.yml`.
The workflow builds the wheel and sdist, checks metadata and file sizes, then
publishes them to PyPI using the configured Trusted Publisher. Do not upload
files from `reports/`, `models/` or `data/` manually.

## 8. Verify installation as a new user

After PyPI shows release `0.1.0`, use a separate clean environment:

```powershell
py -3.12 -m venv .venv-pypi-smoke
.\.venv-pypi-smoke\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install eclipsekit
python -c "import eclipsekit; print(eclipsekit.__version__)"
```

Expected import version: `0.1.0`. Optional neural support is separate and may
install a large PyTorch dependency:

```powershell
python -m pip install "eclipsekit[limb]"
```

Do not include the locally trained checkpoint in the package; users must
supply a checkpoint they are licensed to use. The package's README documents
local/JPL kernel selection and data requirements.

## Scientific status

This is a software Alpha release, not a scientific 1.0.0 certification. The
release profile's result `ALPHA_RELEASE_READY` confirms the configured
software-release gates; it does not turn the four 1.0.0 scientific/maturity
gates into passes. Keep the Alpha/pre-release label and the documented scope
visible in the GitHub release and PyPI description.
