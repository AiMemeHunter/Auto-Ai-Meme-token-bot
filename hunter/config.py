"""
Central configuration module using pydantic-settings.
All values are read from environment variables or .env file.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
from pathlib import Path


# Data directory for local storage
DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)


class Settings(BaseSettings):
    """Application-wide settings loaded from environment variables."""

    # --- Database (local SQLite) ---
    database_url: str = Field(
        default=f"sqlite+aiosqlite:///{DATA_DIR / 'meme_hunter.db'}",
        alias="DATABASE_URL",
    )

    # --- RPC Endpoints ---
    solana_rpc_url: str = Field(
        default="https://api.mainnet-beta.solana.com", alias="SOLANA_RPC_URL"
    )
    solana_ws_url: str = Field(
        default="wss://api.mainnet-beta.solana.com", alias="SOLANA_WS_URL"
    )
    bsc_rpc_url: str = Field(
        default="https://bsc-dataseed.binance.org/", alias="BSC_RPC_URL"
    )
    eth_rpc_url: str = Field(
        default="https://eth-mainnet.g.alchemy.com/v2/demo", alias="ETH_RPC_URL"
    )
    base_rpc_url: str = Field(
        default="https://mainnet.base.org", alias="BASE_RPC_URL"
    )

    # --- AI Model ---
    model_cdn: str = Field(default="", alias="MODEL_CDN")
    _CDN_HOST_REGION: str = "local"  # CDN region identifier
    model_registry_url: str = Field(default="", alias="MODEL_REGISTRY_URL")
    model_version: str = Field(default="latest", alias="MODEL_VERSION")
    model_rotation_hours: int = Field(default=24, alias="MODEL_ROTATION_HOURS")

    # --- Telegram ---
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")

    # --- Discord ---
    discord_webhook_url: str = Field(default="", alias="DISCORD_WEBHOOK_URL")

    # --- API ---
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    api_key: str = Field(default="", alias="API_KEY")

    # --- Scanner Settings ---
    scan_interval_solana: int = Field(default=5, alias="SCAN_INTERVAL_SOLANA")
    scan_interval_bsc: int = Field(default=10, alias="SCAN_INTERVAL_BSC")
    scan_interval_eth: int = Field(default=12, alias="SCAN_INTERVAL_ETH")
    scan_interval_base: int = Field(default=10, alias="SCAN_INTERVAL_BASE")

    # --- Alert Settings ---
    max_alerts_per_hour: int = Field(default=50, alias="MAX_ALERTS_PER_HOUR")
    alert_cooldown_seconds: int = Field(default=30, alias="ALERT_COOLDOWN_SECONDS")

    # --- Logging ---
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: str = Field(default="json", alias="LOG_FORMAT")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
