"""Alert API routes."""
from fastapi import APIRouter, Query
from typing import Optional
from hunter.database.repository import get_session, AlertRepository
from hunter.database.models import AlertLevel

router = APIRouter()


@router.get("/")
async def list_alerts(
    level: Optional[str] = Query(None),
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(50, ge=1, le=500),
):
    """List recent alerts."""
    session = await get_session()
    alert_level = AlertLevel(level) if level else None
    alerts = await AlertRepository.get_recent(session, level=alert_level, hours=hours, limit=limit)
    await session.close()
    return [{
        "id": a.id, "level": a.level.value, "title": a.title,
        "message": a.message, "sent_telegram": a.sent_telegram,
        "sent_discord": a.sent_discord,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    } for a in alerts]
