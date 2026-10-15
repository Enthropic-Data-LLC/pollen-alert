"""Tests for per-plant alerting and the weather-based mold estimate."""

from datetime import date

from pollen_alert import mold_estimate
from pollen_alert.main import _hot_plants, _heads_up
from pollen_alert.scorer import score_day

SENS = {"RAGWEED": 4, "ELM": 3, "MOLD_SPORES": 3}
TODAY = date(2026, 10, 14)
FRIDAY = date(2026, 10, 16)


def _day(**upis):
    return score_day({c: {"upi": u, "display_name": c.title()} for c, u in upis.items()}, SENS)


def test_single_plant_triggers_below_summed_threshold():
    today = _day(RAGWEED=3, ELM=1)
    assert today.score < 30
    hot = _hot_plants(today, TODAY, [], 8)
    assert hot == {"RAGWEED": ("Ragweed", TODAY)}


def test_onset_at_moderate_level_triggers():
    # UPI 2 on a sensitivity-4 plant is the early warning before it gets bad
    assert "RAGWEED" in _hot_plants(_day(RAGWEED=2), TODAY, [], 8)


def test_low_level_does_not_trigger():
    assert _hot_plants(_day(RAGWEED=1, ELM=2), TODAY, [], 8) == {}


def test_forecast_gives_lead_time():
    forecast = [(_day(RAGWEED=1), date(2026, 10, 15)), (_day(RAGWEED=3), FRIDAY)]
    hot = _hot_plants(_day(RAGWEED=1), TODAY, forecast, 8)
    assert hot == {"RAGWEED": ("Ragweed", FRIDAY)}
    assert "Ragweed (Friday)" in _heads_up(hot, TODAY)


def test_mold_after_heavy_rain_is_high():
    # 2026-10-11: 54.7 mm rain in Indian Trail, warm and humid after
    assert mold_estimate.upi_for(54.7, 72, 21.5, 16.3, 10) >= 4


def test_mold_dry_cool_is_low():
    assert mold_estimate.upi_for(0, 45, 12, 4, 10) <= 2


def test_mold_frost_suppresses():
    assert mold_estimate.upi_for(40, 90, 4, -1, 11) <= 1


def test_mold_estimate_uses_past_days_and_merges():
    resp = {"daily": {
        "time": ["2026-10-11", "2026-10-12", "2026-10-13", "2026-10-14"],
        "precipitation_sum": [54.7, 0, 0, 0],
        "relative_humidity_2m_mean": [85, 72, 65, 64],
        "temperature_2m_mean": [21.5, 21.5, 21.1, 23.7],
        "temperature_2m_min": [17.8, 16.3, 13.2, 15.5],
    }}
    est = mold_estimate.estimate(resp)
    assert list(est) == [TODAY]  # earlier days lack a full rain window
    days = [{"date": TODAY, "plants": {}}, {"date": FRIDAY, "plants": {"MOLD_SPORES": {"upi": 1}}}]
    mold_estimate.merge_into(days, est)
    assert days[0]["plants"]["MOLD_SPORES"]["upi"] == est[TODAY]
    assert days[1]["plants"]["MOLD_SPORES"]["upi"] == 1  # real reading never overwritten


def _kday(**upis):
    return score_day({c: {"upi": u, "display_name": c.title()} for c, u in upis.items()},
                     SENS, {"RAGWEED"})


def test_kryptonite_alerts_at_any_detectable_level():
    hot = _hot_plants(_kday(RAGWEED=1), TODAY, [], 8)
    assert hot == {"RAGWEED": ("Ragweed", TODAY)}


def test_kryptonite_counts_double_and_is_flagged():
    plain, kryp = _day(RAGWEED=3), _kday(RAGWEED=3)
    assert kryp.score == 2 * plain.score
    assert kryp.plant_scores[0].kryptonite and not plain.plant_scores[0].kryptonite


def test_kryptonite_absent_does_not_alert():
    assert _hot_plants(_kday(RAGWEED=0, ELM=1), TODAY, [], 8) == {}
