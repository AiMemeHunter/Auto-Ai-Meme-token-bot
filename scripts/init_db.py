"""
Database initialization script.
Creates all tables and initial data.
"""
import asyncio
import sys
sys.path.insert(0, '.')

from hunter.database.repository import init_db, get_session, ScanStateRepository
from hunter.database.models import ChainType
from hunter.logger import setup_logging, get_logger

logger = get_logger(__name__)


async def main():
    setup_logging()
    logger.info("init_db_start")

    await init_db()

    # Initialize scan states for all chains
    session = await get_session()
    for chain in ChainType:
        await ScanStateRepository.get_or_create(session, chain)
        logger.info("scan_state_created", chain=chain.value)
    await session.close()

    logger.info("init_db_complete")


if __name__ == "__main__":
    asyncio.run(main())
