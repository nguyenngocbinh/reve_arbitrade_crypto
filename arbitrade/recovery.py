from __future__ import annotations

import logging
from dataclasses import dataclass

from arbitrade.exchange.base import ExchangeAdapter
from arbitrade.models import utcnow
from arbitrade.persistence import Persistence
from arbitrade.simulation import PaperAccount

logger = logging.getLogger(__name__)


@dataclass
class RecoveryAction:
    kind: str
    details: str
    success: bool = True
    error: str = ""


class SessionRecovery:
    def __init__(
        self,
        persistence: Persistence,
        exchanges: dict[str, ExchangeAdapter],
        paper_account: PaperAccount | None = None,
    ):
        self.persistence = persistence
        self.exchanges = exchanges
        self.paper_account = paper_account

    def recover(self) -> list[RecoveryAction]:
        actions: list[RecoveryAction] = []
        actions.extend(self._reconcile_exchanges())
        actions.extend(self._reconcile_incomplete_trades())
        if self.paper_account is not None:
            actions.extend(self._reconcile_paper_state())
        return actions

    def _reconcile_exchanges(self) -> list[RecoveryAction]:
        actions = []
        for name, adapter in self.exchanges.items():
            try:
                balances = adapter.fetch_balances()
                actions.append(RecoveryAction(
                    kind="balance_reconcile",
                    details=f"{name}: {len(balances)} assets"
                ))
                # Persist recovered balances
                session = self.persistence.get_latest_session()
                session_id = session["id"] if session else "unknown"
                for asset, amount in balances.items():
                    if amount > 0:
                        self.persistence.save_balance(session_id, name, asset, amount, 0.0, amount)
            except Exception as exc:
                logger.warning("Balance reconcile failed for %s: %s", name, exc)
                actions.append(RecoveryAction(kind="balance_reconcile", details=f"{name}: failed", success=False, error=str(exc)))

            try:
                open_orders = adapter.fetch_open_orders()
                actions.append(RecoveryAction(
                    kind="order_reconcile",
                    details=f"{name}: {len(open_orders)} open orders"
                ))
            except Exception as exc:
                logger.warning("Order reconcile failed for %s: %s", name, exc)
                actions.append(RecoveryAction(kind="order_reconcile", details=f"{name}: failed", success=False, error=str(exc)))

            try:
                positions = adapter.fetch_positions()
                actions.append(RecoveryAction(
                    kind="position_reconcile",
                    details=f"{name}: {len(positions)} positions"
                ))
            except Exception as exc:
                logger.warning("Position reconcile failed for %s: %s", name, exc)
                actions.append(RecoveryAction(kind="position_reconcile", details=f"{name}: failed", success=False, error=str(exc)))

        return actions

    def _reconcile_incomplete_trades(self) -> list[RecoveryAction]:
        actions = []
        try:
            incomplete = self.persistence.get_incomplete_trades()
            for trade in incomplete:
                logger.warning("Found incomplete trade %s (state=%s) — marking RECOVERY_REQUIRED", trade["id"], trade["state"])
                self.persistence.save_alert(
                    message=f"Incomplete trade detected on restart: {trade['id']} (state={trade['state']})",
                    severity="warning",
                    category="recovery",
                )
                actions.append(RecoveryAction(
                    kind="incomplete_trade",
                    details=f"trade {trade['id']} state={trade['state']}"
                ))
        except Exception as exc:
            logger.error("Failed to reconcile incomplete trades: %s", exc)
            actions.append(RecoveryAction(kind="incomplete_trade", details="failed", success=False, error=str(exc)))
        return actions

    def _reconcile_paper_state(self) -> list[RecoveryAction]:
        """Restore paper account balances from the persisted state."""
        actions = []
        try:
            session = self.persistence.get_latest_session()
            if not session:
                return actions
            db_balances = self.persistence.get_balances(session_id=session["id"])
            if db_balances:
                # Restore paper account balances from DB
                for row in db_balances:
                    if row["exchange"] == "paper":
                        self.paper_account.balances[row["asset"]] = row["free"]
                actions.append(RecoveryAction(
                    kind="paper_state_reconcile",
                    details=f"Restored {len(db_balances)} balance records"
                ))
                logger.info("Paper account state restored from DB")
            else:
                actions.append(RecoveryAction(
                    kind="paper_state_reconcile",
                    details="No prior paper state found — starting fresh"
                ))
        except Exception as exc:
            logger.error("Paper state reconcile failed: %s", exc)
            actions.append(RecoveryAction(kind="paper_state_reconcile", details="failed", success=False, error=str(exc)))
        return actions

    def persist_paper_state(self, session_id: str) -> None:
        """Persist current paper account state to DB."""
        if self.paper_account is None:
            return
        for asset, amount in self.paper_account.balances.items():
            self.persistence.save_balance(session_id, "paper", asset, amount, 0.0, amount)
