"""
Ethereum scanner. Monitors Uniswap V2/V3 for new pool creation.
"""
from typing import Optional
from web3 import AsyncWeb3
from web3.providers import AsyncHTTPProvider
from tenacity import retry, stop_after_attempt, wait_exponential
from hunter.config import settings
from hunter.database.models import ChainType
from hunter.scanners.base_scanner import BaseScanner, DiscoveredToken
from hunter.logger import get_logger

UNISWAP_V2_FACTORY = "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f"
UNISWAP_V3_FACTORY = "0x1F98431c8aD98523631AE4a59f267346ea31F984"

PAIR_CREATED_ABI = [{
    "anonymous": False,
    "inputs": [
        {"indexed": True, "name": "token0", "type": "address"},
        {"indexed": True, "name": "token1", "type": "address"},
        {"indexed": False, "name": "pair", "type": "address"},
        {"indexed": False, "name": "", "type": "uint256"},
    ],
    "name": "PairCreated", "type": "event",
}]

POOL_CREATED_ABI = [{
    "anonymous": False,
    "inputs": [
        {"indexed": True, "name": "token0", "type": "address"},
        {"indexed": True, "name": "token1", "type": "address"},
        {"indexed": True, "name": "fee", "type": "uint24"},
        {"indexed": False, "name": "tickSpacing", "type": "int24"},
        {"indexed": False, "name": "pool", "type": "address"},
    ],
    "name": "PoolCreated", "type": "event",
}]

ERC20_ABI = [
    {"constant": True, "inputs": [], "name": "name", "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
]

KNOWN_ETH_BASE = {
    "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
    "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
    "0xdAC17F958D2ee523a2206206994597C13D831ec7",  # USDT
    "0x6B175474E89094C44Da98b954EedeAC495271d0F",  # DAI
}


class EthereumScanner(BaseScanner):
    def __init__(self):
        super().__init__(chain=ChainType.ETHEREUM, rpc_url=settings.eth_rpc_url, scan_interval=settings.scan_interval_eth)
        self._w3: Optional[AsyncWeb3] = None
        self._last_block: int = 0

    async def connect(self) -> None:
        self._w3 = AsyncWeb3(AsyncHTTPProvider(self.rpc_url))
        self._last_block = await self._w3.eth.block_number
        self.logger.info("eth_scanner_connected", block=self._last_block)

    async def disconnect(self) -> None:
        self._w3 = None

    async def scan_new_tokens(self) -> list[DiscoveredToken]:
        discovered = []
        try:
            current_block = await self._w3.eth.block_number
            if current_block <= self._last_block:
                return discovered
            from_block = self._last_block + 1
            to_block = min(current_block, from_block + 50)

            # Uniswap V2
            v2_factory = self._w3.eth.contract(address=self._w3.to_checksum_address(UNISWAP_V2_FACTORY), abi=PAIR_CREATED_ABI)
            try:
                events = await v2_factory.events.PairCreated().get_logs(from_block=from_block, to_block=to_block)
                for event in events:
                    token = self._extract_new_token(event["args"]["token0"], event["args"]["token1"])
                    if token and not await self.is_duplicate(token):
                        info = await self.get_token_info(token)
                        discovered.append(DiscoveredToken(
                            address=token, chain=ChainType.ETHEREUM,
                            name=info.get("name") if info else None,
                            symbol=info.get("symbol") if info else None,
                            pool_address=event["args"]["pair"], dex_name="Uniswap V2",
                        ))
            except Exception as e:
                self.logger.error("uniswap_v2_error", error=str(e))

            # Uniswap V3
            v3_factory = self._w3.eth.contract(address=self._w3.to_checksum_address(UNISWAP_V3_FACTORY), abi=POOL_CREATED_ABI)
            try:
                events = await v3_factory.events.PoolCreated().get_logs(from_block=from_block, to_block=to_block)
                for event in events:
                    token = self._extract_new_token(event["args"]["token0"], event["args"]["token1"])
                    if token and not await self.is_duplicate(token):
                        info = await self.get_token_info(token)
                        discovered.append(DiscoveredToken(
                            address=token, chain=ChainType.ETHEREUM,
                            name=info.get("name") if info else None,
                            symbol=info.get("symbol") if info else None,
                            pool_address=event["args"]["pool"], dex_name="Uniswap V3",
                        ))
            except Exception as e:
                self.logger.error("uniswap_v3_error", error=str(e))

            self._last_block = to_block
        except Exception as e:
            self.logger.error("eth_scan_error", error=str(e))
        return discovered

    def _extract_new_token(self, token0: str, token1: str) -> Optional[str]:
        if token0.lower() not in {t.lower() for t in KNOWN_ETH_BASE}:
            return token0
        if token1.lower() not in {t.lower() for t in KNOWN_ETH_BASE}:
            return token1
        return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=5))
    async def get_token_info(self, address: str) -> Optional[dict]:
        try:
            contract = self._w3.eth.contract(address=self._w3.to_checksum_address(address), abi=ERC20_ABI)
            return {
                "name": await contract.functions.name().call(),
                "symbol": await contract.functions.symbol().call(),
                "decimals": await contract.functions.decimals().call(),
            }
        except Exception as e:
            self.logger.debug("eth_token_info_error", address=address, error=str(e))
            return None
