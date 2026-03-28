"""Webhook output — JSON POST to any HTTP endpoint (n8n, Node-RED, Home Assistant, etc.)."""

import json
import urllib.request
import urllib.error
from datetime import date

from pollen_alert.outputs.base import BaseOutput
from pollen_alert.scorer import DayScore, PLANT_CATEGORY


class WebhookOutput(BaseOutput):
    def send(self, today: DayScore, today_date: date, tomorrow: DayScore | None = None) -> None:
        url = self.config.get("webhook_url", "")
        if not url:
            raise RuntimeError("WEBHOOK_URL not set")

        payload = _build_payload(self.profile, today, today_date, tomorrow)
        _post(url, payload)


def _build_payload(
    profile: dict,
    today: DayScore,
    today_date: date,
    tomorrow: DayScore | None,
) -> dict:
    location = profile.get("location", {})
    threats = [
        {
            "plant": p.code,
            "display_name": p.display_name,
            "category": PLANT_CATEGORY.get(p.code, "weeds"),
            "upi": p.upi,
            "sensitivity": p.sensitivity,
            "contribution": round(p.contribution, 2),
        }
        for p in today.top_threats
        if p.contribution > 0
    ]

    payload = {
        "profile_name": profile.get("profile_name", ""),
        "date": today_date.isoformat(),
        "location": {
            "zip": location.get("zip", ""),
            "city": location.get("city", ""),
            "lat": location.get("lat"),
            "lon": location.get("lon"),
        },
        "personal_score": today.score,
        "risk_label": today.risk_label,
        "risk_color": today.color,
        "top_threats": threats,
    }

    if tomorrow is not None:
        payload["forecast_tomorrow"] = {
            "score": tomorrow.score,
            "risk_label": tomorrow.risk_label,
        }

    return payload


def _post(url: str, payload: dict) -> None:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            pass  # 2xx is success; caller can ignore response body
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"Webhook HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Webhook network error: {e.reason}") from e
