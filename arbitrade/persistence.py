from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


REQUIRED_TABLES = [
    "sessions",
    "exchanges",
    "markets",
    "opportunities",
    "orders",
    "fills",
    "trades",
    "positions",
    "balances",
    "risk_events",
    "alerts",
    "market_snapshots",
    "backtest_runs",
]

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'STARTING',
    enabled_exchanges TEXT,
    enabled_pairs TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    error_state TEXT
);

CREATE TABLE IF NOT EXISTS exchanges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    status TEXT,
    latency_ms REAL,
    last_update TEXT
);

CREATE TABLE IF NOT EXISTS markets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    base TEXT,
    quote TEXT,
    UNIQUE(exchange, symbol)
);

CREATE TABLE IF NOT EXISTS opportunities (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    buy_exchange TEXT NOT NULL,
    sell_exchange TEXT NOT NULL,
    quantity REAL NOT NULL,
    buy_price REAL,
    sell_price REAL,
    gross_spread REAL,
    estimated_fees REAL,
    estimated_slippage REAL,
    expected_net_pnl REAL,
    required_capital REAL,
    expected_roi REAL,
    status TEXT DEFAULT 'DETECTED',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    opportunity_id TEXT,
    correlation_id TEXT,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL,
    status TEXT NOT NULL DEFAULT 'open',
    filled_quantity REAL DEFAULT 0,
    avg_fill_price REAL DEFAULT 0,
    fee REAL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS fills (
    id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    fee REAL NOT NULL,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trades (
    id TEXT PRIMARY KEY,
    opportunity_id TEXT,
    correlation_id TEXT,
    buy_order_id TEXT,
    sell_order_id TEXT,
    symbol TEXT NOT NULL,
    quantity REAL,
    buy_price REAL,
    sell_price REAL,
    fees REAL DEFAULT 0,
    slippage REAL DEFAULT 0,
    realized_pnl REAL,
    state TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    closed_at TEXT
);

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    quantity REAL NOT NULL,
    entry_price REAL,
    mark_price REAL,
    leverage REAL DEFAULT 1,
    liquidation_distance REAL,
    updated_at TEXT NOT NULL,
    UNIQUE(exchange, symbol)
);

CREATE TABLE IF NOT EXISTS balances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    exchange TEXT NOT NULL,
    asset TEXT NOT NULL,
    free REAL NOT NULL,
    used REAL DEFAULT 0,
    total REAL NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(session_id, exchange, asset)
);

CREATE TABLE IF NOT EXISTS risk_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    severity TEXT DEFAULT 'info',
    opportunity_id TEXT,
    rule TEXT,
    current_value REAL,
    configured_limit REAL,
    details TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT,
    severity TEXT DEFAULT 'info',
    category TEXT,
    message TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    acknowledged INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS market_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    bid REAL,
    ask REAL,
    depth_json TEXT,
    exchange_ts TEXT,
    local_ts TEXT NOT NULL,
    latency_ms REAL,
    stale INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    total_pnl REAL,
    net_pnl REAL,
    roi REAL,
    max_drawdown REAL,
    report_json TEXT
);
"""


@dataclass
class Persistence:
    db_path: str

    def initialize(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(_SCHEMA)
            conn.commit()
        logger.info("Database initialized at %s", self.db_path)

    @contextmanager
    def transaction(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def list_tables(self) -> list[str]:
        with self.transaction() as conn:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        return sorted([row[0] for row in rows])

    # ── Sessions ──────────────────────────────────────────────────────────────

    def save_session(self, session_id: str, mode: str, status: str, enabled_exchanges: list[str], enabled_pairs: list[str], started_at: datetime, ended_at: datetime | None = None, error_state: str | None = None) -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO sessions (id, mode, status, enabled_exchanges, enabled_pairs, started_at, ended_at, error_state)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (session_id, mode, status, json.dumps(enabled_exchanges), json.dumps(enabled_pairs),
                 started_at.isoformat(), ended_at.isoformat() if ended_at else None, error_state)
            )

    def update_session_status(self, session_id: str, status: str, ended_at: datetime | None = None, error_state: str | None = None) -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE sessions SET status=?, ended_at=?, error_state=? WHERE id=?",
                (status, ended_at.isoformat() if ended_at else None, error_state, session_id)
            )

    def get_latest_session(self) -> dict[str, Any] | None:
        with self.transaction() as conn:
            row = conn.execute("SELECT * FROM sessions ORDER BY started_at DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    # ── Opportunities ─────────────────────────────────────────────────────────

    def save_opportunity(self, opp) -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO opportunities
                   (id, symbol, buy_exchange, sell_exchange, quantity, buy_price, sell_price, gross_spread,
                    estimated_fees, estimated_slippage, expected_net_pnl, required_capital, expected_roi, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (opp.id, opp.symbol, opp.buy_exchange, opp.sell_exchange, opp.quantity,
                 opp.executable_buy_price, opp.executable_sell_price, opp.gross_spread,
                 opp.estimated_fees, opp.estimated_slippage, opp.expected_net_pnl,
                 opp.required_capital, opp.expected_roi, opp.status, opp.created_at.isoformat())
            )

    def get_opportunities(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.transaction() as conn:
            rows = conn.execute("SELECT * FROM opportunities ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    # ── Orders ────────────────────────────────────────────────────────────────

    def save_order(self, order) -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO orders
                   (id, opportunity_id, correlation_id, exchange, symbol, side, quantity, price, status,
                    filled_quantity, avg_fill_price, fee, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (order.id, order.opportunity_id, order.correlation_id, order.exchange, order.symbol,
                 order.side, order.quantity, order.price, order.status,
                 order.filled_quantity, order.avg_fill_price, order.fee,
                 order.created_at.isoformat(), order.updated_at.isoformat())
            )

    def get_orders(self, opportunity_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self.transaction() as conn:
            if opportunity_id:
                rows = conn.execute("SELECT * FROM orders WHERE opportunity_id=? ORDER BY created_at DESC LIMIT ?",
                                    (opportunity_id, limit)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    # ── Fills ─────────────────────────────────────────────────────────────────

    def save_fill(self, fill) -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO fills (id, order_id, exchange, symbol, side, quantity, price, fee, timestamp)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (fill.id, fill.order_id, fill.exchange, fill.symbol, fill.side,
                 fill.quantity, fill.price, fill.fee, fill.timestamp.isoformat())
            )

    def get_fills(self, order_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self.transaction() as conn:
            if order_id:
                rows = conn.execute("SELECT * FROM fills WHERE order_id=? ORDER BY timestamp DESC LIMIT ?",
                                    (order_id, limit)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM fills ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    # ── Trades ────────────────────────────────────────────────────────────────

    def save_trade(self, trade) -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO trades
                   (id, opportunity_id, correlation_id, buy_order_id, sell_order_id, symbol, quantity,
                    buy_price, sell_price, fees, slippage, realized_pnl, state, opened_at, closed_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (trade.id, trade.opportunity_id, trade.correlation_id, trade.buy_order_id, trade.sell_order_id,
                 trade.symbol, trade.quantity, trade.buy_price, trade.sell_price,
                 trade.fees, trade.slippage, trade.realized_pnl, trade.state,
                 trade.opened_at.isoformat(), trade.closed_at.isoformat() if trade.closed_at else None)
            )

    def get_trades(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.transaction() as conn:
            rows = conn.execute("SELECT * FROM trades ORDER BY opened_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def get_incomplete_trades(self) -> list[dict[str, Any]]:
        with self.transaction() as conn:
            rows = conn.execute("SELECT * FROM trades WHERE state NOT IN ('COMPLETED', 'FAILED')").fetchall()
        return [dict(row) for row in rows]

    # ── Balances ──────────────────────────────────────────────────────────────

    def save_balance(self, session_id: str, exchange: str, asset: str, free: float, used: float, total: float) -> None:
        now = datetime.utcnow().isoformat()
        with self.transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO balances (session_id, exchange, asset, free, used, total, updated_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (session_id, exchange, asset, free, used, total, now)
            )

    def get_balances(self, session_id: str | None = None) -> list[dict[str, Any]]:
        with self.transaction() as conn:
            if session_id:
                rows = conn.execute("SELECT * FROM balances WHERE session_id=?", (session_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM balances ORDER BY updated_at DESC").fetchall()
        return [dict(row) for row in rows]

    # ── Positions ─────────────────────────────────────────────────────────────

    def save_position(self, exchange: str, symbol: str, quantity: float, entry_price: float, mark_price: float = 0.0) -> None:
        now = datetime.utcnow().isoformat()
        with self.transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO positions (exchange, symbol, quantity, entry_price, mark_price, updated_at)
                   VALUES (?,?,?,?,?,?)""",
                (exchange, symbol, quantity, entry_price, mark_price, now)
            )

    def get_positions(self) -> list[dict[str, Any]]:
        with self.transaction() as conn:
            rows = conn.execute("SELECT * FROM positions WHERE quantity != 0").fetchall()
        return [dict(row) for row in rows]

    # ── Risk Events ───────────────────────────────────────────────────────────

    def save_risk_event(self, kind: str, severity: str = "info", opportunity_id: str | None = None,
                        rule: str | None = None, current_value: float | None = None,
                        configured_limit: float | None = None, details: str = "") -> None:
        now = datetime.utcnow().isoformat()
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO risk_events (kind, severity, opportunity_id, rule, current_value, configured_limit, details, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (kind, severity, opportunity_id, rule, current_value, configured_limit, details, now)
            )

    def get_risk_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.transaction() as conn:
            rows = conn.execute("SELECT * FROM risk_events ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    # ── Alerts ────────────────────────────────────────────────────────────────

    def save_alert(self, message: str, severity: str = "info", category: str = "system", channel: str = "system") -> None:
        now = datetime.utcnow().isoformat()
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO alerts (channel, severity, category, message, created_at) VALUES (?,?,?,?,?)",
                (channel, severity, category, message, now)
            )

    def get_alerts(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.transaction() as conn:
            rows = conn.execute("SELECT * FROM alerts ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def acknowledge_alert(self, alert_id: int) -> None:
        with self.transaction() as conn:
            conn.execute("UPDATE alerts SET acknowledged=1 WHERE id=?", (alert_id,))

    # ── Market Snapshots ──────────────────────────────────────────────────────

    def save_market_snapshot(self, exchange: str, symbol: str, bid: float, ask: float,
                             depth_json: str, exchange_ts: str, local_ts: str,
                             latency_ms: float, stale: bool) -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO market_snapshots (exchange, symbol, bid, ask, depth_json, exchange_ts, local_ts, latency_ms, stale)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (exchange, symbol, bid, ask, depth_json, exchange_ts, local_ts, latency_ms, int(stale))
            )

    # ── Exchange health ───────────────────────────────────────────────────────

    def save_exchange_health(self, name: str, status: str, latency_ms: float | None, last_update: str | None) -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO exchanges (name, status, latency_ms, last_update) VALUES (?,?,?,?)""",
                (name, status, latency_ms, last_update)
            )

    def get_exchange_health(self) -> list[dict[str, Any]]:
        with self.transaction() as conn:
            rows = conn.execute("SELECT * FROM exchanges").fetchall()
        return [dict(row) for row in rows]
