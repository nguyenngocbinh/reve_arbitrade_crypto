from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


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
    realized_pnl: float
    unrealized_pnl: float
    active_opportunities: int
    open_positions: int
    exposure: float
    trade_count: int
    win_rate: float
    exchange_connectivity: str
    websocket_status: str
    api_latency_ms: float
    execution_latency_ms: float
    circuit_breaker_status: str
    last_market_data_update: str
    session_status: str
    trading_mode: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_pnl": self.current_pnl,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "active_opportunities": self.active_opportunities,
            "open_positions": self.open_positions,
            "exposure": self.exposure,
            "trade_count": self.trade_count,
            "win_rate": self.win_rate,
            "exchange_connectivity": self.exchange_connectivity,
            "websocket_status": self.websocket_status,
            "api_latency_ms": self.api_latency_ms,
            "execution_latency_ms": self.execution_latency_ms,
            "circuit_breaker_status": self.circuit_breaker_status,
            "last_market_data_update": self.last_market_data_update,
            "session_status": self.session_status,
            "trading_mode": self.trading_mode,
        }


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


try:
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse
    import uvicorn

    def create_app(app_state: dict[str, Any]) -> FastAPI:
        """Create and configure the FastAPI dashboard application."""
        app = FastAPI(title="Arbitrade Dashboard", version="0.1.0")

        @app.get("/", response_class=HTMLResponse)
        async def root():
            return _DASHBOARD_HTML

        @app.get("/api/health")
        async def health():
            return {"status": "ok", "mode": app_state.get("mode", "paper")}

        @app.get("/api/overview")
        async def get_overview():
            overview = _build_overview(app_state)
            return overview.to_dict()

        @app.get("/api/opportunities")
        async def get_opportunities():
            persistence = app_state.get("persistence")
            if persistence:
                return persistence.get_opportunities(limit=50)
            return []

        @app.get("/api/trades")
        async def get_trades():
            persistence = app_state.get("persistence")
            if persistence:
                return persistence.get_trades(limit=50)
            return []

        @app.get("/api/orders")
        async def get_orders():
            persistence = app_state.get("persistence")
            if persistence:
                return persistence.get_orders(limit=100)
            return []

        @app.get("/api/positions")
        async def get_positions():
            persistence = app_state.get("persistence")
            if persistence:
                return persistence.get_positions()
            return []

        @app.get("/api/risk")
        async def get_risk():
            risk_manager = app_state.get("risk_manager")
            cb = risk_manager.circuit_breaker if risk_manager else None
            exposure = app_state.get("exposure")
            return {
                "circuit_breaker": {"open": cb.is_open, "reason": cb.reason} if cb else {},
                "daily_pnl": exposure.daily_pnl if exposure else 0.0,
                "drawdown": _calc_drawdown(exposure),
                "active_opportunities": risk_manager.active_opportunities if risk_manager else 0,
            }

        @app.get("/api/alerts")
        async def get_alerts():
            persistence = app_state.get("persistence")
            if persistence:
                return persistence.get_alerts(limit=100)
            return []

        @app.get("/api/exchanges")
        async def get_exchanges():
            persistence = app_state.get("persistence")
            if persistence:
                return persistence.get_exchange_health()
            return []

        @app.get("/api/balances")
        async def get_balances():
            paper_account = app_state.get("paper_account")
            if paper_account:
                return [
                    {"asset": asset, "free": amount, "total": amount}
                    for asset, amount in paper_account.balances.items()
                    if amount > 0
                ]
            return []

        return app

    def _build_overview(state: dict[str, Any]) -> DashboardOverview:
        paper_account = state.get("paper_account")
        risk_manager = state.get("risk_manager")
        exposure = state.get("exposure")
        market_store = state.get("market_store")
        persistence = state.get("persistence")

        realized_pnl = paper_account.realized_pnl if paper_account else 0.0
        cb = risk_manager.circuit_breaker if risk_manager else None
        cb_status = "open" if (cb and cb.is_open) else "closed"

        trades = persistence.get_trades(limit=1000) if persistence else []
        completed = [t for t in trades if t.get("state") == "COMPLETED"]
        wins = [t for t in completed if (t.get("realized_pnl") or 0) > 0]
        win_rate = len(wins) / len(completed) if completed else 0.0

        last_update = ""
        if market_store:
            all_data = market_store.all_data()
            if all_data:
                latest = max(all_data, key=lambda d: d.local_receive_timestamp)
                last_update = latest.local_receive_timestamp.isoformat()

        connectivity = "healthy"
        if persistence:
            exchange_health = persistence.get_exchange_health()
            unhealthy = [e for e in exchange_health if e.get("status") != "healthy"]
            if unhealthy:
                connectivity = f"{len(unhealthy)} exchange(s) unhealthy"

        return DashboardOverview(
            current_pnl=realized_pnl,
            realized_pnl=realized_pnl,
            unrealized_pnl=paper_account.unrealized_pnl if paper_account else 0.0,
            active_opportunities=risk_manager.active_opportunities if risk_manager else 0,
            open_positions=len([v for v in (paper_account.positions.values() if paper_account else []) if v != 0]),
            exposure=exposure.by_exchange.get("paper", 0.0) if exposure else 0.0,
            trade_count=len(completed),
            win_rate=win_rate,
            exchange_connectivity=connectivity,
            websocket_status="polling",
            api_latency_ms=0.0,
            execution_latency_ms=0.0,
            circuit_breaker_status=cb_status,
            last_market_data_update=last_update,
            session_status=state.get("session_status", "UNKNOWN"),
            trading_mode=state.get("mode", "paper"),
        )

    def _calc_drawdown(exposure) -> float:
        if not exposure or exposure.peak_equity <= 0:
            return 0.0
        return max(0.0, (exposure.peak_equity - exposure.equity) / exposure.peak_equity)

    _DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Arbitrade Dashboard</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 0; background: #0f1117; color: #e2e8f0; }
  header { background: #1a1d2e; padding: 1rem 2rem; border-bottom: 1px solid #2d3748; display: flex; align-items: center; gap: 1rem; }
  h1 { margin: 0; font-size: 1.4rem; color: #7ee787; }
  .mode-badge { background: #2d3748; padding: 0.2rem 0.6rem; border-radius: 9999px; font-size: 0.75rem; }
  nav { display: flex; gap: 0.5rem; padding: 1rem 2rem; background: #13151f; border-bottom: 1px solid #1a1d2e; flex-wrap: wrap; }
  nav button { background: none; border: 1px solid #2d3748; color: #a0aec0; padding: 0.4rem 0.9rem; border-radius: 6px; cursor: pointer; font-size: 0.85rem; }
  nav button.active { background: #2d5a9e; border-color: #4a90e2; color: #fff; }
  main { padding: 1.5rem 2rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }
  .card { background: #1a1d2e; border: 1px solid #2d3748; border-radius: 8px; padding: 1rem; }
  .card .label { font-size: 0.75rem; color: #718096; margin-bottom: 0.25rem; text-transform: uppercase; }
  .card .value { font-size: 1.5rem; font-weight: 700; }
  .card .value.green { color: #48bb78; }
  .card .value.red { color: #fc8181; }
  .card .value.yellow { color: #f6e05e; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th { text-align: left; padding: 0.5rem 0.75rem; color: #718096; border-bottom: 1px solid #2d3748; font-size: 0.75rem; text-transform: uppercase; }
  td { padding: 0.5rem 0.75rem; border-bottom: 1px solid #1a1d2e; }
  tr:hover td { background: #1a1d2e; }
  .section { display: none; }
  .section.active { display: block; }
  .status-ok { color: #48bb78; }
  .status-err { color: #fc8181; }
  .refresh { float: right; font-size: 0.75rem; color: #718096; }
</style>
</head>
<body>
<header>
  <h1>⚡ Arbitrade</h1>
  <span class="mode-badge" id="mode-badge">PAPER</span>
  <span class="mode-badge" id="session-status">STARTING</span>
  <span class="refresh" id="last-refresh"></span>
</header>
<nav>
  <button class="active" onclick="showSection('overview')">Overview</button>
  <button onclick="showSection('opportunities')">Opportunities</button>
  <button onclick="showSection('trades')">Trades</button>
  <button onclick="showSection('orders')">Orders</button>
  <button onclick="showSection('positions')">Positions</button>
  <button onclick="showSection('risk')">Risk</button>
  <button onclick="showSection('alerts')">Alerts</button>
  <button onclick="showSection('exchanges')">Exchange Health</button>
  <button onclick="showSection('balances')">Balances</button>
</nav>
<main>
  <div id="overview" class="section active">
    <div class="grid" id="overview-grid"></div>
  </div>
  <div id="opportunities" class="section">
    <table id="opp-table"><thead><tr><th>Symbol</th><th>Buy</th><th>Sell</th><th>Spread</th><th>Net PnL</th><th>Status</th><th>Time</th></tr></thead><tbody></tbody></table>
  </div>
  <div id="trades" class="section">
    <table id="trades-table"><thead><tr><th>ID</th><th>Symbol</th><th>Qty</th><th>Buy</th><th>Sell</th><th>PnL</th><th>State</th><th>Time</th></tr></thead><tbody></tbody></table>
  </div>
  <div id="orders" class="section">
    <table id="orders-table"><thead><tr><th>ID</th><th>Exchange</th><th>Side</th><th>Qty</th><th>Price</th><th>Filled</th><th>Status</th></tr></thead><tbody></tbody></table>
  </div>
  <div id="positions" class="section">
    <table id="pos-table"><thead><tr><th>Exchange</th><th>Symbol</th><th>Qty</th><th>Entry</th><th>Mark</th></tr></thead><tbody></tbody></table>
  </div>
  <div id="risk" class="section">
    <div class="grid" id="risk-grid"></div>
  </div>
  <div id="alerts" class="section">
    <table id="alerts-table"><thead><tr><th>Severity</th><th>Category</th><th>Message</th><th>Time</th></tr></thead><tbody></tbody></table>
  </div>
  <div id="exchanges" class="section">
    <table id="exch-table"><thead><tr><th>Exchange</th><th>Status</th><th>Latency</th><th>Last Update</th></tr></thead><tbody></tbody></table>
  </div>
  <div id="balances" class="section">
    <table id="bal-table"><thead><tr><th>Asset</th><th>Free</th><th>Total</th></tr></thead><tbody></tbody></table>
  </div>
</main>
<script>
function showSection(name) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.getElementById(name).classList.add('active');
  document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
}
function fmt(v, digits=4) { return typeof v === 'number' ? v.toFixed(digits) : v; }
function pnlClass(v) { return v > 0 ? 'green' : v < 0 ? 'red' : ''; }
function card(label, value, cls='') {
  return `<div class="card"><div class="label">${label}</div><div class="value ${cls}">${value}</div></div>`;
}
async function refresh() {
  try {
    const [ov, opps, trades, orders, pos, risk, alerts, exch, bal] = await Promise.all([
      fetch('/api/overview').then(r=>r.json()),
      fetch('/api/opportunities').then(r=>r.json()),
      fetch('/api/trades').then(r=>r.json()),
      fetch('/api/orders').then(r=>r.json()),
      fetch('/api/positions').then(r=>r.json()),
      fetch('/api/risk').then(r=>r.json()),
      fetch('/api/alerts').then(r=>r.json()),
      fetch('/api/exchanges').then(r=>r.json()),
      fetch('/api/balances').then(r=>r.json()),
    ]);
    document.getElementById('mode-badge').textContent = (ov.trading_mode||'paper').toUpperCase();
    document.getElementById('session-status').textContent = ov.session_status || '';
    document.getElementById('last-refresh').textContent = 'Updated: ' + new Date().toLocaleTimeString();
    document.getElementById('overview-grid').innerHTML = [
      card('Realized PnL', fmt(ov.realized_pnl, 2), pnlClass(ov.realized_pnl)),
      card('Unrealized PnL', fmt(ov.unrealized_pnl, 2), pnlClass(ov.unrealized_pnl)),
      card('Trades', ov.trade_count),
      card('Win Rate', fmt(ov.win_rate*100,1)+'%', ov.win_rate > 0.5 ? 'green' : ''),
      card('Open Positions', ov.open_positions),
      card('Active Opps', ov.active_opportunities),
      card('Circuit Breaker', ov.circuit_breaker_status, ov.circuit_breaker_status==='open'?'red':'green'),
      card('Mode', ov.trading_mode||'paper', 'yellow'),
    ].join('');
    const ob = document.querySelector('#opp-table tbody');
    ob.innerHTML = opps.map(o=>`<tr><td>${o.symbol}</td><td>${o.buy_exchange}</td><td>${o.sell_exchange}</td><td>${fmt(o.gross_spread,2)}</td><td class="${pnlClass(o.expected_net_pnl)}">${fmt(o.expected_net_pnl,4)}</td><td>${o.status}</td><td>${(o.created_at||'').slice(0,19)}</td></tr>`).join('');
    const tb = document.querySelector('#trades-table tbody');
    tb.innerHTML = trades.map(t=>`<tr><td>${(t.id||'').slice(0,8)}</td><td>${t.symbol}</td><td>${fmt(t.quantity,6)}</td><td>${fmt(t.buy_price,2)}</td><td>${fmt(t.sell_price,2)}</td><td class="${pnlClass(t.realized_pnl)}">${fmt(t.realized_pnl,4)}</td><td>${t.state}</td><td>${(t.opened_at||'').slice(0,19)}</td></tr>`).join('');
    const orb = document.querySelector('#orders-table tbody');
    orb.innerHTML = orders.map(o=>`<tr><td>${(o.id||'').slice(0,8)}</td><td>${o.exchange}</td><td>${o.side}</td><td>${fmt(o.quantity,6)}</td><td>${fmt(o.price,2)}</td><td>${fmt(o.filled_quantity,6)}</td><td>${o.status}</td></tr>`).join('');
    const pb = document.querySelector('#pos-table tbody');
    pb.innerHTML = pos.map(p=>`<tr><td>${p.exchange}</td><td>${p.symbol}</td><td>${fmt(p.quantity,6)}</td><td>${fmt(p.entry_price,2)}</td><td>${fmt(p.mark_price,2)}</td></tr>`).join('');
    document.getElementById('risk-grid').innerHTML = [
      card('Circuit Breaker', risk.circuit_breaker?.open?'OPEN':'CLOSED', risk.circuit_breaker?.open?'red':'green'),
      card('Daily PnL', fmt(risk.daily_pnl,2), pnlClass(risk.daily_pnl)),
      card('Drawdown', fmt(risk.drawdown*100,2)+'%', risk.drawdown > 0.1 ? 'red' : ''),
      card('Active Opps', risk.active_opportunities),
    ].join('');
    const ab = document.querySelector('#alerts-table tbody');
    ab.innerHTML = alerts.map(a=>`<tr><td>${a.severity}</td><td>${a.category}</td><td>${a.message}</td><td>${(a.created_at||'').slice(0,19)}</td></tr>`).join('');
    const eb = document.querySelector('#exch-table tbody');
    eb.innerHTML = exch.map(e=>`<tr><td>${e.name}</td><td class="${e.status==='healthy'?'status-ok':'status-err'}">${e.status}</td><td>${e.latency_ms!=null?fmt(e.latency_ms,1)+' ms':'—'}</td><td>${(e.last_update||'').slice(0,19)}</td></tr>`).join('');
    const bb = document.querySelector('#bal-table tbody');
    bb.innerHTML = bal.map(b=>`<tr><td>${b.asset}</td><td>${fmt(b.free,6)}</td><td>${fmt(b.total,6)}</td></tr>`).join('');
  } catch(e) { console.error('Dashboard refresh error:', e); }
}
refresh();
setInterval(refresh, 3000);
</script>
</body>
</html>"""

    _FASTAPI_AVAILABLE = True

except ImportError:
    _FASTAPI_AVAILABLE = False
    logger.warning("FastAPI not installed — dashboard will not start")
