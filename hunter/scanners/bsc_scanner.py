"""
BSC (Binance Smart Chain) scanner.
Monitors PancakeSwap and BakerySwap for new token pairs.
"""

from typing import Optional
from web3 import AsyncWeb3
from web3.providers import AsyncHTTPProvider
from tenacity import retry, stop_after_attempt, wait_exponential
from hunter.config import settings
from hunter.database.models import ChainType
from hunter.scanners.base_scanner import BaseScanner, DiscoveredToken
from hunter.logger import get_logger

logger = get_logger(__name__)

PANCAKESWAP_V2_FACTORY = "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73"
BAKERYSWAP_FACTORY = "0x01bF7C66c6BD861915CdaaE475042d3c4BaE16A7"

PAIR_CREATED_ABI = [{
    "anonymous": False,
    "inputs": [
        {"indexed": True, "name": "token0", "type": "address"},
        {"indexed": True, "name": "token1", "type": "address"},
        {"indexed": False, "name": "pair", "type": "address"},
        {"indexed": False, "name": "", "type": "uint256"},
    ],
    "name": "PairCreated",
    "type": "event",
}]

ERC20_ABI = [
    {"constant": True, "inputs": [], "name": "name", "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "totalSupply", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "owner", "outputs": [{"name": "", "type": "address"}], "type": "function"},
]

KNOWN_BASE_TOKENS = {
    "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
    "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56",
    "0x55d398326f99059fF775485246999027B3197955",
    "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
}


class BSCScanner(BaseScanner):
    def __init__(self):
        super().__init__(chain=ChainType.BSC, rpc_url=settings.bsc_rpc_url, scan_interval=settings.scan_interval_bsc)
        self._w3: Optional[AsyncWeb3] = None
        self._last_block: int = 0

    async def connect(self) -> None:
        self._w3 = AsyncWeb3(AsyncHTTPProvider(self.rpc_url))
        self._last_block = await self._w3.eth.block_number
        self.logger.info("bsc_scanner_connected", block=self._last_block)

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

            for factory_addr, dex_name in [(PANCAKESWAP_V2_FACTORY, "PancakeSwap"), (BAKERYSWAP_FACTORY, "BakerySwap")]:
                factory = self._w3.eth.contract(address=self._w3.to_checksum_address(factory_addr), abi=PAIR_CREATED_ABI)
                try:
                    events = await factory.events.PairCreated().get_logs(from_block=from_block, to_block=to_block)
                    for event in events:
                        token0, token1 = event["args"]["token0"], event["args"]["token1"]
                        pair_address = event["args"]["pair"]
                        new_token = token0 if token0.lower() not in {t.lower() for t in KNOWN_BASE_TOKENS} else token1
                        if new_token and not await self.is_duplicate(new_token):
                            info = await self.get_token_info(new_token)
                            discovered.append(DiscoveredToken(
                                address=new_token, chain=ChainType.BSC,
                                name=info.get("name") if info else None,
                                symbol=info.get("symbol") if info else None,
                                decimals=info.get("decimals") if info else None,
                                pool_address=pair_address, dex_name=dex_name,
                                raw_data={"token0": token0, "token1": token1, "pair": pair_address},
                            ))
                except Exception as e:
                    self.logger.error("factory_scan_error", dex=dex_name, error=str(e))
            self._last_block = to_block
        except Exception as e:
            self.logger.error("bsc_scan_error", error=str(e))
        return discovered

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=5))
    async def get_token_info(self, address: str) -> Optional[dict]:
        try:
            contract = self._w3.eth.contract(address=self._w3.to_checksum_address(address), abi=ERC20_ABI)
            name = await contract.functions.name().call()
            symbol = await contract.functions.symbol().call()
            decimals = await contract.functions.decimals().call()
            return {"name": name, "symbol": symbol, "decimals": decimals}
        except Exception as e:
            self.logger.debug("bsc_token_info_error", address=address, error=str(e))
            return None
