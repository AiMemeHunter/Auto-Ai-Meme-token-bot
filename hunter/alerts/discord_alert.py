"""
Discord webhook alert module. Sends formatted alerts to Discord channels.
"""
from typing import Optional
import httpx
from hunter.config import settings
from hunter.alerts.alert_formatter import AlertFormatter
from hunter.logger import get_logger

logger = get_logger(__name__)


class DiscordAlert:
    """Sends formatted alerts to Discord via webhooks."""

    def __init__(self):
        self._webhook_url = settings.discord_webhook_url
        self._enabled = bool(self._webhook_url)
        self._client: Optional[httpx.AsyncClient] = None

    async def initialize(self) -> bool:
        if not self._enabled:
            logger.warning("discord_disabled", msg="No Discord webhook configured")
            return False
        self._client = httpx.AsyncClient(timeout=15.0)
        logger.info("discord_alert_ready")
        return True

    async def send_alert(self, alert_data: dict) -> bool:
        if not self._enabled or not self._client:
            return False
        try:
            payload = AlertFormatter.format_discord(alert_data)
            resp = await self._client.post(self._webhook_url, json=payload)
            resp.raise_for_status()
            logger.info("discord_alert_sent", symbol=alert_data.get("symbol"))
            return True
        except Exception as e:
            logger.error("discord_send_error", error=str(e))
            return False

    async def close(self):
        if self._client:
            await self._client.aclose()

    @property
    def is_enabled(self) -> bool:
        return self._enabled
