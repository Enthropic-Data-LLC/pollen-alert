"""Deterministic risk scoring: allergen profile × pollen level → 0–100 score."""

from __future__ import annotations
from dataclasses import dataclass

WEIGHT_FACTORS = {
    "trees":   1.0,
    "grasses": 0.9,
    "weeds":   1.0,
    "mold":    0.8,
}

# Maps every Google Pollen API plant code → category
PLANT_CATEGORY = {
    # Trees
    "ALDER": "trees", "ASH": "trees", "BIRCH": "trees", "COTTONWOOD": "trees",
    "CEDAR": "trees", "CYPRESS_PINE": "trees", "ELM": "trees", "GRAMINALES": "trees",
    "HAZEL": "trees", "JUNIPER": "trees", "MAPLE": "trees", "MULBERRY": "trees",
    "OAK": "trees", "OLIVE": "trees", "PINE": "trees", "PLANE": "trees",
    "POPLAR": "trees", "SYCAMORE": "trees", "WILLOW": "trees",
    # Grasses
    "GRASS": "grasses", "BERMUDA_GRASS": "grasses",
    # Weeds
    "RAGWEED": "weeds", "MUGWORT": "weeds", "NETTLE": "weeds",
    "DOCK": "weeds", "RUSSIAN_THISTLE": "weeds", "LAMB_QUARTERS": "weeds",
    "DANDELION": "weeds", "PLANTAIN": "weeds",
    # Mold
    "MOLD_SPORES": "mold",
}

# Risk bands (score → label, color code)
RISK_BANDS = [
    (0,  20, "Low",       "green"),
    (21, 40, "Moderate",  "yellow"),
    (41, 65, "High",      "orange"),
    (66, 85, "Very High", "red"),
    (86, 100, "Extreme",  "purple"),
]


@dataclass
class PlantScore:
    code: str
    display_name: str
    upi: int           # 0–5
    sensitivity: int   # 0–4
    contribution: float


@dataclass
class DayScore:
    score: int         # 0–100
    risk_label: str
    color: str
    plant_scores: list[PlantScore]

    @property
    def top_threats(self) -> list[PlantScore]:
        return sorted(self.plant_scores, key=lambda p: p.contribution, reverse=True)


def score_day(plants: dict, sensitivities: dict) -> DayScore:
    """Compute a personal risk score for one day of pollen data.

    Args:
        plants: {plant_code: {"upi": int, "display_name": str, ...}}
                as returned by fetcher.parse() or fetcher_openmeteo.parse()
        sensitivities: flat dict of {PLANT_CODE: sensitivity_level (0–4)}
                       merged across all categories from profile.json

    Returns:
        DayScore with normalized 0–100 score and breakdown.
    """
    plant_scores: list[PlantScore] = []
    raw_total = 0.0

    for code, data in plants.items():
        upi = data.get("upi", 0)
        sensitivity = sensitivities.get(code, 0)
        if sensitivity == 0 or upi == 0:
            continue

        category = PLANT_CATEGORY.get(code, "weeds")
        weight = WEIGHT_FACTORS.get(category, 1.0)
        contribution = upi * sensitivity * weight

        plant_scores.append(PlantScore(
            code=code,
            display_name=data.get("display_name", code),
            upi=upi,
            sensitivity=sensitivity,
            contribution=round(contribution, 2),
        ))
        raw_total += contribution

    # Normalize against a calibrated ceiling of 100.
    # Derived from Charlotte, NC peak April scenario: Oak UPI 5 + Birch 4 + Maple 4 + Pine 4
    # + Ash 3 + Cottonwood 3 + Alder 2 + Juniper 2 + Elm 2 + Sycamore 3 = raw 112.
    # At CEILING=100, today (late March, raw ~60) → score 60 (High), peak April → Extreme (capped).
    # Calibrated 2026-03-28 against live Google Pollen API data for Indian Trail, NC.
    CEILING = 100.0
    normalized = min(raw_total / CEILING * 100, 100)
    score = round(normalized)

    label, color = _risk_band(score)
    return DayScore(score=score, risk_label=label, color=color, plant_scores=plant_scores)


def _risk_band(score: int) -> tuple[str, str]:
    for low, high, label, color in RISK_BANDS:
        if low <= score <= high:
            return label, color
    return "Extreme", "purple"


def flatten_sensitivities(profile_sensitivities: dict) -> dict:
    """Flatten nested {category: {PLANT: level}} → {PLANT: level}."""
    flat = {}
    for category_plants in profile_sensitivities.values():
        flat.update(category_plants)
    return flat
