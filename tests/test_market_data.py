"""Tests for the market data engine."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from arbitrade.market_data import MarketDataStore, MarketDataStatus, evaluate_market_data
from arbitrade.models import BookLevel, NormalizedMarketData


def _now():
    return datetime.now(timezone.utc)


def _make_md(exchange: str, symbol: str, latency_ms: float = 0.0, bid: float = 100.0, ask: float = 101.0) -> NormalizedMarketData:
    recv = _now()
    exch_ts = recv - timedelta(milliseconds=latency_ms)
    return NormalizedMarketData(
        exchange=exchange,
        symbol=symbol,
        bids=(BookLevel(bid, 1.0),),
        asks=(BookLevel(ask, 1.0),),
        last_trade=bid,
        exchange_timestamp=exch_ts,
        local_receive_timestamp=recv,
    )


def test_fresh_market_data():
    md = _make_md("binance", "BTC/USDT", latency_ms=100.0)
    status = evaluate_market_data(md, stale_threshold_ms=2000)
    assert status.fresh
    assert not status.stale
    assert abs(status.latency_ms - 100.0) < 1.0


def test_stale_market_data():
    md = _make_md("binance", "BTC/USDT", latency_ms=6000.0)
    status = evaluate_market_data(md, stale_threshold_ms=5000)
    assert status.stale
    assert not status.fresh


def test_market_data_store_update_and_get():
    store = MarketDataStore(stale_threshold_ms=5000)
    md = _make_md("binance", "BTC/USDT")
    store.update(md)
    result = store.get("binance", "BTC/USDT")
    assert result is not None
    assert result.exchange == "binance"
    assert result.symbol == "BTC/USDT"


def test_market_data_store_get_fresh_when_stale():
    store = MarketDataStore(stale_threshold_ms=100)
    md = _make_md("binance", "BTC/USDT", latency_ms=5000.0)
    store.update(md)
    result = store.get_fresh("binance", "BTC/USDT")
    assert result is None


def test_market_data_store_get_all_fresh():
    store = MarketDataStore(stale_threshold_ms=5000)
    store.update(_make_md("binance", "BTC/USDT"))
    store.update(_make_md("okx", "BTC/USDT"))
    store.update(_make_md("binance", "ETH/USDT"))
    results = store.get_all_fresh("BTC/USDT")
    assert len(results) == 2
    exchanges = {r.exchange for r in results}
    assert exchanges == {"binance", "okx"}


def test_market_data_store_missing_returns_none():
    store = MarketDataStore()
    assert store.get("nonexistent", "BTC/USDT") is None
    assert store.get_fresh("nonexistent", "BTC/USDT") is None


def test_normalized_market_data_best_bid_ask():
    md = _make_md("binance", "BTC/USDT", bid=100_000.0, ask=100_100.0)
    assert md.best_bid == 100_000.0
    assert md.best_ask == 100_100.0
