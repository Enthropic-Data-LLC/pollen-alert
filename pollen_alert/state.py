"""Persist run state (last_high_date) across daily invocations."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

_DEFAULT_PATH = Path("config/state.json")


def load(path: Path = _DEFAULT_PATH) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save(data: dict, path: Path = _DEFAULT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def days_since_last_high(state: dict) -> int | None:
    """Return days since last_high_date, or None if never recorded."""
    raw = state.get("last_high_date")
    if not raw:
        return None
    try:
        last = date.fromisoformat(raw)
        return (date.today() - last).days
    except ValueError:
        return None
