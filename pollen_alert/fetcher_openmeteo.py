"""Open-Meteo Air Quality API client — fallback pollen source (no key required)."""

import urllib.request
import urllib.parse
import json
from datetime import date, datetime
from typing import Optional


API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

# Map Open-Meteo variable names → Google Pollen API plant codes
OPENMETEO_TO_PLANT = {
    "alder_pollen":   "ALDER",
    "birch_pollen":   "BIRCH",
    "grass_pollen":   "GRASS",
    "mugwort_pollen": "MUGWORT",
    "olive_pollen":   "OLIVE",
    "ragweed_pollen": "RAGWEED",
}

# Open-Meteo reports grains/m³; approximate UPI bands (0–5)
# Based on WHO / EAN thresholds
def _grains_to_upi(variable: str, value: float) -> int:
    thresholds = {
        "alder_pollen":   [10, 70, 200, 500],
        "birch_pollen":   [10, 70, 200, 500],
        "grass_pollen":   [5,  20,  80, 200],
        "mugwort_pollen": [10, 30, 100, 300],
        "olive_pollen":   [10, 50, 150, 400],
        "ragweed_pollen": [5,  20,  80, 200],
    }
    bands = thresholds.get(variable, [10, 50, 150, 400])
    for i, threshold in enumerate(bands):
        if value <= threshold:
            return i + 1
    return 5


def fetch(lat: float, lon: float, days: int = 2) -> dict:
    """Fetch pollen forecast from Open-Meteo. Returns raw response dict."""
    variables = list(OPENMETEO_TO_PLANT.keys())
    params = urllib.parse.urlencode({
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(variables),
        "forecast_days": min(max(days, 1), 7),
        "timezone": "auto",
    })
    url = f"{API_URL}?{params}"

    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"Open-Meteo API HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Open-Meteo API network error: {e.reason}") from e


def parse(api_response: dict) -> list[dict]:
    """Parse Open-Meteo response into the same normalized format as fetcher.parse."""
    hourly = api_response.get("hourly", {})
    times = hourly.get("time", [])
    if not times:
        return []

    # Aggregate hourly values to daily max per plant
    daily_data: dict[date, dict[str, list[float]]] = {}

    for i, time_str in enumerate(times):
        try:
            dt = datetime.fromisoformat(time_str)
            day = dt.date()
        except ValueError:
            continue

        if day not in daily_data:
            daily_data[day] = {v: [] for v in OPENMETEO_TO_PLANT}

        for var in OPENMETEO_TO_PLANT:
            val = hourly.get(var, [None])[i]
            if val is not None:
                daily_data[day][var].append(val)

    days = []
    for day in sorted(daily_data):
        plants = {}
        for var, values in daily_data[day].items():
            if not values:
                continue
            daily_max = max(values)
            code = OPENMETEO_TO_PLANT[var]
            upi = _grains_to_upi(var, daily_max)
            display_names = {
                "ALDER": "Alder", "BIRCH": "Birch", "GRASS": "Grass",
                "MUGWORT": "Mugwort", "OLIVE": "Olive", "RAGWEED": "Ragweed",
            }
            plants[code] = {
                "upi": upi,
                "display_name": display_names.get(code, code),
                "in_season": daily_max > 0,
            }
        days.append({"date": day, "plants": plants})

    return days
