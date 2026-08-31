from arbitrade.execution import ExecutionStateMachine
from arbitrade.models import ExecutionState, ExecutionTransaction


def test_recovers_when_one_leg_fails():
    sm = ExecutionStateMachine()
    tx = ExecutionTransaction(opportunity_id="opp-1")
    sm.start_validation(tx)
    sm.start_execution(tx)
    sm.record_leg_fill(tx, "buy", True)
    sm.record_leg_fill(tx, "sell", False)
    assert tx.state == ExecutionState.RECOVERY


def test_completes_when_both_legs_fill():
    sm = ExecutionStateMachine()
    tx = ExecutionTransaction(opportunity_id="opp-1")
    sm.start_validation(tx)
    sm.start_execution(tx)
    sm.record_leg_fill(tx, "buy", True)
    sm.record_leg_fill(tx, "sell", True)
    assert tx.state == ExecutionState.COMPLETED
