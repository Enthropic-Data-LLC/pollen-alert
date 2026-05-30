# pollen-alert

Personalized daily pollen forecast with Telegram, email, and webhook alerts.

Fetches pollen data from the Google Pollen API (up to 5 days) with Open-Meteo as a fallback (up to 7 days), scores it against your personal sensitivity profile, and sends alerts via your configured outputs.

## Features

- **Personalized scoring** — each plant weighted by your sensitivity level (0–4)
- **Multi-day forecast** — today's threat summary + full forecast through available days
- **Multiple outputs** — Telegram, email (HTML), webhook, console
- **Smart thresholds** — only alerts when your personal score exceeds your configured threshold
- **Automatic fallback** — Google Pollen API → Open-Meteo if Google is unavailable

## Setup

### 1. Install

```bash
python -m venv venv
source venv/bin/activate
pip install -e .
```

### 2. Configure your profile

Copy the example and edit:

```bash
cp config/profile.example.json config/profile.json
```

Key fields in `profile.json`:

| Field | Description |
|-------|-------------|
| `profile_name` | Your name (appears in alerts) |
| `location.lat/lon` | Your coordinates |
| `location.city` | Display name for alerts |
| `sensitivities` | Per-plant sensitivity 0–4 (0 = not sensitive, 4 = highly allergic) |
| `thresholds.notify_above_score` | Minimum personal score to trigger an alert (0–100) |
| `thresholds.critical_score` | Score treated as critical severity |
| `outputs` | List of `"telegram"`, `"email"`, `"webhook"`, `"console"` |

### 3. Configure environment variables

Copy and edit the example:

```bash
cp config/settings.example.env .env
```

| Variable | Required for |
|----------|-------------|
| `GOOGLE_POLLEN_API_KEY` | Google Pollen API (preferred source) |
| `TELEGRAM_BOT_TOKEN` | Telegram output |
| `TELEGRAM_CHAT_ID` | Telegram output |
| `SMTP_HOST/USER/PASSWORD/FROM/TO` | Email output |
| `WEBHOOK_URL` | Webhook output |

## Usage

```bash
# Send alert if score exceeds threshold
python pollen_alert/main.py

# Force send regardless of threshold
python pollen_alert/main.py --force

# Preview output without sending
python pollen_alert/main.py --dry-run

# Use a specific profile
python pollen_alert/main.py --profile /path/to/profile.json
```

## Scoring

Each plant's contribution = `UPI × sensitivity`, where UPI is the Universal Pollen Index (0–5) from the API and sensitivity is your configured level (0–4). Contributions are summed, capped at 100, and mapped to a risk band:

| Score | Color | Label |
|-------|-------|-------|
| 0–19 | 🟢 Green | Low |
| 20–39 | 🟡 Yellow | Moderate |
| 40–59 | 🟠 Orange | High |
| 60–79 | 🔴 Red | Very High |
| 80–100 | 🟣 Purple | Extreme |

## Data Sources

- **[Google Pollen API](https://developers.google.com/maps/documentation/pollen)** — primary source, up to 5-day forecast
- **[Open-Meteo](https://open-meteo.com/en/docs/air-quality-api)** — fallback (no API key required), up to 7-day forecast

## Automation

To run the daily alert automatically via systemd (example for otto.local):

```bash
# /etc/systemd/system/pollen-alert.service
[Unit]
Description=PollenAlert daily report

[Service]
WorkingDirectory=/home/pi/projects/pollen-alert
ExecStart=/home/pi/projects/pollen-alert/venv/bin/python pollen_alert/main.py --force
EnvironmentFile=/home/pi/projects/pollen-alert/.env

# /etc/systemd/system/pollen-alert.timer
[Timer]
OnCalendar=*-*-* 07:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

## Project Structure

```
pollen_alert/
├── main.py              # Entry point — fetch, score, dispatch
├── fetcher.py           # Google Pollen API client (max 5 days)
├── fetcher_openmeteo.py # Open-Meteo fallback (max 7 days)
├── profile.py           # Profile loader and validator
├── scorer.py            # Personal risk scoring engine
└── outputs/
    ├── console_output.py  # stdout + canonical message formatter
    ├── telegram_output.py # Telegram Bot API
    ├── email_output.py    # SMTP / HTML email
    └── webhook_output.py  # JSON POST to any endpoint
config/
├── profile.example.json   # Example sensitivity profile
└── settings.example.env   # Example environment variables
```

---

## About

Built and maintained by **[Enthropic Data](https://enthropicdata.com)** — an AI product studio based in Weddington, NC.

Follow our work at [enthropicdata.com](https://enthropicdata.com) or explore our other open source projects at [github.com/Enthropic-Data-LLC](https://github.com/Enthropic-Data-LLC).
