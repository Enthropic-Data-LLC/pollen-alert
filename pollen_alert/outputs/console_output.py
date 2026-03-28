"""Console / stdout output — also used as the canonical message formatter."""

from datetime import date
from pollen_alert.scorer import DayScore, PlantScore
from pollen_alert.outputs.base import BaseOutput

RISK_EMOJI = {
    "green":  "🟢",
    "yellow": "🟡",
    "orange": "🟠",
    "red":    "🔴",
    "purple": "🟣",
}

CATEGORY_EMOJI = {
    "trees":   "🌳",
    "grasses": "🌾",
    "weeds":   "🌱",
    "mold":    "🍄",
}

from pollen_alert.scorer import PLANT_CATEGORY


def format_message(
    profile: dict,
    today: DayScore,
    today_date: date,
    tomorrow: DayScore | None = None,
) -> str:
    name = profile.get("profile_name", "You")
    location = profile.get("location", {})
    zip_code = location.get("zip", "")
    city = location.get("city", zip_code)

    emoji = RISK_EMOJI.get(today.color, "⚪")
    lines = [
        f"🌿 PollenAlert — {today_date.strftime('%A, %B %-d')}",
        f"📍 {city}" + (f" ({zip_code})" if zip_code and city != zip_code else ""),
        "",
        f"{emoji} Personal Risk Score: {today.score}/100 — {today.risk_label.upper()}",
    ]

    threats = [p for p in today.top_threats if p.contribution > 0]
    if threats:
        lines.append("")
        lines.append("Active Threats:")
        for p in threats:
            cat = PLANT_CATEGORY.get(p.code, "weeds")
            cat_emoji = CATEGORY_EMOJI.get(cat, "🌿")
            severity = _contribution_label(p.contribution)
            lines.append(
                f"  {cat_emoji} {p.display_name:<12} UPI {p.upi}/5  ×  "
                f"Your sensitivity {p.sensitivity}  →  {severity}"
            )
    else:
        lines.append("")
        lines.append("No significant active threats for your profile today.")

    if tomorrow is not None:
        t_emoji = RISK_EMOJI.get(tomorrow.color, "⚪")
        direction = _trend(today.score, tomorrow.score)
        lines.append("")
        lines.append(
            f"Tomorrow: {t_emoji} {tomorrow.risk_label} (score: {tomorrow.score}) — {direction}"
        )

    lines += [
        "",
        "---",
        "Source: Google Pollen API | pollen-alert v1.0",
    ]
    return "\n".join(lines)


def _contribution_label(contribution: float) -> str:
    if contribution >= 16:
        return "Critical"
    if contribution >= 9:
        return "High"
    if contribution >= 4:
        return "Moderate"
    return "Low"


def _trend(today_score: int, tomorrow_score: int) -> str:
    delta = tomorrow_score - today_score
    if delta <= -10:
        return "improving"
    if delta >= 10:
        return "worsening"
    return "similar"


class ConsoleOutput(BaseOutput):
    def send(self, today: DayScore, today_date: date, tomorrow: DayScore | None = None) -> None:
        msg = format_message(self.profile, today, today_date, tomorrow)
        print(msg)
