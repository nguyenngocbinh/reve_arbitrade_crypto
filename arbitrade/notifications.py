from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


@dataclass
class NotificationLimiter:
    min_interval_seconds: int = 5
    last_sent: dict[str, datetime] = field(default_factory=dict)

    def allowed(self, key: str) -> bool:
        now = datetime.now(timezone.utc)
        last = self.last_sent.get(key)
        if last and now - last < timedelta(seconds=self.min_interval_seconds):
            return False
        self.last_sent[key] = now
        return True


class TelegramNotifier:
    def __init__(self, token: str | None, chat_id: str | None, limiter: NotificationLimiter | None = None):
        self.token = token
        self.chat_id = chat_id
        self.limiter = limiter or NotificationLimiter()

    def notify(self, event_type: str, message: str) -> bool:
        if not self.token or not self.chat_id:
            return False
        if not self.limiter.allowed(event_type):
            return False
        return True
