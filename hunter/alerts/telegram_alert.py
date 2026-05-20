"""
Telegram alert module. Sends real-time alerts via Telegram Bot API.
"""
from typing import Optional
from telegram import Bot
from telegram.constants import ParseMode
from hunter.config import settings
from hunter.alerts.alert_formatter import AlertFormatter
from hunter.logger import get_logger

logger = get_logger(__name__)


class TelegramAlert:
    """Sends formatted alerts to Telegram."""

    def __init__(self):
        self._bot: Optional[Bot] = None
        self._chat_id = settings.telegram_chat_id
        self._enabled = bool(settings.telegram_bot_token and settings.telegram_chat_id)

    async def initialize(self) -> bool:
        if not self._enabled:
            logger.warning("telegram_disabled", msg="No Telegram credentials configured")
            return False
        try:
            self._bot = Bot(token=settings.telegram_bot_token)
            me = await self._bot.get_me()
            logger.info("telegram_connected", bot=me.username)
            return True
        except Exception as e:
            logger.error("telegram_init_error", error=str(e))
            self._enabled = False
            return False

    async def send_alert(self, alert_data: dict) -> bool:
        if not self._enabled or not self._bot:
            return False
        try:
            message = AlertFormatter.format_telegram(alert_data)
            await self._bot.send_message(
                chat_id=self._chat_id, text=message,
                parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True,
            )
            logger.info("telegram_alert_sent", symbol=alert_data.get("symbol"))
            return True
        except Exception as e:
            logger.error("telegram_send_error", error=str(e))
            return False

    @property
    def is_enabled(self) -> bool:
        return self._enabled
