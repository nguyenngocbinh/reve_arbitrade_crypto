from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from arbitrade.exchange.base import ExchangeAdapter, ExchangeCapabilities, ExchangeHealth
from arbitrade.models import BookLevel, NormalizedMarketData

logger = logging.getLogger(__name__)


@dataclass
class InMemoryCcxtLikeAdapter(ExchangeAdapter):
    """In-memory mock adapter for testing and paper trading without network access."""

    name: str
    capabilities: ExchangeCapabilities = field(
        default_factory=lambda: ExchangeCapabilities(
            public_market_data=True,
            private_account=True,
            create_order=False,  # disabled — paper trading only
            cancel_order=False,
        )
    )
    balances: dict[str, float] = field(default_factory=lambda: {"USDT": 100_000.0, "BTC": 1.0, "ETH": 10.0})
    books: dict[str, dict[str, list[tuple[float, float]]]] = field(default_factory=dict)
    orders: dict[str, dict[str, Any]] = field(default_factory=dict)

    def load_markets(self) -> dict[str, Any]:
        return {symbol: {"symbol": symbol} for symbol in self.books}

    def fetch_balances(self) -> dict[str, float]:
        return dict(self.balances)

    def fetch_positions(self) -> list[dict[str, Any]]:
        return []

    def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        book = self.fetch_order_book(symbol)
        bids = book.get("bids", [])
        asks = book.get("asks", [])
        bid = bids[0][0] if bids else 0.0
        ask = asks[0][0] if asks else 0.0
        return {"symbol": symbol, "bid": bid, "ask": ask, "last": (bid + ask) / 2}

    def fetch_order_book(self, symbol: str, limit: int = 20) -> dict[str, Any]:
        return self.books.get(symbol, {"bids": [], "asks": [], "timestamp": time.time() * 1000})

    def create_order(self, symbol: str, side: str, amount: float, price: float | None = None, order_type: str = "limit") -> str:
        # Paper trading only — in-memory execution, not real exchange
        order_id = str(uuid4())
        self.orders[order_id] = {
            "id": order_id,
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "price": price,
            "type": order_type,
            "status": "open",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return order_id

    def cancel_order(self, order_id: str, symbol: str | None = None) -> bool:
        order = self.orders.get(order_id)
        if not order:
            return False
        order["status"] = "canceled"
        return True

    def fetch_order(self, order_id: str, symbol: str | None = None) -> dict[str, Any]:
        return dict(self.orders[order_id])

    def fetch_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        open_orders = [order for order in self.orders.values() if order["status"] == "open"]
        if symbol:
            open_orders = [order for order in open_orders if order["symbol"] == symbol]
        return [dict(order) for order in open_orders]

    def fetch_fills(self, symbol: str | None = None, order_id: str | None = None) -> list[dict[str, Any]]:
        return []

    def check_health(self) -> ExchangeHealth:
        return ExchangeHealth(exchange=self.name, healthy=True, last_update=datetime.now(timezone.utc).isoformat())

    def normalize_market_data(self, symbol: str, raw: dict[str, Any]) -> NormalizedMarketData:
        now = datetime.now(timezone.utc)
        raw_ts = raw.get("timestamp")
        if raw_ts:
            exchange_ts = datetime.fromtimestamp(raw_ts / 1000, tz=timezone.utc)
        else:
            exchange_ts = now
        bids = tuple(BookLevel(price=float(p), size=float(s)) for p, s in raw.get("bids", []))
        asks = tuple(BookLevel(price=float(p), size=float(s)) for p, s in raw.get("asks", []))
        last = raw.get("last") or (asks[0].price if asks else 0.0)
        return NormalizedMarketData(
            exchange=self.name,
            symbol=symbol,
            bids=bids,
            asks=asks,
            last_trade=float(last),
            exchange_timestamp=exchange_ts,
            local_receive_timestamp=now,
        )


try:
    import ccxt

    class CcxtAdapter(ExchangeAdapter):
        """CCXT-based real exchange adapter for public market data."""

        def __init__(self, exchange_id: str, api_key: str | None = None, secret: str | None = None, password: str | None = None):
            self.name = exchange_id
            self._exchange_id = exchange_id
            # Order submission disabled — paper trading only
            self.capabilities = ExchangeCapabilities(
                public_market_data=True,
                private_account=bool(api_key and secret),
                create_order=False,
                cancel_order=False,
            )
            params: dict[str, Any] = {"enableRateLimit": True}
            if api_key:
                params["apiKey"] = api_key
            if secret:
                params["secret"] = secret
            if password:
                params["password"] = password
            exchange_class = getattr(ccxt, exchange_id, None)
            if exchange_class is None:
                raise ValueError(f"CCXT does not support exchange: {exchange_id}")
            self._ccxt: ccxt.Exchange = exchange_class(params)

        def connect(self) -> None:
            try:
                self._ccxt.load_markets()
                logger.info("Connected to %s via CCXT", self.name)
            except Exception as exc:
                logger.warning("Failed to connect to %s: %s", self.name, exc)
                raise

        def close(self) -> None:
            pass

        def load_markets(self) -> dict[str, Any]:
            return self._ccxt.load_markets()

        def fetch_balances(self) -> dict[str, float]:
            if not self.capabilities.private_account:
                return {}
            raw = self._ccxt.fetch_balance()
            return {k: float(v) for k, v in raw.get("free", {}).items() if v and float(v) > 0}

        def fetch_positions(self) -> list[dict[str, Any]]:
            if not self.capabilities.private_account:
                return []
            try:
                return self._ccxt.fetch_positions() or []
            except Exception:
                return []

        def fetch_ticker(self, symbol: str) -> dict[str, Any]:
            return self._ccxt.fetch_ticker(symbol)

        def fetch_order_book(self, symbol: str, limit: int = 20) -> dict[str, Any]:
            return self._ccxt.fetch_order_book(symbol, limit)

        def create_order(self, symbol: str, side: str, amount: float, price: float | None = None, order_type: str = "limit") -> str:
            # SAFETY: real order submission is disabled
            raise RuntimeError("Real order submission is disabled. Use PaperExecutor for paper trading.")

        def cancel_order(self, order_id: str, symbol: str | None = None) -> bool:
            # SAFETY: disabled
            raise RuntimeError("Real order cancellation is disabled.")

        def fetch_order(self, order_id: str, symbol: str | None = None) -> dict[str, Any]:
            if not self.capabilities.private_account:
                return {}
            return self._ccxt.fetch_order(order_id, symbol)

        def fetch_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
            if not self.capabilities.private_account:
                return []
            return self._ccxt.fetch_open_orders(symbol)

        def fetch_fills(self, symbol: str | None = None, order_id: str | None = None) -> list[dict[str, Any]]:
            if not self.capabilities.private_account:
                return []
            try:
                return self._ccxt.fetch_my_trades(symbol) or []
            except Exception:
                return []

        def check_health(self) -> ExchangeHealth:
            try:
                start = time.time()
                self._ccxt.fetch_ticker("BTC/USDT")
                latency_ms = (time.time() - start) * 1000
                return ExchangeHealth(
                    exchange=self.name,
                    healthy=True,
                    last_update=datetime.now(timezone.utc).isoformat(),
                    latency_ms=latency_ms,
                )
            except Exception as exc:
                return ExchangeHealth(exchange=self.name, healthy=False, reason=str(exc))

        def normalize_market_data(self, symbol: str, raw: dict[str, Any]) -> NormalizedMarketData:
            now = datetime.now(timezone.utc)
            raw_ts = raw.get("timestamp")
            if raw_ts:
                exchange_ts = datetime.fromtimestamp(raw_ts / 1000, tz=timezone.utc)
            else:
                exchange_ts = now
            bids = tuple(BookLevel(price=float(p), size=float(s)) for p, s in raw.get("bids", []))
            asks = tuple(BookLevel(price=float(p), size=float(s)) for p, s in raw.get("asks", []))
            last_raw = raw.get("last") or raw.get("close")
            last = float(last_raw) if last_raw else (asks[0].price if asks else 0.0)
            return NormalizedMarketData(
                exchange=self.name,
                symbol=symbol,
                bids=bids,
                asks=asks,
                last_trade=last,
                exchange_timestamp=exchange_ts,
                local_receive_timestamp=now,
            )

    _CCXT_AVAILABLE = True

except ImportError:
    _CCXT_AVAILABLE = False
    logger.warning("ccxt not installed — using in-memory adapters only")


def build_adapter(exchange_id: str, use_ccxt: bool = True) -> ExchangeAdapter:
    """Build an exchange adapter. Uses CCXT if available and use_ccxt=True, otherwise in-memory mock."""
    if use_ccxt and _CCXT_AVAILABLE:
        import os
        key = os.getenv(f"{exchange_id.upper()}_API_KEY")
        secret = os.getenv(f"{exchange_id.upper()}_API_SECRET")
        password = os.getenv(f"{exchange_id.upper()}_API_PASSWORD")
        try:
            return CcxtAdapter(exchange_id, api_key=key, secret=secret, password=password)
        except Exception as exc:
            logger.warning("Failed to build CCXT adapter for %s (%s), falling back to in-memory", exchange_id, exc)
    return InMemoryCcxtLikeAdapter(name=exchange_id)


def build_default_adapters(use_ccxt: bool = True) -> dict[str, ExchangeAdapter]:
    exchange_ids = ["binance", "kucoin", "okx", "bybit"]
    return {eid: build_adapter(eid, use_ccxt=use_ccxt) for eid in exchange_ids}
