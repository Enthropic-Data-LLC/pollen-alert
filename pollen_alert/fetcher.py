"""Google Pollen API client."""

import os
import urllib.request
import urllib.parse
import json
from datetime import date
from typing import Optional


POLLEN_API_URL = "https://pollen.googleapis.com/v1/forecast:lookup"


def fetch(lat: float, lon: float, days: int = 2, api_key: Optional[str] = None) -> dict:
    """Fetch pollen forecast from Google Pollen API.

    Returns raw API response dict on success.
    Raises RuntimeError on HTTP or API errors.
    """
    key = api_key or os.environ.get("GOOGLE_POLLEN_API_KEY", "")
    if not key:
        raise RuntimeError("GOOGLE_POLLEN_API_KEY not set")

    params = urllib.parse.urlencode({
        "location.latitude": lat,
        "location.longitude": lon,
        "days": min(max(days, 1), 5),
        "key": key,
        "languageCode": "en",
    })
    url = f"{POLLEN_API_URL}?{params}"

    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"Google Pollen API HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Google Pollen API network error: {e.reason}") from e


def parse(api_response: dict) -> list[dict]:
    """Parse raw API response into a normalized list of daily forecast dicts.

    Each day dict:
      {
        "date": date(2026, 3, 28),
        "plants": {
          "OAK": {"upi": 4, "display_name": "Oak", "in_season": True},
          ...
        }
      }
    """
    days = []
    for day_info in api_response.get("dailyInfo", []):
        d = day_info.get("date", {})
        try:
            day_date = date(d["year"], d["month"], d["day"])
        except (KeyError, ValueError):
            continue

        plants = {}
        for plant in day_info.get("plantInfo", []):
            code = plant.get("code")
            if not code:
                continue
            index_info = plant.get("indexInfo", {})
            upi = index_info.get("value", 0)
            plants[code] = {
                "upi": upi,
                "display_name": plant.get("displayName", code),
                "in_season": plant.get("inSeason", False),
            }

        days.append({"date": day_date, "plants": plants})

    return days
