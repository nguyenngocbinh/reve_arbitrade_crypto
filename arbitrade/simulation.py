from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from arbitrade.models import FillRecord, Opportunity, OrderRecord, utcnow
from arbitrade.opportunity import estimate_fees, estimate_slippage

logger = logging.getLogger(__name__)


@dataclass
class PaperAccount:
    balances: dict[str, float] = field(default_factory=lambda: {"USDT": 100_000.0, "BTC": 1.0, "ETH": 10.0})
    positions: dict[str, float] = field(default_factory=dict)  # asset -> quantity
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    orders: dict[str, OrderRecord] = field(default_factory=dict)
    fills: list[FillRecord] = field(default_factory=list)

    def get_balance(self, asset: str) -> float:
        return self.balances.get(asset, 0.0)

    def total_equity(self, mark_prices: dict[str, float] | None = None) -> float:
        usdt = self.balances.get("USDT", 0.0)
        if not mark_prices:
            return usdt
        for asset, qty in self.positions.items():
            price = mark_prices.get(asset, 0.0)
            usdt += qty * price
        return usdt


@dataclass(frozen=True)
class PaperExecutionResult:
    accepted: bool
    reason: str
    filled_quantity: float
    avg_fill_price: float
    fee: float
    slippage: float
    order_id: str = ""


class PaperExecutor:
    def __init__(self, fee_bps: float, slippage_bps: float):
        self.fee_bps = fee_bps
        self.slippage_bps = slippage_bps

    def execute_buy(
        self,
        account: PaperAccount,
        opportunity: Opportunity,
        available_liquidity: float,
        correlation_id: str | None = None,
    ) -> PaperExecutionResult:
        """Execute the buy leg of an arbitrage opportunity."""
        if available_liquidity <= 0:
            return PaperExecutionResult(False, "insufficient_liquidity", 0.0, 0.0, 0.0, 0.0)
        if account.balances.get("USDT", 0.0) < opportunity.required_capital:
            return PaperExecutionResult(False, "insufficient_balance", 0.0, 0.0, 0.0, 0.0)

        fill_qty = min(opportunity.quantity, available_liquidity)
        fill_price = opportunity.executable_buy_price
        notional = fill_qty * fill_price
        fee = estimate_fees(notional, self.fee_bps) / 2  # buy side only
        slip = estimate_slippage(notional, self.slippage_bps)

        # Deduct USDT, credit base asset
        account.balances["USDT"] = account.balances.get("USDT", 0.0) - notional - fee - slip
        base_asset = opportunity.symbol.split("/")[0]
        account.balances[base_asset] = account.balances.get(base_asset, 0.0) + fill_qty
        account.positions[base_asset] = account.positions.get(base_asset, 0.0) + fill_qty

        order_id = str(uuid4())
        order = OrderRecord(
            id=order_id,
            opportunity_id=opportunity.id,
            correlation_id=correlation_id or order_id,
            exchange=opportunity.buy_exchange,
            symbol=opportunity.symbol,
            side="buy",
            quantity=fill_qty,
            price=fill_price,
            status="filled",
            filled_quantity=fill_qty,
            avg_fill_price=fill_price,
            fee=fee,
        )
        account.orders[order_id] = order
        fill = FillRecord(
            id=str(uuid4()),
            order_id=order_id,
            exchange=opportunity.buy_exchange,
            symbol=opportunity.symbol,
            side="buy",
            quantity=fill_qty,
            price=fill_price,
            fee=fee,
        )
        account.fills.append(fill)

        logger.debug("Paper BUY %.6f %s @ %.2f on %s (fee=%.4f)", fill_qty, opportunity.symbol, fill_price, opportunity.buy_exchange, fee)
        return PaperExecutionResult(True, "ok", fill_qty, fill_price, fee, slip, order_id=order_id)

    def execute_sell(
        self,
        account: PaperAccount,
        opportunity: Opportunity,
        fill_qty: float,
        buy_fill_price: float,
        correlation_id: str | None = None,
    ) -> PaperExecutionResult:
        """Execute the sell leg of an arbitrage opportunity."""
        base_asset = opportunity.symbol.split("/")[0]
        if account.balances.get(base_asset, 0.0) < fill_qty:
            return PaperExecutionResult(False, "insufficient_asset_balance", 0.0, 0.0, 0.0, 0.0)

        sell_price = opportunity.executable_sell_price
        notional = fill_qty * sell_price
        fee = estimate_fees(notional, self.fee_bps) / 2  # sell side only
        slip = estimate_slippage(notional, self.slippage_bps)

        # Deduct base asset, credit USDT
        account.balances[base_asset] = account.balances.get(base_asset, 0.0) - fill_qty
        account.positions[base_asset] = account.positions.get(base_asset, 0.0) - fill_qty
        proceeds = notional - fee - slip
        account.balances["USDT"] = account.balances.get("USDT", 0.0) + proceeds

        # Calculate realized PnL
        buy_notional = fill_qty * buy_fill_price
        buy_fee = estimate_fees(buy_notional, self.fee_bps) / 2
        buy_slip = estimate_slippage(buy_notional, self.slippage_bps)
        realized = proceeds - (buy_notional + buy_fee + buy_slip)
        account.realized_pnl += realized

        order_id = str(uuid4())
        order = OrderRecord(
            id=order_id,
            opportunity_id=opportunity.id,
            correlation_id=correlation_id or order_id,
            exchange=opportunity.sell_exchange,
            symbol=opportunity.symbol,
            side="sell",
            quantity=fill_qty,
            price=sell_price,
            status="filled",
            filled_quantity=fill_qty,
            avg_fill_price=sell_price,
            fee=fee,
        )
        account.orders[order_id] = order
        fill = FillRecord(
            id=str(uuid4()),
            order_id=order_id,
            exchange=opportunity.sell_exchange,
            symbol=opportunity.symbol,
            side="sell",
            quantity=fill_qty,
            price=sell_price,
            fee=fee,
        )
        account.fills.append(fill)

        logger.debug("Paper SELL %.6f %s @ %.2f on %s (fee=%.4f, pnl=%.4f)",
                     fill_qty, opportunity.symbol, sell_price, opportunity.sell_exchange, fee, realized)
        return PaperExecutionResult(True, "ok", fill_qty, sell_price, fee, slip, order_id=order_id)

    def execute(
        self,
        account: PaperAccount,
        opportunity: Opportunity,
        available_liquidity: float,
        correlation_id: str | None = None,
    ) -> PaperExecutionResult:
        """Legacy single-leg buy execution for backward compatibility."""
        if available_liquidity <= 0:
            return PaperExecutionResult(False, "insufficient_liquidity", 0.0, 0.0, 0.0, 0.0)
        if account.balances.get("USDT", 0.0) < opportunity.required_capital:
            return PaperExecutionResult(False, "insufficient_balance", 0.0, 0.0, 0.0, 0.0)
        fill_qty = min(opportunity.quantity, available_liquidity)
        fill_price = opportunity.executable_buy_price
        notional = fill_qty * fill_price
        fee = estimate_fees(notional, self.fee_bps)
        slip = estimate_slippage(notional, self.slippage_bps)
        account.balances["USDT"] -= notional + fee + slip
        return PaperExecutionResult(True, "ok", fill_qty, fill_price, fee, slip)
