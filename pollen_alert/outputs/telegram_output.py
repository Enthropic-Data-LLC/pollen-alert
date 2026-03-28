"""Telegram output — sends formatted alert via Bot API."""

import json
import urllib.request
import urllib.error
from datetime import date

from pollen_alert.outputs.base import BaseOutput
from pollen_alert.outputs.console_output import format_message
from pollen_alert.scorer import DayScore

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramOutput(BaseOutput):
    def send(self, today: DayScore, today_date: date, tomorrow: DayScore | None = None) -> None:
        token = self.config.get("telegram_bot_token", "")
        chat_id = self.config.get("telegram_chat_id", "")
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
        if not chat_id:
            raise RuntimeError("TELEGRAM_CHAT_ID not set")

        text = format_message(self.profile, today, today_date, tomorrow)
        _send(token, chat_id, text)


def _send(token: str, chat_id: str, text: str) -> None:
    url = TELEGRAM_API.format(token=token)
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode()

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            if not result.get("ok"):
                raise RuntimeError(f"Telegram API error: {result}")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"Telegram HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Telegram network error: {e.reason}") from e
