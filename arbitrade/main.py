from __future__ import annotations

from datetime import datetime, timezone

from arbitrade.config import AppConfig, validate_live_trading_confirmation
from arbitrade.dashboard import DashboardOverview, render_overview_html
from arbitrade.exchange.adapters import build_default_adapters
from arbitrade.persistence import Persistence
from arbitrade.recovery import SessionRecovery


def bootstrap(confirmation: str | None = None) -> dict[str, object]:
    config = AppConfig()
    if not validate_live_trading_confirmation(config, confirmation):
        raise RuntimeError("Live trading requires explicit ENABLE_LIVE_TRADING confirmation")

    persistence = Persistence(config.db_path)
    persistence.initialize()
    adapters = build_default_adapters()
    recovery = SessionRecovery(persistence, adapters)
    recovery_actions = recovery.recover()
    dashboard_html = render_overview_html(
        DashboardOverview(
            current_pnl=0.0,
            active_opportunities=0,
            open_positions=0,
            exposure=0.0,
            exchange_connectivity="healthy",
            websocket_status="connected",
            api_latency_ms=0.0,
            execution_latency_ms=0.0,
            circuit_breaker_status="closed",
            last_market_data_update=datetime.now(timezone.utc).isoformat(),
        )
    )
    return {"config": config, "recovery_actions": recovery_actions, "dashboard_html": dashboard_html}


if __name__ == "__main__":
    state = bootstrap()
    print(f"bootstrapped in mode={state['config'].trading_mode} with {len(state['recovery_actions'])} recovery actions")
