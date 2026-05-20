"""
Base chain scanner. Monitors Aerodrome and BaseSwap for new pairs.
"""
from typing import Optional
from web3 import AsyncWeb3
from web3.providers import AsyncHTTPProvider
from tenacity import retry, stop_after_attempt, wait_exponential
from hunter.config import settings
from hunter.database.models import ChainType
from hunter.scanners.base_scanner import BaseScanner, DiscoveredToken
from hunter.logger import get_logger

AERODROME_FACTORY = "0x420DD381b31aEf6683db6B902084cB0FFECe40Da"
BASESWAP_FACTORY = "0xFDa619b6d20975be80A10332cD39b9a4b0FAa8BB"

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

ERC20_ABI = [
    {"constant": True, "inputs": [], "name": "name", "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
]

KNOWN_BASE_TOKENS_CHAIN = {
    "0x4200000000000000000000000000000000000006",  # WETH on Base
    "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC on Base
    "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA",  # USDbC
}


class BaseChainScanner(BaseScanner):
    def __init__(self):
        super().__init__(chain=ChainType.BASE, rpc_url=settings.base_rpc_url, scan_interval=settings.scan_interval_base)
        self._w3: Optional[AsyncWeb3] = None
        self._last_block: int = 0

    async def connect(self) -> None:
        self._w3 = AsyncWeb3(AsyncHTTPProvider(self.rpc_url))
        self._last_block = await self._w3.eth.block_number
        self.logger.info("base_scanner_connected", block=self._last_block)

    async def disconnect(self) -> None:
        self._w3 = None

    async def scan_new_tokens(self) -> list[DiscoveredToken]:
        discovered = []
        try:
            current_block = await self._w3.eth.block_number
            if current_block <= self._last_block:
                return discovered
            from_block = self._last_block + 1
            to_block = min(current_block, from_block + 100)

            for factory_addr, dex_name in [(AERODROME_FACTORY, "Aerodrome"), (BASESWAP_FACTORY, "BaseSwap")]:
                factory = self._w3.eth.contract(address=self._w3.to_checksum_address(factory_addr), abi=PAIR_CREATED_ABI)
                try:
                    events = await factory.events.PairCreated().get_logs(from_block=from_block, to_block=to_block)
                    for event in events:
                        token0, token1 = event["args"]["token0"], event["args"]["token1"]
                        new_token = token0 if token0.lower() not in {t.lower() for t in KNOWN_BASE_TOKENS_CHAIN} else token1
                        if new_token and not await self.is_duplicate(new_token):
                            info = await self.get_token_info(new_token)
                            discovered.append(DiscoveredToken(
                                address=new_token, chain=ChainType.BASE,
                                name=info.get("name") if info else None,
                                symbol=info.get("symbol") if info else None,
                                pool_address=event["args"]["pair"], dex_name=dex_name,
                            ))
                except Exception as e:
                    self.logger.error("base_factory_error", dex=dex_name, error=str(e))
            self._last_block = to_block
        except Exception as e:
            self.logger.error("base_scan_error", error=str(e))
        return discovered

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
            self.logger.debug("base_token_info_error", address=address, error=str(e))
            return None
