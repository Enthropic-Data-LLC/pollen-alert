"""Entry point — fetch, score, and dispatch alerts."""

import os
import sys
import argparse
from datetime import date
from pathlib import Path

from pollen_alert import profile as profile_mod
from pollen_alert import fetcher, fetcher_openmeteo, mold_estimate, state as state_mod
from pollen_alert.scorer import score_day, flatten_sensitivities
from pollen_alert.outputs.console_output import ConsoleOutput


def load_config() -> dict:
    """Load env vars into a flat config dict."""
    return {
        "google_pollen_api_key": os.environ.get("GOOGLE_POLLEN_API_KEY", ""),
        "telegram_bot_token":    os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        "telegram_chat_id":      os.environ.get("TELEGRAM_CHAT_ID", ""),
        "smtp_host":             os.environ.get("SMTP_HOST", ""),
        "smtp_port":             int(os.environ.get("SMTP_PORT", "587")),
        "smtp_user":             os.environ.get("SMTP_USER", ""),
        "smtp_password":         os.environ.get("SMTP_PASSWORD", ""),
        "smtp_from":             os.environ.get("SMTP_FROM", ""),
        "smtp_to":               os.environ.get("SMTP_TO", ""),
        "webhook_url":           os.environ.get("WEBHOOK_URL", ""),
    }


def build_outputs(profile: dict, config: dict) -> list:
    outputs = []
    requested = profile.get("outputs", [])

    if "console" in requested:
        outputs.append(ConsoleOutput(profile, config))

    if "telegram" in requested:
        from pollen_alert.outputs.telegram_output import TelegramOutput
        outputs.append(TelegramOutput(profile, config))

    if "email" in requested:
        from pollen_alert.outputs.email_output import EmailOutput
        outputs.append(EmailOutput(profile, config))

    if "webhook" in requested:
        from pollen_alert.outputs.webhook_output import WebhookOutput
        outputs.append(WebhookOutput(profile, config))

    return outputs


def run(profile_path: str | None = None, dry_run: bool = False, force: bool = False) -> int:
    """Main logic. Returns exit code (0 = success, 1 = error)."""
    # Load env file if present
    _load_dotenv()

    config = load_config()

    try:
        profile = profile_mod.load(profile_path)
    except profile_mod.ProfileError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    lat = float(profile["location"]["lat"])
    lon = float(profile["location"]["lon"])
    sensitivities = flatten_sensitivities(profile["sensitivities"])

    # Fetch forecast — try Google first, fall back to Open-Meteo
    days_data = None
    source = "unknown"

    api_key = config.get("google_pollen_api_key")
    if api_key:
        try:
            raw = fetcher.fetch(lat, lon, days=5, api_key=api_key)
            days_data = fetcher.parse(raw)
            source = "Google Pollen API"
        except RuntimeError as e:
            print(f"WARNING: Google Pollen API failed: {e}", file=sys.stderr)

    if not days_data:
        try:
            print("INFO: Falling back to Open-Meteo Pollen API", file=sys.stderr)
            raw = fetcher_openmeteo.fetch(lat, lon, days=7)
            days_data = fetcher_openmeteo.parse(raw)
            source = "Open-Meteo"
        except RuntimeError as e:
            print(f"ERROR: Open-Meteo fallback also failed: {e}", file=sys.stderr)
            return 1

    if not days_data:
        print("ERROR: No forecast data returned", file=sys.stderr)
        return 1

    # Mold isn't measured by either pollen source — add a weather-based estimate
    mold_note = None
    try:
        mold_estimate.merge_into(days_data, mold_estimate.estimate(mold_estimate.fetch(lat, lon)))
    except RuntimeError as e:
        print(f"WARNING: mold estimate unavailable: {e}", file=sys.stderr)
        mold_note = "Mold is not monitored today (weather data unavailable)."

    today_data = days_data[0]
    today_score = score_day(today_data["plants"], sensitivities)

    # Build forecast list: (DayScore, date) for each day after today
    forecast = [
        (score_day(d["plants"], sensitivities), d["date"])
        for d in days_data[1:]
    ]

    # Detect incomplete fallback coverage: Open-Meteo only covers 6 plant types and
    # has no US pollen coverage in many areas. If the fallback returned no plant data,
    # or is missing high-sensitivity plants, warn and always send so the user knows.
    fallback_warning = None
    if source == "Open-Meteo":
        if not today_data["plants"]:
            # Fallback returned no data at all for this location
            fallback_warning = (
                "Google Pollen API unavailable and Open-Meteo has no pollen data for your area. "
                "Risk score cannot be calculated today."
            )
        else:
            # Fallback has some data but may be missing key plants
            missing_sensitive = [
                code for code, level in sensitivities.items()
                if level >= 3 and code not in today_data["plants"]
            ]
            if missing_sensitive:
                # Only list the top plants by sensitivity, not all 20+
                high_sensitivity = [c for c in missing_sensitive if sensitivities.get(c, 0) >= 4]
                listed = high_sensitivity[:6] or missing_sensitive[:4]
                fallback_warning = (
                    f"Google Pollen API unavailable. Open-Meteo fallback missing key plants: "
                    f"{', '.join(sorted(listed))} and others. Actual risk may be higher."
                )
        if fallback_warning:
            print("INFO: Fallback coverage gap — sending report with warning", file=sys.stderr)

    warning = " ".join(w for w in (fallback_warning, mold_note) if w) or None

    thresholds = profile.get("thresholds", {})
    notify_threshold = thresholds.get("notify_above_score", 30)
    cooldown_days = thresholds.get("cooldown_days", 7)

    today_is_high = today_score.score >= notify_threshold
    forecast_has_high = any(fs.score >= notify_threshold for fs, _ in forecast) if forecast else False

    # A single plant you react strongly to can be enough on its own (e.g. fall ragweed
    # with nothing else in the air never reaches the summed threshold).
    plant_threshold = thresholds.get("notify_plant_contribution", 8)
    hot_plants = _hot_plants(today_score, today_data["date"], forecast, plant_threshold)
    today_plant_hot = any(d == today_data["date"] for _, d in hot_plants.values())
    notice = _heads_up(hot_plants, today_data["date"])

    run_state = state_mod.load()
    days_since = state_mod.days_since_last_high(run_state)
    in_cooldown = days_since is not None and days_since <= cooldown_days

    # Determine send reason (None = don't send)
    send_reason = None
    if force:
        send_reason = "forced"
    elif fallback_warning is not None:
        send_reason = "fallback"
    elif today_is_high:
        send_reason = "high"
    elif today_plant_hot:
        send_reason = "plant"
    elif forecast_has_high:
        send_reason = "forecast"
    elif hot_plants:
        send_reason = "plant-forecast"
    elif in_cooldown:
        send_reason = f"cooldown ({days_since}d since last high)"

    # Update state when today is high
    if today_is_high or today_plant_hot:
        state_mod.save({**run_state, "last_high_date": date.today().isoformat()})

    if send_reason is None:
        print(
            f"INFO: Score {today_score.score} below threshold {notify_threshold}, "
            f"no forecast high, cooldown expired ({days_since}d) — no alert sent",
            file=sys.stderr,
        )
        ConsoleOutput(profile, config).send(today_score, today_data["date"], forecast or None,
                                            source=source, warning=warning)
        return 0

    print(f"INFO: Sending — reason: {send_reason}", file=sys.stderr)

    if dry_run:
        print("DRY RUN — would send to:", profile.get("outputs"))
        ConsoleOutput(profile, config).send(today_score, today_data["date"], forecast or None,
                                            source=source, warning=warning, notice=notice)
        return 0

    outputs = build_outputs(profile, config)
    errors = []
    for output in outputs:
        try:
            output.send(today_score, today_data["date"], forecast or None,
                        source=source, warning=warning, notice=notice)
        except Exception as e:
            errors.append(f"{type(output).__name__}: {e}")
            print(f"ERROR in {type(output).__name__}: {e}", file=sys.stderr)

    if errors:
        return 1
    return 0


def _hot_plants(today_score, today_date, forecast, threshold: float) -> dict:
    """{plant code: (display_name, first date)} for plants at or above threshold, today or forecast."""
    hot = {}
    for day_score, day_date in [(today_score, today_date)] + list(forecast or []):
        for p in day_score.plant_scores:
            if p.contribution >= threshold and p.code not in hot:
                hot[p.code] = (p.display_name, day_date)
    return hot


def _heads_up(hot_plants: dict, today_date) -> str | None:
    if not hot_plants:
        return None
    parts = [
        f"{name} ({'today' if d == today_date else d.strftime('%A')})"
        for name, d in sorted(hot_plants.values(), key=lambda x: x[1])
    ]
    return f"Heads-up: {', '.join(parts)} at a level you react to — good time to start antihistamines."


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader — no dependencies required."""
    env_file = Path(path)
    if not env_file.exists():
        return
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def main() -> None:
    parser = argparse.ArgumentParser(description="PollenAlert — personalized pollen forecast")
    parser.add_argument("--profile", help="Path to profile.json", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Print output without sending")
    parser.add_argument("--force", action="store_true", help="Send alert regardless of score threshold")
    args = parser.parse_args()

    sys.exit(run(profile_path=args.profile, dry_run=args.dry_run, force=args.force))


if __name__ == "__main__":
    main()
