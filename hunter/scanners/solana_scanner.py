"""
Solana blockchain scanner.
Monitors Raydium, Orca, and Jupiter for new pool/token launches.
"""

import asyncio
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from hunter.config import settings
from hunter.database.models import ChainType
from hunter.scanners.base_scanner import BaseScanner, DiscoveredToken
from hunter.logger import get_logger

logger = get_logger(__name__)

# Known Solana DEX program IDs
RAYDIUM_AMM_V4 = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
ORCA_WHIRLPOOL = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
JUPITER_V6 = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"

# Raydium pool creation log signature
RAYDIUM_INIT_LOG = "InitializeInstruction2"


class SolanaScanner(BaseScanner):
    """
    Scans the Solana blockchain for new token launches on major DEXes.
    Uses RPC polling and WebSocket subscriptions for real-time detection.
    """

    def __init__(self):
        super().__init__(
            chain=ChainType.SOLANA,
            rpc_url=settings.solana_rpc_url,
            scan_interval=settings.scan_interval_solana,
        )
        self.ws_url = settings.solana_ws_url
        self._client: Optional[httpx.AsyncClient] = None
        self._last_signature: Optional[str] = None

    async def connect(self) -> None:
        """Initialize HTTP client for Solana RPC."""
        self._client = httpx.AsyncClient(
            base_url=self.rpc_url,
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_connections=10),
        )
        self.logger.info("solana_scanner_connected", rpc=self.rpc_url)

    async def disconnect(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
    async def _rpc_call(self, method: str, params: list) -> dict:
        """Make an RPC call to Solana with retries."""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }
        response = await self._client.post("", json=payload)
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            raise Exception(f"RPC Error: {data['error']}")
        return data.get("result", {})

    async def scan_new_tokens(self) -> list[DiscoveredToken]:
        """
        Scan for new token launches on Solana by monitoring DEX program transactions.
        Checks Raydium AMM, Orca Whirlpool, and Jupiter for new pool initializations.
        """
        discovered = []

        # Monitor Raydium AMM for new pool creation
        raydium_tokens = await self._scan_raydium()
        discovered.extend(raydium_tokens)

        # Monitor Orca for new whirlpool creation
        orca_tokens = await self._scan_orca()
        discovered.extend(orca_tokens)

        return discovered

    async def _scan_raydium(self) -> list[DiscoveredToken]:
        """Scan Raydium AMM V4 for new pool initialization transactions."""
        tokens = []
        try:
            params = [
                RAYDIUM_AMM_V4,
                {
                    "limit": 20,
                    "commitment": "confirmed",
                }
            ]
            if self._last_signature:
                params[1]["until"] = self._last_signature

            result = await self._rpc_call("getSignaturesForAddress", params)

            if not result:
                return tokens

            for sig_info in result:
                signature = sig_info.get("signature")
                if not signature:
                    continue

                # Get transaction details
                try:
                    tx_detail = await self._rpc_call(
                        "getTransaction",
                        [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
                    )
                    if tx_detail:
                        token = await self._parse_raydium_pool_init(tx_detail, signature)
                        if token:
                            tokens.append(token)
                except Exception as e:
                    self.logger.debug("raydium_tx_parse_error", sig=signature, error=str(e))

            # Update last signature for pagination
            if result:
                self._last_signature = result[0].get("signature")

        except Exception as e:
            self.logger.error("raydium_scan_error", error=str(e))

        return tokens

    async def _parse_raydium_pool_init(self, tx_data: dict, signature: str) -> Optional[DiscoveredToken]:
        """Parse a Raydium transaction to extract new pool information."""
        try:
            meta = tx_data.get("meta", {})
            if meta.get("err"):
                return None

            # Look for token mint addresses in pre/post token balances
            post_balances = meta.get("postTokenBalances", [])
            pre_balances = meta.get("preTokenBalances", [])

            # Find new token mints (present in post but not pre)
            pre_mints = {b.get("mint") for b in pre_balances if b.get("mint")}
            new_mints = set()
            for balance in post_balances:
                mint = balance.get("mint")
                if mint and mint not in pre_mints:
                    new_mints.add(mint)

            # Known stable tokens and SOL wrappers to exclude
            excluded = {
                "So11111111111111111111111111111111111111112",  # Wrapped SOL
                "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
                "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
            }

            for mint in new_mints:
                if mint not in excluded:
                    # Get token info
                    token_info = await self.get_token_info(mint)

                    return DiscoveredToken(
                        address=mint,
                        chain=ChainType.SOLANA,
                        name=token_info.get("name") if token_info else None,
                        symbol=token_info.get("symbol") if token_info else None,
                        decimals=token_info.get("decimals") if token_info else None,
                        pool_address=signature,
                        dex_name="Raydium",
                        creator_address=tx_data.get("transaction", {}).get("message", {}).get("accountKeys", [{}])[0].get("pubkey") if isinstance(tx_data.get("transaction", {}).get("message", {}).get("accountKeys", [{}])[0], dict) else None,
                        raw_data={"signature": signature},
                    )
        except Exception as e:
            self.logger.debug("raydium_parse_error", error=str(e))
        return None

    async def _scan_orca(self) -> list[DiscoveredToken]:
        """Scan Orca Whirlpool program for new pool creation."""
        tokens = []
        try:
            result = await self._rpc_call(
                "getSignaturesForAddress",
                [ORCA_WHIRLPOOL, {"limit": 10, "commitment": "confirmed"}]
            )
            if not result:
                return tokens

            for sig_info in result:
                signature = sig_info.get("signature")
                if not signature:
                    continue
                try:
                    tx_detail = await self._rpc_call(
                        "getTransaction",
                        [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
                    )
                    if tx_detail:
                        meta = tx_detail.get("meta", {})
                        if not meta.get("err"):
                            post_balances = meta.get("postTokenBalances", [])
                            for balance in post_balances:
                                mint = balance.get("mint")
                                if mint and not await self.is_duplicate(mint):
                                    info = await self.get_token_info(mint)
                                    tokens.append(DiscoveredToken(
                                        address=mint,
                                        chain=ChainType.SOLANA,
                                        name=info.get("name") if info else None,
                                        symbol=info.get("symbol") if info else None,
                                        pool_address=signature,
                                        dex_name="Orca",
                                        raw_data={"signature": signature},
                                    ))
                except Exception as e:
                    self.logger.debug("orca_tx_parse_error", error=str(e))

        except Exception as e:
            self.logger.error("orca_scan_error", error=str(e))
        return tokens

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=0.5, max=5))
    async def get_token_info(self, address: str) -> Optional[dict]:
        """Get token metadata from Solana."""
        try:
            result = await self._rpc_call(
                "getAccountInfo",
                [address, {"encoding": "jsonParsed"}]
            )
            if result and result.get("value"):
                data = result["value"].get("data", {})
                if isinstance(data, dict) and data.get("parsed"):
                    info = data["parsed"].get("info", {})
                    return {
                        "name": info.get("name"),
                        "symbol": info.get("symbol"),
                        "decimals": info.get("decimals"),
                        "supply": info.get("supply"),
                        "mint_authority": info.get("mintAuthority"),
                        "freeze_authority": info.get("freezeAuthority"),
                    }
        except Exception as e:
            self.logger.debug("token_info_error", address=address, error=str(e))
        return None
