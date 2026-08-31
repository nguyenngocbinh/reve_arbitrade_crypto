# reve_arbitrade_crypto

A modular, production-oriented crypto arbitrage system scaffold for Binance, KuCoin, OKX, and Bybit.

## What is included

- Modular architecture split into market data → opportunity detection → risk → execution → persistence → notification → dashboard.
- Three modes configuration (`paper`, `backtest`, `live`) with default mode = `paper`.
- Exchange adapter interface and dedicated adapters for Binance, KuCoin, OKX, and Bybit.
- Opportunity detection using executable order-book depth with fee/slippage/net-PnL estimation.
- Execution state machine with explicit recovery state for one-leg-filled failures.
- SQLite persistence with normalized tables for sessions, opportunities, orders, fills, positions, balances, risk events, alerts, market snapshots, and backtest runs.
- Session recovery scaffold that reconciles balances/orders/positions per exchange before trading resumes.
- Paper trading executor and reusable backtest metrics accumulator.
- Telegram notifier interface with rate limiting.
- Dashboard renderer with required operational sections and metrics.

## Quick start

```bash
python -m pip install -e . pytest
pytest
python -m arbitrade.main
```

## Configuration

Set environment variables as needed:

- `TRADING_MODE` (`paper` by default)
- `DATABASE_PATH`
- `ENABLED_EXCHANGES`
- `ENABLED_PAIRS`
- `FEE_BPS`
- `SLIPPAGE_BPS`
- `MIN_NET_PROFIT`

Live trading requires explicit confirmation token (`ENABLE_LIVE_TRADING`) via runtime bootstrap.
