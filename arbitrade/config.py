from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
    _dotenv_path = Path(__file__).resolve().parent.parent / ".env"
    if _dotenv_path.exists():
        load_dotenv(_dotenv_path)
except ImportError:
    pass


def _env(key: str, default: str) -> str:
    return os.getenv(key, default)


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


def _env_tuple(key: str, default: str) -> tuple[str, ...]:
    raw = os.getenv(key, default)
    return tuple(part.strip() for part in raw.split(",") if part.strip())


@dataclass(frozen=True)
class RiskConfig:
    max_position_size: float = field(default_factory=lambda: _env_float("MAX_POSITION_SIZE", 10_000.0))
    max_trade_size: float = field(default_factory=lambda: _env_float("MAX_TRADE_SIZE", 5_000.0))
    max_exposure_per_exchange: float = field(default_factory=lambda: _env_float("MAX_EXPOSURE_PER_EXCHANGE", 20_000.0))
    max_exposure_per_asset: float = field(default_factory=lambda: _env_float("MAX_EXPOSURE_PER_ASSET", 15_000.0))
    max_daily_loss: float = field(default_factory=lambda: _env_float("MAX_DAILY_LOSS", 2_000.0))
    max_drawdown: float = field(default_factory=lambda: _env_float("MAX_DRAWDOWN", 0.2))
    max_concurrent_opportunities: int = field(default_factory=lambda: _env_int("MAX_CONCURRENT_OPPORTUNITIES", 4))
    max_order_age_seconds: int = field(default_factory=lambda: _env_int("MAX_ORDER_AGE_SECONDS", 10))
    stale_market_data_ms: int = field(default_factory=lambda: _env_int("STALE_MARKET_DATA_MS", 1_500))
    cooldown_seconds: int = field(default_factory=lambda: _env_int("COOLDOWN_SECONDS", 10))


@dataclass(frozen=True)
class PaperConfig:
    starting_usdt: float = field(default_factory=lambda: _env_float("PAPER_STARTING_USDT", 100_000.0))
    starting_btc: float = field(default_factory=lambda: _env_float("PAPER_STARTING_BTC", 1.0))
    starting_eth: float = field(default_factory=lambda: _env_float("PAPER_STARTING_ETH", 10.0))
    simulated_latency_ms: int = field(default_factory=lambda: _env_int("PAPER_LATENCY_MS", 50))


@dataclass(frozen=True)
class TelegramConfig:
    token: str | None = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN"))
    chat_id: str | None = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID"))
    min_interval_seconds: int = field(default_factory=lambda: _env_int("TELEGRAM_MIN_INTERVAL_SECONDS", 5))


@dataclass(frozen=True)
class AppConfig:
    db_path: str = field(default_factory=lambda: _env("DATABASE_PATH", "data/arbitrade.db"))
    trading_mode: str = field(default_factory=lambda: _env("TRADING_MODE", "paper"))
    enabled_exchanges: tuple[str, ...] = field(
        default_factory=lambda: _env_tuple("ENABLED_EXCHANGES", "binance,kucoin,okx,bybit")
    )
    enabled_pairs: tuple[str, ...] = field(
        default_factory=lambda: _env_tuple("ENABLED_PAIRS", "BTC/USDT,ETH/USDT")
    )
    fee_bps: float = field(default_factory=lambda: _env_float("FEE_BPS", 10.0))
    slippage_bps: float = field(default_factory=lambda: _env_float("SLIPPAGE_BPS", 5.0))
    min_net_profit: float = field(default_factory=lambda: _env_float("MIN_NET_PROFIT", 1.0))
    max_trade_quantity: float = field(default_factory=lambda: _env_float("MAX_TRADE_QUANTITY", 0.01))
    market_data_refresh_seconds: float = field(default_factory=lambda: _env_float("MARKET_DATA_REFRESH_SECONDS", 2.0))
    stale_data_threshold_ms: int = field(default_factory=lambda: _env_int("STALE_DATA_THRESHOLD_MS", 5_000))
    dashboard_host: str = field(default_factory=lambda: _env("DASHBOARD_HOST", "0.0.0.0"))
    dashboard_port: int = field(default_factory=lambda: _env_int("DASHBOARD_PORT", 8000))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))
    use_ccxt: bool = field(default_factory=lambda: _env("USE_CCXT", "true").lower() == "true")
    risk: RiskConfig = field(default_factory=RiskConfig)
    paper: PaperConfig = field(default_factory=PaperConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)


def validate_live_trading_confirmation(config: AppConfig, confirmation: str | None) -> bool:
    if config.trading_mode != "live":
        return True
    return confirmation == "ENABLE_LIVE_TRADING"
