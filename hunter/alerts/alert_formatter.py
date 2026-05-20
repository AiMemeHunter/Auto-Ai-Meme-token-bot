"""
Alert message formatting templates for Telegram, Discord, and API.
"""
from datetime import datetime
from typing import Optional


class AlertFormatter:
    """Formats alert messages for different platforms."""

    LEVEL_EMOJIS = {
        "critical": "🚨",
        "high": "🔥",
        "medium": "⚠️",
        "low": "📊",
        "info": "ℹ️",
    }

    CHAIN_EMOJIS = {
        "solana": "◎",
        "bsc": "🔶",
        "ethereum": "⟠",
        "base": "🔵",
    }

    @classmethod
    def format_telegram(cls, alert_data: dict) -> str:
        """Format alert for Telegram (Markdown)."""
        level = alert_data.get("level", "info")
        emoji = cls.LEVEL_EMOJIS.get(level, "📋")
        chain_emoji = cls.CHAIN_EMOJIS.get(alert_data.get("chain", ""), "")

        lines = [
            f"{emoji} *{level.upper()} ALERT* {emoji}",
            "",
            f"{chain_emoji} *{alert_data.get('symbol', 'Unknown')}* on {alert_data.get('chain', 'unknown').upper()}",
            f"📍 `{alert_data.get('address', 'N/A')}`",
            "",
        ]

        if alert_data.get("safety_score") is not None:
            score = alert_data["safety_score"]
            bar = cls._score_bar(score)
            lines.append(f"🛡 Safety: {bar} {score}/100")

        if alert_data.get("rugpull_risk") is not None:
            lines.append(f"⚠️ Rug Risk: {alert_data['rugpull_risk']:.0f}%")

        if alert_data.get("liquidity_usd"):
            lines.append(f"💰 Liquidity: ${alert_data['liquidity_usd']:,.0f}")

        if alert_data.get("price_usd"):
            lines.append(f"💵 Price: ${alert_data['price_usd']:.8f}")

        if alert_data.get("dex"):
            lines.append(f"🏪 DEX: {alert_data['dex']}")

        lines.extend([
            "",
            f"🔗 [DexScreener](https://dexscreener.com/{alert_data.get('chain', '')}/{alert_data.get('address', '')})",
            f"⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        ])

        return "\n".join(lines)

    @classmethod
    def format_discord(cls, alert_data: dict) -> dict:
        """Format alert for Discord webhook (embed)."""
        level = alert_data.get("level", "info")
        colors = {"critical": 0x00FF00, "high": 0xFFD700, "medium": 0xFFA500, "low": 0xFF6347, "info": 0x808080}

        fields = []
        if alert_data.get("safety_score") is not None:
            fields.append({"name": "🛡 Safety Score", "value": f"{alert_data['safety_score']}/100", "inline": True})
        if alert_data.get("rugpull_risk") is not None:
            fields.append({"name": "⚠️ Rug Risk", "value": f"{alert_data['rugpull_risk']:.0f}%", "inline": True})
        if alert_data.get("liquidity_usd"):
            fields.append({"name": "💰 Liquidity", "value": f"${alert_data['liquidity_usd']:,.0f}", "inline": True})
        if alert_data.get("dex"):
            fields.append({"name": "🏪 DEX", "value": alert_data["dex"], "inline": True})

        return {
            "embeds": [{
                "title": f"{cls.LEVEL_EMOJIS.get(level, '')} {alert_data.get('symbol', 'Unknown')} — {level.upper()}",
                "description": f"New token on **{alert_data.get('chain', 'unknown').upper()}**\n`{alert_data.get('address', '')}`",
                "color": colors.get(level, 0x808080),
                "fields": fields,
                "url": f"https://dexscreener.com/{alert_data.get('chain', '')}/{alert_data.get('address', '')}",
                "timestamp": datetime.utcnow().isoformat(),
                "footer": {"text": "Meme Token Hunter 🤖"},
            }]
        }

    @classmethod
    def format_api(cls, alert_data: dict) -> dict:
        """Format alert for REST API response."""
        return {
            "level": alert_data.get("level"),
            "token": {
                "address": alert_data.get("address"),
                "symbol": alert_data.get("symbol"),
                "name": alert_data.get("name"),
                "chain": alert_data.get("chain"),
            },
            "analysis": {
                "safety_score": alert_data.get("safety_score"),
                "rugpull_risk": alert_data.get("rugpull_risk"),
                "is_honeypot": alert_data.get("is_honeypot"),
                "social_score": alert_data.get("social_score"),
            },
            "market": {
                "price_usd": alert_data.get("price_usd"),
                "liquidity_usd": alert_data.get("liquidity_usd"),
                "dex": alert_data.get("dex"),
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def _score_bar(score: float, length: int = 10) -> str:
        filled = int(score / 100 * length)
        return "█" * filled + "░" * (length - filled)
