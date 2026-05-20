"""Token API routes."""
from fastapi import APIRouter, Query
from typing import Optional
from hunter.database.repository import get_session, TokenRepository
from hunter.database.models import ChainType

router = APIRouter()


@router.get("/")
async def list_tokens(
    chain: Optional[str] = Query(None),
    min_safety: Optional[float] = Query(None, ge=0, le=100),
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(50, ge=1, le=500),
):
    """List recently discovered tokens."""
    session = await get_session()
    chain_type = ChainType(chain) if chain else None
    tokens = await TokenRepository.get_recent(session, chain=chain_type, min_safety=min_safety, hours=hours, limit=limit)
    await session.close()
    return [{
        "id": t.id, "address": t.address, "chain": t.chain.value,
        "name": t.name, "symbol": t.symbol, "safety_score": t.safety_score,
        "rugpull_risk": t.rugpull_risk_score, "is_honeypot": t.is_honeypot,
        "liquidity_usd": t.current_liquidity_usd or t.initial_liquidity_usd,
        "price_usd": t.current_price_usd or t.initial_price_usd,
        "dex": t.discovered_dex, "social_score": t.social_score,
        "discovered_at": t.discovered_at.isoformat() if t.discovered_at else None,
    } for t in tokens]


@router.get("/{address}")
async def get_token(address: str):
    """Get detailed token info."""
    session = await get_session()
    token = await TokenRepository.get_by_address(session, address)
    await session.close()
    if not token:
        return {"error": "Token not found"}
    return {
        "id": token.id, "address": token.address, "chain": token.chain.value,
        "name": token.name, "symbol": token.symbol,
        "safety_score": token.safety_score, "rugpull_risk": token.rugpull_risk_score,
        "is_honeypot": token.is_honeypot, "social_score": token.social_score,
        "dex": token.discovered_dex,
        "discovered_at": token.discovered_at.isoformat() if token.discovered_at else None,
    }
