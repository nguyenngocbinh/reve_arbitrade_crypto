from __future__ import annotations

from dataclasses import dataclass

from arbitrade.models import NormalizedMarketData


@dataclass(frozen=True)
class MarketDataStatus:
    fresh: bool
    stale: bool
    latency_ms: float


def evaluate_market_data(data: NormalizedMarketData, stale_threshold_ms: int) -> MarketDataStatus:
    latency = data.market_data_latency_ms
    stale = latency > stale_threshold_ms
    return MarketDataStatus(fresh=not stale, stale=stale, latency_ms=latency)
