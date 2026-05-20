"""
Export discovered token signals to CSV.
"""
import asyncio
import csv
import sys
from datetime import datetime
sys.path.insert(0, '.')

from hunter.database.repository import get_session, TokenRepository
from hunter.logger import setup_logging


async def main():
    setup_logging()
    session = await get_session()

    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    tokens = await TokenRepository.get_recent(session, hours=hours, limit=10000)

    filename = f"signals_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv"
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Address', 'Symbol', 'Name', 'Chain', 'Safety', 'Rug Risk',
                         'Honeypot', 'Liquidity', 'Price', 'DEX', 'Social', 'Discovered'])
        for t in tokens:
            writer.writerow([
                t.address, t.symbol, t.name, t.chain.value, t.safety_score,
                t.rugpull_risk_score, t.is_honeypot, t.current_liquidity_usd or t.initial_liquidity_usd,
                t.current_price_usd, t.discovered_dex, t.social_score, t.discovered_at,
            ])

    print(f"Exported {len(tokens)} tokens to {filename}")
    await session.close()


if __name__ == "__main__":
    asyncio.run(main())
