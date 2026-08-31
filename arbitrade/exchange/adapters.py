from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from arbitrade.exchange.base import ExchangeAdapter, ExchangeHealth
from arbitrade.models import BookLevel, NormalizedMarketData


@dataclass
class InMemoryCcxtLikeAdapter(ExchangeAdapter):
    name: str
    balances: dict[str, float] = field(default_factory=lambda: {"USDT": 100_000.0})
    books: dict[str, dict[str, list[tuple[float, float]]]] = field(default_factory=dict)
    orders: dict[str, dict[str, Any]] = field(default_factory=dict)

    def load_markets(self) -> dict[str, Any]:
        return {symbol: {"symbol": symbol} for symbol in self.books}

    def fetch_balances(self) -> dict[str, float]:
        return dict(self.balances)

    def fetch_positions(self) -> list[dict[str, Any]]:
        return []

    def fetch_order_book(self, symbol: str) -> dict[str, Any]:
        return self.books.get(symbol, {"bids": [], "asks": [], "timestamp": datetime.now(timezone.utc).timestamp() * 1000})

    def create_order(self, symbol: str, side: str, amount: float, price: float) -> str:
        order_id = str(uuid4())
        self.orders[order_id] = {
            "id": order_id,
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "price": price,
            "status": "open",
            "created_at": datetime.now(timezone.utc),
        }
        return order_id

    def cancel_order(self, order_id: str) -> bool:
        order = self.orders.get(order_id)
        if not order:
            return False
        order["status"] = "canceled"
        return True

    def fetch_order(self, order_id: str) -> dict[str, Any]:
        return dict(self.orders[order_id])

    def fetch_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        open_orders = [order for order in self.orders.values() if order["status"] == "open"]
        if symbol:
            open_orders = [order for order in open_orders if order["symbol"] == symbol]
        return [dict(order) for order in open_orders]

    def fetch_fills(self, order_id: str | None = None) -> list[dict[str, Any]]:
        return []

    def subscribe_market_data(self, symbol: str) -> Any:
        return {"stream": f"{self.name}:{symbol}:orderbook"}

    def subscribe_private_events(self) -> Any:
        return {"stream": f"{self.name}:private"}

    def check_health(self) -> ExchangeHealth:
        return ExchangeHealth(exchange=self.name, healthy=True)

    def normalize_market_data(self, symbol: str, raw: dict[str, Any]) -> NormalizedMarketData:
        now = datetime.now(timezone.utc)
        bids = tuple(BookLevel(price=float(p), size=float(s)) for p, s in raw.get("bids", []))
        asks = tuple(BookLevel(price=float(p), size=float(s)) for p, s in raw.get("asks", []))
        return NormalizedMarketData(
            exchange=self.name,
            symbol=symbol,
            bids=bids,
            asks=asks,
            last_trade=float(raw.get("last", asks[0].price if asks else 0.0)),
            exchange_timestamp=now,
            local_receive_timestamp=now,
        )


def build_default_adapters() -> dict[str, ExchangeAdapter]:
    return {
        "binance": InMemoryCcxtLikeAdapter(name="binance"),
        "kucoin": InMemoryCcxtLikeAdapter(name="kucoin"),
        "okx": InMemoryCcxtLikeAdapter(name="okx"),
        "bybit": InMemoryCcxtLikeAdapter(name="bybit"),
    }
