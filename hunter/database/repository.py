"""
Data access layer (repository pattern) for the Meme Token Hunter database.
Provides async CRUD operations for all models using SQLite.
"""

from datetime import datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy import select, func, and_, desc, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from hunter.config import settings
from hunter.database.models import (
    Base, Token, SafetyCheck, Alert, ScanState,
    ChainType, AlertLevel, SafetyStatus,
)
from hunter.logger import get_logger

logger = get_logger(__name__)

# Create async engine for SQLite (no pool settings needed)
engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False},
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    """Create all tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("database_initialized", db=settings.database_url)


async def get_session() -> AsyncSession:
    """Get a new async database session."""
    return async_session()


class TokenRepository:
    """Repository for Token CRUD operations."""

    @staticmethod
    async def create(session: AsyncSession, **kwargs) -> Token:
        """Create a new token record."""
        token = Token(**kwargs)
        session.add(token)
        await session.commit()
        await session.refresh(token)
        logger.info("token_created", address=token.address, chain=token.chain.value)
        return token

    @staticmethod
    async def get_by_address(session: AsyncSession, address: str) -> Optional[Token]:
        """Find a token by its contract address."""
        result = await session.execute(
            select(Token).where(Token.address == address)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def exists(session: AsyncSession, address: str) -> bool:
        """Check if a token already exists (for deduplication)."""
        result = await session.execute(
            select(func.count()).where(Token.address == address)
        )
        return result.scalar() > 0

    @staticmethod
    async def get_recent(
        session: AsyncSession,
        chain: Optional[ChainType] = None,
        min_safety: Optional[float] = None,
        hours: int = 24,
        limit: int = 100,
    ) -> Sequence[Token]:
        """Get recently discovered tokens with optional filters."""
        since = datetime.utcnow() - timedelta(hours=hours)
        query = select(Token).where(Token.discovered_at >= since)

        if chain:
            query = query.where(Token.chain == chain)
        if min_safety is not None:
            query = query.where(Token.safety_score >= min_safety)

        query = query.order_by(desc(Token.discovered_at)).limit(limit)
        result = await session.execute(query)
        return result.scalars().all()

    @staticmethod
    async def update_safety(
        session: AsyncSession,
        token_id: int,
        safety_score: float,
        **kwargs,
    ) -> None:
        """Update safety analysis results for a token."""
        result = await session.execute(
            select(Token).where(Token.id == token_id)
        )
        token = result.scalar_one_or_none()
        if token:
            token.safety_score = safety_score
            for key, value in kwargs.items():
                if hasattr(token, key):
                    setattr(token, key, value)
            token.updated_at = datetime.utcnow()
            await session.commit()

    @staticmethod
    async def update_price(
        session: AsyncSession,
        token_id: int,
        current_price_usd: float,
        current_liquidity_usd: Optional[float] = None,
        market_cap_usd: Optional[float] = None,
    ) -> None:
        """Update pricing data for a token."""
        result = await session.execute(
            select(Token).where(Token.id == token_id)
        )
        token = result.scalar_one_or_none()
        if token:
            token.current_price_usd = current_price_usd
            if current_liquidity_usd is not None:
                token.current_liquidity_usd = current_liquidity_usd
            if market_cap_usd is not None:
                token.market_cap_usd = market_cap_usd
            token.updated_at = datetime.utcnow()
            await session.commit()

    @staticmethod
    async def get_stats(session: AsyncSession) -> dict:
        """Get aggregate statistics."""
        total = await session.execute(select(func.count(Token.id)))
        safe_count = await session.execute(
            select(func.count(Token.id)).where(Token.safety_score >= 80)
        )
        honeypots = await session.execute(
            select(func.count(Token.id)).where(Token.is_honeypot == True)
        )
        by_chain = await session.execute(
            select(Token.chain, func.count(Token.id)).group_by(Token.chain)
        )
        return {
            "total_tokens": total.scalar(),
            "safe_tokens": safe_count.scalar(),
            "honeypots_detected": honeypots.scalar(),
            "by_chain": {row[0].value: row[1] for row in by_chain.all()},
        }


class SafetyCheckRepository:
    """Repository for SafetyCheck CRUD operations."""

    @staticmethod
    async def create(session: AsyncSession, **kwargs) -> SafetyCheck:
        """Create a new safety check record."""
        check = SafetyCheck(**kwargs)
        session.add(check)
        await session.commit()
        return check

    @staticmethod
    async def get_for_token(session: AsyncSession, token_id: int) -> Sequence[SafetyCheck]:
        """Get all safety checks for a given token."""
        result = await session.execute(
            select(SafetyCheck).where(SafetyCheck.token_id == token_id)
        )
        return result.scalars().all()


class AlertRepository:
    """Repository for Alert CRUD operations."""

    @staticmethod
    async def create(session: AsyncSession, **kwargs) -> Alert:
        """Create a new alert record."""
        alert = Alert(**kwargs)
        session.add(alert)
        await session.commit()
        await session.refresh(alert)
        return alert

    @staticmethod
    async def get_recent(
        session: AsyncSession,
        level: Optional[AlertLevel] = None,
        hours: int = 1,
        limit: int = 100,
    ) -> Sequence[Alert]:
        """Get recent alerts with optional level filter."""
        since = datetime.utcnow() - timedelta(hours=hours)
        query = select(Alert).where(Alert.created_at >= since)
        if level:
            query = query.where(Alert.level == level)
        query = query.order_by(desc(Alert.created_at)).limit(limit)
        result = await session.execute(query)
        return result.scalars().all()

    @staticmethod
    async def count_recent(session: AsyncSession, hours: int = 1) -> int:
        """Count alerts in the last N hours (for rate limiting)."""
        since = datetime.utcnow() - timedelta(hours=hours)
        result = await session.execute(
            select(func.count(Alert.id)).where(Alert.created_at >= since)
        )
        return result.scalar()


class ScanStateRepository:
    """Repository for scanner state persistence."""

    @staticmethod
    async def get_or_create(session: AsyncSession, chain: ChainType) -> ScanState:
        """Get or create scan state for a chain."""
        result = await session.execute(
            select(ScanState).where(ScanState.chain == chain)
        )
        state = result.scalar_one_or_none()
        if not state:
            state = ScanState(chain=chain)
            session.add(state)
            await session.commit()
            await session.refresh(state)
        return state

    @staticmethod
    async def update(
        session: AsyncSession,
        chain: ChainType,
        last_block: Optional[int] = None,
        last_slot: Optional[int] = None,
    ) -> None:
        """Update the scan state for a chain."""
        result = await session.execute(
            select(ScanState).where(ScanState.chain == chain)
        )
        state = result.scalar_one_or_none()
        if state:
            if last_block is not None:
                state.last_block = last_block
            if last_slot is not None:
                state.last_slot = last_slot
            state.last_scan_at = datetime.utcnow()
            await session.commit()
