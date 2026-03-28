"""Tests for the risk scoring algorithm."""

import pytest
from pollen_alert.scorer import score_day, flatten_sensitivities, RISK_BANDS


DAVID_SENSITIVITIES = {
    "trees": {"OAK": 4, "JUNIPER": 4, "BIRCH": 4, "ALDER": 4, "ASH": 3, "ELM": 3, "CEDAR": 4, "PINE": 3},
    "grasses": {"GRASS": 3, "BERMUDA_GRASS": 3},
    "weeds": {"RAGWEED": 4, "RUSSIAN_THISTLE": 4, "NETTLE": 3, "DOCK": 3},
    "mold": {"MOLD_SPORES": 3},
}


def test_zero_score_when_no_pollen():
    sensitivities = flatten_sensitivities(DAVID_SENSITIVITIES)
    plants = {"OAK": {"upi": 0, "display_name": "Oak", "in_season": True}}
    result = score_day(plants, sensitivities)
    assert result.score == 0
    assert result.risk_label == "Low"


def test_zero_score_for_unsensitized_plant():
    sensitivities = flatten_sensitivities(DAVID_SENSITIVITIES)
    # OLIVE is not in David's profile
    plants = {"OLIVE": {"upi": 5, "display_name": "Olive", "in_season": True}}
    result = score_day(plants, sensitivities)
    assert result.score == 0


def test_high_score_for_known_triggers():
    sensitivities = flatten_sensitivities(DAVID_SENSITIVITIES)
    plants = {
        "OAK":    {"upi": 4, "display_name": "Oak",    "in_season": True},
        "JUNIPER":{"upi": 3, "display_name": "Juniper","in_season": True},
        "BIRCH":  {"upi": 2, "display_name": "Birch",  "in_season": True},
    }
    result = score_day(plants, sensitivities)
    assert result.score > 30, f"Expected high score, got {result.score}"
    assert len(result.plant_scores) == 3


def test_top_threats_ordering():
    sensitivities = flatten_sensitivities(DAVID_SENSITIVITIES)
    plants = {
        "OAK":    {"upi": 4, "display_name": "Oak",    "in_season": True},
        "JUNIPER":{"upi": 3, "display_name": "Juniper","in_season": True},
    }
    result = score_day(plants, sensitivities)
    threats = result.top_threats
    assert threats[0].code == "OAK"
    assert threats[1].code == "JUNIPER"


def test_score_capped_at_100():
    sensitivities = {"OAK": 4, "JUNIPER": 4, "BIRCH": 4, "ALDER": 4, "ASH": 4,
                     "ELM": 4, "CEDAR": 4, "RAGWEED": 4, "RUSSIAN_THISTLE": 4}
    plants = {code: {"upi": 5, "display_name": code, "in_season": True}
              for code in sensitivities}
    result = score_day(plants, sensitivities)
    assert result.score <= 100


def test_flatten_sensitivities():
    flat = flatten_sensitivities(DAVID_SENSITIVITIES)
    assert flat["OAK"] == 4
    assert flat["GRASS"] == 3
    assert flat["RAGWEED"] == 4
    assert flat["MOLD_SPORES"] == 3


def test_risk_bands_cover_0_to_100():
    covered = set()
    for low, high, _, _ in RISK_BANDS:
        covered.update(range(low, high + 1))
    assert 0 in covered
    assert 100 in covered
    assert len(covered) == 101
