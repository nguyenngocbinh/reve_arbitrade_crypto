from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from arbitrade.models import (
    ExecutionState,
    ExecutionTransaction,
    FillRecord,
    Opportunity,
    OrderRecord,
    TradeRecord,
    utcnow,
)
from arbitrade.simulation import PaperAccount, PaperExecutor

logger = logging.getLogger(__name__)


class ExecutionStateMachine:
    def start_validation(self, tx: ExecutionTransaction) -> None:
        tx.transition(ExecutionState.VALIDATING)

    def start_submission(self, tx: ExecutionTransaction) -> None:
        tx.transition(ExecutionState.SUBMITTING)

    def start_execution(self, tx: ExecutionTransaction) -> None:
        tx.transition(ExecutionState.EXECUTING)

    def record_leg_fill(self, tx: ExecutionTransaction, leg: str, filled: bool) -> None:
        tx.leg_status[leg] = "filled" if filled else "failed"
        statuses = set(tx.leg_status.values())
        all_filled = statuses == {"filled"} and len(tx.leg_status) >= 2
        any_filled = "filled" in statuses
        any_failed = "failed" in statuses

        if all_filled:
            tx.transition(ExecutionState.COMPLETED)
        elif any_failed and any_filled:
            tx.transition(ExecutionState.RECOVERY)
        elif any_filled and not any_failed:
            tx.transition(ExecutionState.PARTIALLY_FILLED)
        else:
            tx.transition(ExecutionState.FAILED)

    def mark_completed(self, tx: ExecutionTransaction) -> None:
        tx.transition(ExecutionState.COMPLETED)

    def mark_failed(self, tx: ExecutionTransaction, reason: str = "") -> None:
        tx.transition(ExecutionState.FAILED)

    def mark_recovery_required(self, tx: ExecutionTransaction) -> None:
        tx.transition(ExecutionState.RECOVERY_REQUIRED)


@dataclass
class TwoLegResult:
    success: bool
    buy_result: object
    sell_result: object
    trade: TradeRecord | None = None
    error: str = ""


class PaperExecutionEngine:
    """Concurrent two-leg paper trading execution engine."""

    def __init__(self, executor: PaperExecutor, account: PaperAccount, on_trade: Callable[[TradeRecord], None] | None = None):
        self._executor = executor
        self._account = account
        self._sm = ExecutionStateMachine()
        self._on_trade = on_trade
        self._active_transactions: dict[str, ExecutionTransaction] = {}

    async def execute_opportunity(self, opportunity: Opportunity) -> TwoLegResult:
        tx = ExecutionTransaction(
            opportunity_id=opportunity.id,
            correlation_id=str(uuid4()),
        )
        self._active_transactions[tx.correlation_id] = tx

        try:
            self._sm.start_validation(tx)
            # Run both legs concurrently
            self._sm.start_submission(tx)
            self._sm.start_execution(tx)

            buy_coro = asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._executor.execute_buy(
                    self._account, opportunity, available_liquidity=opportunity.quantity, correlation_id=tx.correlation_id
                )
            )
            sell_coro = asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._executor.execute_sell(
                    self._account, opportunity, fill_qty=opportunity.quantity,
                    buy_fill_price=opportunity.executable_buy_price, correlation_id=tx.correlation_id
                )
            )

            # Execute buy first, then sell (to have the asset to sell)
            buy_result = await buy_coro

            if not buy_result.accepted:
                self._sm.record_leg_fill(tx, "buy", False)
                self._sm.record_leg_fill(tx, "sell", False)
                return TwoLegResult(False, buy_result, None, error=f"buy_failed:{buy_result.reason}")

            tx.buy_order = self._account.orders.get(buy_result.order_id)

            sell_result = await sell_coro
            self._sm.record_leg_fill(tx, "buy", True)
            self._sm.record_leg_fill(tx, "sell", sell_result.accepted)

            if not sell_result.accepted:
                # Buy filled, sell failed — recovery needed
                logger.error("Sell leg failed after buy: %s — entering recovery", sell_result.reason)
                trade = self._create_trade_record(tx, opportunity, buy_result, sell_result, failed=True)
                if self._on_trade:
                    self._on_trade(trade)
                return TwoLegResult(False, buy_result, sell_result, trade=trade, error=f"sell_failed:{sell_result.reason}")

            tx.sell_order = self._account.orders.get(sell_result.order_id)
            trade = self._create_trade_record(tx, opportunity, buy_result, sell_result, failed=False)
            if self._on_trade:
                self._on_trade(trade)

            logger.info(
                "Paper trade completed: %s %s buy@%.2f sell@%.2f qty=%.6f pnl=%.4f",
                opportunity.buy_exchange, opportunity.sell_exchange,
                buy_result.avg_fill_price, sell_result.avg_fill_price,
                buy_result.filled_quantity, trade.realized_pnl,
            )
            return TwoLegResult(True, buy_result, sell_result, trade=trade)

        except Exception as exc:
            logger.exception("Execution engine error: %s", exc)
            self._sm.mark_failed(tx, str(exc))
            return TwoLegResult(False, None, None, error=str(exc))
        finally:
            del self._active_transactions[tx.correlation_id]

    def _create_trade_record(
        self, tx: ExecutionTransaction, opportunity: Opportunity, buy_result, sell_result, failed: bool
    ) -> TradeRecord:
        now = utcnow()
        if failed or sell_result is None:
            return TradeRecord(
                id=str(uuid4()),
                opportunity_id=opportunity.id,
                correlation_id=tx.correlation_id,
                buy_order_id=getattr(buy_result, "order_id", ""),
                sell_order_id="",
                symbol=opportunity.symbol,
                quantity=buy_result.filled_quantity if buy_result else 0.0,
                buy_price=buy_result.avg_fill_price if buy_result else 0.0,
                sell_price=0.0,
                fees=(buy_result.fee if buy_result else 0.0),
                slippage=(buy_result.slippage if buy_result else 0.0),
                realized_pnl=0.0,
                state="RECOVERY",
                opened_at=now,
                closed_at=now,
            )
        fees = buy_result.fee + sell_result.fee
        slippage = buy_result.slippage + sell_result.slippage
        buy_notional = buy_result.filled_quantity * buy_result.avg_fill_price
        sell_notional = buy_result.filled_quantity * sell_result.avg_fill_price
        realized_pnl = sell_notional - buy_notional - fees - slippage
        return TradeRecord(
            id=str(uuid4()),
            opportunity_id=opportunity.id,
            correlation_id=tx.correlation_id,
            buy_order_id=buy_result.order_id,
            sell_order_id=sell_result.order_id,
            symbol=opportunity.symbol,
            quantity=buy_result.filled_quantity,
            buy_price=buy_result.avg_fill_price,
            sell_price=sell_result.avg_fill_price,
            fees=fees,
            slippage=slippage,
            realized_pnl=realized_pnl,
            state="COMPLETED",
            opened_at=now,
            closed_at=now,
        )
