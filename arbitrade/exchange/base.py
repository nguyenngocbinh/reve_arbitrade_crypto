from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from arbitrade.models import NormalizedMarketData


@dataclass(frozen=True)
class ExchangeCapabilities:
    public_market_data: bool = True
    private_account: bool = False
    websocket_order_book: bool = False
    websocket_ticker: bool = False
    websocket_trades: bool = False
    create_order: bool = False
    cancel_order: bool = False
    fetch_positions: bool = False


@dataclass(frozen=True)
class ExchangeHealth:
    exchange: str
    healthy: bool
    reason: str = "ok"
    last_update: str | None = None
    latency_ms: float | None = None


class ExchangeAdapter(ABC):
    name: str
    capabilities: ExchangeCapabilities = ExchangeCapabilities()

    @abstractmethod
    def load_markets(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def fetch_balances(self) -> dict[str, float]:
        raise NotImplementedError

    @abstractmethod
    def fetch_positions(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def fetch_order_book(self, symbol: str, limit: int = 20) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def create_order(self, symbol: str, side: str, amount: float, price: float | None = None, order_type: str = "limit") -> str:
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, order_id: str, symbol: str | None = None) -> bool:
        raise NotImplementedError

    @abstractmethod
    def fetch_order(self, order_id: str, symbol: str | None = None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def fetch_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def fetch_fills(self, symbol: str | None = None, order_id: str | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def check_health(self) -> ExchangeHealth:
        raise NotImplementedError

    @abstractmethod
    def normalize_market_data(self, symbol: str, raw: dict[str, Any]) -> NormalizedMarketData:
        raise NotImplementedError

    def connect(self) -> None:
        """Optional: establish connection."""

    def close(self) -> None:
        """Optional: close connection."""
