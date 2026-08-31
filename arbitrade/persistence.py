from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


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


@dataclass
class Persistence:
    db_path: str

    def initialize(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, mode TEXT, started_at TEXT, ended_at TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS exchanges (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, status TEXT, latency_ms REAL)")
            conn.execute("CREATE TABLE IF NOT EXISTS markets (id INTEGER PRIMARY KEY AUTOINCREMENT, exchange TEXT, symbol TEXT, base TEXT, quote TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS opportunities (id TEXT PRIMARY KEY, symbol TEXT, buy_exchange TEXT, sell_exchange TEXT, expected_net_pnl REAL, state TEXT, created_at TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, opportunity_id TEXT, exchange TEXT, symbol TEXT, side TEXT, quantity REAL, price REAL, status TEXT, correlation_id TEXT, created_at TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS fills (id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, exchange TEXT, symbol TEXT, side TEXT, quantity REAL, price REAL, fee REAL, created_at TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS trades (id TEXT PRIMARY KEY, opportunity_id TEXT, pnl REAL, state TEXT, opened_at TEXT, closed_at TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS positions (id INTEGER PRIMARY KEY AUTOINCREMENT, exchange TEXT, symbol TEXT, quantity REAL, entry_price REAL, mark_price REAL, leverage REAL, liquidation_distance REAL, updated_at TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS balances (id INTEGER PRIMARY KEY AUTOINCREMENT, exchange TEXT, asset TEXT, free REAL, used REAL, total REAL, updated_at TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS risk_events (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, severity TEXT, details TEXT, created_at TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, channel TEXT, message TEXT, status TEXT, created_at TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS market_snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, exchange TEXT, symbol TEXT, bid REAL, ask REAL, depth_json TEXT, exchange_ts TEXT, local_ts TEXT, latency_ms REAL, stale INTEGER)")
            conn.execute("CREATE TABLE IF NOT EXISTS backtest_runs (id TEXT PRIMARY KEY, started_at TEXT, ended_at TEXT, total_pnl REAL, net_pnl REAL, roi REAL, max_drawdown REAL, report_json TEXT)")

    @contextmanager
    def transaction(self):
        conn = sqlite3.connect(self.db_path)
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
