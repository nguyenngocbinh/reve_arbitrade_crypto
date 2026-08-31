"""Tests for the extended paper trading simulator."""
from __future__ import annotations

import pytest

from arbitrade.models import Opportunity, utcnow
from arbitrade.simulation import PaperAccount, PaperExecutor


def _opp(qty: float = 0.01, buy_price: float = 100_000.0, sell_price: float = 100_200.0) -> Opportunity:
    required = qty * buy_price
    return Opportunity(
        id="test-opp",
        symbol="BTC/USDT",
        buy_exchange="binance",
        sell_exchange="okx",
        quantity=qty,
        executable_buy_price=buy_price,
        executable_sell_price=sell_price,
        gross_spread=(sell_price - buy_price) * qty,
        estimated_fees=0.0,
        estimated_slippage=0.0,
        expected_net_pnl=(sell_price - buy_price) * qty,
        required_capital=required,
        expected_roi=((sell_price - buy_price) * qty) / required,
        created_at=utcnow(),
    )


def test_buy_leg_deducts_usdt_credits_btc():
    ex = PaperExecutor(fee_bps=0, slippage_bps=0)
    account = PaperAccount(balances={"USDT": 10_000.0, "BTC": 0.0})
    opp = _opp(qty=0.01, buy_price=100_000.0)
    result = ex.execute_buy(account, opp, available_liquidity=0.01)
    assert result.accepted
    assert result.filled_quantity == 0.01
    assert abs(account.balances["USDT"] - (10_000.0 - 1_000.0)) < 0.01
    assert abs(account.balances["BTC"] - 0.01) < 1e-9


def test_sell_leg_credits_usdt_deducts_btc():
    ex = PaperExecutor(fee_bps=0, slippage_bps=0)
    account = PaperAccount(balances={"USDT": 0.0, "BTC": 0.01})
    opp = _opp(qty=0.01, sell_price=100_200.0)
    result = ex.execute_sell(account, opp, fill_qty=0.01, buy_fill_price=100_000.0)
    assert result.accepted
    assert abs(account.balances["USDT"] - 1_002.0) < 0.01
    assert account.balances["BTC"] < 0.001


def test_realized_pnl_accumulates():
    ex = PaperExecutor(fee_bps=0, slippage_bps=0)
    account = PaperAccount(balances={"USDT": 10_000.0, "BTC": 0.0})
    opp = _opp(qty=0.01, buy_price=100_000.0, sell_price=100_200.0)
    buy_res = ex.execute_buy(account, opp, available_liquidity=0.01)
    assert buy_res.accepted
    sell_res = ex.execute_sell(account, opp, fill_qty=0.01, buy_fill_price=100_000.0)
    assert sell_res.accepted
    # PnL = sell_notional - buy_notional = 100200*0.01 - 100000*0.01 = 2.0
    assert abs(account.realized_pnl - 2.0) < 0.01


def test_buy_leg_rejected_insufficient_balance():
    ex = PaperExecutor(fee_bps=0, slippage_bps=0)
    account = PaperAccount(balances={"USDT": 5.0})
    opp = _opp(qty=0.01, buy_price=100_000.0)
    result = ex.execute_buy(account, opp, available_liquidity=0.01)
    assert not result.accepted
    assert result.reason == "insufficient_balance"


def test_sell_leg_rejected_insufficient_asset():
    ex = PaperExecutor(fee_bps=0, slippage_bps=0)
    account = PaperAccount(balances={"USDT": 0.0, "BTC": 0.0})
    opp = _opp(qty=0.01)
    result = ex.execute_sell(account, opp, fill_qty=0.01, buy_fill_price=100_000.0)
    assert not result.accepted
    assert result.reason == "insufficient_asset_balance"


def test_fee_and_slippage_applied():
    ex = PaperExecutor(fee_bps=10, slippage_bps=5)
    account = PaperAccount(balances={"USDT": 10_000.0, "BTC": 0.0})
    opp = _opp(qty=0.01, buy_price=100_000.0)
    result = ex.execute_buy(account, opp, available_liquidity=0.01)
    assert result.fee > 0
    assert result.slippage > 0
    # USDT deducted more than just notional
    assert account.balances["USDT"] < 10_000.0 - 1_000.0


def test_partial_fill_from_limited_liquidity():
    ex = PaperExecutor(fee_bps=0, slippage_bps=0)
    account = PaperAccount(balances={"USDT": 10_000.0, "BTC": 0.0})
    opp = _opp(qty=0.02)
    result = ex.execute(account, opp, available_liquidity=0.01)
    assert result.accepted
    assert result.filled_quantity == 0.01


def test_order_record_created_on_buy():
    ex = PaperExecutor(fee_bps=0, slippage_bps=0)
    account = PaperAccount(balances={"USDT": 10_000.0, "BTC": 0.0})
    opp = _opp()
    ex.execute_buy(account, opp, available_liquidity=0.01)
    assert len(account.orders) == 1
    order = list(account.orders.values())[0]
    assert order.side == "buy"
    assert order.status == "filled"
