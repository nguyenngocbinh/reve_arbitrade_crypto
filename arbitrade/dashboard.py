from __future__ import annotations

from dataclasses import dataclass


REQUIRED_SECTIONS = [
    "Overview",
    "Live Opportunities",
    "Trading Sessions",
    "Trades",
    "Orders",
    "Positions",
    "Balances",
    "PnL",
    "Risk",
    "Alerts",
    "Backtest Results",
    "Exchange Health",
    "System Settings",
]


@dataclass(frozen=True)
class DashboardOverview:
    current_pnl: float
    active_opportunities: int
    open_positions: int
    exposure: float
    exchange_connectivity: str
    websocket_status: str
    api_latency_ms: float
    execution_latency_ms: float
    circuit_breaker_status: str
    last_market_data_update: str


def render_overview_html(overview: DashboardOverview) -> str:
    section_list = "".join(f"<li>{section}</li>" for section in REQUIRED_SECTIONS)
    return (
        "<html><body>"
        "<h1>Arbitrade Dashboard</h1>"
        f"<ul>{section_list}</ul>"
        f"<p>Current PnL: {overview.current_pnl:.2f}</p>"
        f"<p>Active Opportunities: {overview.active_opportunities}</p>"
        f"<p>Open Positions: {overview.open_positions}</p>"
        f"<p>Exposure: {overview.exposure:.2f}</p>"
        f"<p>Exchange Connectivity: {overview.exchange_connectivity}</p>"
        f"<p>WebSocket Status: {overview.websocket_status}</p>"
        f"<p>API Latency: {overview.api_latency_ms:.1f} ms</p>"
        f"<p>Execution Latency: {overview.execution_latency_ms:.1f} ms</p>"
        f"<p>Circuit Breaker: {overview.circuit_breaker_status}</p>"
        f"<p>Last Market Data Update: {overview.last_market_data_update}</p>"
        "</body></html>"
    )
