from __future__ import annotations

from dataclasses import dataclass, field

from arbitrade.models import Opportunity
from arbitrade.opportunity import estimate_fees, estimate_slippage


@dataclass
class PaperAccount:
    balances: dict[str, float] = field(default_factory=lambda: {"USDT": 100_000.0})


@dataclass(frozen=True)
class PaperExecutionResult:
    accepted: bool
    reason: str
    filled_quantity: float
    avg_fill_price: float
    fee: float
    slippage: float


class PaperExecutor:
    def __init__(self, fee_bps: float, slippage_bps: float):
        self.fee_bps = fee_bps
        self.slippage_bps = slippage_bps

    def execute(self, account: PaperAccount, opportunity: Opportunity, available_liquidity: float) -> PaperExecutionResult:
        if available_liquidity <= 0:
            return PaperExecutionResult(False, "insufficient_liquidity", 0.0, 0.0, 0.0, 0.0)
        if account.balances.get("USDT", 0.0) < opportunity.required_capital:
            return PaperExecutionResult(False, "insufficient_balance", 0.0, 0.0, 0.0, 0.0)
        fill_qty = min(opportunity.quantity, available_liquidity)
        fill_price = opportunity.executable_buy_price
        notional = fill_qty * fill_price
        fee = estimate_fees(notional, self.fee_bps)
        slip = estimate_slippage(notional, self.slippage_bps)
        account.balances["USDT"] -= notional + fee + slip
        return PaperExecutionResult(True, "ok", fill_qty, fill_price, fee, slip)
