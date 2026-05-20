"""Stats API routes."""
from fastapi import APIRouter
from hunter.database.repository import get_session, TokenRepository

router = APIRouter()


@router.get("/")
async def get_stats():
    """Get aggregate scanning statistics."""
    session = await get_session()
    stats = await TokenRepository.get_stats(session)
    await session.close()
    return stats
