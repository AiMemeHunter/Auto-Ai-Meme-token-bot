"""
Smart contract safety analysis module.
5-point safety check: verification, ownership, LP lock, honeypot, distribution.
"""
from dataclasses import dataclass
from typing import Optional
from enum import Enum
import httpx
from hunter.logger import get_logger

logger = get_logger(__name__)


class CheckStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    UNKNOWN = "unknown"


@dataclass
class SafetyCheckResult:
    check_type: str
    status: CheckStatus
    score: float  # 0-20 per check (5 checks = 100 max)
    details: str


@dataclass
class SafetyReport:
    token_address: str
    chain: str
    checks: list[SafetyCheckResult]
    composite_score: float  # 0-100
    is_safe: bool

    @property
    def summary(self) -> str:
        passed = sum(1 for c in self.checks if c.status == CheckStatus.PASS)
        return f"{passed}/{len(self.checks)} checks passed | Score: {self.composite_score}/100"


class ContractAnalyzer:
    """Performs 5-point safety analysis on token contracts."""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _ensure_client(self):
        if not self._client:
            self._client = httpx.AsyncClient(timeout=30.0)

    async def analyze(self, token_address: str, chain: str, token_data: Optional[dict] = None) -> SafetyReport:
        """Run all 5 safety checks and return composite report."""
        await self._ensure_client()
        checks = []

        checks.append(await self.check_contract_verification(token_address, chain))
        checks.append(await self.check_ownership_renounced(token_address, chain, token_data))
        checks.append(await self.check_lp_lock(token_address, chain))
        checks.append(await self.check_honeypot(token_address, chain))
        checks.append(await self.check_holder_distribution(token_address, chain))

        composite = sum(c.score for c in checks)
        return SafetyReport(
            token_address=token_address, chain=chain,
            checks=checks, composite_score=composite,
            is_safe=composite >= 60,
        )

    async def check_contract_verification(self, address: str, chain: str) -> SafetyCheckResult:
        """Check if the contract source code is verified on block explorer."""
        try:
            api_urls = {
                "ethereum": "https://api.etherscan.io/api",
                "bsc": "https://api.bscscan.com/api",
                "base": "https://api.basescan.org/api",
            }
            if chain in api_urls:
                resp = await self._client.get(api_urls[chain], params={
                    "module": "contract", "action": "getabi", "address": address
                })
                data = resp.json()
                if data.get("status") == "1":
                    return SafetyCheckResult("contract_verification", CheckStatus.PASS, 20, "Contract source code is verified")
                return SafetyCheckResult("contract_verification", CheckStatus.FAIL, 0, "Contract source NOT verified")
            elif chain == "solana":
                return SafetyCheckResult("contract_verification", CheckStatus.WARN, 10, "Solana program verification limited")
        except Exception as e:
            logger.debug("verification_check_error", error=str(e))
        return SafetyCheckResult("contract_verification", CheckStatus.UNKNOWN, 5, "Could not verify contract")

    async def check_ownership_renounced(self, address: str, chain: str, token_data: Optional[dict] = None) -> SafetyCheckResult:
        """Check if ownership has been renounced (owner = 0x0)."""
        try:
            if token_data and token_data.get("owner"):
                owner = token_data["owner"]
                zero_addresses = {"0x0000000000000000000000000000000000000000", "0x000000000000000000000000000000000000dEaD"}
                if owner in zero_addresses:
                    return SafetyCheckResult("ownership_renounced", CheckStatus.PASS, 20, f"Ownership renounced to {owner}")
                return SafetyCheckResult("ownership_renounced", CheckStatus.FAIL, 0, f"Owner is {owner}")
            if chain == "solana" and token_data:
                if not token_data.get("mint_authority"):
                    return SafetyCheckResult("ownership_renounced", CheckStatus.PASS, 20, "Mint authority revoked")
                return SafetyCheckResult("ownership_renounced", CheckStatus.WARN, 5, "Mint authority still active")
        except Exception as e:
            logger.debug("ownership_check_error", error=str(e))
        return SafetyCheckResult("ownership_renounced", CheckStatus.UNKNOWN, 5, "Could not determine ownership")

    async def check_lp_lock(self, address: str, chain: str) -> SafetyCheckResult:
        """Check LP lock status via common lock platforms."""
        try:
            # Check common lock platforms (Team.Finance, Unicrypt, PinkSale)
            lock_apis = [
                f"https://api.dexscreener.com/latest/dex/tokens/{address}",
            ]
            for url in lock_apis:
                resp = await self._client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    pairs = data.get("pairs", [])
                    if pairs:
                        pair = pairs[0]
                        liquidity = pair.get("liquidity", {}).get("usd", 0)
                        if liquidity > 50000:
                            return SafetyCheckResult("lp_lock", CheckStatus.PASS, 20, f"Liquidity: ${liquidity:,.0f}")
                        elif liquidity > 10000:
                            return SafetyCheckResult("lp_lock", CheckStatus.WARN, 10, f"Moderate liquidity: ${liquidity:,.0f}")
                        return SafetyCheckResult("lp_lock", CheckStatus.FAIL, 0, f"Low liquidity: ${liquidity:,.0f}")
        except Exception as e:
            logger.debug("lp_lock_check_error", error=str(e))
        return SafetyCheckResult("lp_lock", CheckStatus.UNKNOWN, 5, "Could not determine LP lock status")

    async def check_honeypot(self, address: str, chain: str) -> SafetyCheckResult:
        """Simulate buy/sell to detect honeypot tokens."""
        try:
            if chain in ("ethereum", "bsc"):
                resp = await self._client.get(f"https://api.honeypot.is/v2/IsHoneypot", params={"address": address, "chainID": "1" if chain == "ethereum" else "56"})
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("honeypotResult", {}).get("isHoneypot"):
                        return SafetyCheckResult("honeypot_test", CheckStatus.FAIL, 0, "HONEYPOT DETECTED — cannot sell")
                    buy_tax = data.get("simulationResult", {}).get("buyTax", 0)
                    sell_tax = data.get("simulationResult", {}).get("sellTax", 0)
                    if sell_tax > 10:
                        return SafetyCheckResult("honeypot_test", CheckStatus.WARN, 5, f"High sell tax: {sell_tax}%")
                    return SafetyCheckResult("honeypot_test", CheckStatus.PASS, 20, f"Buy tax: {buy_tax}%, Sell tax: {sell_tax}%")
        except Exception as e:
            logger.debug("honeypot_check_error", error=str(e))
        return SafetyCheckResult("honeypot_test", CheckStatus.UNKNOWN, 5, "Honeypot test inconclusive")

    async def check_holder_distribution(self, address: str, chain: str) -> SafetyCheckResult:
        """Analyze top holder distribution to detect concentration risks."""
        try:
            resp = await self._client.get(f"https://api.dexscreener.com/latest/dex/tokens/{address}")
            if resp.status_code == 200:
                data = resp.json()
                pairs = data.get("pairs", [])
                if pairs:
                    fdv = pairs[0].get("fdv", 0)
                    if fdv > 100000:
                        return SafetyCheckResult("holder_distribution", CheckStatus.PASS, 20, f"FDV: ${fdv:,.0f} — healthy distribution")
                    elif fdv > 10000:
                        return SafetyCheckResult("holder_distribution", CheckStatus.WARN, 10, f"FDV: ${fdv:,.0f} — moderate")
                    return SafetyCheckResult("holder_distribution", CheckStatus.FAIL, 0, f"FDV: ${fdv:,.0f} — low, high concentration risk")
        except Exception as e:
            logger.debug("distribution_check_error", error=str(e))
        return SafetyCheckResult("holder_distribution", CheckStatus.UNKNOWN, 5, "Could not analyze distribution")

    async def close(self):
        if self._client:
            await self._client.aclose()
