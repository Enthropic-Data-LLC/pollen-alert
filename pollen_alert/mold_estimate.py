"""Weather-based outdoor mold estimate (Open-Meteo forecast API, no key required).

Neither pollen source measures mold in the US: Google's Pollen API has no mold
code and Open-Meteo's air-quality pollen layer is Europe-only. This derives an
approximate MOLD_SPORES UPI (0–5) per day from conditions that drive outdoor
spore counts: recent heavy rain, humidity, mild temperatures, and fall leaf
litter. It is an estimate, not a spore count — reports label it "(est.)".
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

API_URL = "https://api.open-meteo.com/v1/forecast"
PAST_DAYS = 3  # rain over the previous days drives today's spore release
CODE = "MOLD_SPORES"
DISPLAY_NAME = "Mold (est.)"


def fetch(lat: float, lon: float, days: int = 5) -> dict:
    """Fetch daily rain/humidity/temperature, including PAST_DAYS of history."""
    params = urllib.parse.urlencode({
        "latitude": lat,
        "longitude": lon,
        "daily": "precipitation_sum,relative_humidity_2m_mean,temperature_2m_mean,temperature_2m_min",
        "past_days": PAST_DAYS,
        "forecast_days": min(max(days, 1), 16),
        "timezone": "auto",
    })
    req = urllib.request.Request(f"{API_URL}?{params}", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Open-Meteo weather HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Open-Meteo weather network error: {e.reason}") from e


def estimate(api_response: dict) -> dict[date, int]:
    """Return {date: estimated mold UPI 0–5} for every day that has enough history."""
    daily = api_response.get("daily", {})
    days = [date.fromisoformat(t) for t in daily.get("time", [])]
    rain = daily.get("precipitation_sum", [])
    rh = daily.get("relative_humidity_2m_mean", [])
    temp = daily.get("temperature_2m_mean", [])
    tmin = daily.get("temperature_2m_min", [])

    result = {}
    for i in range(PAST_DAYS, len(days)):
        try:
            rain_window = sum(r or 0 for r in rain[i - PAST_DAYS:i + 1])
            result[days[i]] = upi_for(rain_window, rh[i], temp[i], tmin[i], days[i].month)
        except (IndexError, TypeError):
            continue
    return result


def upi_for(rain_mm: float, rh: float, temp_c: float, tmin_c: float, month: int) -> int:
    """Score one day. rain_mm is the sum over the day and the PAST_DAYS before it."""
    points = 0
    if rain_mm >= 25:
        points += 2
    elif rain_mm >= 5:
        points += 1
    if rh >= 80:
        points += 2
    elif rh >= 65:
        points += 1
    if 10 <= temp_c <= 30:
        points += 1
    if month in (9, 10, 11):  # leaf litter season
        points += 1
    upi = min(points, 5)
    if tmin_c <= 0 or temp_c < 5:  # frost / cold suppresses spore release
        upi = min(upi, 1)
    return upi


def merge_into(days_data: list[dict], estimates: dict[date, int]) -> None:
    """Add the estimate to each day's plants, unless a real mold reading is present."""
    for day in days_data:
        upi = estimates.get(day["date"])
        if upi is None or CODE in day["plants"]:
            continue
        day["plants"][CODE] = {"upi": upi, "display_name": DISPLAY_NAME, "in_season": upi > 0}

