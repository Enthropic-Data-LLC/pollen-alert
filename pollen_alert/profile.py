"""Profile loader and validator."""

import json
import os
from pathlib import Path
from typing import Any


REQUIRED_KEYS = {"profile_name", "location", "sensitivities", "thresholds", "outputs"}
REQUIRED_LOCATION = {"lat", "lon"}
VALID_OUTPUTS = {"telegram", "email", "webhook", "console"}
MAX_SENSITIVITY = 4


class ProfileError(ValueError):
    pass


def load(path: str | Path | None = None) -> dict:
    """Load and validate a profile.json file.

    Checks path → POLLEN_PROFILE env var → ./config/profile.json → ./profile.json.
    Raises ProfileError on validation failure.
    """
    resolved = _find_profile(path)
    with open(resolved) as f:
        try:
            profile = json.load(f)
        except json.JSONDecodeError as e:
            raise ProfileError(f"profile.json is not valid JSON: {e}") from e

    _validate(profile)
    return profile


def _find_profile(path: str | Path | None) -> Path:
    candidates = []
    if path:
        candidates.append(Path(path))
    env = os.environ.get("POLLEN_PROFILE")
    if env:
        candidates.append(Path(env))
    candidates += [
        Path("config/profile.json"),
        Path("profile.json"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise ProfileError(
        "No profile.json found. Set POLLEN_PROFILE env var or place profile.json in config/"
    )


def _validate(p: dict) -> None:
    missing = REQUIRED_KEYS - p.keys()
    if missing:
        raise ProfileError(f"profile.json missing required keys: {missing}")

    loc = p["location"]
    missing_loc = REQUIRED_LOCATION - loc.keys()
    if missing_loc:
        raise ProfileError(f"profile.json location missing: {missing_loc}")

    try:
        float(loc["lat"])
        float(loc["lon"])
    except (TypeError, ValueError) as e:
        raise ProfileError(f"profile.json location lat/lon must be numbers: {e}") from e

    sensitivities = p["sensitivities"]
    if not isinstance(sensitivities, dict):
        raise ProfileError("profile.json sensitivities must be an object")

    for category, plants in sensitivities.items():
        if not isinstance(plants, dict):
            raise ProfileError(f"sensitivities.{category} must be an object")
        for plant, level in plants.items():
            if not isinstance(level, int) or not (0 <= level <= MAX_SENSITIVITY):
                raise ProfileError(
                    f"sensitivities.{category}.{plant} must be integer 0–{MAX_SENSITIVITY}, got {level!r}"
                )

    outputs = p.get("outputs", [])
    if not isinstance(outputs, list) or not outputs:
        raise ProfileError("profile.json outputs must be a non-empty list")
    unknown = set(outputs) - VALID_OUTPUTS
    if unknown:
        raise ProfileError(f"Unknown outputs: {unknown}. Valid: {VALID_OUTPUTS}")

    thresholds = p.get("thresholds", {})
    for key in ("notify_above_score", "critical_score"):
        val = thresholds.get(key)
        if val is None:
            raise ProfileError(f"thresholds.{key} is required")
        if not isinstance(val, (int, float)) or not (0 <= val <= 100):
            raise ProfileError(f"thresholds.{key} must be 0–100")
