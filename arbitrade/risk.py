from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from arbitrade.config import RiskConfig
from arbitrade.models import Exposure, Opportunity


@dataclass
class CircuitBreaker:
    is_open: bool = False
    opened_at: datetime | None = None
    reason: str | None = None

    def open(self, reason: str) -> None:
        self.is_open = True
        self.opened_at = datetime.now(timezone.utc)
        self.reason = reason

    def close(self) -> None:
        self.is_open = False
        self.opened_at = None
        self.reason = None


@dataclass
class RiskManager:
    config: RiskConfig
    circuit_breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
    active_opportunities: int = 0
    cooldown_until: datetime | None = None

    def can_trade(self, opportunity: Opportunity, exposure: Exposure) -> tuple[bool, str]:
        if self.circuit_breaker.is_open:
            return False, "circuit_breaker_open"
        if self.cooldown_until and datetime.now(timezone.utc) < self.cooldown_until:
            return False, "cooldown"
        if self.active_opportunities >= self.config.max_concurrent_opportunities:
            return False, "max_concurrent_opportunities"
        if opportunity.required_capital > self.config.max_trade_size:
            return False, "max_trade_size"
        buy_exchange_exposure = exposure.by_exchange.get(opportunity.buy_exchange, 0.0)
        if buy_exchange_exposure + opportunity.required_capital > self.config.max_exposure_per_exchange:
            return False, "max_exposure_per_exchange"
        base_asset = opportunity.symbol.split("/")[0]
        asset_exposure = exposure.by_asset.get(base_asset, 0.0)
        if asset_exposure + opportunity.required_capital > self.config.max_exposure_per_asset:
            return False, "max_exposure_per_asset"
        if abs(exposure.daily_pnl) > self.config.max_daily_loss and exposure.daily_pnl < 0:
            self.circuit_breaker.open("max_daily_loss")
            return False, "max_daily_loss"
        if exposure.peak_equity > 0:
            drawdown = (exposure.peak_equity - exposure.equity) / exposure.peak_equity
            if drawdown > self.config.max_drawdown:
                self.circuit_breaker.open("max_drawdown")
                return False, "max_drawdown"
        return True, "ok"

    def register_failed_execution(self) -> None:
        self.cooldown_until = datetime.now(timezone.utc) + timedelta(seconds=self.config.cooldown_seconds)
