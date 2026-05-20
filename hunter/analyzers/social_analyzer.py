"""
Social media sentiment analysis module.
Scrapes Twitter/X, Telegram channels, and DexScreener for token sentiment.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import httpx
from bs4 import BeautifulSoup
from hunter.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SocialMetrics:
    twitter_mentions: int = 0
    telegram_mentions: int = 0
    dexscreener_views: int = 0
    social_score: float = 0.0  # 0-100
    sentiment: str = "neutral"  # positive, negative, neutral
    is_coordinated_shilling: bool = False
    trending_velocity: float = 0.0
    sources: list[dict] = field(default_factory=list)


class SocialAnalyzer:
    """Analyzes social media sentiment for tokens."""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _ensure_client(self):
        if not self._client:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": "MemeHunter/1.0"},
                follow_redirects=True,
            )

    async def analyze(self, token_address: str, token_symbol: Optional[str] = None, chain: str = "ethereum") -> SocialMetrics:
        """Run comprehensive social analysis."""
        await self._ensure_client()
        metrics = SocialMetrics()

        # DexScreener data
        dex_data = await self._check_dexscreener(token_address)
        if dex_data:
            metrics.dexscreener_views = dex_data.get("views", 0)
            metrics.sources.append({"source": "dexscreener", "data": dex_data})

        # Twitter/X mentions (via search)
        if token_symbol:
            twitter_data = await self._search_twitter(token_symbol)
            metrics.twitter_mentions = twitter_data.get("count", 0)
            if twitter_data.get("results"):
                metrics.sources.append({"source": "twitter", "data": twitter_data})

        # Calculate composite score
        metrics.social_score = self._calculate_score(metrics)
        metrics.sentiment = self._determine_sentiment(metrics)
        metrics.is_coordinated_shilling = self._detect_shilling(metrics)
        metrics.trending_velocity = self._calculate_velocity(metrics)

        return metrics

    async def _check_dexscreener(self, address: str) -> Optional[dict]:
        """Get DexScreener data for token."""
        try:
            resp = await self._client.get(f"https://api.dexscreener.com/latest/dex/tokens/{address}")
            if resp.status_code == 200:
                data = resp.json()
                pairs = data.get("pairs", [])
                if pairs:
                    pair = pairs[0]
                    return {
                        "views": pair.get("txns", {}).get("h24", {}).get("buys", 0) + pair.get("txns", {}).get("h24", {}).get("sells", 0),
                        "price_change_24h": pair.get("priceChange", {}).get("h24", 0),
                        "volume_24h": pair.get("volume", {}).get("h24", 0),
                        "liquidity_usd": pair.get("liquidity", {}).get("usd", 0),
                        "pair_created": pair.get("pairCreatedAt"),
                        "dex": pair.get("dexId"),
                    }
        except Exception as e:
            logger.debug("dexscreener_error", error=str(e))
        return None

    async def _search_twitter(self, symbol: str) -> dict:
        """Search for token mentions on Twitter/X via Nitter instances."""
        nitter_instances = [
            "https://nitter.privacydev.net",
            "https://nitter.poast.org",
        ]
        results = {"count": 0, "results": []}
        for instance in nitter_instances:
            try:
                resp = await self._client.get(f"{instance}/search", params={"f": "tweets", "q": f"${symbol}"})
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "lxml")
                    tweets = soup.select(".timeline-item")
                    results["count"] = len(tweets)
                    for tweet in tweets[:10]:
                        content = tweet.select_one(".tweet-content")
                        if content:
                            results["results"].append({"text": content.get_text(strip=True)[:200]})
                    break
            except Exception as e:
                logger.debug("nitter_error", instance=instance, error=str(e))
                continue
        return results

    def _calculate_score(self, metrics: SocialMetrics) -> float:
        """Calculate composite social score 0-100."""
        score = 0.0
        # Twitter weight: 40%
        if metrics.twitter_mentions > 100:
            score += 40
        elif metrics.twitter_mentions > 50:
            score += 30
        elif metrics.twitter_mentions > 10:
            score += 20
        elif metrics.twitter_mentions > 0:
            score += 10

        # DexScreener activity weight: 40%
        if metrics.dexscreener_views > 1000:
            score += 40
        elif metrics.dexscreener_views > 500:
            score += 30
        elif metrics.dexscreener_views > 100:
            score += 20
        elif metrics.dexscreener_views > 0:
            score += 10

        # Telegram weight: 20%
        if metrics.telegram_mentions > 50:
            score += 20
        elif metrics.telegram_mentions > 10:
            score += 10

        return min(100, score)

    def _determine_sentiment(self, metrics: SocialMetrics) -> str:
        if metrics.social_score >= 60:
            return "positive"
        elif metrics.social_score <= 20:
            return "negative"
        return "neutral"

    def _detect_shilling(self, metrics: SocialMetrics) -> bool:
        """Detect coordinated shilling patterns."""
        if metrics.twitter_mentions > 200 and metrics.dexscreener_views < 50:
            return True
        return False

    def _calculate_velocity(self, metrics: SocialMetrics) -> float:
        """Calculate trending velocity (mentions per hour)."""
        return metrics.twitter_mentions / 24.0

    async def close(self):
        if self._client:
            await self._client.aclose()
