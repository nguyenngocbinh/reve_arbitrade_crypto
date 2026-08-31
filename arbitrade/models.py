from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable
from uuid import uuid4


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class BookLevel:
    price: float
    size: float


@dataclass(frozen=True)
class NormalizedMarketData:
    exchange: str
    symbol: str
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    last_trade: float
    exchange_timestamp: datetime
    local_receive_timestamp: datetime

    @property
    def best_bid(self) -> float:
        return self.bids[0].price if self.bids else 0.0

    @property
    def best_ask(self) -> float:
        return self.asks[0].price if self.asks else 0.0

    @property
    def market_data_latency_ms(self) -> float:
        return (self.local_receive_timestamp - self.exchange_timestamp).total_seconds() * 1000


@dataclass(frozen=True)
class Opportunity:
    id: str
    symbol: str
    buy_exchange: str
    sell_exchange: str
    quantity: float
    executable_buy_price: float
    executable_sell_price: float
    gross_spread: float
    estimated_fees: float
    estimated_slippage: float
    expected_net_pnl: float
    required_capital: float
    expected_roi: float
    created_at: datetime


class ExecutionState(str, Enum):
    DETECTED = "DETECTED"
    VALIDATING = "VALIDATING"
    EXECUTING = "EXECUTING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    RECOVERY = "RECOVERY"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class ExecutionTransaction:
    opportunity_id: str
    correlation_id: str = field(default_factory=lambda: str(uuid4()))
    state: ExecutionState = ExecutionState.DETECTED
    state_history: list[tuple[ExecutionState, datetime]] = field(default_factory=lambda: [(ExecutionState.DETECTED, utcnow())])
    leg_status: dict[str, str] = field(default_factory=dict)

    def transition(self, new_state: ExecutionState) -> None:
        self.state = new_state
        self.state_history.append((new_state, utcnow()))


@dataclass(frozen=True)
class TradeFill:
    order_id: str
    exchange: str
    symbol: str
    side: str
    quantity: float
    price: float
    fee: float
    timestamp: datetime


@dataclass
class Exposure:
    by_exchange: dict[str, float] = field(default_factory=dict)
    by_asset: dict[str, float] = field(default_factory=dict)
    daily_pnl: float = 0.0
    peak_equity: float = 0.0
    equity: float = 0.0


@dataclass(frozen=True)
class BacktestReport:
    total_pnl: float
    net_pnl: float
    roi: float
    win_rate: float
    opportunities: int
    executed_trades: int
    average_spread: float
    average_execution_latency_ms: float
    maximum_drawdown: float
    fees_paid: float
    slippage_cost: float
    rejected_opportunities: int
    failed_executions: int


def weighted_average_price(levels: Iterable[BookLevel], quantity: float) -> float | None:
    remaining = quantity
    cost = 0.0
    filled = 0.0
    for level in levels:
        take = min(remaining, level.size)
        if take <= 0:
            continue
        cost += take * level.price
        filled += take
        remaining -= take
        if remaining <= 0:
            break
    if filled < quantity:
        return None
    return cost / filled
