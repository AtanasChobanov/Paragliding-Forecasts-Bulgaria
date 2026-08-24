"""Minimal owned-setting loader for the repository-root .env file."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


def file_environment(path: Path, owned_names: Iterable[str]) -> dict[str, str]:
    if not path.is_file():
        return {}
    owned = set(owned_names)
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.removeprefix("export ").split("=", 1)
        name = name.strip()
        if name not in owned:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[name] = value
    return values
