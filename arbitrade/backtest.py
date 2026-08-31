from __future__ import annotations

from dataclasses import dataclass

from arbitrade.models import BacktestReport, Opportunity


@dataclass
class BacktestAccumulator:
    total_pnl: float = 0.0
    net_pnl: float = 0.0
    opportunities: int = 0
    executed_trades: int = 0
    wins: int = 0
    total_spread: float = 0.0
    total_latency_ms: float = 0.0
    max_drawdown: float = 0.0
    fees_paid: float = 0.0
    slippage_cost: float = 0.0
    rejected_opportunities: int = 0
    failed_executions: int = 0

    def record_opportunity(self, opp: Opportunity) -> None:
        self.opportunities += 1
        self.total_spread += opp.gross_spread

    def record_execution(self, pnl: float, fees: float, slippage: float, latency_ms: float, executed: bool, failed: bool) -> None:
        if not executed:
            self.rejected_opportunities += 1
            return
        self.executed_trades += 1
        self.total_pnl += pnl
        self.net_pnl += pnl - fees - slippage
        self.fees_paid += fees
        self.slippage_cost += slippage
        self.total_latency_ms += latency_ms
        if pnl > 0:
            self.wins += 1
        if failed:
            self.failed_executions += 1

    def report(self, starting_capital: float) -> BacktestReport:
        roi = self.net_pnl / starting_capital if starting_capital else 0.0
        win_rate = self.wins / self.executed_trades if self.executed_trades else 0.0
        avg_spread = self.total_spread / self.opportunities if self.opportunities else 0.0
        avg_latency = self.total_latency_ms / self.executed_trades if self.executed_trades else 0.0
        return BacktestReport(
            total_pnl=self.total_pnl,
            net_pnl=self.net_pnl,
            roi=roi,
            win_rate=win_rate,
            opportunities=self.opportunities,
            executed_trades=self.executed_trades,
            average_spread=avg_spread,
            average_execution_latency_ms=avg_latency,
            maximum_drawdown=self.max_drawdown,
            fees_paid=self.fees_paid,
            slippage_cost=self.slippage_cost,
            rejected_opportunities=self.rejected_opportunities,
            failed_executions=self.failed_executions,
        )
