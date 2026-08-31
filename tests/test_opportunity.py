from datetime import datetime, timezone

from arbitrade.config import AppConfig
from arbitrade.models import BookLevel, NormalizedMarketData
from arbitrade.opportunity import detect_opportunities, estimate_fees, estimate_slippage


def _book(exchange: str, bid: float, ask: float, size: float = 2.0) -> NormalizedMarketData:
    now = datetime.now(timezone.utc)
    return NormalizedMarketData(
        exchange=exchange,
        symbol="BTC/USDT",
        bids=(BookLevel(bid, size),),
        asks=(BookLevel(ask, size),),
        last_trade=bid,
        exchange_timestamp=now,
        local_receive_timestamp=now,
    )


def test_fee_and_slippage_estimates():
    assert estimate_fees(10_000, 10) == 20
    assert estimate_slippage(10_000, 5) == 5


def test_detects_profitable_executable_opportunity():
    config = AppConfig(min_net_profit=1.0)
    opps = detect_opportunities("BTC/USDT", [_book("binance", 100, 101), _book("okx", 103, 104)], 1.0, config)
    assert opps
    best = opps[0]
    assert best.buy_exchange == "binance"
    assert best.sell_exchange == "okx"
    assert best.expected_net_pnl > 1.0
