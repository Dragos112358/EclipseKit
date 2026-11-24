"""Safely merge Phase 15 partial and hybrid eclipse references into a local manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
from typing import Any


def merge_reference_case(
    manifest_path: str | Path,
    case_path: str | Path,
    *,
    hybrid_case_path: str | Path | None = None,
    backup: bool = True,
) -> tuple[str, Path | None]:
    """Merge new published fixtures without replacing existing local records.

    A single backup is made before either addition. Both cases are validated
    through the production reference models, and a conflicting ID aborts the
    entire operation before the local manifest is modified.
    """
    manifest = Path(manifest_path).expanduser().resolve()
    case_file = Path(case_path).expanduser().resolve()
    document = json.loads(manifest.read_text(encoding="utf-8"))
    local_case: Any = json.loads(case_file.read_text(encoding="utf-8"))
    hybrid_case: Any | None = None
    if hybrid_case_path is not None:
        hybrid_file = Path(hybrid_case_path).expanduser().resolve()
        hybrid_case = json.loads(hybrid_file.read_text(encoding="utf-8"))

    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("reference manifest must be a schema_version 1 JSON object")
    local_cases = document.get("local_cases")
    global_cases = document.get("global_maximum_cases", [])
    if not isinstance(local_cases, list) or not isinstance(global_cases, list):
        raise ValueError("reference manifest local_cases and global_maximum_cases must be arrays")

    # Validate additions using the exact runtime models before touching files.
    from eclipsekit.validation import ReferenceGlobalMaximumCase, ReferenceLocalCase

    ReferenceLocalCase.from_mapping(local_case)
    if hybrid_case is not None:
        ReferenceGlobalMaximumCase.from_mapping(hybrid_case)

    all_records = [*local_cases, *global_cases]
    all_ids = [item.get("case_id") for item in all_records if isinstance(item, dict)]
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("manifest already contains duplicate case_id values")

    additions_local: list[dict[str, Any]] = []
    additions_global: list[dict[str, Any]] = []

    def classify_addition(case: Any, existing_group: list[Any], other_group: list[Any], target: list[Any]) -> None:
        case_id = case["case_id"]
        existing = next((item for item in existing_group if isinstance(item, dict) and item.get("case_id") == case_id), None)
        if existing is not None:
            if existing == case:
                return
            raise ValueError(
                f"manifest already contains case_id {case_id!r} with different content; refusing to overwrite"
            )
        if any(isinstance(item, dict) and item.get("case_id") == case_id for item in other_group):
            raise ValueError(f"case_id {case_id!r} is already used by another reference group")
        target.append(case)

    classify_addition(local_case, local_cases, global_cases, additions_local)
    if hybrid_case is not None:
        classify_addition(hybrid_case, global_cases, local_cases, additions_global)

    if not additions_local and not additions_global:
        return "already-present", None

    backup_path = manifest.with_name(manifest.name + ".phase15.bak") if backup else None
    if backup_path is not None:
        if backup_path.exists():
            raise FileExistsError(
                f"Backup already exists: {backup_path}. Move it aside before running another merge."
            )
        shutil.copy2(manifest, backup_path)

    local_cases.extend(additions_local)
    global_cases.extend(additions_global)
    document["local_cases"] = local_cases
    document["global_maximum_cases"] = global_cases
    temporary = manifest.with_name(manifest.name + ".phase15.tmp")
    try:
        temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(manifest)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return "added", backup_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="data/validation/reference_cases.json")
    parser.add_argument("--case", default="examples/phase15_partial_eclipse_reference_case.json")
    parser.add_argument(
        "--hybrid-case", default="examples/phase15_hybrid_eclipse_reference_case.json",
        help="optional published hybrid-eclipse global-maximum reference JSON",
    )
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args(argv)
    try:
        status, backup = merge_reference_case(
            args.manifest, args.case, hybrid_case_path=args.hybrid_case, backup=not args.no_backup,
        )
    except Exception as exc:
        print(f"Could not merge Phase 15 references: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(f"Phase 15 references: {status}")
    if backup is not None:
        print(f"Original manifest backup: {backup}")
    print(f"Manifest: {Path(args.manifest).expanduser()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
