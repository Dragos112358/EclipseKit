from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path, PureWindowsPath

import numpy as np
import pytest

from eclipsekit.serialization import dumps_json, to_jsonable, write_json


class Status(Enum):
    READY = "ready"


@dataclass
class Example:
    name: str
    when: datetime
    path: Path
    values: np.ndarray
    status: Status


def test_to_jsonable_handles_dataclasses_datetime_path_enum_and_numpy():
    value = Example(
        "Lună", datetime(2026, 8, 12, tzinfo=timezone.utc), Path("data/example.img"),
        np.asarray([1, 2.5]), Status.READY,
    )
    converted = to_jsonable(value)
    assert converted == {
        "name": "Lună",
        "when": "2026-08-12T00:00:00+00:00",
        "path": "data/example.img",
        "values": [1.0, 2.5],
        "status": "ready",
    }


def test_to_jsonable_normalizes_windows_paths_to_portable_separators():
    value = PureWindowsPath(r"C:\data\eclipse\report.json")
    assert to_jsonable(value) == "C:/data/eclipse/report.json"


def test_to_jsonable_prefers_public_to_dict_contract():
    class Result:
        def to_dict(self):
            return {"time": datetime(2026, 1, 1, tzinfo=timezone.utc), "value": np.float64(2.0)}

    assert to_jsonable(Result()) == {"time": "2026-01-01T00:00:00+00:00", "value": 2.0}


def test_strict_json_rejects_non_finite_values_and_non_string_keys():
    with pytest.raises(ValueError, match="Non-finite"):
        dumps_json({"invalid": float("nan")})
    with pytest.raises(TypeError, match="key.*str"):
        dumps_json({1: "invalid"})


def test_strict_json_rejects_circular_and_unsupported_values():
    circular = []
    circular.append(circular)
    with pytest.raises(ValueError, match="Circular"):
        to_jsonable(circular)
    with pytest.raises(TypeError, match="Unsupported"):
        to_jsonable(object())


def test_dumps_json_supports_compact_mode_and_unicode():
    output = dumps_json({"lună": np.int64(3)}, indent=None)
    assert output == '{"lună":3}'
    assert json.loads(output) == {"lună": 3}


def test_write_json_is_atomic_and_returns_destination(tmp_path):
    destination = tmp_path / "nested" / "report.json"
    returned = write_json({"status": "PASS", "samples": np.asarray([1, 2, 3])}, destination)
    assert returned == destination
    assert json.loads(destination.read_text(encoding="utf-8")) == {
        "status": "PASS", "samples": [1, 2, 3]
    }
    assert list(destination.parent.glob("*.tmp")) == []


def test_write_json_does_not_replace_existing_file_when_conversion_fails(tmp_path):
    destination = tmp_path / "report.json"
    destination.write_text('{"original": true}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Non-finite"):
        write_json({"bad": float("inf")}, destination)
    assert json.loads(destination.read_text(encoding="utf-8")) == {"original": True}
    assert list(tmp_path.glob("*.tmp")) == []


def test_invalid_indent_is_rejected():
    with pytest.raises(ValueError, match="indent"):
        dumps_json({"a": 1}, indent=-1)
    with pytest.raises(ValueError, match="indent"):
        dumps_json({"a": 1}, indent=True)
