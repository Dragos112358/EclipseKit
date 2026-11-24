from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.merge_phase15_partial_reference import merge_reference_case


def _case() -> dict:
    return {
        "case_id": "partial-london",
        "name": "London partial eclipse",
        "event_time_utc": "2022-10-25T11:00:07Z",
        "latitude": 51.5074,
        "longitude": -0.1278,
        "elevation_m": 11,
        "expected_eclipse_type": "partial",
        "expected_contacts_utc": {
            "C1": "2022-10-25T09:09:00Z",
            "C4": "2022-10-25T10:51:00Z",
        },
        "expected_maximum_utc": "2022-10-25T09:59:00Z",
        "contact_tolerance_seconds": 180,
        "maximum_tolerance_seconds": 180,
        "source_precision_seconds": 60,
        "source_url": "https://example.org/partial-eclipse",
        "source_notes": "Minute-rounded local times converted to UTC.",
    }


def _manifest() -> dict:
    return {
        "schema_version": 1,
        "local_cases": [{"case_id": "existing-total", "expected_eclipse_type": "total"}],
        "global_maximum_cases": [],
    }


def _hybrid_case() -> dict:
    return {
        "case_id": "hybrid-maximum",
        "name": "Published hybrid eclipse maximum",
        "event_time_utc": "2023-04-20T04:16:44.8Z",
        "expected_maximum_utc": "2023-04-20T04:16:44.8Z",
        "tolerance_seconds": 30,
        "expected_eclipse_type": "hybrid",
        "source_url": "https://eclipse.gsfc.nasa.gov/SEbeselm/SEbeselm2001/SE2023Apr20Hbeselm.html",
        "source_notes": "NASA greatest-eclipse epoch; type is source metadata.",
    }


def test_merge_adds_case_with_backup_and_is_idempotent(tmp_path: Path) -> None:
    manifest = tmp_path / "reference_cases.json"
    case_path = tmp_path / "partial.json"
    original = json.dumps(_manifest(), indent=2)
    manifest.write_text(original, encoding="utf-8")
    case_path.write_text(json.dumps(_case()), encoding="utf-8")

    status, backup = merge_reference_case(manifest, case_path)
    assert status == "added"
    assert backup is not None and backup.read_text(encoding="utf-8") == original
    updated = json.loads(manifest.read_text(encoding="utf-8"))
    assert [item["case_id"] for item in updated["local_cases"]] == ["existing-total", "partial-london"]

    status, backup_again = merge_reference_case(manifest, case_path)
    assert status == "already-present"
    assert backup_again is None


def test_merge_refuses_to_overwrite_conflicting_case_id(tmp_path: Path) -> None:
    manifest = tmp_path / "reference_cases.json"
    case_path = tmp_path / "partial.json"
    payload = _manifest()
    payload["local_cases"].append({**_case(), "name": "different"})
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    case_path.write_text(json.dumps(_case()), encoding="utf-8")
    with pytest.raises(ValueError, match="different content"):
        merge_reference_case(manifest, case_path)


def test_merge_rejects_duplicate_id_in_another_group(tmp_path: Path) -> None:
    manifest = tmp_path / "reference_cases.json"
    case_path = tmp_path / "partial.json"
    payload = _manifest()
    payload["global_maximum_cases"].append({"case_id": "partial-london"})
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    case_path.write_text(json.dumps(_case()), encoding="utf-8")
    with pytest.raises(ValueError, match="already used by another reference group"):
        merge_reference_case(manifest, case_path)


def test_merge_can_run_without_creating_a_backup(tmp_path: Path) -> None:
    manifest = tmp_path / "reference_cases.json"
    case_path = tmp_path / "partial.json"
    manifest.write_text(json.dumps(_manifest()), encoding="utf-8")
    case_path.write_text(json.dumps(_case()), encoding="utf-8")
    status, backup = merge_reference_case(manifest, case_path, backup=False)
    assert status == "added"
    assert backup is None
    assert not manifest.with_name(manifest.name + ".phase15.bak").exists()


def test_merge_adds_partial_and_hybrid_global_case_with_one_backup(tmp_path: Path) -> None:
    manifest = tmp_path / "reference_cases.json"
    local_path = tmp_path / "partial.json"
    hybrid_path = tmp_path / "hybrid.json"
    original = json.dumps(_manifest(), indent=2)
    manifest.write_text(original, encoding="utf-8")
    local_path.write_text(json.dumps(_case()), encoding="utf-8")
    hybrid_path.write_text(json.dumps(_hybrid_case()), encoding="utf-8")

    status, backup = merge_reference_case(
        manifest, local_path, hybrid_case_path=hybrid_path,
    )
    assert status == "added"
    assert backup is not None and backup.read_text(encoding="utf-8") == original
    updated = json.loads(manifest.read_text(encoding="utf-8"))
    assert updated["local_cases"][-1]["case_id"] == "partial-london"
    assert updated["global_maximum_cases"][-1]["expected_eclipse_type"] == "hybrid"

    status, backup_again = merge_reference_case(
        manifest, local_path, hybrid_case_path=hybrid_path,
    )
    assert status == "already-present"
    assert backup_again is None
