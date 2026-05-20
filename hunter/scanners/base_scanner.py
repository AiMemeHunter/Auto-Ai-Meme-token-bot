"""
Base scanner interface that all chain-specific scanners must implement.
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, AsyncIterator

from hunter.database.models import ChainType
from hunter.logger import get_logger


@dataclass
class DiscoveredToken:
    """Represents a newly discovered token from any chain."""
    address: str
    chain: ChainType
    name: Optional[str] = None
    symbol: Optional[str] = None
    decimals: Optional[int] = None
    pool_address: Optional[str] = None
    dex_name: Optional[str] = None
    creator_address: Optional[str] = None
    initial_liquidity_usd: Optional[float] = None
    initial_price_usd: Optional[float] = None
    discovered_at: datetime = field(default_factory=datetime.utcnow)
    raw_data: Optional[dict] = None


class BaseScanner(ABC):
    """
    Abstract base class for chain-specific token scanners.
    Each scanner monitors a specific blockchain for new token launches.
    """

    def __init__(self, chain: ChainType, rpc_url: str, scan_interval: int = 10):
        self.chain = chain
        self.rpc_url = rpc_url
        self.scan_interval = scan_interval
        self.is_running = False
        self._seen_tokens: set[str] = set()
        self.logger = get_logger(f"scanner.{chain.value}")

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the blockchain RPC."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Gracefully close connection."""
        pass

    @abstractmethod
    async def scan_new_tokens(self) -> list[DiscoveredToken]:
        """
        Perform a single scan cycle for new token launches.
        Returns list of newly discovered tokens (not previously seen).
        """
        pass

    @abstractmethod
    async def get_token_info(self, address: str) -> Optional[dict]:
        """Get detailed information about a specific token."""
        pass

    async def is_duplicate(self, address: str) -> bool:
        """Check if we've already seen this token."""
        if address in self._seen_tokens:
            return True
        self._seen_tokens.add(address)
        return False

    async def run(self) -> AsyncIterator[DiscoveredToken]:
        """
        Main scan loop. Yields newly discovered tokens.
        """
        self.is_running = True
        self.logger.info("scanner_starting", chain=self.chain.value, interval=self.scan_interval)

        try:
            await self.connect()
            while self.is_running:
                try:
                    tokens = await self.scan_new_tokens()
                    for token in tokens:
                        if not await self.is_duplicate(token.address):
                            self.logger.info(
                                "new_token_discovered",
                                address=token.address,
                                chain=self.chain.value,
                                symbol=token.symbol,
                                dex=token.dex_name,
                            )
                            yield token
                except Exception as e:
                    self.logger.error("scan_cycle_error", error=str(e), chain=self.chain.value)

                await asyncio.sleep(self.scan_interval)
        finally:
            await self.disconnect()
            self.is_running = False
            self.logger.info("scanner_stopped", chain=self.chain.value)

    async def stop(self) -> None:
        """Signal the scanner to stop."""
        self.is_running = False
