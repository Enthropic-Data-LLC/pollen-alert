"""Email output — HTML-formatted alert via SMTP."""

import smtplib
import ssl
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from pollen_alert.outputs.base import BaseOutput
from pollen_alert.outputs.console_output import format_message, RISK_EMOJI
from pollen_alert.scorer import DayScore, PLANT_CATEGORY
from pollen_alert.scorer import RISK_BANDS

_BAND_COLORS = {
    "green":  "#2ea043",
    "yellow": "#d29922",
    "orange": "#e3712a",
    "red":    "#da3633",
    "purple": "#8957e5",
}

_CATEGORY_ICONS = {
    "trees":   "🌳",
    "grasses": "🌾",
    "weeds":   "🌱",
    "mold":    "🍄",
}


class EmailOutput(BaseOutput):
    def send(self, today: DayScore, today_date: date, forecast: list | None = None,
             source: str = "Google Pollen API", warning: str | None = None,
             notice: str | None = None) -> None:
        cfg = self.config
        required = ("smtp_host", "smtp_user", "smtp_password", "smtp_from", "smtp_to")
        missing = [k for k in required if not cfg.get(k)]
        if missing:
            raise RuntimeError(f"Email config missing: {missing}")

        profile_name = self.profile.get("profile_name", "You")
        location = self.profile.get("location", {})
        city = location.get("city", location.get("zip", ""))
        date_str = today_date.strftime("%A, %B %-d")

        subject = (
            f"🌿 PollenAlert — {date_str} — {today.risk_label} ({today.score}/100)"
        )

        plain = format_message(self.profile, today, today_date, forecast, source=source,
                               warning=warning, notice=notice)
        html = _render_html(self.profile, today, today_date, forecast, source=source,
                            warning=warning, notice=notice)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = cfg["smtp_from"]
        msg["To"] = cfg["smtp_to"]
        msg.attach(MIMEText(plain, "plain"))
        msg.attach(MIMEText(html, "html"))

        port = cfg.get("smtp_port", 587)
        context = ssl.create_default_context()
        with smtplib.SMTP(cfg["smtp_host"], port) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(cfg["smtp_user"], cfg["smtp_password"])
            server.sendmail(cfg["smtp_from"], cfg["smtp_to"], msg.as_string())


def _render_html(profile: dict, today: DayScore, today_date: date, forecast: list | None,
                 source: str = "Google Pollen API", warning: str | None = None,
                 notice: str | None = None) -> str:
    name = profile.get("profile_name", "You")
    location = profile.get("location", {})
    city = location.get("city", location.get("zip", ""))
    date_str = today_date.strftime("%A, %B %-d")

    band_color = _BAND_COLORS.get(today.color, "#444")
    emoji = RISK_EMOJI.get(today.color, "⚪")
    threats = [p for p in today.top_threats if p.contribution > 0]

    threat_rows = ""
    for p in threats:
        cat = PLANT_CATEGORY.get(p.code, "weeds")
        icon = _CATEGORY_ICONS.get(cat, "🌿")
        threat_rows += f"""
        <tr>
          <td style="padding:6px 12px;">{icon} {p.display_name}{" ☢️ <strong>KRYPTONITE</strong>" if p.kryptonite else ""}</td>
          <td style="padding:6px 12px; text-align:center;">{p.upi}/5</td>
          <td style="padding:6px 12px; text-align:center;">{p.sensitivity}/4</td>
          <td style="padding:6px 12px; text-align:center; color:{band_color}; font-weight:bold;">
            {_contribution_label(p.contribution)}
          </td>
        </tr>"""

    forecast_section = ""
    if forecast:
        rows = ""
        prev_score = today.score
        for i, (day_score, day_date) in enumerate(forecast):
            t_color = _BAND_COLORS.get(day_score.color, "#444")
            t_emoji = RISK_EMOJI.get(day_score.color, "⚪")
            direction = _trend(prev_score, day_score.score)
            label = "Tomorrow" if i == 0 else day_date.strftime("%A")
            rows += f"<p style='margin:4px 0;'><strong>{label}:</strong> {t_emoji} <span style='color:{t_color};font-weight:bold;'>{day_score.risk_label}</span> (score: {day_score.score}) — {direction}</p>"
            prev_score = day_score.score
        forecast_section = f"""
        <div style="margin-top:16px; padding:12px; background:#f6f8fa; border-radius:6px;">
          {rows}
        </div>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:system-ui,sans-serif; max-width:600px; margin:0 auto; color:#24292f;">
  <div style="background:{band_color}; color:#fff; padding:20px 24px; border-radius:8px 8px 0 0;">
    <h2 style="margin:0;">🌿 PollenAlert</h2>
    <p style="margin:4px 0 0;">{date_str} &middot; {city}</p>
  </div>
  <div style="border:1px solid #d0d7de; border-top:none; padding:20px 24px; border-radius:0 0 8px 8px;">
    <p style="font-size:24px; font-weight:bold; margin:0 0 4px;">
      {emoji} {today.score}/100 &mdash; {today.risk_label}
    </p>
    <p style="color:#57606a; margin:0 0 20px;">Personal risk score for {name}</p>
    {f'<p style="padding:10px 12px; background:#fff8c5; border-radius:6px;">🔔 {notice}</p>' if notice else ""}

    {"<table style='width:100%;border-collapse:collapse;'><thead><tr style='background:#f6f8fa;'><th style='padding:8px 12px;text-align:left;'>Plant</th><th style='padding:8px 12px;'>UPI</th><th style='padding:8px 12px;'>Sensitivity</th><th style='padding:8px 12px;'>Impact</th></tr></thead><tbody>" + threat_rows + "</tbody></table>" if threats else "<p style='color:#57606a;'>No significant active threats for your profile today.</p>"}

    {forecast_section}

    <hr style="border:none;border-top:1px solid #d0d7de;margin:20px 0;">
    <p style="font-size:12px; color:#57606a; margin:0;">
      Source: {source} &mdash;
      <a href="https://github.com/sohocs509/pollen-alert" style="color:#0969da;">pollen-alert v1.0</a>
    </p>
  </div>
</body>
</html>"""


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
