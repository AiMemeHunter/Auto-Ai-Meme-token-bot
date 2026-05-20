"""Tests for chain scanners."""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from hunter.scanners.base_scanner import BaseScanner, DiscoveredToken
from hunter.database.models import ChainType


class MockScanner(BaseScanner):
    """Mock scanner for testing base class."""
    def __init__(self):
        super().__init__(ChainType.SOLANA, "http://mock-rpc", 1)
        self._mock_tokens = []

    async def connect(self): pass
    async def disconnect(self): pass
    async def scan_new_tokens(self): return self._mock_tokens
    async def get_token_info(self, address): return {"name": "Test", "symbol": "TST"}


@pytest.mark.asyncio
async def test_deduplication():
    scanner = MockScanner()
    assert not await scanner.is_duplicate("addr1")
    assert await scanner.is_duplicate("addr1")  # second time = duplicate
    assert not await scanner.is_duplicate("addr2")


@pytest.mark.asyncio
async def test_discovered_token_creation():
    token = DiscoveredToken(
        address="0x123", chain=ChainType.BSC,
        name="TestCoin", symbol="TC", dex_name="PancakeSwap",
    )
    assert token.address == "0x123"
    assert token.chain == ChainType.BSC
    assert token.symbol == "TC"


def test_scanner_init():
    scanner = MockScanner()
    assert scanner.chain == ChainType.SOLANA
    assert scanner.scan_interval == 1
    assert not scanner.is_running
