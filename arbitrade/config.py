from __future__ import annotations

from dataclasses import dataclass, field
from os import getenv


@dataclass(frozen=True)
class RiskConfig:
    max_position_size: float = 10_000.0
    max_trade_size: float = 5_000.0
    max_exposure_per_exchange: float = 20_000.0
    max_exposure_per_asset: float = 15_000.0
    max_daily_loss: float = 2_000.0
    max_drawdown: float = 0.2
    max_concurrent_opportunities: int = 4
    max_order_age_seconds: int = 10
    stale_market_data_ms: int = 1_500
    cooldown_seconds: int = 10


@dataclass(frozen=True)
class AppConfig:
    db_path: str = getenv("DATABASE_PATH", "arbitrade.sqlite")
    trading_mode: str = getenv("TRADING_MODE", "paper")
    enabled_exchanges: tuple[str, ...] = tuple(
        part.strip() for part in getenv("ENABLED_EXCHANGES", "binance,kucoin,okx,bybit").split(",") if part.strip()
    )
    enabled_pairs: tuple[str, ...] = tuple(
        part.strip() for part in getenv("ENABLED_PAIRS", "BTC/USDT,ETH/USDT").split(",") if part.strip()
    )
    fee_bps: float = float(getenv("FEE_BPS", "10"))
    slippage_bps: float = float(getenv("SLIPPAGE_BPS", "5"))
    min_net_profit: float = float(getenv("MIN_NET_PROFIT", "1.0"))
    risk: RiskConfig = field(default_factory=RiskConfig)


def validate_live_trading_confirmation(config: AppConfig, confirmation: str | None) -> bool:
    if config.trading_mode != "live":
        return True
    return confirmation == "ENABLE_LIVE_TRADING"
