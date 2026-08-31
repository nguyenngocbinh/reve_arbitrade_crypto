from __future__ import annotations

from itertools import combinations
from uuid import uuid4

from arbitrade.config import AppConfig
from arbitrade.models import NormalizedMarketData, Opportunity, weighted_average_price


def estimate_fees(notional: float, fee_bps: float) -> float:
    return notional * (fee_bps / 10_000) * 2


def estimate_slippage(notional: float, slippage_bps: float) -> float:
    return notional * (slippage_bps / 10_000)


def detect_opportunities(symbol: str, books: list[NormalizedMarketData], quantity: float, config: AppConfig) -> list[Opportunity]:
    opportunities: list[Opportunity] = []
    for left, right in combinations(books, 2):
        opportunities.extend(_check_direction(symbol, left, right, quantity, config))
        opportunities.extend(_check_direction(symbol, right, left, quantity, config))
    return sorted(opportunities, key=lambda item: item.expected_net_pnl, reverse=True)


def _check_direction(symbol: str, buy_side: NormalizedMarketData, sell_side: NormalizedMarketData, quantity: float, config: AppConfig) -> list[Opportunity]:
    buy_price = weighted_average_price(buy_side.asks, quantity)
    sell_price = weighted_average_price(sell_side.bids, quantity)
    if buy_price is None or sell_price is None:
        return []
    gross_spread = (sell_price - buy_price) * quantity
    notional = buy_price * quantity
    fees = estimate_fees(notional, config.fee_bps)
    slippage = estimate_slippage(notional, config.slippage_bps)
    net = gross_spread - fees - slippage
    if net <= config.min_net_profit:
        return []
    required_capital = notional
    roi = net / required_capital if required_capital else 0.0
    return [
        Opportunity(
            id=str(uuid4()),
            symbol=symbol,
            buy_exchange=buy_side.exchange,
            sell_exchange=sell_side.exchange,
            quantity=quantity,
            executable_buy_price=buy_price,
            executable_sell_price=sell_price,
            gross_spread=gross_spread,
            estimated_fees=fees,
            estimated_slippage=slippage,
            expected_net_pnl=net,
            required_capital=required_capital,
            expected_roi=roi,
            created_at=buy_side.local_receive_timestamp,
        )
    ]
