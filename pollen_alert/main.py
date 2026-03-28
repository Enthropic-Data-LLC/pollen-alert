"""Entry point — fetch, score, and dispatch alerts."""

import os
import sys
import argparse
from datetime import date
from pathlib import Path

from pollen_alert import profile as profile_mod
from pollen_alert import fetcher, fetcher_openmeteo
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
            raw = fetcher.fetch(lat, lon, days=2, api_key=api_key)
            days_data = fetcher.parse(raw)
            source = "Google Pollen API"
        except RuntimeError as e:
            print(f"WARNING: Google Pollen API failed: {e}", file=sys.stderr)

    if not days_data:
        try:
            print("INFO: Falling back to Open-Meteo Pollen API", file=sys.stderr)
            raw = fetcher_openmeteo.fetch(lat, lon, days=2)
            days_data = fetcher_openmeteo.parse(raw)
            source = "Open-Meteo"
        except RuntimeError as e:
            print(f"ERROR: Open-Meteo fallback also failed: {e}", file=sys.stderr)
            return 1

    if not days_data:
        print("ERROR: No forecast data returned", file=sys.stderr)
        return 1

    today_data = days_data[0]
    tomorrow_data = days_data[1] if len(days_data) > 1 else None

    today_score = score_day(today_data["plants"], sensitivities)
    tomorrow_score = score_day(tomorrow_data["plants"], sensitivities) if tomorrow_data else None

    notify_threshold = profile.get("thresholds", {}).get("notify_above_score", 30)
    should_notify = force or today_score.score >= notify_threshold

    if not should_notify:
        print(
            f"INFO: Score {today_score.score} below notify threshold {notify_threshold} — no alert sent",
            file=sys.stderr,
        )
        # Still print to console for logging purposes
        ConsoleOutput(profile, config).send(today_score, today_data["date"], tomorrow_score)
        return 0

    if dry_run:
        print("DRY RUN — would send to:", profile.get("outputs"))
        ConsoleOutput(profile, config).send(today_score, today_data["date"], tomorrow_score)
        print(f"\nSource: {source}")
        return 0

    outputs = build_outputs(profile, config)
    errors = []
    for output in outputs:
        try:
            output.send(today_score, today_data["date"], tomorrow_score)
        except Exception as e:
            errors.append(f"{type(output).__name__}: {e}")
            print(f"ERROR in {type(output).__name__}: {e}", file=sys.stderr)

    if errors:
        return 1
    return 0


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
