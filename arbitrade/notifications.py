from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Telegram Bot API base URL (no credential in code — token is read from config)
_TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/sendMessage"


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

    def reset(self, key: str) -> None:
        self.last_sent.pop(key, None)


class TelegramNotifier:
    def __init__(self, token: str | None, chat_id: str | None, limiter: NotificationLimiter | None = None):
        self.token = token
        self.chat_id = chat_id
        self.limiter = limiter or NotificationLimiter()
        self._configured = bool(token and chat_id)

    def notify(self, event_type: str, message: str) -> bool:
        """Send a Telegram notification. Returns True if sent, False otherwise."""
        if not self._configured:
            logger.debug("Telegram not configured, skipping notification: %s", event_type)
            return False
        if not self.limiter.allowed(event_type):
            logger.debug("Telegram rate-limited for event: %s", event_type)
            return False
        return self._send(message)

    def _send(self, message: str) -> bool:
        try:
            import urllib.request
            import urllib.parse
            import json as _json
            url = _TELEGRAM_API_BASE.format(token=self.token)
            payload = _json.dumps({"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"}).encode()
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = _json.loads(resp.read())
                if result.get("ok"):
                    logger.debug("Telegram notification sent")
                    return True
                logger.warning("Telegram API error: %s", result)
                return False
        except Exception as exc:
            logger.warning("Telegram send failed: %s", exc)
            return False

    def notify_startup(self, mode: str) -> bool:
        return self.notify("startup", f"🚀 <b>Arbitrade started</b>\nMode: <code>{mode}</code>")

    def notify_shutdown(self) -> bool:
        return self.notify("shutdown", "🛑 <b>Arbitrade stopped</b>")

    def notify_opportunity(self, symbol: str, buy_exchange: str, sell_exchange: str, net_pnl: float) -> bool:
        msg = (
            f"📈 <b>Opportunity detected</b>\n"
            f"Symbol: <code>{symbol}</code>\n"
            f"Buy: {buy_exchange} → Sell: {sell_exchange}\n"
            f"Expected PnL: <code>{net_pnl:.4f}</code>"
        )
        return self.notify("opportunity", msg)

    def notify_trade_executed(self, symbol: str, realized_pnl: float, state: str) -> bool:
        icon = "✅" if state == "COMPLETED" else "⚠️"
        msg = (
            f"{icon} <b>Trade {state}</b>\n"
            f"Symbol: <code>{symbol}</code>\n"
            f"Realized PnL: <code>{realized_pnl:.4f}</code>"
        )
        return self.notify("trade_executed", msg)

    def notify_risk_rejection(self, rule: str, reason: str) -> bool:
        msg = f"🚫 <b>Risk rejection</b>\nRule: {rule}\nReason: {reason}"
        return self.notify(f"risk_{rule}", msg)

    def notify_circuit_breaker(self, reason: str) -> bool:
        return self.notify("circuit_breaker", f"⛔ <b>Circuit breaker opened</b>\nReason: {reason}")

    def notify_exchange_error(self, exchange: str, error: str) -> bool:
        return self.notify(f"exchange_error_{exchange}", f"🔴 <b>Exchange error: {exchange}</b>\n{error}")

    def notify_recovery(self, details: str) -> bool:
        return self.notify("recovery", f"🔄 <b>Recovery event</b>\n{details}")
