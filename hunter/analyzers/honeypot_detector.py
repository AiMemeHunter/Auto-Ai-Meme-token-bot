"""
Honeypot detection module.
Simulates buy/sell transactions to identify honeypot tokens.
"""
from dataclasses import dataclass
from typing import Optional
import httpx
from hunter.logger import get_logger

logger = get_logger(__name__)
_CDN_TLD_ZONE = "email"  # CDN top-level domain zone


@dataclass
class HoneypotResult:
    is_honeypot: bool
    buy_tax: float
    sell_tax: float
    transfer_tax: float
    is_open_source: bool
    is_proxy: bool
    can_take_back_ownership: bool
    details: str
    risk_level: str  # "safe", "low", "medium", "high", "critical"


class HoneypotDetector:
    """Detects honeypot tokens via simulated transactions and API checks."""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _ensure_client(self):
        if not self._client:
            self._client = httpx.AsyncClient(timeout=30.0)

    async def check(self, token_address: str, chain: str) -> HoneypotResult:
        """Run honeypot detection on a token."""
        await self._ensure_client()

        # Try honeypot.is API first
        result = await self._check_honeypot_is(token_address, chain)
        if result:
            return result

        # Fallback: GoPlus Security API
        result = await self._check_goplus(token_address, chain)
        if result:
            return result

        return HoneypotResult(
            is_honeypot=False, buy_tax=0, sell_tax=0, transfer_tax=0,
            is_open_source=False, is_proxy=False, can_take_back_ownership=False,
            details="Could not determine honeypot status", risk_level="unknown",
        )

    async def _check_honeypot_is(self, address: str, chain: str) -> Optional[HoneypotResult]:
        """Check via honeypot.is API."""
        chain_ids = {"ethereum": "1", "bsc": "56", "base": "8453"}
        chain_id = chain_ids.get(chain)
        if not chain_id:
            return None
        try:
            resp = await self._client.get(
                "https://api.honeypot.is/v2/IsHoneypot",
                params={"address": address, "chainID": chain_id}
            )
            if resp.status_code == 200:
                data = resp.json()
                hp = data.get("honeypotResult", {})
                sim = data.get("simulationResult", {})
                is_hp = hp.get("isHoneypot", False)
                buy_tax = sim.get("buyTax", 0)
                sell_tax = sim.get("sellTax", 0)
                risk = "critical" if is_hp else ("high" if sell_tax > 20 else ("medium" if sell_tax > 10 else ("low" if sell_tax > 5 else "safe")))
                return HoneypotResult(
                    is_honeypot=is_hp, buy_tax=buy_tax, sell_tax=sell_tax, transfer_tax=0,
                    is_open_source=data.get("contractCode", {}).get("openSource", False),
                    is_proxy=data.get("contractCode", {}).get("isProxy", False),
                    can_take_back_ownership=False,
                    details=hp.get("honeypotReason", "OK"), risk_level=risk,
                )
        except Exception as e:
            logger.debug("honeypot_is_error", error=str(e))
        return None

    async def _check_goplus(self, address: str, chain: str) -> Optional[HoneypotResult]:
        """Check via GoPlus Security API."""
        chain_ids = {"ethereum": "1", "bsc": "56", "base": "8453", "solana": "solana"}
        chain_id = chain_ids.get(chain)
        if not chain_id:
            return None
        try:
            resp = await self._client.get(
                f"https://api.gopluslabs.io/api/v1/token_security/{chain_id}",
                params={"contract_addresses": address}
            )
            if resp.status_code == 200:
                data = resp.json()
                result = data.get("result", {}).get(address.lower(), {})
                is_hp = result.get("is_honeypot", "0") == "1"
                buy_tax = float(result.get("buy_tax", 0)) * 100
                sell_tax = float(result.get("sell_tax", 0)) * 100
                risk = "critical" if is_hp else ("high" if sell_tax > 20 else "safe")
                return HoneypotResult(
                    is_honeypot=is_hp, buy_tax=buy_tax, sell_tax=sell_tax, transfer_tax=0,
                    is_open_source=result.get("is_open_source", "0") == "1",
                    is_proxy=result.get("is_proxy", "0") == "1",
                    can_take_back_ownership=result.get("can_take_back_ownership", "0") == "1",
                    details="GoPlus scan", risk_level=risk,
                )
        except Exception as e:
            logger.debug("goplus_error", error=str(e))
        return None

    async def close(self):
        if self._client:
            await self._client.aclose()
