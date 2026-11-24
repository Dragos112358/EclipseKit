"""Strict, interoperable JSON conversion for EclipseKit result objects.

The helpers deliberately reject unsupported objects, non-string mapping keys,
cyclic structures and non-finite floating-point values instead of silently
producing lossy or non-standard JSON.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
import json
import math
import os
from pathlib import Path, PurePath
import tempfile
from typing import Any, Mapping

import numpy as np


_JSON_SCALARS = (str, int, bool, type(None))


def to_jsonable(value: Any) -> Any:
    """Convert supported Python/EclipseKit values into strict JSON primitives.

    Supported values include dataclasses, objects exposing ``to_dict()``,
    mappings with string keys, tuples/lists, enums, dates/times, paths, NumPy
    arrays and NumPy scalar values. NaN and infinity are rejected.
    """
    return _to_jsonable(value, active=set(), path="$" )


def _to_jsonable(value: Any, *, active: set[int], path: str) -> Any:
    if isinstance(value, _JSON_SCALARS):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Non-finite float at {path} cannot be represented in strict JSON")
        return value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, PurePath):
        # JSON paths use a platform-independent separator convention.
        return value.as_posix()
    if isinstance(value, Enum):
        return _to_jsonable(value.value, active=active, path=path)
    if isinstance(value, np.generic):
        return _to_jsonable(value.item(), active=active, path=path)
    if isinstance(value, np.ndarray):
        return _to_jsonable(value.tolist(), active=active, path=path)

    identity = id(value)
    if identity in active:
        raise ValueError(f"Circular reference detected at {path}")

    converter = getattr(value, "to_dict", None)
    if callable(converter):
        active.add(identity)
        try:
            converted = converter()
            if converted is value:
                raise ValueError(f"to_dict() returned self at {path}")
            return _to_jsonable(converted, active=active, path=path)
        finally:
            active.remove(identity)

    if is_dataclass(value) and not isinstance(value, type):
        active.add(identity)
        try:
            return {
                item.name: _to_jsonable(getattr(value, item.name), active=active,
                                        path=f"{path}.{item.name}")
                for item in fields(value)
            }
        finally:
            active.remove(identity)

    if isinstance(value, Mapping):
        active.add(identity)
        try:
            result: dict[str, Any] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise TypeError(f"JSON object key at {path} must be str, got {type(key).__name__}")
                result[key] = _to_jsonable(item, active=active, path=f"{path}.{key}")
            return result
        finally:
            active.remove(identity)

    if isinstance(value, (list, tuple)):
        active.add(identity)
        try:
            return [
                _to_jsonable(item, active=active, path=f"{path}[{index}]")
                for index, item in enumerate(value)
            ]
        finally:
            active.remove(identity)

    raise TypeError(f"Unsupported value at {path}: {type(value).__name__}")


def dumps_json(value: Any, *, indent: int | None = 2) -> str:
    """Serialize an EclipseKit object as UTF-8-compatible strict JSON text."""
    if indent is not None and (isinstance(indent, bool) or not isinstance(indent, int) or indent < 0):
        raise ValueError("indent must be None or a non-negative integer")
    converted = to_jsonable(value)
    return json.dumps(
        converted,
        ensure_ascii=False,
        allow_nan=False,
        indent=indent,
        separators=None if indent is not None else (",", ":"),
    )


def write_json(value: Any, path: str | Path, *, indent: int | None = 2) -> Path:
    """Atomically write strict JSON, replacing the destination only on success."""
    destination = Path(path).expanduser()
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    document = dumps_json(value, indent=indent) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=parent,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(document)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
    return destination


__all__ = ["to_jsonable", "dumps_json", "write_json"]
