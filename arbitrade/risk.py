from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from arbitrade.config import RiskConfig
from arbitrade.models import Exposure, Opportunity, RiskDecision

logger = logging.getLogger(__name__)


@dataclass
class CircuitBreaker:
    is_open: bool = False
    opened_at: datetime | None = None
    reason: str | None = None

    def open(self, reason: str) -> None:
        self.is_open = True
        self.opened_at = datetime.now(timezone.utc)
        self.reason = reason
        logger.warning("Circuit breaker opened: %s", reason)

    def close(self) -> None:
        self.is_open = False
        self.opened_at = None
        self.reason = None
        logger.info("Circuit breaker closed")


@dataclass
class RiskManager:
    config: RiskConfig
    circuit_breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
    active_opportunities: int = 0
    cooldown_until: datetime | None = None

    def can_trade(self, opportunity: Opportunity, exposure: Exposure) -> RiskDecision:
        if self.circuit_breaker.is_open:
            return RiskDecision(
                approved=False, reason="circuit_breaker_open",
                rule="circuit_breaker", current_value=1.0, configured_limit=0.0
            )
        if self.cooldown_until and datetime.now(timezone.utc) < self.cooldown_until:
            return RiskDecision(approved=False, reason="cooldown", rule="cooldown")
        if self.active_opportunities >= self.config.max_concurrent_opportunities:
            return RiskDecision(
                approved=False, reason="max_concurrent_opportunities",
                rule="max_concurrent_opportunities",
                current_value=float(self.active_opportunities),
                configured_limit=float(self.config.max_concurrent_opportunities),
            )
        if opportunity.required_capital > self.config.max_trade_size:
            return RiskDecision(
                approved=False, reason="max_trade_size",
                rule="max_trade_size",
                current_value=opportunity.required_capital,
                configured_limit=self.config.max_trade_size,
            )
        buy_exchange_exposure = exposure.by_exchange.get(opportunity.buy_exchange, 0.0)
        if buy_exchange_exposure + opportunity.required_capital > self.config.max_exposure_per_exchange:
            return RiskDecision(
                approved=False, reason="max_exposure_per_exchange",
                rule="max_exposure_per_exchange",
                current_value=buy_exchange_exposure + opportunity.required_capital,
                configured_limit=self.config.max_exposure_per_exchange,
            )
        base_asset = opportunity.symbol.split("/")[0]
        asset_exposure = exposure.by_asset.get(base_asset, 0.0)
        if asset_exposure + opportunity.required_capital > self.config.max_exposure_per_asset:
            return RiskDecision(
                approved=False, reason="max_exposure_per_asset",
                rule="max_exposure_per_asset",
                current_value=asset_exposure + opportunity.required_capital,
                configured_limit=self.config.max_exposure_per_asset,
            )
        if abs(exposure.daily_pnl) > self.config.max_daily_loss and exposure.daily_pnl < 0:
            self.circuit_breaker.open("max_daily_loss")
            return RiskDecision(
                approved=False, reason="max_daily_loss",
                rule="max_daily_loss",
                current_value=abs(exposure.daily_pnl),
                configured_limit=self.config.max_daily_loss,
            )
        if exposure.peak_equity > 0:
            drawdown = (exposure.peak_equity - exposure.equity) / exposure.peak_equity
            if drawdown > self.config.max_drawdown:
                self.circuit_breaker.open("max_drawdown")
                return RiskDecision(
                    approved=False, reason="max_drawdown",
                    rule="max_drawdown",
                    current_value=drawdown,
                    configured_limit=self.config.max_drawdown,
                )
        logger.debug("Risk approved opportunity %s", opportunity.id)
        return RiskDecision(approved=True, reason="ok")

    # Backward-compat helper for tests that call can_trade and unpack a 2-tuple
    def can_trade_tuple(self, opportunity: Opportunity, exposure: Exposure) -> tuple[bool, str]:
        decision = self.can_trade(opportunity, exposure)
        return decision.approved, decision.reason

    def register_failed_execution(self) -> None:
        self.cooldown_until = datetime.now(timezone.utc) + timedelta(seconds=self.config.cooldown_seconds)
