"""Tests for the risk engine with structured RiskDecision."""
from __future__ import annotations

import pytest

from arbitrade.config import RiskConfig
from arbitrade.models import Exposure, Opportunity, RiskDecision, utcnow
from arbitrade.risk import RiskManager


def _opp(required_capital: float = 1000.0, net_pnl: float = 0.7) -> Opportunity:
    return Opportunity(
        id="test-opp-1",
        symbol="BTC/USDT",
        buy_exchange="binance",
        sell_exchange="okx",
        quantity=0.01,
        executable_buy_price=100_000.0,
        executable_sell_price=100_200.0,
        gross_spread=2.0,
        estimated_fees=0.2,
        estimated_slippage=0.1,
        expected_net_pnl=net_pnl,
        required_capital=required_capital,
        expected_roi=net_pnl / required_capital,
        created_at=utcnow(),
    )


def test_approved_returns_risk_decision():
    rm = RiskManager(RiskConfig())
    decision = rm.can_trade(_opp(), Exposure())
    assert isinstance(decision, RiskDecision)
    assert decision.approved
    assert decision.reason == "ok"


def test_risk_decision_iterable_for_backward_compat():
    rm = RiskManager(RiskConfig())
    decision = rm.can_trade(_opp(), Exposure())
    approved, reason = decision
    assert approved
    assert reason == "ok"


def test_circuit_breaker_returns_structured_decision():
    rm = RiskManager(RiskConfig())
    rm.circuit_breaker.open("manual_test")
    decision = rm.can_trade(_opp(), Exposure())
    assert not decision.approved
    assert decision.reason == "circuit_breaker_open"
    assert decision.rule == "circuit_breaker"


def test_max_trade_size_structured():
    rm = RiskManager(RiskConfig(max_trade_size=500))
    decision = rm.can_trade(_opp(600), Exposure())
    assert not decision.approved
    assert decision.rule == "max_trade_size"
    assert decision.current_value == 600.0
    assert decision.configured_limit == 500.0


def test_max_concurrent_opportunities():
    rm = RiskManager(RiskConfig(max_concurrent_opportunities=2))
    rm.active_opportunities = 2
    decision = rm.can_trade(_opp(), Exposure())
    assert not decision.approved
    assert decision.rule == "max_concurrent_opportunities"


def test_max_exposure_per_exchange():
    rm = RiskManager(RiskConfig(max_exposure_per_exchange=1000.0))
    exposure = Exposure(by_exchange={"binance": 800.0})
    decision = rm.can_trade(_opp(required_capital=300.0), exposure)
    assert not decision.approved
    assert decision.rule == "max_exposure_per_exchange"


def test_max_exposure_per_asset():
    rm = RiskManager(RiskConfig(max_exposure_per_asset=500.0))
    exposure = Exposure(by_asset={"BTC": 400.0})
    decision = rm.can_trade(_opp(required_capital=200.0), exposure)
    assert not decision.approved
    assert decision.rule == "max_exposure_per_asset"


def test_daily_loss_triggers_circuit_breaker():
    rm = RiskManager(RiskConfig(max_daily_loss=100.0))
    exposure = Exposure(daily_pnl=-150.0)
    decision = rm.can_trade(_opp(), exposure)
    assert not decision.approved
    assert rm.circuit_breaker.is_open


def test_max_drawdown_triggers_circuit_breaker():
    rm = RiskManager(RiskConfig(max_drawdown=0.1))
    exposure = Exposure(peak_equity=100_000.0, equity=80_000.0)
    decision = rm.can_trade(_opp(), exposure)
    assert not decision.approved
    assert rm.circuit_breaker.is_open


def test_cooldown_after_failed_execution():
    from datetime import timedelta
    rm = RiskManager(RiskConfig(cooldown_seconds=60))
    rm.register_failed_execution()
    decision = rm.can_trade(_opp(), Exposure())
    assert not decision.approved
    assert decision.reason == "cooldown"
