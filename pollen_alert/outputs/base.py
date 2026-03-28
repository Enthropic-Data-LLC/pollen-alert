"""Abstract base class for all output plugins."""

from abc import ABC, abstractmethod
from datetime import date
from pollen_alert.scorer import DayScore


class BaseOutput(ABC):
    def __init__(self, profile: dict, config: dict):
        """
        Args:
            profile: full parsed profile.json dict
            config:  flat dict of env/config values (API keys, tokens, etc.)
        """
        self.profile = profile
        self.config = config

    @abstractmethod
    def send(self, today: DayScore, today_date: date, tomorrow: DayScore | None = None) -> None:
        """Deliver the alert. Raise on failure."""
        ...

    def should_notify(self, score: int) -> bool:
        threshold = self.profile.get("thresholds", {}).get("notify_above_score", 30)
        return score >= threshold

    def is_critical(self, score: int) -> bool:
        threshold = self.profile.get("thresholds", {}).get("critical_score", 70)
        return score >= threshold
