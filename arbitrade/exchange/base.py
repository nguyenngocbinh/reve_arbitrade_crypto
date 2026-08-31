from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from arbitrade.models import NormalizedMarketData


@dataclass(frozen=True)
class ExchangeHealth:
    exchange: str
    healthy: bool
    reason: str = "ok"


class ExchangeAdapter(ABC):
    name: str

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
    def fetch_order_book(self, symbol: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def create_order(self, symbol: str, side: str, amount: float, price: float) -> str:
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def fetch_order(self, order_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def fetch_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def fetch_fills(self, order_id: str | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def subscribe_market_data(self, symbol: str) -> Any:
        raise NotImplementedError

    @abstractmethod
    def subscribe_private_events(self) -> Any:
        raise NotImplementedError

    @abstractmethod
    def check_health(self) -> ExchangeHealth:
        raise NotImplementedError

    @abstractmethod
    def normalize_market_data(self, symbol: str, raw: dict[str, Any]) -> NormalizedMarketData:
        raise NotImplementedError
