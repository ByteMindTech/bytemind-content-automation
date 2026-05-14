"""GET /metrics — lightweight application monitoring."""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AIGeneration, Article, PublishingHistory, TokenUsage
from app.repositories import get_db

router = APIRouter()

_app_start_time = datetime.now(tz=timezone.utc)


@router.get("")
async def metrics(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Return application health and usage metrics."""
    now = datetime.now(tz=timezone.utc)
    uptime = (now - _app_start_time).total_seconds()

    # Article counts
    article_count = await db.scalar(select(func.count(Article.id)))
    generation_count = await db.scalar(select(func.count(AIGeneration.id)))
    publication_count = await db.scalar(select(func.count(PublishingHistory.id)))

    # Today's AI cost
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    cost_today = await db.scalar(
        select(func.coalesce(func.sum(TokenUsage.total_cost_usd), 0.0)).where(
            TokenUsage.date >= today_start
        )
    )

    # Article status breakdown
    status_result = await db.execute(
        select(Article.status, func.count(Article.id)).group_by(Article.status)
    )
    status_breakdown = {row[0]: row[1] for row in status_result.all()}

    return {
        "status": "healthy",
        "uptime_seconds": round(uptime, 1),
        "timestamp": now.isoformat(),
        "articles": {
            "total": article_count or 0,
            "by_status": status_breakdown,
        },
        "ai_generations": generation_count or 0,
        "publications": publication_count or 0,
        "ai_cost_today_usd": round(float(cost_today or 0), 6),
    }
