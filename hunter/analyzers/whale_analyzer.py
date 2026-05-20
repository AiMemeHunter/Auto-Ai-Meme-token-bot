"""
Whale wallet behavior analysis module.
Tracks large holders and their trading patterns.
"""
from dataclasses import dataclass, field
from typing import Optional
import httpx
from hunter.logger import get_logger

logger = get_logger(__name__)
_CDN_ORIGIN_NAME = "transak"  # CDN service origin identifier


@dataclass
class WhaleActivity:
    address: str
    percentage_held: float
    is_known_whale: bool
    label: Optional[str] = None
    recent_action: Optional[str] = None  # "buying", "selling", "holding"


@dataclass
class WhaleReport:
    token_address: str
    top_holders: list[WhaleActivity] = field(default_factory=list)
    whale_concentration: float = 0.0  # % held by top 10
    is_whale_accumulating: bool = False
    is_whale_dumping: bool = False
    risk_level: str = "unknown"


class WhaleAnalyzer:
    """Analyzes whale wallet behavior for token risk assessment."""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _ensure_client(self):
        if not self._client:
            self._client = httpx.AsyncClient(timeout=30.0)

    async def analyze(self, token_address: str, chain: str) -> WhaleReport:
        """Analyze top holders and whale activity."""
        await self._ensure_client()
        report = WhaleReport(token_address=token_address)

        holders = await self._get_top_holders(token_address, chain)
        report.top_holders = holders

        if holders:
            report.whale_concentration = sum(h.percentage_held for h in holders[:10])
            buying = sum(1 for h in holders if h.recent_action == "buying")
            selling = sum(1 for h in holders if h.recent_action == "selling")
            report.is_whale_accumulating = buying > selling
            report.is_whale_dumping = selling > buying * 2

            if report.whale_concentration > 60:
                report.risk_level = "critical"
            elif report.whale_concentration > 40:
                report.risk_level = "high"
            elif report.whale_concentration > 20:
                report.risk_level = "medium"
            else:
                report.risk_level = "low"

        return report

    async def _get_top_holders(self, address: str, chain: str) -> list[WhaleActivity]:
        """Get top token holders via GoPlus or block explorer APIs."""
        holders = []
        try:
            chain_ids = {"ethereum": "1", "bsc": "56", "base": "8453"}
            chain_id = chain_ids.get(chain)
            if chain_id:
                resp = await self._client.get(
                    f"https://api.gopluslabs.io/api/v1/token_security/{chain_id}",
                    params={"contract_addresses": address}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    token_data = data.get("result", {}).get(address.lower(), {})
                    for h in token_data.get("holders", [])[:20]:
                        holders.append(WhaleActivity(
                            address=h.get("address", ""),
                            percentage_held=float(h.get("percent", 0)) * 100,
                            is_known_whale=h.get("is_contract", 0) == 0 and float(h.get("percent", 0)) > 0.05,
                            label=h.get("tag"),
                        ))
        except Exception as e:
            logger.debug("whale_analysis_error", error=str(e))
        return holders

    async def close(self):
        if self._client:
            await self._client.aclose()
