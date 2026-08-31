from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from arbitrade.exchange.base import ExchangeAdapter, ExchangeHealth
from arbitrade.models import NormalizedMarketData

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarketDataStatus:
    fresh: bool
    stale: bool
    latency_ms: float


def evaluate_market_data(data: NormalizedMarketData, stale_threshold_ms: int) -> MarketDataStatus:
    latency = data.market_data_latency_ms
    stale = latency > stale_threshold_ms
    return MarketDataStatus(fresh=not stale, stale=stale, latency_ms=latency)


class MarketDataStore:
    """In-memory store for the latest market data per (exchange, symbol)."""

    def __init__(self, stale_threshold_ms: int = 5_000):
        self._data: dict[tuple[str, str], NormalizedMarketData] = {}
        self._stale_threshold_ms = stale_threshold_ms
        self._health: dict[str, ExchangeHealth] = {}

    def update(self, data: NormalizedMarketData) -> None:
        self._data[(data.exchange, data.symbol)] = data

    def get(self, exchange: str, symbol: str) -> NormalizedMarketData | None:
        return self._data.get((exchange, symbol))

    def get_fresh(self, exchange: str, symbol: str) -> NormalizedMarketData | None:
        data = self.get(exchange, symbol)
        if data is None:
            return None
        status = evaluate_market_data(data, self._stale_threshold_ms)
        return data if status.fresh else None

    def get_all_fresh(self, symbol: str) -> list[NormalizedMarketData]:
        result = []
        for (exch, sym), data in self._data.items():
            if sym != symbol:
                continue
            status = evaluate_market_data(data, self._stale_threshold_ms)
            if status.fresh:
                result.append(data)
        return result

    def update_health(self, health: ExchangeHealth) -> None:
        self._health[health.exchange] = health

    def get_health(self) -> dict[str, ExchangeHealth]:
        return dict(self._health)

    def all_data(self) -> list[NormalizedMarketData]:
        return list(self._data.values())


class MarketDataService:
    """Polls configured exchanges for order book data and updates MarketDataStore."""

    def __init__(
        self,
        adapters: dict[str, ExchangeAdapter],
        symbols: list[str],
        store: MarketDataStore,
        refresh_seconds: float = 2.0,
        on_update: Callable[[NormalizedMarketData], None] | None = None,
    ):
        self._adapters = adapters
        self._symbols = symbols
        self._store = store
        self._refresh_seconds = refresh_seconds
        self._on_update = on_update
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._polling_loop())
        logger.info("MarketDataService started for %d exchanges, %d symbols", len(self._adapters), len(self._symbols))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("MarketDataService stopped")

    async def _polling_loop(self) -> None:
        while self._running:
            start = time.monotonic()
            await asyncio.gather(*[
                self._poll_exchange(name, adapter)
                for name, adapter in self._adapters.items()
            ], return_exceptions=True)
            elapsed = time.monotonic() - start
            sleep_time = max(0.0, self._refresh_seconds - elapsed)
            await asyncio.sleep(sleep_time)

    async def _poll_exchange(self, name: str, adapter: ExchangeAdapter) -> None:
        for symbol in self._symbols:
            try:
                raw = await asyncio.get_event_loop().run_in_executor(
                    None, lambda a=adapter, s=symbol: a.fetch_order_book(s)
                )
                normalized = adapter.normalize_market_data(symbol, raw)
                self._store.update(normalized)
                if self._on_update:
                    self._on_update(normalized)
                logger.debug("Updated %s %s: bid=%.2f ask=%.2f", name, symbol,
                             normalized.best_bid, normalized.best_ask)
            except Exception as exc:
                logger.warning("Failed to fetch %s %s: %s", name, symbol, exc)
                health = ExchangeHealth(exchange=name, healthy=False, reason=str(exc))
                self._store.update_health(health)
                return
        health = ExchangeHealth(
            exchange=name,
            healthy=True,
            last_update=datetime.now(timezone.utc).isoformat(),
        )
        self._store.update_health(health)
