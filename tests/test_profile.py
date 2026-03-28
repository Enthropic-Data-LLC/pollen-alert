"""Tests for profile loading and validation."""

import json
import pytest
import tempfile
import os
from pathlib import Path
from pollen_alert.profile import load, ProfileError


VALID_PROFILE = {
    "profile_name": "Test",
    "location": {"lat": 35.07, "lon": -80.65, "zip": "28079"},
    "sensitivities": {
        "trees": {"OAK": 4, "JUNIPER": 3},
        "grasses": {"GRASS": 2},
        "weeds": {"RAGWEED": 4},
        "mold": {"MOLD_SPORES": 2},
    },
    "thresholds": {"notify_above_score": 30, "critical_score": 70},
    "outputs": ["console"],
}


def write_profile(data: dict) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(data, f)
    f.close()
    return f.name


def test_valid_profile_loads():
    path = write_profile(VALID_PROFILE)
    try:
        profile = load(path)
        assert profile["profile_name"] == "Test"
    finally:
        os.unlink(path)


def test_missing_required_key_raises():
    bad = {k: v for k, v in VALID_PROFILE.items() if k != "outputs"}
    path = write_profile(bad)
    try:
        with pytest.raises(ProfileError, match="missing required keys"):
            load(path)
    finally:
        os.unlink(path)


def test_invalid_sensitivity_level_raises():
    bad = json.loads(json.dumps(VALID_PROFILE))
    bad["sensitivities"]["trees"]["OAK"] = 5  # max is 4
    path = write_profile(bad)
    try:
        with pytest.raises(ProfileError, match="must be integer 0"):
            load(path)
    finally:
        os.unlink(path)


def test_unknown_output_raises():
    bad = json.loads(json.dumps(VALID_PROFILE))
    bad["outputs"] = ["slack"]
    path = write_profile(bad)
    try:
        with pytest.raises(ProfileError, match="Unknown outputs"):
            load(path)
    finally:
        os.unlink(path)


def test_invalid_location_raises():
    bad = json.loads(json.dumps(VALID_PROFILE))
    bad["location"]["lat"] = "not-a-number"
    path = write_profile(bad)
    try:
        with pytest.raises(ProfileError, match="lat/lon must be numbers"):
            load(path)
    finally:
        os.unlink(path)


def test_missing_profile_raises():
    with pytest.raises(ProfileError, match="No profile.json found"):
        load("/nonexistent/path/profile.json")
