from arbitrade.models import Opportunity, utcnow
from arbitrade.simulation import PaperAccount, PaperExecutor


def _opp(required_capital: float = 1000.0, qty: float = 1.0) -> Opportunity:
    return Opportunity(
        id="1",
        symbol="BTC/USDT",
        buy_exchange="binance",
        sell_exchange="okx",
        quantity=qty,
        executable_buy_price=1000,
        executable_sell_price=1010,
        gross_spread=10,
        estimated_fees=0.0,
        estimated_slippage=0.0,
        expected_net_pnl=10,
        required_capital=required_capital,
        expected_roi=0.01,
        created_at=utcnow(),
    )


def test_paper_executor_rejects_on_liquidity():
    ex = PaperExecutor(fee_bps=10, slippage_bps=5)
    result = ex.execute(PaperAccount(), _opp(), available_liquidity=0)
    assert not result.accepted
    assert result.reason == "insufficient_liquidity"


def test_paper_executor_partial_fill():
    ex = PaperExecutor(fee_bps=10, slippage_bps=5)
    account = PaperAccount()
    result = ex.execute(account, _opp(qty=2), available_liquidity=1)
    assert result.accepted
    assert result.filled_quantity == 1
