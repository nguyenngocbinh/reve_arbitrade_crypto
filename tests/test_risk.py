from arbitrade.config import RiskConfig
from arbitrade.models import Exposure, Opportunity, utcnow
from arbitrade.risk import RiskManager


def _opp(required_capital: float = 1000.0) -> Opportunity:
    return Opportunity(
        id="1",
        symbol="BTC/USDT",
        buy_exchange="binance",
        sell_exchange="okx",
        quantity=1,
        executable_buy_price=100,
        executable_sell_price=101,
        gross_spread=1,
        estimated_fees=0.2,
        estimated_slippage=0.1,
        expected_net_pnl=0.7,
        required_capital=required_capital,
        expected_roi=0.0007,
        created_at=utcnow(),
    )


def test_circuit_breaker_blocks_new_trades():
    rm = RiskManager(RiskConfig())
    rm.circuit_breaker.open("manual")
    allowed, reason = rm.can_trade(_opp(), Exposure())
    assert not allowed
    assert reason == "circuit_breaker_open"


def test_max_trade_size_guard():
    rm = RiskManager(RiskConfig(max_trade_size=500))
    allowed, reason = rm.can_trade(_opp(600), Exposure())
    assert not allowed
    assert reason == "max_trade_size"
