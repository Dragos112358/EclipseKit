# Lunar-limb checkpoint

`lunar_altitude_contact_bands_fp16_finetuned.pt` is an **optional** neural checkpoint that
predicts lunar limb altitude corrections for eclipse contacts. It is about 66 MB and is
**not** included in the PyPI wheel. Download it from this folder of the repository.

eclipsekit works without it: contacts use a spherical, zero-relief Moon unless you pass a limb
model.

## Requirements

The checkpoint is loaded with PyTorch:

```bash
pip install "eclipsekit[limb]"
```

## Usage

```python
from eclipsekit import LunarLimbCorrector

limb = LunarLimbCorrector.from_checkpoint(
    "models/lunar_altitude_contact_bands_fp16_finetuned.pt"
)
```

Pass the corrector to the local, city or country entry points through their limb-model
arguments (see [`../docs/LUNAR_LIMB_FRAMEWORK.md`](../docs/LUNAR_LIMB_FRAMEWORK.md)). Each
corrected contact records the model provenance.

## Model card

| Field | Value |
|---|---|
| File | `lunar_altitude_contact_bands_fp16_finetuned.pt` (about 66 MB, fp16, fine-tuned) |
| Author | Dragos-Eduard-Gabriel Boncan |
| Task | Predict lunar limb altitude (contact bands) for use in C1–C4 contact corrections |
| Stored validation RMSE | 12.58 m (`best_val_rmse_m` in the checkpoint metadata) |
| Training data | `<DEM / source, version, download date and licence, e.g. LOLA-based product>` |
| Architecture | `<short description, parameter count>` |
| Train / validation / test split | `<how the split was made, and whether the splits are spatially disjoint>` |
| Training setup | `<optimiser, learning rate, schedule, seed>` |
| SHA-256 | `<output of the command below>` |
| Licence | Apache-2.0, same as the code (see [`../LICENSE`](../LICENSE)) |

Compute the checksum on Windows PowerShell:

```powershell
Get-FileHash models\lunar_altitude_contact_bands_fp16_finetuned.pt -Algorithm SHA256
```

or on Linux/macOS:

```bash
sha256sum models/lunar_altitude_contact_bands_fp16_finetuned.pt
```

## Intended use and limitations

- Research and experimentation with limb-relief effects on contact times.
- The stored validation RMSE is metadata from training. It is **not** a global accuracy
  guarantee and was not evaluated against an independent lunar-limb benchmark.
- The model is not independent topographic truth. Use `eclipsekit-validate-limb` with
  independently checked reference heights to assess it (see
  [`../docs/VALIDATION_FRAMEWORK.md`](../docs/VALIDATION_FRAMEWORK.md)).
- Do not use the same data as both training input and benchmark.
- Behaviour outside the data it was trained on is not characterised.
- Corrections are on the order of seconds per contact in the cases we ran. They are not a
  substitute for a validated limb profile.

A future release is planned to integrate documented lunar topography products with explicit
coordinate frame, vertical datum, resolution and provenance checks (roadmap item 7.6).