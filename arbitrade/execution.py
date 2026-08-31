from __future__ import annotations

from arbitrade.models import ExecutionState, ExecutionTransaction


class ExecutionStateMachine:
    def start_validation(self, tx: ExecutionTransaction) -> None:
        tx.transition(ExecutionState.VALIDATING)

    def start_execution(self, tx: ExecutionTransaction) -> None:
        tx.transition(ExecutionState.EXECUTING)

    def record_leg_fill(self, tx: ExecutionTransaction, leg: str, filled: bool) -> None:
        tx.leg_status[leg] = "filled" if filled else "failed"
        statuses = set(tx.leg_status.values())
        if statuses == {"filled"} and len(tx.leg_status) >= 2:
            tx.transition(ExecutionState.COMPLETED)
        elif "failed" in statuses and "filled" in statuses:
            tx.transition(ExecutionState.RECOVERY)
        elif "filled" in statuses:
            tx.transition(ExecutionState.PARTIALLY_FILLED)
        else:
            tx.transition(ExecutionState.FAILED)
