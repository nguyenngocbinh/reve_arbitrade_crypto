from __future__ import annotations

import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone
from uuid import uuid4

from arbitrade.config import AppConfig, validate_live_trading_confirmation
from arbitrade.exchange.adapters import build_default_adapters
from arbitrade.execution import PaperExecutionEngine
from arbitrade.market_data import MarketDataService, MarketDataStore
from arbitrade.models import Exposure, NormalizedMarketData, SessionRecord, SessionStatus, utcnow
from arbitrade.notifications import NotificationLimiter, TelegramNotifier
from arbitrade.opportunity import detect_opportunities
from arbitrade.persistence import Persistence
from arbitrade.recovery import SessionRecovery
from arbitrade.risk import RiskManager
from arbitrade.simulation import PaperAccount, PaperExecutor


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )


async def run(confirmation: str | None = None) -> None:
    config = AppConfig()
    _configure_logging(config.log_level)
    logger = logging.getLogger(__name__)

    if not validate_live_trading_confirmation(config, confirmation):
        raise RuntimeError("Live trading requires explicit ENABLE_LIVE_TRADING confirmation")

    logger.info("Starting Arbitrade in mode=%s", config.trading_mode)

    # ── 1. Initialize database ────────────────────────────────────────────────
    persistence = Persistence(config.db_path)
    persistence.initialize()

    # ── 2. Session record ─────────────────────────────────────────────────────
    session_id = str(uuid4())
    session = SessionRecord(
        id=session_id,
        mode=config.trading_mode,
        enabled_exchanges=list(config.enabled_exchanges),
        enabled_pairs=list(config.enabled_pairs),
    )
    persistence.save_session(
        session_id, config.trading_mode, SessionStatus.STARTING.value,
        list(config.enabled_exchanges), list(config.enabled_pairs), utcnow()
    )

    # ── 3. Build exchange adapters ────────────────────────────────────────────
    use_ccxt = config.use_ccxt and config.trading_mode != "paper"
    adapters = {
        name: adapter
        for name, adapter in build_default_adapters(use_ccxt=use_ccxt).items()
        if name in config.enabled_exchanges
    }

    # ── 4. Paper account ──────────────────────────────────────────────────────
    paper_account = PaperAccount(balances={
        "USDT": config.paper.starting_usdt,
        "BTC": config.paper.starting_btc,
        "ETH": config.paper.starting_eth,
    })

    # ── 5. Market data ────────────────────────────────────────────────────────
    market_store = MarketDataStore(stale_threshold_ms=config.stale_data_threshold_ms)

    # ── 6. Risk engine ────────────────────────────────────────────────────────
    risk_manager = RiskManager(config=config.risk)
    exposure = Exposure(equity=paper_account.get_balance("USDT"), peak_equity=paper_account.get_balance("USDT"))

    # ── 7. Notifications ──────────────────────────────────────────────────────
    telegram = TelegramNotifier(
        token=config.telegram.token,
        chat_id=config.telegram.chat_id,
        limiter=NotificationLimiter(min_interval_seconds=config.telegram.min_interval_seconds),
    )

    # ── 8. Shared app state for dashboard ────────────────────────────────────
    app_state: dict = {
        "mode": config.trading_mode,
        "session_status": SessionStatus.STARTING.value,
        "persistence": persistence,
        "paper_account": paper_account,
        "risk_manager": risk_manager,
        "exposure": exposure,
        "market_store": market_store,
    }

    # ── 9. Paper execution engine ─────────────────────────────────────────────
    paper_executor = PaperExecutor(fee_bps=config.fee_bps, slippage_bps=config.slippage_bps)

    def on_trade(trade):
        persistence.save_trade(trade)
        telegram.notify_trade_executed(trade.symbol, trade.realized_pnl, trade.state)
        logger.info("Trade persisted: %s state=%s pnl=%.4f", trade.id, trade.state, trade.realized_pnl)

    execution_engine = PaperExecutionEngine(paper_executor, paper_account, on_trade=on_trade)

    # ── 10. Recovery ──────────────────────────────────────────────────────────
    _update_session_status(persistence, session_id, SessionStatus.SYNCING, app_state)
    recovery = SessionRecovery(persistence, adapters, paper_account)
    recovery_actions = recovery.recover()
    logger.info("Recovery: %d actions", len(recovery_actions))
    for action in recovery_actions:
        if not action.success:
            logger.warning("Recovery action failed: %s — %s", action.kind, action.error)
            persistence.save_alert(f"Recovery action failed: {action.kind}: {action.error}", severity="warning", category="recovery")

    # ── 11. Connect exchanges ─────────────────────────────────────────────────
    _update_session_status(persistence, session_id, SessionStatus.CONNECTING, app_state)
    for name, adapter in adapters.items():
        try:
            adapter.connect()
            health = adapter.check_health()
            persistence.save_exchange_health(name, "healthy" if health.healthy else "unhealthy", health.latency_ms, health.last_update)
        except Exception as exc:
            logger.warning("Failed to connect to %s: %s", name, exc)
            persistence.save_exchange_health(name, "unhealthy", None, None)
            telegram.notify_exchange_error(name, str(exc))

    # ── 12. Start market data service ─────────────────────────────────────────
    def on_md_update(data: NormalizedMarketData) -> None:
        if not data.bids or not data.asks:
            return
        persistence.save_market_snapshot(
            exchange=data.exchange,
            symbol=data.symbol,
            bid=data.best_bid,
            ask=data.best_ask,
            depth_json="",
            exchange_ts=data.exchange_timestamp.isoformat(),
            local_ts=data.local_receive_timestamp.isoformat(),
            latency_ms=data.market_data_latency_ms,
            stale=False,
        )

    market_service = MarketDataService(
        adapters=adapters,
        symbols=list(config.enabled_pairs),
        store=market_store,
        refresh_seconds=config.market_data_refresh_seconds,
        on_update=on_md_update,
    )
    await market_service.start()

    # ── 13. Start dashboard ───────────────────────────────────────────────────
    dashboard_task = None
    try:
        from arbitrade.dashboard import create_app, _FASTAPI_AVAILABLE
        if _FASTAPI_AVAILABLE:
            import uvicorn
            dash_app = create_app(app_state)
            server_config = uvicorn.Config(
                dash_app,
                host=config.dashboard_host,
                port=config.dashboard_port,
                log_level="warning",
            )
            server = uvicorn.Server(server_config)
            dashboard_task = asyncio.create_task(server.serve())
            logger.info("Dashboard started at http://%s:%d", config.dashboard_host, config.dashboard_port)
    except Exception as exc:
        logger.warning("Dashboard failed to start: %s", exc)

    # ── 14. Notify startup ────────────────────────────────────────────────────
    _update_session_status(persistence, session_id, SessionStatus.RUNNING, app_state)
    telegram.notify_startup(config.trading_mode)
    persistence.save_alert(f"Arbitrade started in {config.trading_mode} mode", category="system")
    logger.info("Arbitrade RUNNING — mode=%s session=%s", config.trading_mode, session_id)

    # ── 15. Main opportunity detection loop ───────────────────────────────────
    shutdown_event = asyncio.Event()

    def _handle_signal(sig, frame):
        logger.info("Received signal %s, shutting down", sig)
        shutdown_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        while not shutdown_event.is_set():
            await _opportunity_cycle(
                config, market_store, execution_engine, persistence,
                risk_manager, exposure, telegram, paper_account, session_id
            )
            await asyncio.sleep(config.market_data_refresh_seconds)
    finally:
        # ── 16. Graceful shutdown ─────────────────────────────────────────────
        logger.info("Shutting down...")
        _update_session_status(persistence, session_id, SessionStatus.STOPPING, app_state)
        await market_service.stop()
        recovery.persist_paper_state(session_id)
        _update_session_status(persistence, session_id, SessionStatus.STOPPED, app_state, ended_at=utcnow())
        telegram.notify_shutdown()
        persistence.save_alert("Arbitrade stopped", category="system")
        if dashboard_task:
            dashboard_task.cancel()
            try:
                await dashboard_task
            except (asyncio.CancelledError, Exception):
                pass
        logger.info("Shutdown complete")


async def _opportunity_cycle(
    config, market_store, execution_engine, persistence, risk_manager, exposure, telegram, paper_account, session_id
) -> None:
    logger = logging.getLogger(__name__)
    for symbol in config.enabled_pairs:
        books = market_store.get_all_fresh(symbol)
        if len(books) < 2:
            continue
        opportunities = detect_opportunities(symbol, books, config.max_trade_quantity, config)
        for opp in opportunities[:1]:  # execute best opportunity per symbol per cycle
            persistence.save_opportunity(opp)
            decision = risk_manager.can_trade(opp, exposure)
            if not decision.approved:
                logger.debug("Risk rejected %s: %s", opp.id, decision.reason)
                persistence.save_risk_event(
                    kind="rejected",
                    severity="info",
                    opportunity_id=opp.id,
                    rule=decision.rule,
                    current_value=decision.current_value,
                    configured_limit=decision.configured_limit,
                    details=decision.reason,
                )
                telegram.notify_risk_rejection(decision.rule or "", decision.reason)
                continue

            telegram.notify_opportunity(opp.symbol, opp.buy_exchange, opp.sell_exchange, opp.expected_net_pnl)
            risk_manager.active_opportunities += 1
            try:
                result = await execution_engine.execute_opportunity(opp)
            finally:
                risk_manager.active_opportunities = max(0, risk_manager.active_opportunities - 1)

            if result.success and result.trade:
                exposure.daily_pnl += result.trade.realized_pnl
                exposure.equity = paper_account.get_balance("USDT")
                if exposure.equity > exposure.peak_equity:
                    exposure.peak_equity = exposure.equity
            elif not result.success:
                risk_manager.register_failed_execution()


def _update_session_status(persistence, session_id, status: SessionStatus, app_state: dict, ended_at=None) -> None:
    persistence.update_session_status(session_id, status.value, ended_at=ended_at)
    app_state["session_status"] = status.value


def bootstrap(confirmation: str | None = None) -> dict:
    """Bootstrap the application synchronously (for tests and CLI checks)."""
    config = AppConfig()
    if not validate_live_trading_confirmation(config, confirmation):
        raise RuntimeError("Live trading requires explicit ENABLE_LIVE_TRADING confirmation")
    persistence = Persistence(config.db_path)
    persistence.initialize()
    adapters = build_default_adapters(use_ccxt=False)
    paper_account = PaperAccount()
    recovery = SessionRecovery(persistence, adapters, paper_account)
    recovery_actions = recovery.recover()
    return {
        "config": config,
        "recovery_actions": recovery_actions,
        "session_status": SessionStatus.READY.value,
    }


if __name__ == "__main__":
    asyncio.run(run())
