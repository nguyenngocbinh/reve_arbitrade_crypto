from __future__ import annotations

from dataclasses import dataclass

from arbitrade.exchange.base import ExchangeAdapter
from arbitrade.persistence import Persistence


@dataclass
class RecoveryAction:
    kind: str
    details: str


class SessionRecovery:
    def __init__(self, persistence: Persistence, exchanges: dict[str, ExchangeAdapter]):
        self.persistence = persistence
        self.exchanges = exchanges

    def recover(self) -> list[RecoveryAction]:
        actions: list[RecoveryAction] = []
        for name, adapter in self.exchanges.items():
            balances = adapter.fetch_balances()
            actions.append(RecoveryAction(kind="balance_reconcile", details=f"{name}:{len(balances)} assets"))
            open_orders = adapter.fetch_open_orders()
            actions.append(RecoveryAction(kind="order_reconcile", details=f"{name}:{len(open_orders)} open orders"))
            positions = adapter.fetch_positions()
            actions.append(RecoveryAction(kind="position_reconcile", details=f"{name}:{len(positions)} positions"))
        return actions
