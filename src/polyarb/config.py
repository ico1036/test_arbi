"""
Configuration settings for Polymarket Arbitrage Bot
"""
import os
from dataclasses import dataclass, field
from typing import Optional

# Load .env if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass
class APIConfig:
    """API endpoints configuration"""
    gamma_api: str = "https://gamma-api.polymarket.com"
    clob_api: str = "https://clob.polymarket.com"
    ws_clob: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    ws_user: str = "wss://ws-subscriptions-clob.polymarket.com/ws/user"
    timeout: int = 30
    max_concurrent: int = 50  # Max concurrent API requests


@dataclass
class ArbitrageConfig:
    """Arbitrage detection settings"""
    # Thresholds (paper recommends 5%+ for safety margin)
    min_profit_percent: float = 1.0  # Minimum profit % to report
    min_liquidity: float = 1000  # Minimum market liquidity USD

    # Scan settings
    max_markets: int = 500  # Markets to scan
    scan_interval: int = 10  # Seconds between scans

    # Order book depth
    max_position_size: float = 1000  # Max position to analyze depth for
    slippage_threshold: float = 0.5  # Max acceptable slippage %

    # Categories to prioritize (paper: sports=high frequency, politics=high value)
    priority_categories: list = field(default_factory=lambda: ["sports", "politics"])


@dataclass
class AlertConfig:
    """Alert/notification settings"""
    discord_webhook: Optional[str] = field(
        default_factory=lambda: os.getenv("DISCORD_WEBHOOK_URL")
    )
    telegram_token: Optional[str] = field(
        default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN")
    )
    telegram_chat_id: Optional[str] = field(
        default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID")
    )
    enabled: bool = True


@dataclass
class Config:
    """Main configuration"""
    api: APIConfig = field(default_factory=APIConfig)
    arbitrage: ArbitrageConfig = field(default_factory=ArbitrageConfig)
    alerts: AlertConfig = field(default_factory=AlertConfig)
    log_file: str = "arbitrage_opportunities.csv"
    debug: bool = False


# Global config instance
config = Config()
